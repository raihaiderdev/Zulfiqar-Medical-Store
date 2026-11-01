# PRD.md — Product Requirements Document

**Product:** Zulfiqar Medical Store Pharmacy Management System
**Version:** 2.2 (delivered 2026-10-30)
**Audience:** Store owner, pharmacy staff, system administrator.
**Status:** Active development. Features marked (E) Existing/Verified, (I) Implemented but not fully tested, (P) Proposed.
**Evidence boundary:** All (E) features are confirmed by source code inspection and automated tests. (I) features are confirmed by code review only. (P) features do not exist in the codebase.

---

## 1. Problem Statement

A small retail pharmacy managing hundreds of medicine SKUs, batch tracking, expiry dates, doctor consultations, and daily sales needs an integrated system that:
- Prevents overselling and expired-medicine dispensing.
- Tracks stock cost and profit accurately.
- Records doctor consultation fees alongside medicine sales on the same patient bill.
- Provides daily, monthly, and on-demand financial reports.
- Works fully offline on a single Windows PC.
- Protects data with role-based access and regular backups.

---

## 2. User Roles and Needs

### Administrator (store owner / manager)
- View full financial reports (revenue, COGS, profit, discounts, doctor fees).
- Manage users and assign granular permissions.
- Back up and restore the database.
- Configure store settings (currency, discount cap, session timeout).
- View the complete audit log.

### Cashier / Staff
- Complete POS sales with FEFO batch allocation, discounts (if permitted), and doctor fee attachment.
- Record purchases from suppliers.
- Process customer and supplier returns.
- View sales history and print invoices.
- Record standalone doctor fees (if permitted).

---

## 3. Product Goals and Success Criteria

| Goal | Measurable Criterion |
|---|---|
| Accurate stock | Batch.quantity never goes negative; every change has a ledger row |
| FEFO compliance | All auto-allocated sales consume the nearest-expiry batch first |
| Financial accuracy | `gross_profit = revenue − COGS` with returns and discounts correctly netted |
| Data safety | Backup before every restore; WAL cleared on restore |
| Access control | Every service mutation checks permissions before touching the DB |
| Offline operation | App runs with zero network calls |

---

## 4. Functional Requirements

### FR-01: Authentication and Session Management (E)
- FR-01.1: First-run setup wizard creates the initial admin account.
- FR-01.2: Login requires username + password (bcrypt hashed); generic error message prevents account enumeration.
- FR-01.3: Session auto-expires after configurable idle period (default 30 min).
- FR-01.4: Admin can reset any user's password; users can change their own with correct current password.
- FR-01.5: Admin cannot deactivate their own account.
- FR-01.6: Deactivated users cannot log in.

### FR-02: User and Permission Management (E)
- FR-02.1: Admin creates users with any subset of grantable permissions.
- FR-02.2: Admin-only permissions (`users.manage`, `settings.manage`, `backup.manage`, `audit_log.view`) can never be granted to non-admin users.
- FR-02.3: Admins implicitly have all permissions without explicit grants.

### FR-03: Medicine and Batch Management (E)
- FR-03.1: Create medicines with category, manufacturer, dosage form, barcode, rack/shelf location.
- FR-03.2: Add batches (batch number, quantity, purchase/selling price, expiry date, manufacturing date, shelf location).
- FR-03.3: Search medicines by name or barcode (up to 10,000 results).
- FR-03.4: Expiry alert fires on login if batches expire within the configured warning window.
- FR-03.5: Low-stock report lists batches below the configured threshold.
- FR-03.6: Inactive medicines cannot be purchased.

### FR-04: Purchases (E)
- FR-04.1: Record a purchase from a supplier; creates or tops up batches; writes stock ledger entries.
- FR-04.2: Multi-line purchases are atomic — a single invalid line rolls back the whole transaction.
- FR-04.3: Batch top-up updates purchase/selling price to latest values; expiry date mismatch is rejected.
- FR-04.4: Mark a purchase as paid.
- FR-04.5: Supplier purchase history report.
- FR-04.6: Inactive suppliers cannot receive new purchases.

### FR-05: POS Sales (E)
- FR-05.1: Cart-based POS with live DB-available-stock display.
- FR-05.2: FEFO auto-allocation; cashier can also pick a specific batch.
- FR-05.3: Unit selector (base unit or pack size).
- FR-05.4: Discount requires `sales.discount` permission; capped at admin-configured maximum percent.
- FR-05.5: Expired batches blocked unless override is explicitly authorized (setting + permission).
- FR-05.6: Sequential, unique invoice numbers.
- FR-05.7: Doctor fee can be attached at POS (doctor name + amount); appears as separate bill line; recorded atomically with the sale.
- FR-05.8: Stale-stock errors include medicine name and prompt to refresh cart.

### FR-06: Sales History and Invoice Editing (E / I)
- FR-06.1 (E): View list of sales with date range filter.
- FR-06.2 (E): View full invoice detail including line profit.
- FR-06.3 (I): Edit a completed invoice: adjust quantities, prices, discounts. Requires `sales.edit_invoice` permission. Stock ledger updated via delta entries. Audit log records old and new totals plus mandatory reason.
- FR-06.4 (I): Cannot edit a REFUNDED or CANCELLED sale.

### FR-07: Returns (E)
- FR-07.1: Sale return: specify quantity per line; cannot exceed originally sold quantity.
- FR-07.2: `restock=True` → returns units to batch stock (SALE_RETURN txn).
- FR-07.3: `restock=False` → damaged goods removed from circulation (DAMAGED txn).
- FR-07.4: Purchase return: reduces batch stock (PURCHASE_RETURN txn).
- FR-07.5: Manual stock adjustment: requires a non-empty reason; supports positive and negative delta.
- FR-07.6: Write-off expired batch: sets batch quantity to zero (EXPIRED txn); rejects non-expired batches.

### FR-08: Doctor Fee Management (I)
- FR-08.1: Record a standalone doctor fee (date, name, amount, payment method, patient reference, notes).
- FR-08.2: Doctor fees are stored in a separate table; they do not affect medicine sales totals or stock.
- FR-08.3: List and filter fees by date range and doctor name.
- FR-08.4: Daily collection summary: total collected, per-doctor breakdown, full entry list.
- FR-08.5: Correct a fee (updates fields, sets status=CORRECTED, audits old/new + reason).
- FR-08.6: Void a fee (sets status=VOIDED, excluded from totals, audited with reason).
- FR-08.7: Three permission keys: `doctor_fees.view`, `doctor_fees.record`, `doctor_fees.correct`.

### FR-09: Purchase Orders (I)
- FR-09.1: Create a DRAFT PO with supplier and line items.
- FR-09.2: Approve a DRAFT PO (transitions to APPROVED).
- FR-09.3: Cancel a DRAFT or APPROVED PO.
- FR-09.4: Receive goods against an APPROVED or PARTIALLY_RECEIVED PO; delegates to `purchase_service.record_purchase()` for stock entry.
- FR-09.5: Status transitions: DRAFT → APPROVED → PARTIALLY_RECEIVED / COMPLETED / CANCELLED.

### FR-10: Cashier Shifts (I)
- FR-10.1: Open a shift with opening cash amount.
- FR-10.2: Only one open shift per cashier at a time.
- FR-10.3: Close a shift with actual closing cash; system computes expected closing cash and variance.
- FR-10.4: Variance = actual − (opening + cash sales − cash expenses).

### FR-11: Smart Inventory Intelligence (E)
- FR-11.1: Reorder suggestions based on average daily sales, lead time, and safety stock.
- FR-11.2: Expiry risk report with financial waste estimates and risk levels.
- FR-11.3: Dead stock report (medicines with non-zero stock but no sales in N days).
- FR-11.4: ABC classification by revenue contribution.
- FR-11.5: Inventory turnover ratio with annualized figure.
- FR-11.6: Demand forecast using Holt's double exponential smoothing (≥14 data points) or flat ADS fallback. Returns confidence level and explanation. Read-only — never creates a purchase.

### FR-12: Reports and Dashboard (E)
- FR-12.1: Sales and profit report: revenue, COGS, gross profit, expenses, net profit, discounts — filtered by date range, with returns and discounts correctly netted.
- FR-12.2: Best-selling medicines report.
- FR-12.3: Stock valuation report (cost and retail value of current stock).
- FR-12.4: Month-close snapshot (cached, recomputable).
- FR-12.5: Admin dashboard: KPIs for medicines, stock, sales by period, expiry alerts, intelligence summary.

### FR-13: Excel Import/Export (E)
- FR-13.1: Import medicines from Excel with column mapping, row-level validation, and preview before commit.
- FR-13.2: Export data to Excel.

### FR-14: PDF Invoices (E)
- FR-14.1: Generate PDF invoice from a completed sale.
- FR-14.2: Invoice includes pharmacy name, items, prices, discount, total.

### FR-15: Settings (E)
- FR-15.1: Configure pharmacy name, currency, discount cap, session timeout, low-stock threshold, expiry warning days.
- FR-15.2: Settings stored in `application_settings` table as key/value pairs.

### FR-16: Backup and Restore (E)
- FR-16.1: Create a consistent SQLite backup using the SQLite backup API.
- FR-16.2: Auto-rotate backups (default retention: 14).
- FR-16.3: Restore: validate the file, make a safety backup of the current DB, swap the file, clear WAL/SHM sidecars.

### FR-17: Audit Log (E)
- FR-17.1: Every sensitive action writes an `AuditLog` row in the same DB transaction.
- FR-17.2: Fields: `user_id`, `action`, `entity`, `entity_id`, `old_value` (JSON), `new_value` (JSON), `created_at`.
- FR-17.3: Admin-only view via `audit_log.view` permission.

---

## 5. Business Rules Summary

- Discount cap: configurable (default 20%). Requires `sales.discount` permission.
- Expiry override: requires settings flag + `sales.override_expired` permission + explicit caller flag.
- Stock quantity never negative (enforced in service layer before DB constraint).
- Backup before every restore (non-bypassable).
- Admin cannot deactivate themselves.
- Minimum password length: 8 characters.
- Doctor fee amount must be > 0 and finite.
- Doctor fee date cannot be in the future.

---

## 6. Non-Functional Requirements

| Requirement | Target |
|---|---|
| Offline operation | 100% — no network calls at runtime |
| Platform | Windows 10/11, 64-bit |
| Database | SQLite, single file, WAL mode |
| Single user per process | One logged-in user at a time |
| Session security | Idle timeout (configurable), bcrypt passwords |
| Data integrity | All writes transactional; stock never negative |
| Backup | SQLite API backup (consistent), WAL cleared on restore |
| Deployment | PyInstaller `--onedir` bundle; migrations run on first launch |
| Test isolation | Disposable temp SQLite DB, no shared state between tests |

---

## 7. Out of Scope

- Multi-user concurrent access or network server mode.
- Patient medical records, prescriptions, or diagnosis assistance.
- Automated purchase creation (forecasting is advisory only).
- Cloud sync or remote backup.
- Barcode printing hardware integration.
- Tax calculation (tax_total column exists but is always 0).

---

## 8. Open Questions

1. Should doctor fee revenue appear as a separate line in `sales_and_profit_report()`, or remain only in the Doctor Fees page?
2. Should the `ForecastPage` be included in the UI smoke tests?
3. Is `INVOICE_EDITED` (actual code) the correct audit action name, or should it be `INVOICE_CORRECTED` (as some documents say)?
4. Should `settings.app_version` be updated to `"2.2"` and shown in a UI About screen?
5. Should the monthly close snapshot include doctor fee revenue?
6. Are cashier shifts expected to gate actual sales (e.g. require an open shift before a sale can proceed)?
