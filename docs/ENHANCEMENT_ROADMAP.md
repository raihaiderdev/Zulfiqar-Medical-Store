# Enhancement Roadmap

## Phase Status

| Phase | Title | Status |
|-------|-------|--------|
| Phase 0 | Codebase Audit | ✅ Complete |
| Phase 1 | Smart Inventory Intelligence | ✅ Complete |
| Phase 2 | Purchasing & Financial Management | ✅ Complete (POs + Shifts) |
| Phase 3 | Offline AI Copilot | ⏳ Pending |
| Phase 4 | AI-Powered Excel Import | ⏳ Pending |
| Phase 5 | Natural Language Navigation | ⏳ Pending |
| Phase 6 | Voice Assistant (Optional) | ⏳ Pending |
| Phase 7 | Advanced UX | ⏳ Pending |
| Phase 8 | Multi-Branch Readiness | ⏳ Pending |

---

## Phase 1 — Smart Inventory Intelligence

### 1.1 Smart Reorder Suggestions

**Service**: `app/services/inventory_intelligence_service.py`

**Formulas** (deterministic, documented):
```
Average Daily Sales (ADS) = total_units_sold / analysis_days

Days of Stock Remaining = sellable_stock / ADS  (if ADS > 0)

Reorder Point = ADS × lead_time_days + safety_stock

Suggested Order Quantity = max(0, target_stock - available_stock - incoming_stock)

target_stock = ADS × (lead_time_days + review_period_days) + safety_stock
```

**Sellable stock** = sum of quantities from non-expired, active batches only.

**Inputs**:
- `analysis_period_days`: configurable (default 90)
- `lead_time_days`: per-supplier or per-medicine (default 7)
- `safety_stock_days`: configurable (default 14)
- `review_period_days`: configurable (default 7)

**UI**: `app/ui/inventory/reorder_page.py`
- Table: Medicine | Stock | ADS | Days Left | Lead Time | Reorder Point | Suggested Qty | Action
- Filter: All | Below Reorder Point | Critical (≤ 7 days)
- "Generate Draft PO" button (Phase 2 integration)

### 1.2 Expiry Risk Intelligence

**Enhancements to existing `expiry_report()`**:
- Add `purchase_value` (batch.quantity × batch.purchase_price)
- Add `avg_daily_sales` for the medicine
- Add `estimated_waste_units` = max(0, quantity - ADS × days_until_expiry)
- Add `estimated_waste_value` = estimated_waste_units × purchase_price
- Add risk classification: LOW / MODERATE / HIGH

**Risk Rules**:
- HIGH: estimated_waste_value > 1000 PKR OR days_until_expiry ≤ 30
- MODERATE: estimated_waste_value > 200 PKR OR days_until_expiry ≤ 90
- LOW: otherwise

### 1.3 Dead Stock Detection

**Criteria**: No sale of a medicine within configurable `dead_stock_days` (default 90).

**Output per item**:
- Medicine name, last sale date, days without sales
- Current stock, stock valuation, expiry date
- Suggested action: "Review for return/write-off"

### 1.4 Inventory Analytics

**ABC Classification**:
- A: top 70% of revenue (typically ~20% of items)
- B: next 20% of revenue
- C: bottom 10% of revenue

**Inventory Turnover**:
```
Turnover = COGS for period / Average Inventory Value
```

**Dashboard card additions**:
- Stock turnover ratio
- Dead stock count
- Items needing reorder

---

## Phase 2 — Purchasing & Financial Management

### New Models Required
- `PurchaseOrder` (draft → approved → partially_received → completed)
- `PurchaseOrderItem`
- `CashierShift` (open/close, opening_cash, closing_cash)
- `ShiftTransaction`

### New Permission Keys
- `purchase_orders.create`
- `purchase_orders.approve`
- `purchase_orders.receive`
- `shifts.manage`

---

## Phase 3 — Offline AI Copilot

### Technical Architecture
```
User Input (text)
    ↓
CopilotService.process_message(text, user_permissions)
    ↓
LocalLLM.generate(prompt + tools + context)
    ↓
Tool Selection (validated against registry)
    ↓
Tool Execution (via existing services, permission-checked)
    ↓
Response Assembly
    ↓
UI Display (CopilotPanel)
```

### Model Requirements
- GGUF format, Q4_K_M quantization
- ≥4B parameters for multilingual support
- Supports Urdu / Roman Urdu
- RAM: ≤4 GB (Q4_K_M)
- Inference: ≥5 tokens/sec on 4-core CPU

### Recommended Model
- Qwen2.5-3B-Instruct-GGUF (Q4_K_M, ~2 GB) — multilingual, tool-calling support
- Fallback: Phi-3-mini-4k-instruct-GGUF (Q4_K_M, ~2.3 GB)

### Tool Registry (read-only)
All tools call existing services and enforce user permissions:
- `search_inventory(query)` → `medicine_service.search_medicines()`
- `get_expiry_risk(warning_days)` → `medicine_service.expiry_report()`
- `get_reorder_suggestions()` → `inventory_intelligence_service.get_reorder_suggestions()`
- `get_sales_summary(date_from, date_to)` → `report_engine.sales_and_profit_report()`
- `get_best_sellers(date_from, date_to)` → `report_engine.best_selling_medicines()`
- `get_stock_valuation()` → `report_engine.stock_valuation_report()`
- `search_invoice(invoice_number)` → `sales_service.list_sales()`
- `search_supplier(name)` → `party_service.list_all_suppliers()`
- `search_help(query)` → local documentation index

---

## Implementation Order

1. ✅ Phase 0 docs
2. 🔄 Phase 1.1: `inventory_intelligence_service.py` (core business logic)
3. 🔄 Phase 1.1: `reorder_page.py` (UI)
4. 🔄 Phase 1.2: Enhanced expiry risk
5. 🔄 Phase 1.3: Dead stock detection
6. 🔄 Phase 1.4: ABC classification + analytics
7. 🔄 Migration for `supplier_lead_times` / `lead_time_days` column
8. 🔄 Tests for all Phase 1 calculations
9. ⏳ Phase 2: Purchase Orders + Cashier Shifts
10. ⏳ Phase 3: Offline AI Copilot
