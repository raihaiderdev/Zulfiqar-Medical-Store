# Developer Guide

## Architecture

Strict layering, enforced by convention (not a hard framework boundary, but consistently
followed throughout):

```
UI (app/ui/)  →  Services (app/services/)  →  Repositories (app/repositories/)  →  Models (app/models/)
```

- **UI** never touches the ORM or opens a DB session directly. It calls service functions
  and catches `ApplicationError` subclasses to show friendly `QMessageBox` dialogs.
- **Services** own business rules, permission checks (`@require_permission` /
  `@require_admin`), transactions (`session_scope()`), and audit logging. This is where
  almost all of the "interesting" logic in this codebase lives.
- **Repositories** are thin, permission-free data access — `session.query(...)` wrapped
  in a class per aggregate root.
- **Models** are SQLAlchemy 2.0 declarative classes only — no business logic beyond a
  couple of trivial computed properties (`SaleItem.line_total`, `Shelf.full_location`).

## Directory Map

```
app/
├── config/settings.py        # env-driven AppSettings dataclass, path constants
├── database/
│   ├── engine.py              # engine + SQLite pragmas (FK enforcement, WAL)
│   ├── session.py             # session_scope() context manager, init_db()
│   └── migrate.py             # run_migrations_to_head() — used by main.py at startup
├── models/                    # one file per domain area, all imported in __init__.py
├── repositories/               # data access, one repository class per aggregate
├── services/                   # business logic — see "Services" below
├── security/
│   ├── passwords.py            # bcrypt hashing (falls back to scrypt if bcrypt absent)
│   ├── session_context.py      # process-wide logged-in-user state + idle timeout
│   └── decorators.py           # @require_permission / @require_admin
├── permissions/keys.py          # the canonical permission key catalog
├── imports/excel_importer.py    # column-mapping Excel import pipeline
├── exports/data_exporter.py      # CSV/Excel export
├── printing/pdf_documents.py     # invoice + tabular report PDF generation (reportlab)
├── reports/report_engine.py      # revenue/COGS/profit, best-sellers, stock valuation, month-close
├── logging/setup.py               # rotating application.log / error.log
├── utils/
│   ├── exceptions.py              # ApplicationError hierarchy
│   ├── numbering.py                # sequential invoice numbers
│   └── barcode_utils.py            # barcode/QR image generation
└── ui/                              # one subpackage per screen (see below)

database/migrations/            # Alembic — env.py wired to app.models, render_as_batch=True
scripts/seed_demo_data.py        # permission catalog + first admin (+ optional demo data)
tests/                             # 67 tests, one file per phase/feature area
```

## Services (the core of the business logic)

| Service | Responsibility |
|---|---|
| `auth_service` | First-run admin bootstrap, login/logout, self password change |
| `user_service` | Admin-only user CRUD, permission grants, password reset |
| `medicine_service` | Catalog CRUD, manual batch entry, low-stock/expiry reports |
| `party_service` | Suppliers, customers |
| `purchase_service` | Atomic purchase recording (batch create/top-up + stock + ledger) |
| `sales_service` | FEFO allocation, atomic sale completion, discount rules |
| `returns_service` | Sale/purchase returns, manual adjustments, expired write-off |
| `stock_service` | The **only** place `MedicineBatch.quantity` is mutated — every call writes a matching `StockTransaction` |
| `dashboard_service` | KPI aggregation for the admin dashboard |
| `backup_service` | SQLite-consistent backup/restore with WAL-sidecar cleanup and rotation |
| `settings_service` | Key/value application settings |
| `audit_service` | Writes `AuditLog` rows — called from inside other services' transactions |

## Key Invariants (don't break these)

1. **Never mutate `MedicineBatch.quantity` directly.** Always go through
   `stock_service.apply_stock_change()`, which writes the paired `StockTransaction` row.
   This is what makes the stock ledger trustworthy — `test_stock_transaction_ledger_matches_batch_quantity`
   in `tests/test_database.py` verifies the invariant.
2. **Every service mutation runs inside `session_scope()`.** A raised exception rolls
   back everything in that `with` block — see `test_failed_purchase_line_rolls_back_entire_transaction`
   for why this matters (a bad line in a multi-line purchase must not leave a good line's
   stock change committed).
3. **Permission checks live in the service layer**, via `@require_permission("key")` or
   `@require_admin` — never trust that the UI already checked. `ADMIN_ONLY_KEYS` (in
   `app/permissions/keys.py`) can never be granted to a non-admin, enforced independently
   in both `user_service._apply_permission_grants()` and `SessionContext.has_permission()`.
4. **Money is `Numeric(12, 2)` everywhere**, never a Python `float` column type (though
   values move through the code as `float` for convenience — SQLAlchemy handles the
   `Decimal` conversion at the boundary). Don't introduce a raw float DB column for a
   price/cost/total field.
5. **`unit_price`/`unit_cost` on `SaleItem` are captured at sale time**, not recomputed
   later from the batch's current prices — this is what makes historical profit reports
   accurate even after a medicine's price changes.
6. **FEFO, not FIFO.** `allocate_fefo()` in `sales_service.py` orders by `expiry_date`,
   and `MedicineBatchRepository.fefo_candidates()` excludes already-expired batches from
   the query entirely — expired stock can only be sold via the explicit, disabled-by-default
   `allow_expired_override` path.

## Database

See [`DATABASE.md`](DATABASE.md) for the full schema, ER diagram, and migration workflow.

## Adding a New Feature

1. Add/extend the model in `app/models/` if new data needs to be stored. Run
   `alembic revision --autogenerate -m "..."` and check the generated migration by eye —
   SQLite's limited `ALTER TABLE` support means `render_as_batch=True` (already configured)
   rebuilds the table under the hood for anything beyond adding a column.
2. Add repository query methods if needed (`app/repositories/`).
3. Write the service function: permission decorator, `session_scope()`, business rules,
   call `stock_service`/`audit_service` where relevant, return plain data (not detached
   ORM objects with lazy-loadable relationships the UI might touch after the session closes
   — see the `selectinload(Medicine.batches)` fix in `inventory_repository.py` for why that
   matters).
4. Write a test in `tests/` alongside the existing ones for that phase/area.
5. Wire up the UI: a page in `app/ui/<area>/`, added to `MainWindow._build_pages()` behind
   the right permission check.

## Testing

```bash
python -m pytest tests/ -v
```

`tests/conftest.py` points the app's global SQLAlchemy engine at a disposable temp-file
SQLite DB (set via the `PHARMACY_DB_URL` env var, read at import time — this is why the
env var must be set before any `app.*` import happens, which is why it's set at the very
top of `conftest.py` before those imports). The `bootstrap_admin`/`admin_logged_in`
fixtures give every test module a consistent, order-independent way to get a logged-in
admin session without recreating one from scratch each time.

UI code has an automated smoke-test suite (`tests/test_ui_smoke.py`) that runs Qt in
offscreen mode (`QT_QPA_PLATFORM=offscreen`, set at the top of that file before PySide6
is imported) — no real display needed, works in CI/sandboxes. It instantiates every page
and dialog and drives a couple of full flows (a POS sale, a purchase submission) through
their actual button-handler methods rather than through `exec()`, so it runs headless
and non-interactively. It caught a real bug during development (a `DetachedInstanceError`
from an ORM relationship accessed after the session closed — fixed with `selectinload()`
in `inventory_repository.py`) and several `QMessageBox` modal-hang risks (blocking dialogs
must be monkeypatched in tests, since there's no user to click them under `offscreen`).
It's a smoke-test suite, not full UI regression coverage — `pytest-qt` with `QTest` click
simulation would be the natural upgrade for testing widget-level interaction rather than
calling handler methods directly.

## Known Gaps / Natural Next Steps

- No dedicated **Returns UI page** yet — `returns_service` is fully implemented and
  tested, just not wired to a screen (an admin/power-user can be given a script or a
  future page). This was a scope call, not an oversight.
- **Charts** on the dashboard are simple tables, not visual charts — `matplotlib` or a
  Qt charting widget could be dropped in against the same `dashboard_service` KPI payload
  without changing the service layer.
- **Purchases UI** only submits one batch line per form submission (the service layer
  supports multi-line purchases in one atomic call — see `purchase_service.record_purchase(lines=[...])`).
  A proper multi-row grid editor would be the natural upgrade.
- **Printer configuration** (A4 vs. thermal width, printer selection) isn't in Settings
  yet — `render_invoice_pdf()` always produces an A4-sized PDF today.
- UI test coverage is smoke-level (see above) rather than full interaction-level
  (`pytest-qt` + `QTest`).
