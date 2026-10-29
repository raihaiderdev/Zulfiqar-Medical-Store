# Requirements Document

## Introduction

This spec covers three work streams on the existing Zulfiqar Medical Store pharmacy management application: six targeted bug fixes, an AI-assisted inventory forecasting feature, and a Doctor Fee management feature. The application is an offline-first Python/PySide6/SQLite desktop application with service-layer business rules, role-based permissions, a full audit log, and batch-level FEFO inventory.

All changes must preserve existing functionality. The 105 existing tests must continue to pass. No external API calls or cloud services are introduced.

## Requirements

### 1. Expired-Stock Clearance Authorization

**1.1** The system MUST add a dedicated permission key `sales.override_expired` to `app/permissions/keys.py` under `GRANTABLE_PERMISSIONS` with description "Sell expired batches under an authorized clearance override (admin-enabled feature)".

**1.2** `complete_sale()` in `app/services/sales_service.py` MUST check `current_session.has_permission("sales.override_expired")` before allowing `allow_expired_override=True` to take effect. If the user lacks this permission, an `AuthorizationError` MUST be raised even when `settings.expiry_clearance_override_enabled` is `True` and `allow_expired_override=True` is passed.

**1.3** The override MUST remain disabled by default (`allow_expired_override=False`). A call to `complete_sale()` without the parameter MUST behave identically to the current behavior (expired batches blocked).

**1.4** The FEFO auto-allocation path (where no `batch_id` is supplied) MUST NEVER allocate expired batches regardless of the override flag or permission.

**1.5** When an expired batch is sold under an authorized override, the system MUST emit a dedicated audit event with `action="EXPIRED_STOCK_CLEARANCE"` and `new_value` containing at minimum: `batch_id`, `batch_number`, `quantity`, `reason`, `sale_id`, `user_id`.

**1.6** A new Alembic data migration MUST seed the `sales.override_expired` permission row idempotently, following the existing migration pattern used in `b2c3d4e5f6a7_add_stock_intelligence_permission.py`.

**Acceptance criteria:**
- Expired batch sale without override flag → `ValidationError` (unchanged behavior)
- Expired batch sale with `allow_expired_override=True` but user lacks `sales.override_expired` → `AuthorizationError`
- Expired batch sale with `allow_expired_override=True`, `sales.override_expired` permission granted, and `settings.expiry_clearance_override_enabled=True` → sale succeeds and audit log contains `"EXPIRED_STOCK_CLEARANCE"` record with all required fields
- FEFO auto-allocation with override flag → expired batches are still excluded

### 2. Negative and Non-Finite Payment Values

**2.1** `complete_sale()` MUST reject `amount_paid < 0` with `ValidationError("Amount paid cannot be negative.")`.

**2.2** `complete_sale()` MUST reject non-finite values (`math.isnan()` or `math.isinf()`) for `amount_paid`, `discount_total`, and per-line `line_discount`. The error message MUST identify the field name: `ValidationError("Invalid numeric value: <field> must be a finite number.")`.

**2.3** All numeric validation checks MUST occur before any DB writes.

**2.4** `change_due` MUST always be stored as `max(0.0, amount_paid - total)` and MUST be a finite, non-negative value.

**Acceptance criteria:**
- `amount_paid = -1` → `ValidationError`
- `amount_paid = float('nan')` → `ValidationError`
- `amount_paid = float('inf')` → `ValidationError`
- `discount_total = float('nan')` → `ValidationError`
- `line_discount = float('inf')` → `ValidationError`
- Valid sale with `amount_paid = 0` (credit/tab) → accepted (change_due = 0)
- Valid sale with `amount_paid > total` → `change_due = amount_paid - total`

### 3. Purchase Validation

**3.1** `record_purchase()` in `app/services/purchase_service.py` MUST validate each purchase line's `medicine_id` by querying the Medicine table. If not found, raise `NotFoundError(f"Medicine {medicine_id} not found.")`. If found but `medicine.is_active == False`, raise `ValidationError(f"Medicine '{medicine.name}' is inactive and cannot be purchased.")`.

**3.2** `record_purchase()` MUST validate that `batch_number` is a non-empty string. If empty or missing, raise `ValidationError("Batch number cannot be empty.")`.

**3.3** For **new** batches (batch does not yet exist in the DB), `record_purchase()` MUST validate that `expiry_date` is in the future (strictly `> date.today()`). If not, raise `ValidationError(f"Expiry date {expiry_date} must be in the future for a new batch.")`.

**3.4** For **existing batch top-ups** (batch already exists), if the caller provides an `expiry_date` that differs from the stored batch expiry, the system MUST raise `ValidationError(f"Expiry date mismatch for batch '{batch_number}': stored {stored_expiry}, received {received_expiry}. Create a separate batch for a different lot.")`. The stored expiry date MUST NOT be silently changed.

**3.5** `record_purchase()` MUST validate that `purchase_price` and `selling_price` are finite numbers (`math.isfinite()`). Raise `ValidationError("Invalid numeric value: <field> must be a finite number.")`.

**3.6** `record_purchase()` MUST validate that the supplier is active. If `supplier.is_active == False`, raise `ValidationError(f"Supplier '{supplier.name}' is inactive and cannot accept new purchases.")`. The `Supplier` model already has an `is_active` field (confirmed in `app/models/party.py`).

**Acceptance criteria:**
- Non-existent `medicine_id` → `NotFoundError`
- Inactive medicine → `ValidationError`
- Empty `batch_number` → `ValidationError`
- `expiry_date = date.today()` for new batch → `ValidationError`
- `expiry_date` in the past for new batch → `ValidationError`
- Expiry date mismatch on existing batch top-up → `ValidationError`; stored expiry unchanged
- `purchase_price = float('nan')` → `ValidationError`
- Inactive supplier → `ValidationError`
- Valid purchase with all correct inputs → succeeds

### 4. Stale POS Stock Error Messages

**4.1** `allocate_fefo()` in `app/services/sales_service.py` MUST receive the medicine name (or look it up from the session) and include it in the insufficient-stock error message: `"Insufficient stock for '{medicine_name}' (ID {medicine_id}): requested {quantity}, only {available} available. Stock may have changed — please refresh your cart."`.

**4.2** The service-layer stock revalidation MUST NOT be weakened. The service remains the final authority on stock availability.

**4.3** In `app/ui/sales/pos_page.py`, when `complete_sale()` raises an error containing the phrase `"please refresh your cart"`, the UI MUST show a dialog with title "Stock Changed" and a message that appends: `"\n\nPlease clear the cart and rebuild it to see current stock levels."`. Otherwise, the existing `QMessageBox.critical("Sale failed", ...)` behavior is preserved.

**Acceptance criteria:**
- Service raises `ValidationError` with medicine name and refresh prompt when stock is insufficient
- POS UI shows "Stock Changed" dialog title when the service error contains the refresh sentinel
- Direct service-layer test: reducing batch qty to 0 after cart build and then calling `complete_sale()` raises `ValidationError` with the expected message
- FEFO allocation still raises immediately for insufficient stock without any weakened check

### 5. Invoice Correction Auditability

**5.1** Inspect the existing invoice-edit flow (if any) triggered by `sales.edit_invoice` permission. Any function that modifies a completed sale's totals, discounts, or line items MUST produce an audit record with `action="INVOICE_CORRECTED"`, `old_value` containing the pre-edit values, `new_value` containing the post-edit values and `reason` field, `user_id`, and `entity="sales"`.

**5.2** Stock ledger changes from invoice corrections MUST use additive reversal entries (`StockTxnType.ADJUSTMENT_OUT` or `ADJUSTMENT_IN`) and MUST NOT destructively overwrite the original `SALE` ledger row.

**5.3** If the existing code already satisfies 5.1–5.2, requirements.md MUST document this as "already compliant" so future developers know the audit trail is intentional.

**Acceptance criteria:**
- If invoice editing exists: correction produces `INVOICE_CORRECTED` audit record with old/new/reason
- If invoice editing does not exist as a service function: requirements document that `sales.edit_invoice` permission exists but no correction service is implemented yet (no regression introduced)
- No existing SALE ledger rows are destructively overwritten

### 6. Documentation Accuracy

**6.1** `README.md` MUST be updated to reflect the actual test count of 105 (including 38 Phase 1 intelligence tests and 8 UI smoke tests).

**6.2** `README.md` MUST add feature bullets for Phase 1 Smart Inventory Intelligence (reorder suggestions, expiry risk, dead stock, ABC classification, inventory turnover) and Phase 2 (Purchase Orders lifecycle, Cashier Shifts with cash reconciliation).

**6.3** Only demonstrably stale claims MUST be updated. No invented functionality or coverage MUST be added.

**Acceptance criteria:**
- README test count matches the actual pytest output
- Phase 1 and Phase 2 features are listed in the Features section
- README does not claim features that are not implemented

### 7. AI-Assisted Inventory Forecasting

**7.1** A new function `get_demand_forecast(medicine_id, horizon_days=30, analysis_days=90)` MUST be added to `app/services/inventory_intelligence_service.py`. It MUST:
- Require the `stock.intelligence` permission (via `@require_permission`).
- Use Holt's double exponential smoothing (α=0.3, β=0.1, configurable) when ≥14 data points (days with sales records) exist in the analysis window.
- Fall back to flat ADS when < 14 data points exist; return `forecast_method="flat_average"`.
- Return `forecast_method="insufficient_history"` and `suggested_qty=0` when zero sales records exist.
- Account for near-expiry stock: if ≥50% of sellable stock expires before the forecast horizon end, set `expiry_risk_flag=True` and reduce `effective_available` to only count non-expiring stock.
- Return a `confidence` field: `"high"` (≥60 data points), `"medium"` (14–59 data points), `"low"` (< 14 data points).
- Return a human-readable `explanation` string describing the method and key inputs.
- NEVER write a purchase, stock change, or any DB row. It is read-only.

**7.2** `get_demand_forecast()` MUST return a dict with at minimum: `medicine_id`, `name`, `forecast_method`, `horizon_days`, `estimated_demand`, `effective_available`, `suggested_qty`, `days_until_stockout`, `expiry_risk_flag`, `confidence`, `explanation`.

**7.3** A `ForecastPage` widget MUST be added to `app/ui/inventory/forecast_page.py`. It MUST:
- Follow the existing page widget pattern (QWidget subclass, QVBoxLayout, QTableWidget, QThread worker) matching the style of `ReorderPage` in `app/ui/inventory/reorder_page.py`.
- Display a configuration row: `horizon_days` spin box (range 7–180, default 30) and `analysis_days` spin box (range 30–365, default 90), and a "Calculate" button.
- Show a header notice (non-editable label): *"These are estimates only. All purchases must be reviewed and approved by an authorized user."*
- Display an empty state when no calculation has been run.
- Display a loading indicator while the background worker is running.
- Display an error state (red label) if the service raises an exception.
- Show a table with columns: Medicine, Current Stock, Est. Demand, Days Until Stockout, Suggested Qty, Expiry Risk, Confidence, Explanation.
- Provide an "Initiate Purchase" button (or context action) per row that opens `CreatePODialog` from `app/ui/purchase_orders/purchase_orders_page.py` pre-filled with the medicine and `suggested_qty`. Staff MUST be able to edit the quantity before saving.
- Be gated by the `stock.intelligence` permission (UI entry point hidden or disabled for users without it).

**7.4** `ForecastPage` MUST be added to the main window navigation in `app/ui/main/main_window.py` under the Inventory section, consistent with how existing Phase 1 inventory pages are added.

**7.5** No Alembic migration is required for forecasting (all results are computed on-the-fly, not persisted).

**7.6** No external API calls MUST be made. All calculations MUST be local.

**7.7** The feature MUST NOT add symptom checking, diagnosis, prescribing, or treatment recommendations.

**Acceptance criteria:**
- `get_demand_forecast()` with no sales history → `forecast_method="insufficient_history"`, `suggested_qty=0`
- `get_demand_forecast()` with < 14 data points → `forecast_method="flat_average"`
- `get_demand_forecast()` with ≥ 14 data points → `forecast_method="exponential_smoothing"`
- Near-expiry stock (≥50% expiring before horizon) → `expiry_risk_flag=True`
- User without `stock.intelligence` → `AuthorizationError`
- `get_demand_forecast()` never writes any DB row
- `ForecastPage` shows empty state on load, loading state during calculation, table on completion
- "Initiate Purchase" pre-fills `CreatePODialog` with medicine and suggested qty; staff can change qty
- Forecast UI is accessible from the main navigation for authorized users

### 8. Tests

**8.1** New test file `tests/test_bug_fixes.py` MUST be added covering the acceptance criteria for Requirements 1–5:
- Expired stock blocked by default
- Unauthorized expired-stock override → `AuthorizationError`
- Authorized override audited with all required fields
- Negative `amount_paid` → `ValidationError`
- NaN `amount_paid` → `ValidationError`
- Infinite `discount_total` → `ValidationError`
- Invalid `medicine_id` in purchase → `NotFoundError`
- Inactive medicine → `ValidationError`
- Empty `batch_number` → `ValidationError`
- Past `expiry_date` for new batch → `ValidationError`
- Expiry date mismatch on top-up → `ValidationError`
- Stale-stock scenario (batch depleted between cart build and sale) → `ValidationError` with refresh prompt
- Invoice correction audit (if feature exists) preserves old/new values

**8.2** New test file `tests/test_forecasting.py` MUST be added covering Requirement 7:
- No history → `insufficient_history`
- Sparse history → `flat_average`
- Sufficient history → `exponential_smoothing`
- Zero stock + demand → `suggested_qty > 0`
- Near-expiry batch → `expiry_risk_flag=True`
- No permission → `AuthorizationError`
- Read-only: no DB rows written by forecast function

**8.3** All 105 existing tests MUST continue to pass after changes. New test files (`test_bug_fixes.py`, `test_forecasting.py`, `test_doctor_fees.py`) MUST pass alongside the existing suite.

**8.4** Tests MUST use the existing `conftest.py` fixtures (disposable SQLite file, seeded users with `admin` session, service-layer calls only — no UI instantiation except in `test_ui_smoke.py`).

### 9. Doctor Fee Management

**9.1** A new SQLAlchemy model `DoctorFee` MUST be added to `app/models/doctor_fee.py` following the existing model conventions (`Base`, `IDMixin`, `TimestampMixin`, `Mapped`/`mapped_column` typing, `MONEY = Numeric(12, 2)` for amounts). The model MUST store:
- `fee_date` (Date, nullable=False, indexed) — the date the fee was earned.
- `doctor_name` (String(180), nullable=False, indexed) — free-text doctor name (no doctor entity table required).
- `amount` (MONEY, nullable=False) — the fee amount.
- `payment_method` (String(32), nullable=True) — optional: "CASH", "CARD", "ONLINE", or any user-entered method string.
- `patient_reference` (String(120), nullable=True) — optional, non-identifying reference (e.g. a token or initials). MUST NOT be a required field and MUST NOT store full patient names or contact details by default.
- `notes` (String(500), nullable=True) — optional free-text notes.
- `created_by_user_id` (ForeignKey to `users.id`, ondelete="SET NULL", nullable=True).
- `status` (Enum or String, nullable=False, default `"ACTIVE"`) — values: `"ACTIVE"`, `"CORRECTED"`, `"VOIDED"`.

The model MUST be registered in `app/models/__init__.py` so Alembic autogenerate detects it.

**9.2** A new Alembic migration MUST create the `doctor_fees` table and seed the three new permission rows (see 9.3). The migration MUST follow the existing chain (`c3d4e5f6a7b8` is the current head) and use `INSERT OR IGNORE` for permission seeding, matching the pattern in existing migrations.

**9.3** Three new permission keys MUST be added to `app/permissions/keys.py` under `GRANTABLE_PERMISSIONS`:
- `doctor_fees.view` — "View doctor fee records and summaries"
- `doctor_fees.record` — "Record new doctor fee entries"
- `doctor_fees.correct` — "Correct or void a doctor fee entry"

**9.4** A new service module `app/services/doctor_fee_service.py` MUST implement:
- `record_doctor_fee(*, fee_date, doctor_name, amount, payment_method=None, patient_reference=None, notes=None) -> int` — requires `doctor_fees.record` permission. Validates: `doctor_name` non-empty, `amount` finite and ≥ 0, `fee_date` not in the future. Creates a `DoctorFee` row with `status="ACTIVE"` and emits an audit record with `action="DOCTOR_FEE_RECORDED"`.
- `list_doctor_fees(*, date_from=None, date_to=None, doctor_name=None, status=None, limit=200) -> list[dict]` — requires `doctor_fees.view`. Returns dicts with `fee_id`, `fee_date`, `doctor_name`, `amount`, `payment_method`, `patient_reference`, `notes`, `status`, `created_by_user_id`.
- `get_doctor_fee_summary(*, date_from=None, date_to=None, doctor_name=None) -> dict` — requires `doctor_fees.view`. Returns `{"total_fees": float, "fee_count": int, "by_doctor": [{"doctor_name": str, "total": float, "count": int}], "by_payment_method": [{"method": str, "total": float, "count": int}]}`. Only counts `status="ACTIVE"` fees (voided/corrected originals are excluded from totals).
- `correct_doctor_fee(*, fee_id, new_amount=None, new_payment_method=None, new_notes=None, reason) -> int` — requires `doctor_fees.correct`. Updates the existing fee row's fields, sets `status="CORRECTED"`, and emits an audit record with `action="DOCTOR_FEE_CORRECTED"`, `old_value` (original amount/method/notes), `new_value` (new values + reason). Returns the fee_id.
- `void_doctor_fee(*, fee_id, reason) -> None` — requires `doctor_fees.correct`. Sets `status="VOIDED"` and emits an audit record with `action="DOCTOR_FEE_VOIDED"`, `old_value` (original fee details), `new_value={"reason": reason}`.

**9.5** All doctor fee service functions MUST use `session_scope()`, `audit_service.record()`, and the existing `ValidationError`/`NotFoundError`/`AuthorizationError` exception types from `app/utils/exceptions.py`.

**9.6** `amount` validation MUST reject: negative values (`ValidationError("Doctor fee amount cannot be negative.")`), non-finite values (`ValidationError("Doctor fee amount must be a finite number.")`), and zero (`ValidationError("Doctor fee amount must be greater than zero.")`).

**9.7** Doctor fees MUST be kept completely separate from medicine sales, purchases, stock, and medicine-sales tax/discount calculations. They MUST NOT be stored as fake `Sale` or `Expense` records. The `DoctorFee` model is a standalone entity with its own table.

**9.8** The report engine (`app/reports/report_engine.py`) MUST include a separate "Doctor Fees" revenue line in financial reports (e.g. the sales/profit report), clearly distinguishable from medicine sales revenue. The `PeriodFinancials` dataclass (or equivalent) MUST gain a `doctor_fee_revenue` field. Doctor fee totals MUST be filterable by date range and doctor name, matching the existing report parameters.

**9.9** The dashboard summary (`app/services/dashboard_service.py` or equivalent) MUST include a doctor fee total in its KPI set, displayed as a separate line from medicine sales revenue.

**9.10** A `DoctorFeesPage` widget MUST be added to `app/ui/doctor_fees/doctor_fees_page.py` following the existing page widget pattern (QWidget, QVBoxLayout, QTableWidget). It MUST provide:
- A date-range filter (two `QDateEdit` controls) and a doctor-name filter (`QLineEdit` or `QComboBox`).
- A "Record Fee" button (gated by `doctor_fees.record` permission) that opens a dialog with fields: date, doctor name, amount, payment method, patient reference (optional), notes (optional).
- A table showing fee records: Date, Doctor, Amount, Payment Method, Reference, Notes, Status.
- Clear totals at the bottom (total fees in the filtered range, count).
- "Correct" and "Void" action buttons per row (gated by `doctor_fees.correct` permission) that open a dialog requiring a reason.
- Empty state when no fees match the filter.
- Error state if the service raises an exception.

**9.11** `DoctorFeesPage` MUST be added to the main window navigation in `app/ui/main/main_window.py` as a top-level section or under an existing section, consistent with how other feature pages are added.

**9.12** The data export module (`app/exports/data_exporter.py`) MUST include doctor fees as a separate export sheet/section if it already exports sales and expenses, following the existing export format conventions.

**9.13 — Doctor fee on the POS bill (billing integration)**

The Sales/POS screen MUST allow a cashier to add a doctor fee to the current bill before completing the sale:

- A "Doctor Fee" section MUST be added to the POS screen (`app/ui/sales/pos_page.py`), visible below the cart or in the payment area. It MUST contain: a doctor-name field (free-text `QLineEdit` with placeholder "Doctor name"), a fee-amount field (`QLineEdit`, numeric), and an "Add to Bill" button.
- When the cashier fills in the doctor name and amount and clicks "Add to Bill", the fee is held in memory as part of the current sale context (not yet saved to DB).
- The POS bill total display MUST update to show: Medicine Subtotal, Doctor Fee, Discount, and Grand Total as separate lines so the cashier and patient can see the breakdown clearly.
- When `complete_sale()` is called, the cashier-entered doctor fee MUST be passed to the service layer. The sale completes atomically: the medicine `Sale` record is created as usual, AND a `DoctorFee` row is created in the same transaction with `fee_date = sale_date`, `doctor_name` from the POS input, `amount` from the POS input, and a `sale_reference` field linking it to the invoice number (see 9.13a).
- `complete_sale()` MUST accept an optional `doctor_fee: Optional[dict]` parameter (with keys `doctor_name`, `amount`, and optionally `payment_method`, `patient_reference`). When provided, it calls `record_doctor_fee()` logic inside the same `session_scope()` so both the sale and the fee are committed together or both roll back.
- The doctor fee amount MUST be shown as a separate line on the printed PDF invoice (it is NOT included in the medicine subtotal or discount calculation — it is an additional charge on top).
- If the doctor-name or fee-amount field is left blank when the sale is completed, the doctor fee MUST be silently ignored (not required). If a doctor name is entered but the amount is 0 or invalid, the UI MUST show a validation message before allowing the sale to proceed.
- The `DoctorFee.sale_reference` field (String(32), nullable=True) MUST store the invoice number of the associated sale. This field MUST be added to the `DoctorFee` model (9.1) so fees recorded via POS are traceable back to their invoice.

**9.14 — Daily doctor fee collection summary**

A dedicated **"Doctor Fee Collections"** view MUST be added to the `DoctorFeesPage` as a second tab or a clearly labelled section. It MUST show:

- A date picker (single date, defaults to today) and a "Show" button.
- A summary card for the selected date: total fees collected that day, count of fee entries, and a per-doctor breakdown (doctor name | count | total amount).
- A **daily breakdown table** with columns: Time Recorded, Doctor Name, Amount, Payment Method, Reference, Invoice No., Status.
- Rows filtered to `fee_date = selected_date` and `status = "ACTIVE"` (voided entries shown in a muted style but still listed so the cashier can see what was voided).
- A "Today" shortcut button that resets the date picker to today and refreshes immediately.
- Grand total row at the bottom of the table showing the sum of ACTIVE fees for the selected day.

**9.15** `get_daily_fee_collection(*, fee_date: date) -> dict` MUST be added to `app/services/doctor_fee_service.py`. It MUST:
- Require `doctor_fees.view` permission.
- Return `{"fee_date": str, "total_collected": float, "fee_count": int, "entries": list[dict], "by_doctor": list[dict]}` where `entries` are all fee rows for that date (all statuses) and `by_doctor` sums only ACTIVE fees per doctor.

**Acceptance criteria:**
- Recording a valid fee creates a `DoctorFee` row with `status="ACTIVE"` and an audit record with `action="DOCTOR_FEE_RECORDED"`.
- Recording a fee with `amount = -1` → `ValidationError`.
- Recording a fee with `amount = float('nan')` → `ValidationError`.
- Recording a fee with `amount = 0` → `ValidationError`.
- Recording a fee with empty `doctor_name` → `ValidationError`.
- Recording a fee with a future `fee_date` → `ValidationError`.
- User without `doctor_fees.record` → `AuthorizationError`.
- `list_doctor_fees()` with date range filter returns only fees in that range.
- `list_doctor_fees()` with `doctor_name` filter returns only fees for that doctor (case-insensitive partial match).
- `get_doctor_fee_summary()` returns correct totals excluding voided/corrected fees.
- `correct_doctor_fee()` updates the row, sets `status="CORRECTED"`, and audit record contains `old_value` and `new_value` with reason.
- `void_doctor_fee()` sets `status="VOIDED"` and audit record contains original values and reason.
- User without `doctor_fees.correct` cannot correct or void → `AuthorizationError`.
- Report engine includes a separate "Doctor Fees" revenue line distinguishable from medicine sales.
- Dashboard includes doctor fee total as a separate KPI.
- Doctor fees are NOT stored as `Sale` or `Expense` records.
- `DoctorFeesPage` UI shows empty, error, and populated states correctly.
- "Record Fee" dialog validates amount finite + positive, doctor name non-empty, date not future.
- POS "Doctor Fee" section adds the fee to the in-memory bill; bill total updates to show Medicine Subtotal + Doctor Fee + Discount = Grand Total.
- Completing a sale with a doctor fee creates both the `Sale` and `DoctorFee` rows atomically; rolling back one rolls back both.
- Doctor fee amount appears as a separate line on the printed PDF invoice and is NOT included in medicine subtotal or discount.
- Completing a sale with blank doctor-name/amount fields silently skips the fee (not required).
- `get_daily_fee_collection()` returns correct totals for the given date, counting only ACTIVE fees.
- Daily collection view shows per-doctor breakdown and grand total for the selected day.

### 10. Tests (Doctor Fees)

**10.1** New test file `tests/test_doctor_fees.py` MUST be added covering Requirement 9:
- Record a valid fee → returns fee_id, audit log contains `DOCTOR_FEE_RECORDED`.
- Record fee with negative amount → `ValidationError`.
- Record fee with NaN amount → `ValidationError`.
- Record fee with zero amount → `ValidationError`.
- Record fee with empty doctor_name → `ValidationError`.
- Record fee with future date → `ValidationError`.
- User without `doctor_fees.record` → `AuthorizationError`.
- `list_doctor_fees()` date range filter works.
- `list_doctor_fees()` doctor name filter works (case-insensitive partial match).
- `get_doctor_fee_summary()` totals exclude voided fees.
- `correct_doctor_fee()` → status becomes `CORRECTED`, audit has old/new values + reason.
- `void_doctor_fee()` → status becomes `VOIDED`, audit has original values + reason.
- User without `doctor_fees.correct` cannot correct or void → `AuthorizationError`.
- Doctor fees are stored in `doctor_fees` table, NOT in `sales` or `expenses` tables.
- Report engine includes doctor fee revenue as a separate line.
- `complete_sale()` with `doctor_fee={"doctor_name": "Dr. X", "amount": 200}` creates both a `Sale` and a `DoctorFee` row; the `DoctorFee.sale_reference` matches the invoice number.
- `complete_sale()` with invalid doctor fee amount raises `ValidationError` before any DB writes.
- `complete_sale()` with `doctor_fee=None` (no fee) creates only the `Sale` row (no `DoctorFee` row created).
- `get_daily_fee_collection(fee_date=today)` returns correct total and per-doctor breakdown counting only ACTIVE fees.
- `get_daily_fee_collection()` excludes VOIDED fees from totals.

## Glossary

- **FEFO**: First-Expiry-First-Out — stock allocation strategy that uses the soonest-expiring batch first.
- **ADS**: Average Daily Sales — units sold in a period divided by the number of days.
- **Holt's double exponential smoothing**: A time-series forecasting method that models both level and trend; used here to weight recent demand more heavily than older history.
- **Sellable stock**: Quantity across non-expired, active batches with quantity > 0.
- **Reorder point**: The stock level at which a reorder should be triggered: `ADS × lead_time_days + safety_stock_units`.
- **Expired-stock clearance**: The authorized sale of a past-expiry batch under a gated override (admin-enabled setting + dedicated permission).
- **Audit log**: Append-only record of every sensitive action, stored in the `audit_logs` table with actor, timestamp, entity, and before/after values.
- **Session context**: `current_session` — the service-layer object that carries the logged-in user's ID, role, and permission set.
- **ValidationError / NotFoundError / AuthorizationError**: The application's own exception types from `app/utils/exceptions.py`, used for user-facing error messages.
- **Doctor fee**: A consultation fee charged by a doctor affiliated with the pharmacy, recorded as a separate business transaction from medicine sales.
- **Fee status**: The lifecycle state of a doctor fee entry: `ACTIVE` (valid and counted in totals), `CORRECTED` (edited with audit trail), or `VOIDED` (cancelled with audit trail).
- **Patient reference**: An optional, non-identifying token (e.g. initials or a token number) associated with a fee entry. Not a required field and not used to store full patient identity.
- **POS billing integration**: The ability to add a doctor fee directly on the Sales/POS screen so it appears as a separate line on the same patient bill as their medicines.
- **Daily collection summary**: A date-filtered view of all doctor fees collected on a specific day, broken down by doctor, used by staff to reconcile cash at end of day.
