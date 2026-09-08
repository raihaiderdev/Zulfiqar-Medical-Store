"""
Session-scoped setup for tests that exercise the service layer (auth,
user management) rather than the ORM directly.

`app.database.engine` builds its engine from `app.config.settings` at
*import time*, so the DB URL env var must be set before anything under
`app.*` is imported anywhere in the test run. conftest.py is collected by
pytest before test modules, which is what makes this ordering work.
"""
from __future__ import annotations

import os
import tempfile

import pytest

_fd, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["PHARMACY_DB_URL"] = f"sqlite:///{_TEST_DB_PATH}"

from app.database.session import init_db, session_scope  # noqa: E402
from app.security.session_context import current_session  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _initialize_schema():
    init_db()
    # The permission catalog must exist before any grant/check logic runs —
    # in the real app this is done by scripts/seed_demo_data.py on first run.
    from app.models import Permission
    from app.permissions.keys import ADMIN_ONLY_PERMISSIONS, GRANTABLE_PERMISSIONS

    with session_scope() as session:
        for key, description in {**GRANTABLE_PERMISSIONS, **ADMIN_ONLY_PERMISSIONS}.items():
            session.add(Permission(key=key, description=description, admin_only=key in ADMIN_ONLY_PERMISSIONS))
    yield
    if os.path.exists(_TEST_DB_PATH):
        os.remove(_TEST_DB_PATH)


@pytest.fixture(autouse=True)
def _reset_session_context():
    """The process-wide login session must not leak between tests."""
    current_session.clear()
    yield
    current_session.clear()


# Shared admin identity for every test module that needs a logged-in admin.
# Session-scoped and idempotent, so it doesn't matter which test module
# happens to request it first — module run order is not relied upon.
ADMIN_USERNAME = "test_suite_admin"
ADMIN_PASSWORD = "AdminPass123!"


@pytest.fixture(scope="session")
def bootstrap_admin():
    from app.services import auth_service

    if auth_service.needs_first_run_setup():
        auth_service.create_first_admin(ADMIN_USERNAME, ADMIN_PASSWORD, full_name="Test Suite Admin")
    return ADMIN_USERNAME, ADMIN_PASSWORD


@pytest.fixture()
def admin_logged_in(bootstrap_admin):
    """Logs in as the shared admin for the duration of one test."""
    from app.services import auth_service

    username, password = bootstrap_admin
    auth_service.login(username, password)
    yield username, password
    auth_service.logout()
