# Database — Phase 2

## Setup

```bash
pip install -r requirements.txt --break-system-packages   # or use a venv without the flag
python -m alembic upgrade head          # creates database/pharmacy.db with all 26 tables
python scripts/seed_demo_data.py                    # permission catalog + default admin only
python scripts/seed_demo_data.py --with-demo-data    # + sample medicine/batch/purchase/sale
```

Default admin created by the seed script: **username `admin`, password `ChangeMe123!`.**
This is a first-run bootstrap placeholder only — Phase 3 (Authentication) replaces this
with an interactive setup wizard that lets the real administrator choose their own
credentials, per the Phase 1 spec (§3, §42).

## Tables (26)

| Group | Tables |
|---|---|
| Auth | `users`, `permissions`, `user_permissions` |
| Audit | `audit_logs` |
| Catalog | `categories`, `manufacturers`, `medicines` |
| Locations | `wardrobes`, `racks`, `shelves` |
| Parties | `suppliers`, `customers` |
| Inventory | `medicine_batches`, `stock_transactions` |
| Purchasing | `purchases`, `purchase_items`, `purchase_returns`, `purchase_return_items` |
| Sales | `sales`, `sale_items`, `sale_returns`, `sale_return_items` |
| Finance | `expense_categories`, `expenses` |
| System | `application_settings`, `report_snapshots` |

## Key design points

- **Batch-centric inventory.** `medicines` holds catalog info only; `medicine_batches`
  holds quantity, cost, and expiry. A medicine with zero batches has zero stock by
  construction — there's no separate "current stock" field to drift out of sync.
- **Append-only stock ledger.** Every quantity change on a batch must be paired with a
  `stock_transactions` row in the same DB transaction. `previous_quantity`/`new_quantity`
  make each row self-auditing; the sum of all `quantity` deltas for a batch always equals
  its current `quantity` (enforced by application code in Phase 4+, verified by
  `test_stock_transaction_ledger_matches_batch_quantity`).
- **Money as `Numeric(12, 2)`**, never `float`, everywhere a price/cost/total is stored.
- **Foreign keys are enforced** — SQLite has them off by default; `app/database/engine.py`
  turns `PRAGMA foreign_keys=ON` on for every connection.
- **Soft delete via `is_active`** on `medicines`, `users`, `customers`, `suppliers` —
  physical deletion is reserved for records with no historical references.
- **Cascade behavior**: `medicine_batches` cascades on medicine delete (`ondelete="CASCADE"`,
  `passive_deletes=True` on the ORM side so SQLite's own cascade — not the ORM — does the
  work). Sale/purchase items, returns, and stock transactions use `RESTRICT` on their
  parent financial records so historical transactions can never be deleted out from under
  a report.
- **`report_snapshots`** is an optional, explicitly-created cache for a *closed* period —
  reports are always computed from the transactional tables first; this table never
  becomes the source of truth (Phase 1 §I, §M.4).

## Migrations

Schema changes go through Alembic, not manual `create_all()` calls in production:

```bash
# after changing a model:
python -m alembic revision --autogenerate -m "describe the change"
python -m alembic upgrade head
```

`render_as_batch=True` is set in `database/migrations/env.py` because SQLite can't do
most `ALTER TABLE` operations directly — Alembic's "batch mode" rebuilds the table under
the hood instead, which is required for any future column add/drop/rename on SQLite.

`init_db()` in `app/database/session.py` (a plain `create_all()`) exists only for tests
and quick local experiments — the real app and the Phase-1-mandated first-run wizard
should always go through `alembic upgrade head`.

## Tests

```bash
python -m pytest tests/test_database.py -v
```

9 tests covering: schema creation, unique constraints, FK enforcement, check constraints
(no negative stock), cascade delete, the stock-ledger-matches-quantity invariant, and the
password hashing round trip. All run against a disposable temp-file SQLite DB, never the
real `database/pharmacy.db`.
