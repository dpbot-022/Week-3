import pytest
import jwt
from datetime import datetime, timezone, timedelta
from starlette.testclient import TestClient
from sqlalchemy.orm import Session
from src.api.main import app
from src.db.session import init_db, SessionLocal
from src.db.models import User, OTPToken, WrongAnswerReport
from src.auth.service import AuthService, _hash_otp
from src.core.rbac import Role, ALL_ROLES
from src.core.config import settings

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_database():
    init_db()
    with SessionLocal() as db:
        for r in ALL_ROLES:
            email = f"user_{r}@test.safestrata"
            existing = db.query(User).filter(User.email == email).first()
            if not existing:
                u = User(email=email, role=r, role_version=1, is_active=True)
                db.add(u)
        db.commit()

def get_auth_headers(role: str) -> dict:
    with SessionLocal() as db:
        email = f"user_{role}@test.safestrata"
        user = db.query(User).filter(User.email == email).first()
        token = jwt.encode({
            "sub": user.email,
            "role": user.role,
            "role_version": user.role_version,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=60),
            "type": "access"
        }, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
        return {"Authorization": f"Bearer {token}"}

def test_quality_reports_and_wrong_answers():
    # Reports endpoint requires quality read permission (compliance_manager, auditor, admin)
    res_forbidden = client.get("/api/v1/quality/reports", headers=get_auth_headers("viewer"))
    assert res_forbidden.status_code == 403

    res_ok = client.get("/api/v1/quality/reports", headers=get_auth_headers("compliance_manager"))
    assert res_ok.status_code == 200
    data = res_ok.json()
    assert "available_reports" in data
    assert "calibration" in data

    # Submit wrong answer report (analyst)
    report_payload = {
        "query": "What is the capital requirement?",
        "answer": "100 percent.",
        "citations": [{"title": "Doc A", "page": 1}],
        "reason": "Hallucinated percentage."
    }
    submit_res = client.post("/api/v1/quality/report-wrong-answer", json=report_payload, headers=get_auth_headers("analyst"))
    assert submit_res.status_code == 200
    submit_data = submit_res.json()
    assert "report_id" in submit_data

    # List wrong answers (compliance_manager)
    list_res = client.get("/api/v1/quality/wrong-answers", headers=get_auth_headers("compliance_manager"))
    assert list_res.status_code == 200
    reports = list_res.json()
    assert len(reports) >= 1
    assert any(r["reason"] == "Hallucinated percentage." for r in reports)

def test_auth_service_flow():
    db: Session = SessionLocal()
    test_email = "service.user@enterprise.io"
    try:
        # 1. Generate OTP
        res = AuthService.generate_and_send_otp(db, test_email)
        assert res["email"] == test_email
        assert res["expires_in_seconds"] == 300

        # Retrieve stored token
        token_rec = db.query(OTPToken).filter(OTPToken.email == test_email).first()
        assert token_rec is not None

        # Verify wrong code
        with pytest.raises(ValueError, match="Invalid verification code"):
            AuthService.verify_otp_and_login(db, test_email, "000000")

        # Test valid login by setting known code
        known_code = "789123"
        token_rec.otp_hash = _hash_otp(test_email, known_code)
        db.commit()

        login_res, user = AuthService.verify_otp_and_login(db, test_email, known_code)
        assert login_res["user"]["email"] == test_email
        assert "access_token" in login_res
        assert "refresh_token" in login_res
        assert user.email == test_email

        # Test refresh
        refresh_token = login_res["refresh_token"]
        refreshed = AuthService.refresh_access_token(db, refresh_token)
        assert "access_token" in refreshed

        # Test invalid refresh token
        with pytest.raises(ValueError):
            AuthService.refresh_access_token(db, "invalid.token.here")

    finally:
        db.query(OTPToken).filter(OTPToken.email == test_email).delete()
        db.query(User).filter(User.email == test_email).delete()
        db.commit()
        db.close()
