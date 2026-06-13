"""
RBAC matrix tests — 4 roles × 5 domains.
Verifies that system roles get the correct domain permissions on bootstrap.
"""

import pytest

from app.services.auth.rbac_service import ALL_DOMAINS, SYSTEM_ROLES


@pytest.mark.unit
def test_platform_admin_has_all_domains() -> None:
    admin = next(r for r in SYSTEM_ROLES if r["name"] == "platform_admin")
    assert set(admin["domains"]) == set(ALL_DOMAINS)
    assert admin["can_export"] is True


@pytest.mark.unit
def test_power_user_has_all_domains() -> None:
    pu = next(r for r in SYSTEM_ROLES if r["name"] == "power_user")
    assert set(pu["domains"]) == set(ALL_DOMAINS)
    assert pu["can_export"] is True


@pytest.mark.unit
def test_business_user_has_no_default_domains() -> None:
    bu = next(r for r in SYSTEM_ROLES if r["name"] == "business_user")
    assert bu["domains"] == []
    assert bu["can_export"] is False


@pytest.mark.unit
def test_viewer_has_no_default_domains() -> None:
    viewer = next(r for r in SYSTEM_ROLES if r["name"] == "viewer")
    assert viewer["domains"] == []
    assert viewer["can_export"] is False


@pytest.mark.unit
def test_all_domains_covered() -> None:
    assert set(ALL_DOMAINS) == {"finance", "sales", "purchasing", "inventory", "operations"}


@pytest.mark.unit
def test_exactly_four_system_roles() -> None:
    names = {r["name"] for r in SYSTEM_ROLES}
    assert names == {"platform_admin", "power_user", "business_user", "viewer"}
