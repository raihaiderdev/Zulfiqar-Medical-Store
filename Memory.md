# Memory.md

Quick-reference for developers and AI coding assistants working on this repository.
See [Architecture.md](Architecture.md), [Design.md](Design.md), [Rules.md](Rules.md) for detail.

---

## What This Application Does

Offline-first Windows desktop pharmacy management system for Zulfiqar Medical Store. Manages inventory (FEFO batch-level), POS sales, purchases, returns, doctor fees, reporting, user permissions, and backup/restore. No internet connection required.

---

## Verified Stack

Python 3.12+, PySide6 ≥ 6.6, SQLAlchemy 2.0 (mapped-column API), SQLite, Alembic ≥ 1.13, bcrypt, pandas/openpyxl, reportlab, PyInstaller.

---

## Dev Commands

```bash
# Setup
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt

# Run app
python main.py

# Run migrations
python -m alembic upgrade head

# Seed permissions + demo admin
python scripts/seed_demo_data.py

# Run tests (set DB URL first so tests use a temp file)
python -m pytest tests/ --ignore=tests/test_ui_smoke.py -q

# Build Windows EXE
pyinstaller pharmacy_management.spec --clean --noconfirm
```

**Test DB isolation:** `tests/conftest.py` sets `PHARMACY_DB_URL` to a temp SQLite file before importing any `app.*` module. This is load-order-dependent — do not import `app.*` in conftest before the env var is set.

---

## High-Level Module Map

| Directory | Purpose |
|---|---|
| `app/config/settings.py` | Frozen `AppSettings` dataclass; reads env vars |
| `app/database/session.py` | `session_scope()` context manager; all DB writes go here |
| `app/database/migrate.py` | `run_migrations_to_head()` called at app startup |
| `app/models/` | SQLAlchemy ORM models; `__init__.py` imports all for Alembic |
| `app/permissions/keys.py` | Single source of truth for permission key strings |
| `app/services/` | All business logic; permission-gated; own transaction boundaries |
| `app/services/stock_service.py` | **ONLY** place that mutates `MedicineBatch.quantity` |
| `app/repositories/` | DB queries; called by services |
| `app/security/session_context.py` | `current_session` singleton; do not bypass it |
| `app/reports/report_engine.py` | Financial reports; `sales_and_profit_report()` is source of truth |
| `app/ui/` | PySide6 pages; never touch ORM directly |
| `tests/conftest.py` | Session-scoped fixtures, admin login, test DB |

---

## Domain Terms

| Term | Meaning |
|---|---|
| **MedicineBatch** | One lot of a medicine: batch number, expiry, quantity, prices |
| **FEFO** | First-Expiry-First-Out — how batches are allocated in sales |
| **StockTransaction** | Immutable ledger row for every quantity change |
| **SaleItem** | One line of a Sale; links to a specific batch |
| **session_scope()** | DB transaction wrapper — commit on success, rollback on error |
| **current_session** | Process-wide login state singleton |
| **DoctorFee** | Consultation fee separate from medicine sale |
| **PurchaseOrder** | Planned purchase (DRAFT→APPROVED→RECEIVED→COMPLETED) |
| **CashierShift** | Cash reconciliation period per cashier |

---

## Critical Invariants (Never Break These)

1. **`apply_stock_change()` only.** No code outside `stock_service.py` may write `MedicineBatch.quantity`.
2. **`session_scope()` for all writes.** Every service write must be inside a `session_scope()` context manager.
3. **Audit every sensitive action.** Call `audit_service.record()` inside the same session as the action.
4. **`@require_permission` on all mutating services.** Never add a service function that writes data without a permission decorator.
5. **FEFO never allocates expired batches.** `fefo_candidates()` filters `expiry_date >= today`.
6. **Discount cannot make total negative.** Validated in `complete_sale()`.
7. **All models imported in `app/models/__init__.py`** so Alembic autogenerate detects them.

---

## Where to Find Things

| Question | Answer |
|---|---|
| How is a sale completed? | `app/services/sales_service.py` → `complete_sale()` |
| How is stock decremented? | `app/services/stock_service.py` → `apply_stock_change()` |
| How are permission checks enforced? | `app/security/decorators.py` → `@require_permission` |
| Where are invoice numbers generated? | `app/utils/numbering.py` → `next_invoice_number()` |
| What migrations exist? | `database/migrations/versions/` (5 files, head: `d4e5f6a7b8c9`) |
| What are all permissions? | `app/permissions/keys.py` |
| How do reports exclude returns? | `app/reports/report_engine.py` → `_returned_quantity_by_sale_item()` |
| How does backup work? | `app/services/backup_service.py` → `create_backup()` / `restore_backup()` |

---

## Safe Workflow for a New Feature

1. Add model to `app/models/<name>.py`; import in `app/models/__init__.py`.
2. Create Alembic migration: `alembic revision -m "description"` then fill `upgrade()`/`downgrade()`.
3. Add permission key(s) to `app/permissions/keys.py`.
4. Write service in `app/services/<name>_service.py` using `session_scope()`, `@require_permission`, and `audit_service.record()`.
5. Add repository queries to `app/repositories/` if needed.
6. Add UI page to `app/ui/<area>/<name>_page.py`; register in `main_window.py` with the correct permission gate.
7. Write tests in `tests/test_<name>.py` using the existing conftest fixtures.
8. Run `python -m pytest tests/ --ignore=tests/test_ui_smoke.py -q`.
9. Run migration on the real DB: `alembic upgrade head`.

---

## Known Gaps

- `doctor_fee_service`, `invoice_edit_service`, `shift_service`, `purchase_order_service` have **no tests**.
- Doctor fee revenue is **not included** in `sales_and_profit_report()` — it is tracked separately but not surfaced in the standard report.
- `settings.app_version` is hardcoded `"1.0.0"` in `config/settings.py` (deployed version is 2.2).
- The `softsolz-test` pytest plugin was installed in the environment and crashed the test runner; it has been removed (`pip uninstall softsolz-test`).

---

## Source of Truth

- **Behavior:** Source code and tests.
- **Schema:** `database/migrations/versions/` and `app/models/`.
- **Permissions:** `app/permissions/keys.py`.
- **Docs:** May lag the code; treat as intended behavior, not verified behavior.

---

## Unresolved Questions

1. Should doctor fee revenue appear in `sales_and_profit_report()`? Currently it does not.
2. Is the `ForecastPage` UI intended to be smoke-tested? Currently excluded from `test_ui_smoke.py`.
3. Should `settings.app_version` drive the About screen / EXE version metadata?
4. Is the invoice edit action name `INVOICE_EDITED` (what the code records) or `INVOICE_CORRECTED` (what some docs say)?
