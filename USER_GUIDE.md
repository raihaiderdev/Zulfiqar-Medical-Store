# Zulfiqar Medical Store — Complete User Guide

> **Written for non-technical staff.**
> You do not need any programming knowledge to use this software.
> Every section explains *what* to do, *where* to find it, and *why* it matters.

---

## Table of Contents

1. [Starting the App for the First Time](#1-starting-the-app-for-the-first-time)
2. [Logging In & Out](#2-logging-in--out)
3. [Understanding the Screen Layout](#3-understanding-the-screen-layout)
4. [Dashboard](#4-dashboard)
5. [Medicines — Your Medicine Catalog](#5-medicines--your-medicine-catalog)
   - What is a Medicine vs a Batch?
   - Adding a New Medicine
   - Editing a Medicine
   - Adding a Batch (Stock Entry)
   - Understanding: Unit, Qty, Batch
   - Viewing Full Medicine Detail
   - Deactivating a Medicine
6. [Inventory — Checking Stock Levels](#6-inventory--checking-stock-levels)
   - Searching Inventory
   - Filters (In Stock / Low Stock / Expired etc.)
   - Manually Adjusting Stock
7. [Sales / POS — Making a Sale](#7-sales--pos--making-a-sale)
   - Searching for a Medicine
   - Choosing a Unit (Tablet / Strip / Box / Bottle)
   - Cart — What it Shows
   - Discounts
   - Completing a Sale
   - Printing an Invoice
8. [Sales History — Viewing Past Invoices](#8-sales-history--viewing-past-invoices)
   - Editing an Invoice After a Mistake
9. [Purchases — Recording Stock Arrival](#9-purchases--recording-stock-arrival)
10. [Customers](#10-customers)
11. [Suppliers](#11-suppliers)
12. [Expenses](#12-expenses)
13. [Reports](#13-reports)
14. [Users — Managing Staff Accounts (Admin Only)](#14-users--managing-staff-accounts-admin-only)
    - Permissions Explained
15. [Settings & Backup (Admin Only)](#15-settings--backup-admin-only)
16. [Expiry Alerts — What They Mean](#16-expiry-alerts--what-they-mean)
17. [Glossary — Plain-English Definitions](#17-glossary--plain-english-definitions)
18. [Common Questions & Troubleshooting](#18-common-questions--troubleshooting)

---

## 1. Starting the App for the First Time

When you open the app for the very first time on a new computer, a **Setup Wizard** appears.

**Step 1 — Pharmacy Information**

| Field | What to Enter |
|-------|--------------|
| Pharmacy Name | e.g. `Zulfiqar Medical Store` — appears on every invoice |
| Address | Your shop's address |
| Phone | Contact number |

**Step 2 — Create Administrator**

| Field | What to Enter |
|-------|--------------|
| Username | A short login name, e.g. `admin` or `naeem` |
| Full Name | Your full name (optional) |
| Password | At least 8 characters — choose something you will remember |
| Confirm Password | Type the same password again |

> ⚠️ **Important:** Write down this username and password. If you forget it and have no other admin account, you cannot log in.

**Step 3 — Finish**

Click **Finish**. The wizard closes and the Login screen appears.

---

## 2. Logging In & Out

### Logging In

1. Type your **Username** and **Password**.
2. Tick **Show password** if you want to see what you are typing.
3. Tick **Remember username** if you want the username to be pre-filled next time.
4. Click **Login**.

> If you type the wrong password, a red message appears. Check for capital letters (passwords are case-sensitive).

### Session Timeout

After **30 minutes of not doing anything**, the app will ask you to log in again. This protects the store's data if you walk away from the computer.

### Logging Out

Click the red **⏻ Logout** button at the bottom of the left sidebar.

---

## 3. Understanding the Screen Layout

```
┌────────────────────────────────────────────────────────┐
│  Zulfiqar Medical Store — Pharmacy Management          │
├──────────────┬─────────────────────────────────────────┤
│              │                                         │
│  SIDEBAR     │   MAIN CONTENT AREA                     │
│  (left)      │   (changes based on what you click)     │
│              │                                         │
│  Dashboard   │                                         │
│  Medicines   │                                         │
│  Inventory   │                                         │
│  Sales/POS   │                                         │
│  ...         │                                         │
│              │                                         │
│  ⏻ Logout   │                                         │
└──────────────┴─────────────────────────────────────────┘
```

- **Sidebar (left):** Click any item to go to that section. You only see sections you have permission to use.
- **Main Content Area (right):** Shows the current section — tables, forms, buttons.
- **Your name** is shown in the sidebar so you always know who is logged in.

---

## 4. Dashboard

The **Dashboard** is the home screen for administrators. It shows a summary of the entire pharmacy at a glance.

### KPI Cards (the boxes at the top)

| Card | What it means |
|------|--------------|
| **Total Medicines** | How many different medicines are in the catalog |
| **Total Stock Units** | Total number of individual units (tablets, bottles, etc.) across all medicines |
| **Low Stock Items** | Medicines running low — need to order soon |
| **Expired Batches** | Batches whose expiry date has passed — must not be sold |
| **Expiring Soon** | Batches that will expire within 7 months |
| **Active Users** | Staff accounts that are currently enabled |
| **Total Purchases** | Total money spent on purchases ever recorded |
| **Stock Value (Cost)** | Current inventory value at the prices you paid |
| **Stock Value (Retail)** | Current inventory value at the prices you sell |

> 💡 **Tip:** Click any card to jump straight to that section. For example, clicking **Low Stock Items** takes you directly to the Inventory page.

### Sales by Period Table

Shows your revenue and gross profit for **Today**, **This Week**, **This Month**, and **This Year**.

### Expiry Alert Badge

If medicines are expiring soon or already expired, an **orange/red warning button** appears at the top right of the Dashboard. Click it to see the full list with details.

---

## 5. Medicines — Your Medicine Catalog

### What is a Medicine vs a Batch?

This is the most important concept to understand:

- **Medicine** = The *product* itself. For example: *Panadol 500mg Tablets*. A medicine has a name, formula, brand, and dosage form. It has **no stock quantity by itself**.

- **Batch** = A *physical delivery* of that medicine. Each batch has:
  - Its own **batch number** (printed on the box)
  - Its own **expiry date**
  - Its own **quantity** (how many units you have)
  - Its own **purchase price** and **selling price**
  - Its own **shelf location** (Wardrobe, Rack, Shelf)

> **Example:** Panadol might have two batches:
> - Batch A: 100 tablets, expires March 2027, stored in Rack R-02
> - Batch B: 200 tablets, expires November 2027, stored in Rack R-05
>
> The total stock of Panadol = 300 tablets (100 + 200).

The system always sells from the batch that **expires first** (called FEFO — First Expiry, First Out). You do not need to choose which batch to sell from — the system does it automatically.

---

### Adding a New Medicine

1. Go to **Medicines**.
2. Click **＋ Add Medicine** (green button, top right).
3. Fill in the form:

| Field | What to enter | Required? |
|-------|--------------|-----------|
| **Name** | Full medicine name, e.g. `Panadol 500mg` | ✅ Yes |
| **Generic Formula** | Active ingredient, e.g. `Paracetamol` | No |
| **Brand Name** | Manufacturer brand, e.g. `GlaxoSmithKline` | No |
| **Category** | Type of medicine, e.g. `Painkiller`, `Antibiotic` | No |
| **Manufacturer** | Who made it | No |
| **Dosage Form** | Choose: Tablet, Capsule, Syrup, Injection, etc. | ✅ Yes |
| **Strength** | e.g. `500mg`, `250mg/5ml` | No |
| **Pack Size** | e.g. `10 Tablets per Strip` | No |
| **Base Unit** | The smallest unit you count, e.g. `Tablet`, `mL`, `Bottle` | No |
| **Pack Unit** | A larger unit containing multiple base units, e.g. `Strip`, `Box` | No |
| **Units per Pack** | How many base units in one pack, e.g. `10` (if 1 Strip = 10 Tablets) | No |
| **Barcode** | Scan with a barcode scanner or type manually | No |
| **Min Stock Level** | Minimum quantity — below this triggers a Low Stock alert | No |
| **Reorder Level** | Quantity at which you should order more | No |
| **Notes** | Any extra notes | No |

4. Click **Save**.

> After saving, the medicine exists in the catalog but has **zero stock**. You must add a **Batch** before you can sell it.

---

### What is "Unit", "Base Unit", "Pack Unit", and "Units per Pack"?

These fields let the system sell medicines in different packaging:

| Term | Meaning | Example |
|------|---------|---------|
| **Base Unit** | The smallest piece you count | `Tablet` |
| **Pack Unit** | A group of base units | `Strip` |
| **Units per Pack** | How many base units in one pack | `10` (1 Strip = 10 Tablets) |

**Why does this matter?**

When you sell **2 Strips** of Panadol (each strip has 10 tablets), the system automatically deducts **20 tablets** from inventory. You never have to calculate this yourself.

**Setting it up:**

- Go to **Add Medicine** (or **Edit** an existing one)
- Base Unit: `Tablet`
- Pack Unit: `Strip`
- Units per Pack: `10`

Now in the POS, when you select Panadol, a dropdown will appear:
```
Sell as: [ Tablet ▼ ]  or  [ Strip (10 Tablets) ▼ ]
```

---

### Editing a Medicine

1. Find the medicine in the **Medicines** table.
2. Click the **Edit** button in the Actions column.
3. Change any fields you need.
4. Click **Save**.

> This only changes the medicine's information (name, formula, etc.). It does **not** change stock quantities. To change stock, use **Add Batch** or **Adjust Stock**.

---

### Adding a Batch (Stock Entry)

A **Batch** represents a physical delivery of medicine. You add a batch when:
- You receive new stock from a supplier
- You want to record existing stock that wasn't recorded before

**How to add a batch from the Medicines page:**

1. Go to **Medicines**.
2. Find the medicine you want to add stock for.
3. Click **+ Batch** in the Actions column.
4. Fill in the form:

| Field | What to enter | Meaning |
|-------|--------------|---------|
| **Batch Number** | The batch/lot number printed on the medicine box | Tracks which delivery this stock came from |
| **Purchase Price** | How much you paid per base unit (e.g. per tablet) | Used for profit calculations |
| **Selling Price** | How much you sell per base unit | Used by POS when this batch is sold |
| **Quantity** | How many base units you are adding | e.g. 500 tablets |
| **Expiry Date** | The expiry date printed on the box | System warns when this is near |
| **Wardrobe** | Cabinet/wardrobe code where stored, e.g. `W-01` | Physical location |
| **Rack** | Rack code inside the wardrobe, e.g. `R-03` | Physical location |
| **Shelf** | Shelf code on the rack, e.g. `S-02` | Physical location |

5. Click **Save**.

> Stock is immediately updated. Every stock addition is recorded in the audit log with your username, date, and time.

---

### Viewing Full Medicine Detail

Click the **Detail** button (or **double-click any row**) to open a full detail popup showing:

- Medicine name, formula, brand, dosage form
- Total stock across all batches
- Overall status (IN STOCK / LOW STOCK / etc.)
- Location summary: **Wardrobe | Rack | Shelf** for each batch
- Full batch table with:
  - Batch number
  - Quantity
  - Selling price
  - Expiry date
  - Days until expiry (or "Expired X days ago")
  - Wardrobe, Rack, Shelf
  - Status of each batch

---

### Deactivating a Medicine

If a medicine is discontinued, click **Deactivate**. It will:
- No longer appear in POS searches
- No longer accept new sales
- Remain visible in the Medicines list (shown as Inactive) so history is preserved

Click **Reactivate** to bring it back.

---

## 6. Inventory — Checking Stock Levels

The **Inventory** page shows every batch of every medicine with full details including location.

### Searching Inventory

Type in the **Search** bar at the top to filter by:
- Medicine name
- Formula
- Brand
- Batch number
- Wardrobe, Rack or Shelf code
- Supplier name

Results update instantly as you type. **Clearing the search shows all inventory.**

### Filters

Use the **Show:** dropdown to filter by status:

| Filter | Shows |
|--------|-------|
| **All** | Every batch |
| **In Stock** | Batches with quantity > 0 and not expiring soon |
| **Low Stock** | Batches at or below minimum stock level |
| **Out of Stock** | Batches with zero quantity |
| **Expiring Soon** | Batches expiring within 7 months |
| **Expired** | Batches past their expiry date |

### Inventory Table Columns

| Column | Meaning |
|--------|---------|
| Medicine | Medicine name |
| Formula | Generic ingredient |
| Batch | Batch number (from the box) |
| Qty | Current quantity available |
| Unit | Base unit (Tablet, mL, etc.) |
| Buy Price | Price you paid per unit |
| Sell Price | Price you sell per unit |
| Expiry | Expiry date |
| Wardrobe | Cabinet where stored |
| Rack | Rack inside the cabinet |
| Shelf | Shelf on the rack |
| Supplier | Supplier who provided this batch |
| Status | IN STOCK / LOW STOCK / EXPIRED etc. |

### Manually Adjusting Stock

Use this when stock changes for reasons other than a sale or purchase (e.g. damaged goods, miscounted stock).

1. Click **Adjust Stock…** (top right of Inventory page).
2. Select the **Medicine** from the dropdown.
3. Select the **Batch** from the second dropdown (shows batch number, current qty, expiry date).
4. Enter the **Quantity Change**:
   - Positive number = stock is being added (e.g. `+10` — you found 10 extra)
   - Negative number = stock is being removed (e.g. `-5` — 5 units were damaged)
5. Enter a **Reason** — this is mandatory. Examples: `Damaged in storage`, `Miscounted during stocktake`.
6. Click **Save**.

> Every adjustment is permanently recorded in the audit log — what changed, by how much, who did it, and why.

---

## 7. Sales / POS — Making a Sale

The **Sales / POS** page is used by the cashier to process customer sales.

### Searching for a Medicine

1. Click inside the search box (or your barcode scanner will automatically type into it).
2. Type part of the medicine name, formula, brand, or barcode.
3. Suggestions appear instantly in a dropdown as you type.
4. Click the medicine you want (or press Enter if only one result appears).

After selecting a medicine, a **detail panel** appears showing:
- Medicine name and status
- Total stock available
- 📍 Location: Wardrobe, Rack, Shelf
- Batch table with expiry dates and quantities

### Choosing a Unit (Tablet / Strip / Box / Bottle)

After selecting a medicine, use the **"Sell as"** dropdown to choose the unit:

```
Sell as:  [ Tablet ▼ ]   @ Rs 5.00 each
         [ Strip (10 Tablets) ▼ ]   @ Rs 50.00 each
```

- If you sell **2 Strips**, the system deducts **20 tablets** from inventory automatically.
- The price shown updates based on the selected unit.
- Set the **Qty** (quantity) spinner to how many of that unit the customer wants.

### Adding to Cart

Click **＋ Add to Cart** (or press Enter). The item appears in the cart table below.

### Cart — What Each Column Means

| Column | Meaning |
|--------|---------|
| **Medicine** | Medicine name |
| **Sale Unit** | What unit you chose (Tablet, Strip, etc.) |
| **Qty** | How many of that unit in the cart |
| **Unit Price (Rs)** | Price per unit |
| **DB Avail** | How many base units are still available in stock right now (stock minus what is already in this cart) |
| **Est. Total (Rs)** | Estimated total for this line |
| **Remove** | Click the red ✕ button to remove this line from the cart |

> **DB Avail** is especially useful: if a customer wants 10 strips but only 5 are available, the system shows `0` and blocks adding more than what is in stock.

### Discounts

- Type a discount amount (in Rs) in the **Discount** field.
- Only staff who have the **"Apply discounts"** permission can do this.
- There is a maximum discount percentage set by the administrator — if you exceed it, the sale is blocked with a clear message.

### Completing a Sale

1. Type the amount the customer gave you in **Amount Paid (Rs)**.
2. Click **✔ Complete Sale**.
3. A summary pops up showing:
   - Invoice number
   - Total amount
   - Amount paid
   - Change due (how much to give back to the customer)
4. The system then asks: **"Save this invoice as a PDF?"** Click Yes to save a PDF invoice, or No to skip.

After the sale completes, the cart is cleared and stock is deducted from inventory automatically.

### Printing an Invoice

When asked after completing a sale, click **Yes** → choose where to save the PDF → it opens for printing.

---

## 8. Sales History — Viewing Past Invoices

Go to **Sales History** to see all completed invoices.

### Searching by Date

Use the **From** and **To** date pickers to set a date range, then click **Search**.

### Invoice Table Columns

| Column | Meaning |
|--------|---------|
| Invoice # | Unique invoice number (e.g. INV-2026-000001) |
| Date | When the sale was made |
| Total (Rs) | Total amount of the invoice |
| Paid (Rs) | Amount the customer paid |
| Change (Rs) | Change given back |
| Status | COMPLETED, CANCELLED, etc. |
| View | Opens full detail showing every medicine sold |
| Edit | Correct a mistake in the invoice (see below) |

### Editing an Invoice After a Mistake

If a cashier made an error (wrong quantity, wrong medicine), an authorised user can correct it:

1. Click **✏ Edit Invoice** on the invoice row.
2. The invoice loads with all its line items.
3. **To change quantity:** Type the new quantity in the Qty column. Set to `0` to remove a line entirely.
4. **To change price or discount:** Edit the Unit Price or Discount fields.
5. Enter a **Reason** (mandatory) — e.g. `Customer was overcharged, returning 2 units`.
6. Click **✔ Save Changes**.

**What happens automatically:**
- If you reduce a quantity, the stock is returned to inventory.
- If you increase a quantity, it checks there is enough stock first.
- The total, subtotal and change due are all recalculated.
- A permanent record of who edited it, when, and why is saved in the audit log.

> Only users with the **"Edit / correct a completed invoice"** permission can do this.

---

## 9. Purchases — Recording Stock Arrival

When medicine arrives from a supplier, record it here. This is different from "Add Batch" on the Medicines page — **Purchases also records the supplier, invoice number, and payment status**.

### Recording a New Purchase

1. Go to **Purchases**.
2. On the left side, fill in the form:

| Field | Meaning |
|-------|---------|
| **Supplier** | Who you bought from (must be added in Suppliers first) |
| **Medicine** | Which medicine arrived |
| **Supplier Invoice #** | The invoice number on the supplier's paper |
| **Batch Number** | The batch/lot number on the medicine box |
| **Quantity** | How many units received |
| **Purchase Price** | Price per unit you paid |
| **Selling Price** | Price per unit you will sell at |
| **Expiry Date** | Expiry date printed on the box |

3. Click **✔ Record Purchase**.

Stock is immediately increased and the batch is linked to this purchase.

### Purchase History (right side)

The right side shows all past purchases for the selected supplier, with their total cost and payment status (PAID / UNPAID).

Click **Mark as Paid** when you have paid the supplier's invoice.

---

## 10. Customers

Record your regular customers here for tracking purchase history.

| Action | How |
|--------|-----|
| **Add Customer** | Click ＋ Add Customer, fill in name/phone/address |
| **Edit** | Click Edit on any row |
| **History** | Click History to see all invoices for that customer |
| **Deactivate** | Click Deactivate to disable (does not delete history) |

---

## 11. Suppliers

Record the companies or individuals you buy medicine from.

| Action | How |
|--------|-----|
| **Add Supplier** | Click ＋ Add Supplier, fill in name/company/phone/email |
| **Edit** | Click Edit on any row |
| **Deactivate / Reactivate** | Disable or re-enable a supplier |

> A deactivated supplier no longer appears in the Purchases dropdown but their history is preserved.

---

## 12. Expenses

Record shop expenses (rent, electricity, salaries, etc.) for accurate profit calculation.

1. First create a **Category**: click **＋ Add Category** and type the name (e.g. `Rent`, `Electricity`).
2. Then click **＋ Add Expense** and fill in category, description, amount, and date.
3. Use the filter dropdowns to view expenses by category or date range.

The **Running Total** at the bottom shows total expenses for the filtered period. This figure is used in the **Reports** section to calculate Net Profit.

---

## 13. Reports

Go to **Reports** to see how the business is performing.

1. Set the **From** and **To** dates.
2. Click **Run Report**.

### Summary Line

| Figure | What it means |
|--------|--------------|
| **Revenue** | Total money received from sales (after discounts) |
| **COGS** | Cost of Goods Sold — what you paid for the stock that was sold |
| **Gross Profit** | Revenue minus COGS — profit before expenses |
| **Expenses** | Total expenses recorded for the period |
| **Net Profit** | Gross Profit minus Expenses — your actual profit |
| **Returned Units** | Number of units returned by customers |

### Best-Selling Medicines Table

Shows your top 20 medicines ranked by units sold, with revenue and profit per medicine. Click **Export CSV** to save this as a spreadsheet.

### Stock Valuation

Shows:
- How many batches and units are currently in stock
- Total value of stock at cost price (what you paid)
- Total value of stock at retail price (what you can sell for)
- Potential gross profit if all current stock is sold

---

## 14. Users — Managing Staff Accounts (Admin Only)

Go to **Users** to manage who can access the software and what they can do.

### Creating a New User

1. Click **＋ Create User**.
2. Fill in username, full name, and password.
3. Choose one of:
   - **Grant full administrator access** — this person can do everything.
   - OR tick individual permissions from the list below.

### Permissions Explained

| Permission | What it allows |
|-----------|----------------|
| **View medicines** | See the medicines list |
| **Add medicines** | Add new medicines and batches |
| **Edit medicines** | Change medicine details |
| **Import medicines from Excel** | Bulk import via Excel file |
| **View stock levels** | See the Inventory page |
| **Create manual stock adjustments** | Use "Adjust Stock" on Inventory |
| **Create sales (POS)** | Use the Sales / POS screen |
| **View sales history** | See past invoices |
| **Apply discounts** | Give discounts at sale (up to the admin-set maximum) |
| **Print sales invoices** | Save/print PDF invoices |
| **Edit / correct a completed invoice** | Fix mistakes on past invoices |
| **Record and manage purchases** | Use Purchases screen |
| **Manage customers** | Add/edit customers |
| **Manage suppliers** | Add/edit suppliers |
| **View reports** | Access Reports page |
| **Process sale/purchase returns** | Process customer returns |

### Resetting a Password

1. Find the user in the list.
2. Click **Reset Password**.
3. Type a new password (or leave blank to auto-generate one).
4. The new password is shown on screen — write it down and give it to the staff member privately.

### Deactivating a User

Click **Deactivate** on any user row. Their account is disabled but all their sales history and audit records are kept.

---

## 15. Settings & Backup (Admin Only)

### Pharmacy Information

Go to **Settings** to update:
- **Pharmacy Name** — appears on every invoice PDF
- **Address** — appears on every invoice PDF
- **Phone** — appears on every invoice PDF

Click **Save Settings** after making changes.

### Backup

Your data is stored in a file called `pharmacy.db` inside the `database/` folder. Regular backups protect against computer failure.

**To create a backup:**
Click **Backup Database Now**. A timestamped copy is saved to the `backups/` folder. Example: `pharmacy_2026-09-08_22-30-00.db`.

**To restore from a backup:**
Click **Restore From Backup…**, choose a backup file. Before restoring, the system automatically saves a safety copy of your current data — so you can always undo a restore.

> 💡 **Best practice:** Create a backup at the end of every working day and copy it to a USB drive or cloud storage.

---

## 16. Expiry Alerts — What They Mean

The system checks all medicine batches and warns you before they expire.

### Alert Levels

| Level | Meaning | What to do |
|-------|---------|-----------|
| 🔴 **EXPIRED** | Expiry date has passed | Remove from shelf immediately. Cannot be sold. Write off using Adjust Stock. |
| 🟠 **EXPIRING VERY SOON** | Expires within 1 month | Sell urgently. Contact supplier if possible. |
| 🟡 **EXPIRING SOON** | Expires within 7 months | Plan to sell before expiry. Avoid over-ordering. |

### Where Alerts Appear

1. **On the Dashboard** — orange/red warning button at the top right shows a count.
2. **Automatic popup** — when the app starts, if there are any expiry alerts, a dialog appears automatically (once per login session only — it won't keep popping up every time you click around).
3. **Inventory page** — use the **"Expiring Soon"** or **"Expired"** filter.
4. **Medicine detail dialog** — each batch shows its expiry status and days remaining.

### Can You Sell Expired Medicine?

**No.** The POS automatically blocks any sale of an expired batch. An error message will appear if you try. This cannot be bypassed without a special administrator override that is disabled by default.

---

## 17. Glossary — Plain-English Definitions

| Term | Plain-English Meaning |
|------|----------------------|
| **Batch** | One specific delivery/lot of a medicine, with its own batch number, expiry date, and quantity |
| **Batch Number** | The lot/batch number printed on the medicine box or strip |
| **Base Unit** | The smallest unit the system counts — e.g. one Tablet, one mL, one Bottle |
| **Pack Unit** | A group of base units — e.g. one Strip contains 10 Tablets |
| **Units per Pack** | How many base units make up one pack unit |
| **FEFO** | First Expiry, First Out — the system always sells the batch that expires soonest |
| **POS** | Point of Sale — the screen used for making sales to customers |
| **Invoice** | A receipt/document recording a completed sale |
| **COGS** | Cost of Goods Sold — what you paid for the stock that was sold |
| **Gross Profit** | Money earned from sales minus what you paid for those medicines |
| **Net Profit** | Gross Profit minus all shop expenses (rent, electricity, etc.) |
| **Min Stock Level** | Minimum quantity you want to keep — below this triggers a Low Stock warning |
| **Reorder Level** | Quantity at which you should place a new order with the supplier |
| **Wardrobe** | A cabinet or storage unit in the pharmacy |
| **Rack** | A specific rack/shelf unit inside a wardrobe |
| **Shelf** | A specific shelf on a rack |
| **Audit Log** | An automatic record of every important action — who did what, when |
| **Permission** | What a user is allowed to do in the system |
| **Administrator** | A user with full access to everything |
| **Session Timeout** | Automatic logout after 30 minutes of inactivity |
| **Deactivate** | Disable without deleting — history is always preserved |

---

## 18. Common Questions & Troubleshooting

**Q: I forgot my password — what do I do?**
A: Ask another administrator to reset your password in the **Users** section.
If there is only one admin and no one knows the password, contact your software support contact.

**Q: I added a medicine but it won't show in POS search.**
A: Check if the medicine has been **deactivated** (Medicines page — look for red "Reactivate" button). Also check that at least one **batch with quantity > 0** has been added.

**Q: The sale is blocked saying "Insufficient stock".**
A: The customer is asking for more units than you currently have. Check the **DB Avail** column in the cart — it shows exactly how many are left. You may need to record a new **Purchase** to top up stock first.

**Q: The medicine shows "EXPIRING SOON" — can I still sell it?**
A: Yes. EXPIRING SOON only means it expires within 7 months — you can still sell it normally. Only **EXPIRED** batches are blocked.

**Q: I made a mistake on an invoice — can I fix it?**
A: Yes, if you have the **"Edit / correct a completed invoice"** permission. Go to **Sales History**, find the invoice, and click **✏ Edit Invoice**.

**Q: Where does the backup file get saved?**
A: Inside the `backups/` folder in the same folder as the application. You can also copy this file to a USB drive or email it to yourself for extra safety.

**Q: A column in a table is too narrow to read. What do I do?**
A: Click and drag the column border in the table header to make it wider.

**Q: The app asked me to log in again even though I was just using it.**
A: The session timeout is set to 30 minutes of inactivity. If you leave the app idle (not clicking anything) for 30 minutes, it automatically logs you out. Just log back in — no data is lost.

**Q: I see an error message I don't understand.**
A: Take a photo or note what it says and share it with your support contact. Technical details are also written to the `logs/error.log` file for diagnosis.

---

*Zulfiqar Medical Store Pharmacy Management System — Version 1.0.0*
*For technical issues contact your system administrator.*
