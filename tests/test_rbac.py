import pytest
from starlette.testclient import TestClient
from src.api.main import app
from src.db.session import SessionLocal, init_db
from src.db.models import User, Document
from src.auth.service import AuthService
from src.core.rbac import Role, ALL_ROLES

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_database():
    init_db()
    with SessionLocal() as db:
        # Create test users for each role
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
        auth_service_instance = AuthService()
        # Create JWT access token
        import jwt
        from datetime import datetime, timedelta
        from src.core.config import settings
        token = jwt.encode({
            "sub": user.email,
            "role": user.role,
            "role_version": user.role_version,
            "exp": datetime.utcnow() + timedelta(minutes=60),
            "type": "access"
        }, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
        return {"Authorization": f"Bearer {token}"}

def test_rbac_permission_matrix():
    """Validates role x endpoint permission matrix across viewer, analyst, compliance_manager, auditor, admin."""
    endpoints = [
        ("POST", "/api/v1/rag/query", {"query": "Hello compliance"}, {"viewer": 200, "analyst": 200, "compliance_manager": 200, "auditor": 403, "admin": 403}),
        ("GET", "/api/v1/documents", None, {"viewer": 200, "analyst": 200, "compliance_manager": 200, "auditor": 403, "admin": 403}),
        ("POST", "/api/v1/documents/upload", {"title": "Test", "content": "Sample content"}, {"viewer": 403, "analyst": 403, "compliance_manager": 200, "auditor": 403, "admin": 403}),
        ("DELETE", "/api/v1/documents/non_existent_doc", None, {"viewer": 403, "analyst": 403, "compliance_manager": 404, "auditor": 403, "admin": 403}),
        ("GET", "/api/v1/audit/logs", None, {"viewer": 403, "analyst": 403, "compliance_manager": 403, "auditor": 200, "admin": 200}),
        ("GET", "/api/v1/admin/users", None, {"viewer": 403, "analyst": 403, "compliance_manager": 403, "auditor": 403, "admin": 200}),
        ("GET", "/metrics", None, {"viewer": 403, "analyst": 403, "compliance_manager": 403, "auditor": 403, "admin": 200}),
    ]

    for method, path, body, expected_status in endpoints:
        for role in ALL_ROLES:
            headers = get_auth_headers(role)
            expected = expected_status[role]
            if method == "GET":
                res = client.get(path, headers=headers)
            elif method == "POST":
                if "upload" in path:
                    res = client.post(path, data=body, headers=headers)
                else:
                    res = client.post(path, json=body, headers=headers)
            elif method == "DELETE":
                res = client.delete(path, headers=headers)

            assert res.status_code == expected, (
                f"Failed matrix: Role '{role}' accessing {method} {path} returned {res.status_code}, expected {expected}."
            )

def test_admin_has_no_implicit_document_access():
    """Verifies that an admin cannot access RAG queries or documents unless explicitly granted the role."""
    admin_headers = get_auth_headers("admin")
    rag_res = client.post("/api/v1/rag/query", json={"query": "Internal audit"}, headers=admin_headers)
    assert rag_res.status_code == 403
    doc_res = client.get("/api/v1/documents", headers=admin_headers)
    assert doc_res.status_code == 403

def test_last_admin_protection():
    """Security rule: System must protect the last active administrator against demotion or deactivation."""
    admin_headers = get_auth_headers("admin")
    with SessionLocal() as db:
        # Keep only one admin in DB for test
        db.query(User).filter(User.role == "admin", User.email != "user_admin@test.safestrata").delete()
        db.commit()

    # Attempt to demote last admin
    demote_res = client.put(
        "/api/v1/admin/users/user_admin@test.safestrata/role",
        json={"role": "viewer"},
        headers=admin_headers
    )
    assert demote_res.status_code == 400
    assert "Cannot demote the last active administrator" in demote_res.json()["detail"]

    # Attempt to disable last admin
    disable_res = client.put(
        "/api/v1/admin/users/user_admin@test.safestrata/status",
        json={"is_active": False},
        headers=admin_headers
    )
    assert disable_res.status_code == 400
    assert "Cannot disable the last active administrator" in disable_res.json()["detail"]

def test_access_change_takes_effect_without_restart():
    """Verifies that an admin updating a user's role takes immediate effect on their next request."""
    admin_headers = get_auth_headers("admin")
    viewer_headers = get_auth_headers("viewer")

    # Initially, user_viewer cannot access audit logs
    audit_res = client.get("/api/v1/audit/logs", headers=viewer_headers)
    assert audit_res.status_code == 403

    # Admin promotes user_viewer to auditor
    promote_res = client.put(
        "/api/v1/admin/users/user_viewer@test.safestrata/role",
        json={"role": "auditor"},
        headers=admin_headers
    )
    assert promote_res.status_code == 200

    # The EXACT SAME viewer_headers token immediately succeeds because role is resolved from DB!
    audit_res_after = client.get("/api/v1/audit/logs", headers=viewer_headers)
    assert audit_res_after.status_code == 200

    # Revert back to viewer
    client.put(
        "/api/v1/admin/users/user_viewer@test.safestrata/role",
        json={"role": "viewer"},
        headers=admin_headers
    )
