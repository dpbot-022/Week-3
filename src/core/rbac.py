from enum import Enum
from typing import Dict, Set, List

class Role(str, Enum):
    VIEWER = "viewer"
    ANALYST = "analyst"
    COMPLIANCE_MANAGER = "compliance_manager"
    AUDITOR = "auditor"
    ADMIN = "admin"

ALL_ROLES: List[str] = [
    Role.VIEWER.value,
    Role.ANALYST.value,
    Role.COMPLIANCE_MANAGER.value,
    Role.AUDITOR.value,
    Role.ADMIN.value,
]

# Permissions
PERM_READ_RAG = "read:rag"
PERM_READ_DOCUMENTS = "read:documents"
PERM_MANAGE_DOCUMENTS = "manage:documents"
PERM_UPLOAD_DOCUMENTS = "upload:documents"
PERM_DELETE_DOCUMENTS = "delete:documents"
PERM_READ_QUALITY = "read:quality"
PERM_READ_AUDIT = "read:audit"
PERM_READ_METRICS = "read:metrics"
PERM_MANAGE_USERS = "manage:users"

# Central Permission Map
ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    Role.VIEWER.value: {
        PERM_READ_RAG,
        PERM_READ_DOCUMENTS,
    },
    Role.ANALYST.value: {
        PERM_READ_RAG,
        PERM_READ_DOCUMENTS,
    },
    Role.COMPLIANCE_MANAGER.value: {
        PERM_READ_RAG,
        PERM_READ_DOCUMENTS,
        PERM_MANAGE_DOCUMENTS,
        PERM_UPLOAD_DOCUMENTS,
        PERM_DELETE_DOCUMENTS,
        PERM_READ_QUALITY,
    },
    Role.AUDITOR.value: {
        PERM_READ_AUDIT,
        PERM_READ_QUALITY,
    },
    Role.ADMIN.value: {
        PERM_MANAGE_USERS,
        PERM_READ_AUDIT,
        PERM_READ_METRICS,
        PERM_READ_QUALITY,
        # Note: admin has NO implicit document access (read:documents / read:rag)
    },
}

def has_permission(role: str, permission: str) -> bool:
    """Checks whether a role possesses a given permission."""
    return permission in ROLE_PERMISSIONS.get(role, set())
