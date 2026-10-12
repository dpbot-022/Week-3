import re
import json
import logging
import time
from datetime import datetime, timezone, timedelta
import pytest
from starlette.testclient import TestClient
from aiosmtpd.controller import Controller

from src.api.main import app
from src.core.config import settings
from src.auth.store import auth_store
from src.auth.jwt_handler import create_access_token, decode_access_token
import jwt

client = TestClient(app)

class MockSMTPHandler:
    def __init__(self):
        self.messages = []

    async def handle_DATA(self, server, session, envelope):
        self.messages.append({
            "mail_from": envelope.mail_from,
            "rcpt_tos": envelope.rcpt_tos,
            "content": envelope.content.decode("utf8", errors="replace")
        })
        return "250 OK"

def get_free_port():
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

def extract_email_body_and_code(msg_content: str):
    import email
    parsed = email.message_from_string(msg_content)
    body = ""
    for part in parsed.walk():
        if part.get_content_type() in ["text/plain", "text/html"]:
            payload = part.get_payload(decode=True)
            if payload:
                body += payload.decode("utf-8", errors="replace") + "\n"
    code_match = re.search(r"\b(\d{6})\b", body)
    code = code_match.group(1) if code_match else None
    return body, code

@pytest.fixture
def smtp_server():
    handler = MockSMTPHandler()
    free_port = get_free_port()
    controller = Controller(handler, hostname="127.0.0.1", port=free_port)
    controller.start()
    
    orig_host = settings.SMTP_HOST
    orig_port = settings.SMTP_PORT
    orig_starttls = settings.SMTP_STARTTLS
    orig_ssl = settings.SMTP_SSL

    settings.SMTP_HOST = "127.0.0.1"
    settings.SMTP_PORT = free_port
    settings.SMTP_STARTTLS = False
    settings.SMTP_SSL = False

    yield handler

    controller.stop()
    settings.SMTP_HOST = orig_host
    settings.SMTP_PORT = orig_port
    settings.SMTP_STARTTLS = orig_starttls
    settings.SMTP_SSL = orig_ssl

def test_smtp_email_sent_with_code_and_redaction(smtp_server, caplog):
    """Asserts that OTP email is genuinely delivered via SMTP, contains the 6-digit code,

    and that the code NEVER appears in the API response JSON, headers, or captured logs.
    """
    email = "security.lead@enterprise.io"

    with caplog.at_level(logging.DEBUG):
        response = client.post("/api/v1/auth/request-otp", json={"email": email})

    assert response.status_code == 200
    res_data = response.json()
    assert res_data["message"] == "If this email is valid, a verification code has been sent."
    assert res_data["cooldown_seconds"] == 60

    # 1. Verify email was genuinely sent through SMTP
    assert len(smtp_server.messages) >= 1
    msg = smtp_server.messages[-1]
    assert email in msg["rcpt_tos"]
    body, otp_code = extract_email_body_and_code(msg["content"])
    assert "SafeStrata Context Engine" in body
    assert "Message-ID" in msg["content"]
    assert otp_code is not None, "6-digit OTP code missing from sent email!"

    # 2. P0 Assertion: OTP code must NEVER appear anywhere in response JSON or text
    response_body_str = response.text
    assert otp_code not in response_body_str, (
        f"CRITICAL SECURITY LEAK: OTP code '{otp_code}' leaked in API response body: {response_body_str}"
    )

    # 3. P0 Assertion: OTP code must NEVER appear in captured logs
    assert otp_code not in caplog.text, (
        f"CRITICAL SECURITY LEAK: OTP code '{otp_code}' leaked into system logs: {caplog.text}"
    )

def test_otp_verify_creates_account_and_sets_cookies(smtp_server):
    """Tests passwordless verify-otp creates new user, returns access token, and sets httpOnly refresh cookie."""
    email = "new.engineer@enterprise.io"
    client.post("/api/v1/auth/request-otp", json={"email": email})

    msg = smtp_server.messages[-1]
    _, otp_code = extract_email_body_and_code(msg["content"])
    assert otp_code is not None

    verify_res = client.post("/api/v1/auth/verify-otp", json={"email": email, "code": otp_code})
    assert verify_res.status_code == 200
    data = verify_res.json()

    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == email
    assert "id" in data["user"]

    # Check httpOnly refresh cookie
    assert "refresh_token" in verify_res.cookies
    refresh_cookie = verify_res.cookies["refresh_token"]
    assert len(refresh_cookie) > 20

def test_identical_responses_for_existing_and_new_emails(smtp_server):
    """Asserts responses to request-otp are identical whether or not the account exists (no user enumeration)."""
    # 1. New email
    res_new = client.post("/api/v1/auth/request-otp", json={"email": "fresh.user@domain.com"})
    # 2. Existing email (pre-created in auth store, no OTP requested yet)
    auth_store.get_or_create_user("preexisting.user@domain.com")
    res_existing = client.post("/api/v1/auth/request-otp", json={"email": "preexisting.user@domain.com"})

    assert res_new.status_code == res_existing.status_code == 200
    assert res_new.json() == res_existing.json()

def test_otp_rejections_and_boundaries(smtp_server):
    """Tests wrong code, over-attempts (max 5), expired codes, reused codes, and resend cooldown."""
    email = "boundary.test@domain.com"
    client.post("/api/v1/auth/request-otp", json={"email": email})

    msg = smtp_server.messages[-1]
    _, otp_code = extract_email_body_and_code(msg["content"])
    assert otp_code is not None

    # 1. Resend cooldown: immediate 2nd request is blocked
    cooldown_res = client.post("/api/v1/auth/request-otp", json={"email": email})
    assert cooldown_res.status_code == 429
    assert "wait" in cooldown_res.json()["detail"].lower()

    # 2. Wrong code
    wrong_res = client.post("/api/v1/auth/verify-otp", json={"email": email, "code": "000000"})
    assert wrong_res.status_code == 400
    assert "Invalid verification code" in wrong_res.json()["detail"]

    # 3. Exhaust attempts (5 attempts total)
    for _ in range(4):
        client.post("/api/v1/auth/verify-otp", json={"email": email, "code": "000000"})

    # 6th attempt should state code was invalidated
    exhausted_res = client.post("/api/v1/auth/verify-otp", json={"email": email, "code": otp_code})
    assert exhausted_res.status_code == 400

    # 4. Expired code test
    auth_store.save_otp("expired@domain.com", "123456")
    auth_store.otps["expired@domain.com"].expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    expired_res = client.post("/api/v1/auth/verify-otp", json={"email": "expired@domain.com", "code": "123456"})
    assert expired_res.status_code == 400
    assert "expired" in expired_res.json()["detail"].lower()

    # 5. Reused code test
    auth_store.save_otp("reused@domain.com", "654321")
    succ_res = client.post("/api/v1/auth/verify-otp", json={"email": "reused@domain.com", "code": "654321"})
    assert succ_res.status_code == 200
    # Reusing the exact same code
    reused_res = client.post("/api/v1/auth/verify-otp", json={"email": "reused@domain.com", "code": "654321"})
    assert reused_res.status_code == 400

def test_jwt_refresh_rotation_and_reuse_attack(smtp_server):
    """Tests refresh token rotation on every use and automatic family revocation upon token reuse."""
    email = "rotation.user@enterprise.io"
    client.post("/api/v1/auth/request-otp", json={"email": email})
    msg = smtp_server.messages[-1]
    _, otp_code = extract_email_body_and_code(msg["content"])
    assert otp_code is not None

    verify_res = client.post("/api/v1/auth/verify-otp", json={"email": email, "code": otp_code})
    original_refresh_token = verify_res.cookies["refresh_token"]

    # First refresh: legitimate rotation
    client.cookies.set("refresh_token", original_refresh_token)
    refresh_res_1 = client.post("/api/v1/auth/refresh")
    assert refresh_res_1.status_code == 200
    new_refresh_token = refresh_res_1.cookies["refresh_token"]
    assert new_refresh_token != original_refresh_token

    # ATTACK: Replay original_refresh_token (reuse detection!)
    client.cookies.set("refresh_token", original_refresh_token)
    reuse_res = client.post("/api/v1/auth/refresh")
    assert reuse_res.status_code == 401
    assert "reuse detected" in reuse_res.json()["detail"].lower()

    # Legitimate new token should now ALSO be revoked because family was compromised
    client.cookies.set("refresh_token", new_refresh_token)
    compromised_res = client.post("/api/v1/auth/refresh")
    assert compromised_res.status_code == 401

def test_jwt_claims_tampering_and_expiration():
    """Asserts that tampered, expired, or wrong-audience JWTs are rejected with 401."""
    # 1. Tampered token
    tampered_res = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer bad.token.here"})
    assert tampered_res.status_code == 401

    # 2. Expired token
    now = datetime.now(timezone.utc)
    expired_payload = {
        "sub": "user-123",
        "jti": "jti-123",
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "iat": int((now - timedelta(minutes=20)).timestamp()),
        "exp": int((now - timedelta(minutes=5)).timestamp())
    }
    expired_token = jwt.encode(expired_payload, settings.JWT_SECRET, algorithm="HS256")
    exp_res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert exp_res.status_code == 401
    assert "expired" in exp_res.json()["detail"].lower()

    # 3. Wrong audience token
    wrong_aud_payload = {
        "sub": "user-123",
        "jti": "jti-123",
        "iss": settings.JWT_ISSUER,
        "aud": "wrong-audience-app",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=15)).timestamp())
    }
    wrong_aud_token = jwt.encode(wrong_aud_payload, settings.JWT_SECRET, algorithm="HS256")
    aud_res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {wrong_aud_token}"})
    assert aud_res.status_code == 401

def test_production_unconfigured_smtp_fails():
    """Asserts that in production (APP_ENV=production), unconfigured SMTP explicitly raises 503."""
    orig_env = settings.APP_ENV
    orig_host = settings.SMTP_HOST
    try:
        settings.APP_ENV = "production"
        settings.SMTP_HOST = None
        res = client.post("/api/v1/auth/request-otp", json={"email": "prod.test@domain.com"})
        assert res.status_code == 503
        assert "unconfigured" in res.json()["detail"].lower()
    finally:
        settings.APP_ENV = orig_env
        settings.SMTP_HOST = orig_host

def test_all_protected_endpoints_require_token():
    """Asserts that every protected endpoint returns 401 when accessed without an authorization token."""
    protected_urls = [
        ("POST", "/api/v1/documents/preview-chunking", {"text": "hello", "strategy": "recursive"}),
        ("POST", "/api/v1/documents/ingest", {"title": "T", "content": "C", "strategy": "recursive"}),
        ("POST", "/api/v1/documents/reset", {}),
        ("POST", "/api/v1/search", {"query": "test"}),
        ("POST", "/api/v1/rag/query", {"query": "test"}),
        ("POST", "/api/v1/guardrails/check", {"text": "test"}),
        ("POST", "/api/v1/evaluations/benchmark", {}),
        ("GET", "/api/v1/auth/me", None)
    ]

    for method, path, body in protected_urls:
        if method == "POST":
            res = client.post(path, json=body or {})
        else:
            res = client.get(path)
        assert res.status_code == 401, f"Expected 401 on {path} without token, but got {res.status_code}"

    # Public endpoints must NOT return 401
    assert client.get("/healthz").status_code == 200
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/healthz").status_code == 200

def test_ui_dashboard_not_in_dom_when_signed_out():
    """Asserts that when signed out, the dashboard HTML is isolated in <template> and not in active DOM."""
    from pathlib import Path
    html = Path("src/static/index.html").read_text()
    
    # Assert template exists
    assert '<template id="dashboard-template">' in html
    assert '<template id="login-template">' in html

    # Inside the active app-root mount point before authentication, only session loader is present
    root_content = html[html.find('<div id="app-root">') : html.find('</div>\n\n  <!-- Sign-in')]
    assert 'tab-rag' not in root_content
    assert 'app-header' not in root_content
    assert 'nav-tabs' not in root_content
