# Pharmacy Management System

A complete, offline-first desktop Pharmacy Store Management application.

- **Stack:** Python 3.12+, SQLite, PySide6, SQLAlchemy 2.0, Alembic, pandas/openpyxl, reportlab
- **Runs fully offline** — no cloud services, no internet dependency for any core feature
- **Packaged as a standalone Windows executable** via PyInstaller

## Features

- Batch-level inventory with FEFO (First-Expiry-First-Out) sale allocation
- Full audit trail — every stock change is a ledger entry, every sensitive action is logged
- Role-based permissions, enforced in the service layer (not just hidden UI)
- Sales / POS with barcode-scanner support, discounts (capped, permission-gated), invoice PDF printing
- Purchases, sale/purchase returns, manual stock adjustments — all atomic and traceable
- Excel import with column mapping, row-level validation, and a preview before commit
- Reporting: sales/profit (with correct COGS and return handling), best-sellers, stock valuation, month-close snapshots
- Admin dashboard with live KPIs
- Backup/restore with automatic safety-backup-before-restore and rotation
- Full user/permission management, first-run setup wizard, session timeout

## Quick Start (development)

```bash
python -m venv .venv
source .venv/bin/activate        # or .venv\Scripts\activate on Windows
pip install -r requirements.txt

python -m alembic upgrade head              # create database/pharmacy.db
python scripts/seed_demo_data.py            # permission catalog + a first admin
python scripts/seed_demo_data.py --with-demo-data   # + sample medicine/batch/sale

python main.py
```

On first launch (no admin account yet), the app shows a **Setup Wizard** instead of
skipping straight to login — use that instead of the seed script for a real install.
The seed script's default admin (`admin` / `ChangeMe123!`) is a dev/demo convenience only.

## Running Tests

```bash
python -m pytest tests/ -v
```

75 tests cover the schema, authentication/permissions, inventory, purchases, sales/POS
(including FEFO and expired-stock blocking), returns/adjustments, reporting, dashboards,
backup/restore, exports, PDF printing, and settings, plus 8 UI smoke tests (offscreen,
no display needed) exercising every page and dialog end-to-end. All run against a
disposable SQLite file, never your real `database/pharmacy.db`.

## Project Structure

See [`DATABASE.md`](DATABASE.md) for the schema and [`DEVELOPER_GUIDE.md`](DEVELOPER_GUIDE.md)
for the module layout and architecture. See [`USER_GUIDE.md`](USER_GUIDE.md) for how to use
the application day-to-day.

## Building the Windows Executable

```bash
pip install pyinstaller
pyinstaller pharmacy_management.spec
```

Produces `dist/PharmacyManagement/PharmacyManagement.exe` (plus its supporting files —
this is a `--onedir`-style build, not a single-file exe; see the spec file for why).
Ship the whole `dist/PharmacyManagement/` folder. The app runs its own Alembic
migrations on first launch, so the database is created automatically — no separate
install step needed. Full details in `DEVELOPER_GUIDE.md`.

## Troubleshooting

- **"Database is locked" errors**: close any other instance of the app, or a DB browser
  tool, that has `database/pharmacy.db` open.
- **Forgot the admin password**: there's no self-service reset for the last remaining
  admin by design (Phase 1 security model). Restore from a recent backup, or use
  `scripts/seed_demo_data.py` against a *fresh* database if you're still in initial setup.
- **Barcode scanner doesn't work**: most USB scanners act as a keyboard ("keyboard-wedge")
  — just make sure the Sales/POS search box or Medicine barcode field has focus before
  scanning; no special driver is needed.
- **Excel import rejects everything**: check the column-mapping step — required fields
  are medicine name, batch number, purchase price, selling price, quantity, and expiry date.
