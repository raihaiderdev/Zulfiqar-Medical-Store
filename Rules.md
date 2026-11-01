# Rules.md

Rules for contributors and AI coding assistants working on this repository.
Rules derived from verified source code are marked **(V)**. Recommendations not yet enforced by code are marked **(P — Proposed)**.

---

## 1. Architecture and Layer Responsibilities

**R-01 (V):** UI code (`app/ui/`) must never import SQLAlchemy sessions, models, or repositories directly. All DB access goes through service functions.

**R-02 (V):** Repository code (`app/repositories/`) must never call service functions. Repositories only query the ORM.

**R-03 (V):** Service functions own transaction boundaries. Open exactly one `session_scope()` per service call. Do not open nested `session_scope()` calls from within an outer one unless you are the `purchase_order_service` calling `purchase_service` across separate sessions by design.

**R-04 (V):** Do not bypass `current_session`. UI and service code must read user identity from `current_session`, never from function arguments, to prevent privilege escalation.

---

## 2. Service-Layer Permission Checks

**R-05 (V):** Every service function that reads sensitive data or performs any mutation must be decorated with `@require_permission(key)` or `@require_admin`.

**R-06 (V):** Add the permission key to `app/permissions/keys.py` before using it in a decorator. `GRANTABLE_PERMISSIONS` for user-grantable keys; `ADMIN_ONLY_PERMISSIONS` for admin-only keys.

**R-07 (V):** Inline authorization checks (e.g. discount permission) must happen before the `session_scope()` block opens, so no partial DB writes occur on authorization failure.

**R-08 (V):** Never rely on UI hiding for security. A user who bypasses the UI must still be rejected at the service layer.

---

## 3. Atomic Transactions and Audit Logging

**R-09 (V):** Every service write must be inside a `session_scope()` context manager. This guarantees commit on success and rollback on any exception — including validation errors raised mid-loop.

**R-10 (V):** Call `audit_service.record()` inside the same `session_scope()` as the action it describes. This ensures the audit record commits with the action or rolls back with it.

**R-11 (V):** Include `old_value` in the audit record for any update or deletion. Use the snapshot-before-change pattern: capture the original dict before writing.

**R-12 (V):** Require a non-empty `reason` string for any action that modifies historical data (invoice edits, stock adjustments, doctor fee corrections/voids, returns). Enforce this in the service, not the UI.

---

## 4. Stock Changes and Ledger Consistency

**R-13 (V):** `stock_service.apply_stock_change()` is the **only function** permitted to write `MedicineBatch.quantity`. Never assign `batch.quantity` directly anywhere else.

**R-14 (V):** Pass the already-open `session` to `apply_stock_change()`. Do not call it with a new `session_scope()` from inside a parent transaction — that would split the commit.

**R-15 (V):** `apply_stock_change()` rejects any delta that would make quantity negative. Do not pre-check and conditionally call it — let it enforce the invariant.

**R-16 (V):** Invoice corrections must use `StockTxnType.SALE` (for increases) or `StockTxnType.SALE_RETURN` (for decreases with restock). Never overwrite or delete existing `StockTransaction` rows.

---

## 5. FEFO and Expired Stock

**R-17 (V):** `fefo_candidates()` in `MedicineBatchRepository` must only return batches where `expiry_date >= today` and `is_active = True` and `quantity > 0`. Expired batches must never be auto-allocated.

**R-18 (V):** Selling an expired batch requires all four conditions: (a) explicit `batch_id` in the sale line, (b) `allow_expired_override=True` passed by the caller, (c) `settings.expiry_clearance_override_enabled = True`, and (d) `current_session.has_permission("sales.override_expired")`. Do not relax any condition.

**R-19 (V):** `write_off_expired_batch()` must verify `expiry_date < today` before proceeding. Rejecting a non-expired batch prevents accidental write-offs.

---

## 6. Money Precision and Historical Values

**R-20 (V):** Use `Numeric(12, 2)` for all monetary columns. Never use `Float` for money.

**R-21 (V):** Once a `Sale` is completed, its original `invoice_number` and `sale_date` must not be changed. Only totals, amounts, and notes may be corrected via `invoice_edit_service`.

**R-22 (V):** `SaleItem.unit_cost` captures the purchase price at the time of sale. Do not recalculate it from the current batch price when generating reports — the original value is the historical fact.

**R-23 (V):** Validate all incoming float parameters with `math.isfinite()` before using them in calculations. Reject NaN and infinite values with a clear `ValidationError`.

---

## 7. Alembic Migrations and SQLite

**R-24 (V):** Always generate a new Alembic migration for schema changes. Do not use `Base.metadata.create_all()` as a schema update mechanism in production.

**R-25 (V):** Write both `upgrade()` and `downgrade()` functions. `downgrade()` must reverse the `upgrade()` exactly, including data rows inserted.

**R-26 (V):** Use `INSERT OR IGNORE INTO permissions ...` for permission seeding in migrations, not `INSERT INTO`. This makes migrations idempotent.

**R-27 (V):** SQLite does not support `ALTER COLUMN`. To change a column type, use a table-rename + create-new + copy + drop sequence, or add a new column and migrate data.

**R-28 (V):** Before adding a new model, import it in `app/models/__init__.py`. Alembic's `autogenerate` will not detect it otherwise.

**R-29 (P — Proposed):** Pin a `pytest.ini` or `[tool.pytest.ini_options]` section specifying `testpaths = ["tests"]` and `addopts = --ignore=tests/test_ui_smoke.py` to avoid relying on the absence of broken environment-level plugins.

---

## 8. Error Handling and Logging

**R-30 (V):** Raise only `app/utils/exceptions.py` exception types from service functions: `ValidationError`, `NotFoundError`, `AuthorizationError`, `AuthenticationError`, `SessionExpiredError`, `ConflictError`. Never raise plain `Exception` or `ValueError` from services.

**R-31 (V):** UI code catches `ApplicationError` (the base class of all app exceptions) at the boundary and shows it via `QMessageBox`. Never let an unhandled service exception crash the application.

**R-32 (V):** Log to `logs/application.log` and `logs/error.log` via the configured logger. Do not use `print()` for operational messages.

---

## 9. ORM and Detached Object Safety

**R-33 (V):** Never return ORM objects from a service function. Always convert to plain dicts (or dataclasses) before the `session_scope()` context manager exits. Returning a detached ORM object causes `DetachedInstanceError` when the UI accesses lazy-loaded relationships.

**R-34 (V):** For queries that need related objects (e.g. `supplier.name`, `len(items)`), use `selectinload()` or `joinedload()` inside the session, not lazy loading after the session closes.

---

## 10. Test Isolation

**R-35 (V):** All tests use the `conftest.py` temp-DB fixture. Never hardcode a path to `database/pharmacy.db` in tests.

**R-36 (V):** The `PHARMACY_DB_URL` env var must be set before any `app.*` module is imported. This is handled by `conftest.py` at the top of the file, before the imports. Do not reorder this.

**R-37 (V):** Use `admin_logged_in` fixture (or `bootstrap_admin` + `auth_service.login`) to set up an authenticated session for each test. Never leave `current_session` populated between tests — the `_reset_session_context` autouse fixture in conftest handles cleanup.

**R-38 (V):** Do not delete, weaken, or rewrite existing tests to make them pass. If a test fails, fix the code.

---

## 11. Documentation Requirements

**R-39 (V):** Distinguish between "Verified", "Implemented not fully tested", and "Proposed" in all documentation. Do not claim a feature works unless tests or code review support the claim.

**R-40 (V):** When fixing a defect, add a regression test that would have caught it.

**R-41 (V):** Update `Architecture.md`, `Design.md`, `Memory.md`, `PRD.md`, `Task.md` whenever a new service, model, migration, or page is added.

---

## 12. Required Verification Steps for Any Code Change

1. Run `python -m pytest tests/ --ignore=tests/test_ui_smoke.py -q` — all existing tests must pass.
2. If you added a model: verify `alembic revision --autogenerate` detects it.
3. If you added a migration: run `alembic upgrade head` against a temp DB and verify the table exists.
4. If you added a service function: add at least one test covering the happy path and one covering a validation/permission failure.
5. If you modified `stock_service.apply_stock_change()` or `allocate_fefo()`: run the full test suite, not just the affected test.
6. Inspect `git diff` before committing: confirm no unintended files changed.
