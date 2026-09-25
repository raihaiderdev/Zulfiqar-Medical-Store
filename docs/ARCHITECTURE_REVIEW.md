# Architecture Review — Zulfiqar Medical Store Pharmacy Management System

## 1. Current Architecture Summary

### Technology Stack
- **Runtime**: Python 3.13, Windows desktop (standalone EXE via PyInstaller)
- **GUI**: PySide6 (Qt 6.x) — `QMainWindow` + `QStackedWidget` sidebar nav
- **ORM**: SQLAlchemy 2.0 with SQLite (WAL mode, FK enforcement)
- **Migrations**: Alembic (2 migrations: initial schema + unit fields)
- **Security**: bcrypt password hashing (scrypt fallback), role-based permissions
- **Reporting**: ReportLab PDF, pandas CSV/Excel
- **Packaging**: PyInstaller onedir, `ZulfiqarMedicalStore.exe`

### Layered Architecture (strictly enforced)
```
UI (app/ui/)
    ↓ calls
Services (app/services/)          ← business logic + permission enforcement
    ↓ calls
Repositories (app/repositories/)  ← data access only, no business rules
    ↓ uses
Models (app/models/)              ← SQLAlchemy ORM, no business logic
    ↓ stored in
SQLite (database/pharmacy.db)     ← WAL mode, FK enforcement
```

### Database: 26 Tables
Core entities: `users`, `permissions`, `user_permissions`, `medicines`, `medicine_batches`, `stock_transactions`, `sales`, `sale_items`, `sale_returns`, `sale_return_items`, `purchases`, `purchase_items`, `purchase_returns`, `purchase_return_items`, `suppliers`, `customers`, `categories`, `manufacturers`, `wardrobes`, `racks`, `shelves`, `expenses`, `expense_categories`, `audit_logs`, `application_settings`, `report_snapshots`

### Permission System
16 grantable permissions + 4 admin-only keys. Enforced exclusively in the service layer via `@require_permission()` / `@require_admin` decorators.

## 2. Strengths

| Strength | Detail |
|----------|--------|
| Stock ledger integrity | `stock_service.apply_stock_change()` is the ONLY mutation point for `MedicineBatch.quantity`. Every call creates a `StockTransaction` row atomically. |
| FEFO allocation | `allocate_fefo()` always uses earliest-expiring non-expired batches. Expired stock can only be sold via explicit admin override. |
| Transaction safety | All service mutations use `session_scope()` — commit on success, rollback on any exception. No partial writes possible. |
| Historical accuracy | `SaleItem.unit_price` and `unit_cost` are captured at sale time, never recomputed. |
| Audit trail | Every sensitive action writes to append-only `audit_logs` in the same transaction. |
| Permission enforcement | Authorization is never done by hiding UI elements alone — it is enforced at the service layer on every call. |
| Money precision | All financial values stored as `Numeric(12, 2)`, never float columns. |

## 3. Gaps Identified (for Phase 1–8 implementation)

### Phase 1 — Smart Inventory Intelligence
- **No sales velocity analysis**: No historical sales rate computation exists. The `sale_items` table has all the data needed but no service queries it for velocity.
- **No reorder suggestion engine**: `min_stock_level` and `reorder_level` exist on `Medicine` but no logic computes reorder quantities based on lead time or demand.
- **Expiry risk lacks financial context**: Current `expiry_report()` does not include purchase value or estimated waste cost.
- **No dead stock detection**: No query identifies medicines with zero sales over a configurable period.
- **Supplier lead time not tracked**: `Supplier` model has no `lead_time_days` field.

### Phase 2 — Purchasing & Financial Management
- **No Purchase Order workflow**: `Purchase` is a record of receipt, not a pre-purchase order. No draft/approved/received workflow exists.
- **No cashier shift management**: No shift open/close, no cash reconciliation.
- **Financial reporting is basic**: Revenue/COGS/Gross Profit exist but no cash flow, AP/AR, or shift-level reconciliation.
- **Purchases page is single-line**: The UI only records one batch per purchase submission.

### Phase 3 — Offline AI Copilot
- **No AI infrastructure**: No local inference, no embedding store, no tool registry, no chat UI.
- **No documentation index**: USER_GUIDE.md exists but is not indexed for retrieval.

### Phase 4 — AI Excel Import
- **Manual column mapping only**: `excel_importer.py` has a column mapping system but no AI-assisted suggestions.

### Phase 5 — Natural Language Navigation
- **No navigation registry**: No programmatic route registry for AI to use.

### Phase 6 — Voice Assistant
- **Not implemented**: No speech-to-text or TTS.

### Phase 7 — UX Improvements
- **No global search**: Each section has its own search.
- **No Urdu localization**: English only.
- **Error messages are technical**: Some SQLAlchemy exceptions surface as raw text.

### Phase 8 — Multi-branch
- **No branch identifiers**: All records are implicitly single-branch.

## 4. Compatibility Risks

| Risk | Mitigation |
|------|-----------|
| AI model RAM usage on low-spec Windows PCs | Use quantized GGUF models (Q4_K_M ≈ 4 GB RAM). Make AI optional — app must work without it. |
| PyInstaller size increase with AI libraries | Ship llama-cpp-python as optional dependency. Keep base EXE lean. |
| SQLite concurrent access during AI background thread | AI tools must use their own `session_scope()` — never share sessions across threads. |
| Schema migrations on existing installations | All new columns must use `ALTER TABLE ADD COLUMN` with defaults. Never drop existing columns. |
| PySide6 UI thread blocking during AI inference | All inference must run in `QThread` / `QRunnable`. |

## 5. New Tables Required

### Phase 1
- `supplier_lead_times` (or add `lead_time_days` to `suppliers`)
- No new tables needed for analytics — computed from existing `sale_items` + `stock_transactions`

### Phase 2
- `purchase_orders` — draft PO header
- `purchase_order_items` — PO lines
- `cashier_shifts` — shift open/close
- `shift_transactions` — cash movements within a shift

### Phase 3
- `ai_conversations` — optional session conversation history
- `ai_tool_calls` — audit log of AI-triggered tool calls

## 6. Migration Strategy

All new migrations must:
1. Use `render_as_batch=True` (already configured in `database/migrations/env.py`)
2. Add nullable columns or columns with `server_default`
3. Never drop existing columns in upgrade path
4. Support both fresh installs and existing v1.0/v2.x installations
