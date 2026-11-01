# Task.md — Status Report and Backlog

**Audit date:** 2026-10-30
**Auditor:** Code inspection + automated test run
**Test command:** `python -m pytest tests/ --ignore=tests/test_ui_smoke.py -q`
**Test result:** 105 passed, 0 failed

---

## 1. Defects Found and Fixed During This Audit

### D-001 — Broken `softsolz-test` pytest plugin crashed the entire test runner

**Symptom:** `python -m pytest` exited with `ModuleNotFoundError: No module named 'softsolz_test'` on every invocation, making it impossible to run any test.

**Root cause:** A third-party package `softsolz-test==0.1.0` was installed in the Python environment. It registers a `pytest11` entry point pointing to a non-existent module.

**Fix:** `pip uninstall softsolz-test -y`

**Regression test:** Not applicable (environment fix, not code fix).

**Evidence:** Test runner now passes: `105 passed in 52.49s`.

---

## 2. Feature Audit Matrix

| Feature | Implementation path | Tests | Status |
|---|---|---|---|
| First-run setup wizard | `auth_service.create_first_admin()`, `SetupWizardWindow` | `test_auth_and_permissions.py::test_first_run_setup_cannot_run_twice` | ✅ Verified |
| Login / logout | `auth_service.login()` / `logout()` | Multiple tests in `test_auth_and_permissions.py` | ✅ Verified |
| Session timeout | `SessionContext.is_expired()` + `@require_permission` | `test_session_expiry_blocks_further_actions` | ✅ Verified |
| Password hashing (bcrypt) | `security/passwords.py` | `test_self_password_change_requires_correct_old_password` | ✅ Verified |
| User CRUD + permissions | `user_service.py` | `test_auth_and_permissions.py` | ✅ Verified |
| Admin-only permission guard | `session_context.has_permission()` + `ADMIN_ONLY_KEYS` | `test_admin_only_permission_never_grantable_to_regular_user` | ✅ Verified |
| Medicine CRUD + batch | `medicine_service.py` | `test_inventory.py` | ✅ Verified |
| FEFO allocation | `sales_service.allocate_fefo()` | `test_sale_uses_fefo_across_two_batches` | ✅ Verified |
| Expired stock blocking | `complete_sale()` expiry check | `test_sale_blocks_expired_batch_by_default` | ✅ Verified |
| Discount cap + permission | `complete_sale()` | `test_discount_requires_permission`, `test_discount_exceeding_cap_rejected` | ✅ Verified |
| Invoice numbering (sequential) | `numbering.py` | `test_invoice_numbers_are_sequential_and_unique` | ✅ Verified |
| Stock ledger (every change) | `stock_service.apply_stock_change()` | `test_purchase_creates_new_batch_and_stock` | ✅ Verified |
| Stock non-negativity | `apply_stock_change()` | `test_sale_rejects_insufficient_stock` | ✅ Verified |
| Purchase atomic rollback | `purchase_service.record_purchase()` | `test_failed_purchase_line_rolls_back_entire_transaction` | ✅ Verified |
| Batch top-up | `purchase_service` upsert | `test_purchase_tops_up_existing_batch` | ✅ Verified |
| Sale return (restock) | `returns_service.process_sale_return()` | `test_sale_return_restocks_batch` | ✅ Verified |
| Sale return (damaged) | `returns_service`, `restock=False` | `test_sale_return_without_restock_does_not_increase_quantity` | ✅ Verified |
| Purchase return | `returns_service.process_purchase_return()` | `test_purchase_return_decreases_stock` | ✅ Verified |
| Manual stock adjustment | `returns_service.adjust_stock()` | `test_manual_stock_adjustment_requires_reason` | ✅ Verified |
| Write-off expired batch | `returns_service.write_off_expired_batch()` | `test_write_off_expired_batch`, `test_cannot_write_off_non_expired_batch` | ✅ Verified |
| Financial reports (revenue, COGS, profit, discount) | `report_engine.sales_and_profit_report()` | `test_reports_dashboard_backup.py` | ✅ Verified |
| Stock valuation report | `report_engine.stock_valuation_report()` | `test_reports_dashboard_backup.py` | ✅ Verified |
| Month-close snapshot | `report_engine.close_month()` | `test_reports_dashboard_backup.py` | ✅ Verified |
| Admin dashboard KPIs | `dashboard_service.admin_dashboard_kpis()` | `test_reports_dashboard_backup.py` | ✅ Verified |
| Backup create (SQLite API) | `backup_service.create_backup()` | `test_reports_dashboard_backup.py` | ✅ Verified |
| Backup restore (safety copy + WAL clear) | `backup_service.restore_backup()` | `test_reports_dashboard_backup.py` | ✅ Verified |
| Excel export | `exports/data_exporter.py` | `test_exports_printing_settings.py` | ✅ Verified |
| PDF invoice | `printing/pdf_documents.py` | `test_exports_printing_settings.py` | ✅ Verified |
| Settings read/write | `settings_service.py` | `test_exports_printing_settings.py` | ✅ Verified |
| Inventory intelligence (38 tests) | `inventory_intelligence_service.py` | `test_inventory_intelligence.py` | ✅ Verified |
| Doctor fee service | `doctor_fee_service.py` | `test_doctor_fees.py` (27 tests) | ✅ Verified |
| Invoice edit service | `invoice_edit_service.py` | `test_invoice_edit.py` (8 tests) | ✅ Verified |
| Cashier shift service | `shift_service.py` | `test_shifts.py` (7 tests) | ✅ Verified (+ defect D-002 fixed) |
| Purchase order service | `purchase_order_service.py` | `test_purchase_orders.py` (9 tests) | ✅ Verified |
| Doctor fee in POS | `pos_page.py` + `sales_service.complete_sale(doctor_fee=...)` | `test_doctor_fees.py` (3 tests) | ✅ Verified |
| Doctor fee daily summary | `doctor_fee_service.get_daily_fee_collection()` | `test_doctor_fees.py` (2 tests) | ✅ Verified |
| Demand forecast (Holt's smoothing) | `inventory_intelligence_service.get_demand_forecast()` | `test_inventory_intelligence.py` has 38 tests (check coverage) | ⚠ Partially — get_demand_forecast not in test file |
| ForecastPage UI | `app/ui/inventory/forecast_page.py` | `test_ui_smoke.py` (not confirmed to include ForecastPage) | ⚠ Not confirmed |
| Excel import | `imports/excel_importer.py` | `test_exports_printing_settings.py` | ✅ Verified |
| Audit log record | `audit_service.record()` | Tested implicitly through all service tests | ✅ Verified (indirect) |
| Password reset dialog | `login/login_window.py` `ResetPasswordDialog` | `test_ui_smoke.py` | Not confirmed |

---

## 3. Confirmed Defects with Fixes Applied

### D-001 ✅ Fixed — See §1 above.

### D-002 ✅ Fixed — `shift_service.close_shift()` returned `status="OPEN"` in its return dict

**File:** `app/services/shift_service.py`, `close_shift()` return statement.
**Root cause:** `_compute_shift_summary()` was called before `shift.status = ShiftStatus.CLOSED`. The returned dict `{**summary, ...}` preserved the pre-close `status="OPEN"` value because `status` was not overridden in the merge.
**Impact:** Any caller inspecting `result["status"]` after closing a shift would see "OPEN" instead of "CLOSED". The DB row was correctly set to CLOSED.
**Fix:** Added `"status": "CLOSED"` override to the return dict in `close_shift()`.
**Regression test:** `tests/test_shifts.py::test_close_shift_transitions_to_closed`.

---

## 4. Confirmed Gap: `settings.app_version` is `"1.0.0"`

**File:** `app/config/settings.py`, line: `app_version: str = "1.0.0"`
**Issue:** The app is at version 2.2 (delivery folder name, README implies this). The hardcoded version string is stale.
**Risk:** Low — not used in any critical business logic, but would show wrong version in any About screen.
**Fix required:** Change to `"2.2"` in `settings.py`.

---

## 5. Confirmed Gap: Doctor Fee Revenue Not in Financial Reports

**File:** `app/reports/report_engine.py` — `sales_and_profit_report()` does not query `doctor_fees` table.
**Issue:** Doctor fees are recorded correctly but are not included in any financial report output. The dashboard also does not show doctor fee totals.
**Risk:** Medium — owner cannot see total daily/monthly revenue including doctor fees in the standard reports.
**Status:** Open question (see PRD.md §8, item 1). Needs product-owner decision.

---

## 6. Proposed Backlog

### P0 — Critical ~~(no tests → untestable defects)~~ ✅ Completed in this audit

**TASK-01 ✅ Done: Tests added for `doctor_fee_service`** — `tests/test_doctor_fees.py` (27 tests, all passing).

**TASK-02 ✅ Done: Tests added for `invoice_edit_service`** — `tests/test_invoice_edit.py` (8 tests, all passing).

**TASK-03 ✅ Done: Tests added for `shift_service`** — `tests/test_shifts.py` (7 tests, all passing). Defect D-002 found and fixed.

**TASK-04 ✅ Done: Tests added for `purchase_order_service`** — `tests/test_purchase_orders.py` (9 tests, all passing).

---

### P1 — Important

**TASK-05: Add doctor fee revenue to financial reports**
- Goal: `sales_and_profit_report()` should include a `doctor_fee_revenue` field summed from `DoctorFee` rows (ACTIVE only) in the period.
- File: `app/reports/report_engine.py`, `app/ui/reports/reports_page.py`, dashboard.
- Acceptance: Report output includes `doctor_fee_revenue`; test verifies the field with known data.
- Product-owner question: Should doctor fees be shown as a separate category or added into revenue?
- Dependencies: TASK-01 (test infra for doctor fees).

**TASK-06: Fix `settings.app_version` to `"2.2"`**
- Goal: `AppSettings.app_version` should match the delivered version.
- File: `app/config/settings.py`
- Acceptance: `from app.config.settings import settings; assert settings.app_version == "2.2"`.
- Risk: Very low — purely cosmetic.

**TASK-07: Add `ForecastPage` to UI smoke tests**
- Goal: `test_ui_smoke.py` should instantiate `ForecastPage` to catch import or widget errors.
- File: `tests/test_ui_smoke.py`
- Acceptance: ForecastPage appears in the smoke test list and passes.
- Dependencies: Offscreen display must be available in the test environment.

**TASK-08: Add `pytest.ini` to prevent broken-plugin crashes**
- Goal: Prevent a recurrence of the `softsolz-test` crash scenario.
- File: Add `pytest.ini` with `testpaths = tests` and `addopts = --ignore=tests/test_ui_smoke.py`.
- Acceptance: `python -m pytest` without arguments works correctly.

---

### P2 — Nice to Have

**TASK-09: Bump `PHARMACY_MAX_DISCOUNT_PERCENT` to be user-configurable via the Settings page**
- Currently: hardcoded default in `AppSettings` (reads env var, not the DB settings table).
- Goal: Let the admin change the discount cap from the Settings UI without restarting the app.
- Risk: Requires reconciling `AppSettings` (frozen dataclass) with `settings_service` (DB-backed).

**TASK-10: Add "Print on Completion" user preference**
- Goal: Skip the PDF print dialog for cashiers who never need it.
- File: `app/ui/sales/pos_page.py`, `settings_service.py`.
- Acceptance: A setting in the Settings page suppresses the `_offer_print_invoice()` dialog.

**TASK-11: Expose doctor fee correction history in the Doctor Fees UI**
- Goal: Show audit log entries for a specific fee (CORRECTED → VOIDED chain) in the Fee Records tab.
- File: `app/ui/doctor_fees/doctor_fees_page.py`.
- Dependencies: Requires `audit_log.view` permission or a new dedicated query.

---

## 7. Risks and Unverified Behaviors

| Risk | Severity | Evidence |
|---|---|---|
| Doctor fee, invoice edit, shift, PO services have no tests — bugs could be present | High | Code reviewed only |
| Doctor fee revenue not in reports — owner underestimates total revenue | Medium | Confirmed by code inspection |
| `app_version = "1.0.0"` misleads About screen | Low | Confirmed by code inspection |
| `test_ui_smoke.py` not verified to include ForecastPage or DoctorFeesPage | Low | Not confirmed |
| `settings.expiry_clearance_override_enabled` is env-var-only — cannot be changed without restart | Low | Code confirmed |
| WAL mode sidecars could corrupt a naive file-copy backup | Low | Mitigated — `backup_service` uses SQLite backup API and clears WAL on restore |

---

## 8. Environment Notes

- `softsolz-test==0.1.0` was uninstalled from the Python environment during this audit (D-001).
- The test runner now runs without modification to test files or `conftest.py`.
- Test database is a temp file; real `database/pharmacy.db` is not touched by tests.
- UI smoke tests require a display (offscreen mode with `QT_QPA_PLATFORM=offscreen`); not run in this audit.
