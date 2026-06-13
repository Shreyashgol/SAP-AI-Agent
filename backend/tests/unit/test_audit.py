"""
Audit log service — immutability contract tests.
"""

import uuid

import pytest

from app.services.audit_service import AuditEvent


@pytest.mark.unit
def test_audit_event_constants_are_strings() -> None:
    """All AuditEvent constants must be non-empty dot-separated strings."""
    for attr in vars(AuditEvent):
        if attr.startswith("_"):
            continue
        value = getattr(AuditEvent, attr)
        assert isinstance(value, str)
        assert "." in value, f"{attr} should be dot-namespaced"
        assert len(value) > 3


@pytest.mark.unit
def test_audit_covers_dml_blocked() -> None:
    assert AuditEvent.DML_BLOCKED == "sql.dml_blocked"


@pytest.mark.unit
def test_audit_covers_auth_events() -> None:
    assert AuditEvent.AUTH_LOGIN == "auth.login"
    assert AuditEvent.AUTH_LOGOUT == "auth.logout"
    assert AuditEvent.AUTH_LOCKOUT == "auth.lockout"
