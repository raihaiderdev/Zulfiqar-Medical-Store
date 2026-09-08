"""
Phase 3 tests — authentication, session/permission enforcement, and admin
user management. Runs against the disposable DB configured in conftest.py.
"""
from __future__ import annotations

import pytest

from app.services import auth_service, user_service
from app.security.session_context import current_session
from app.utils.exceptions import AuthenticationError, AuthorizationError, ConflictError, ValidationError

from tests.conftest import ADMIN_USERNAME, ADMIN_PASSWORD


@pytest.fixture(scope="module", autouse=True)
def _use_shared_admin(bootstrap_admin):
    """Every test in this module relies on the shared admin already
    existing — `bootstrap_admin` (from conftest.py) creates it exactly
    once per test session, regardless of which module runs first."""
    yield


def test_first_run_setup_cannot_run_twice():
    with pytest.raises(ConflictError):
        auth_service.create_first_admin("second_admin", "SomePass123!")


def test_login_success_populates_session():
    auth_service.login(ADMIN_USERNAME, ADMIN_PASSWORD)
    assert current_session.is_authenticated is True
    assert current_session.username == ADMIN_USERNAME
    assert current_session.is_admin is True
    auth_service.logout()
    assert current_session.is_authenticated is False


def test_login_wrong_password_rejected():
    with pytest.raises(AuthenticationError):
        auth_service.login(ADMIN_USERNAME, "totally-wrong-password")
    assert current_session.is_authenticated is False


def test_login_unknown_username_rejected():
    with pytest.raises(AuthenticationError):
        auth_service.login("no-such-user", "whatever123")


def test_logout_clears_session():
    auth_service.login(ADMIN_USERNAME, ADMIN_PASSWORD)
    assert current_session.is_authenticated is True
    auth_service.logout()
    assert current_session.is_authenticated is False
    assert current_session.username is None


def test_service_call_without_session_raises():
    # No login has happened in this test — current_session is cleared by
    # the autouse fixture in conftest.py.
    with pytest.raises(Exception):
        user_service.list_users()


def test_admin_can_create_user_and_grant_permissions():
    auth_service.login(ADMIN_USERNAME, ADMIN_PASSWORD)
    user_id = user_service.create_user(
        username="cashier1",
        password="CashierPass123!",
        full_name="Cashier One",
        is_admin=False,
        permission_keys=["sales.create", "sales.view", "medicine.view"],
    )
    assert isinstance(user_id, int)

    granted = user_service.get_user_permissions(user_id)
    assert granted == {"sales.create", "sales.view", "medicine.view"}
    auth_service.logout()


def test_non_admin_cannot_manage_users():
    # cashier1 was created by the previous test.
    auth_service.login("cashier1", "CashierPass123!")
    with pytest.raises(AuthorizationError):
        user_service.create_user(username="another", password="AnotherPass123!")
    auth_service.logout()


def test_admin_only_permission_never_grantable_to_regular_user():
    auth_service.login(ADMIN_USERNAME, ADMIN_PASSWORD)
    user_id = user_service.create_user(
        username="sneaky_grant_test",
        password="SneakyPass123!",
        permission_keys=["users.manage"],  # admin-only — must be silently ignored
    )
    granted = user_service.get_user_permissions(user_id)
    assert "users.manage" not in granted
    auth_service.logout()

    # And even if a permission row existed, has_permission() must still
    # refuse it for a non-admin session.
    auth_service.login("sneaky_grant_test", "SneakyPass123!")
    assert current_session.has_permission("users.manage") is False
    auth_service.logout()


def test_deactivated_user_cannot_login():
    auth_service.login(ADMIN_USERNAME, ADMIN_PASSWORD)
    user_id = user_service.create_user(username="temp_user", password="TempPass123!")
    user_service.deactivate_user(user_id)
    auth_service.logout()

    with pytest.raises(AuthenticationError):
        auth_service.login("temp_user", "TempPass123!")


def test_admin_cannot_deactivate_self():
    auth_service.login(ADMIN_USERNAME, ADMIN_PASSWORD)
    admin_users = [u for u in user_service.list_users() if u.username == ADMIN_USERNAME]
    admin_id = admin_users[0].id
    with pytest.raises(ValidationError):
        user_service.deactivate_user(admin_id)
    auth_service.logout()


def test_password_reset_by_admin_allows_new_login():
    auth_service.login(ADMIN_USERNAME, ADMIN_PASSWORD)
    user_id = user_service.create_user(username="reset_target", password="OldPass123!")
    new_password = user_service.reset_password(user_id, new_password="BrandNewPass123!")
    auth_service.logout()

    auth_service.login("reset_target", new_password)
    assert current_session.username == "reset_target"
    auth_service.logout()

    with pytest.raises(AuthenticationError):
        auth_service.login("reset_target", "OldPass123!")


def test_self_password_change_requires_correct_old_password():
    auth_service.login(ADMIN_USERNAME, ADMIN_PASSWORD)
    user_id = user_service.create_user(username="self_change_user", password="Initial123!")
    auth_service.logout()

    auth_service.login("self_change_user", "Initial123!")
    with pytest.raises(AuthenticationError):
        auth_service.change_own_password("wrong-old-password", "NewOne1234!")
    auth_service.change_own_password("Initial123!", "NewOne1234!")
    auth_service.logout()

    auth_service.login("self_change_user", "NewOne1234!")
    assert current_session.is_authenticated is True
    auth_service.logout()


def test_weak_password_rejected():
    auth_service.login(ADMIN_USERNAME, ADMIN_PASSWORD)
    with pytest.raises(ValidationError):
        user_service.create_user(username="weakpw", password="short")
    auth_service.logout()


def test_session_expiry_blocks_further_actions(monkeypatch):
    auth_service.login(ADMIN_USERNAME, ADMIN_PASSWORD)
    # Force the idle clock back so is_expired() reports True without
    # sleeping the test suite for real minutes.
    from datetime import datetime, timedelta, timezone

    current_session.last_activity_at = datetime.now(timezone.utc) - timedelta(hours=1)
    with pytest.raises(Exception):
        user_service.list_users()
    # A failed permission-gated call clears the stale session.
    assert current_session.is_authenticated is False
