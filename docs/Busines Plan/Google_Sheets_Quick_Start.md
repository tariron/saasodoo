# SaaSOdoo Google Sheets Financial Dashboard - Quick Start

**⏱️ Setup Time:** 15-20 minutes
**💪 Difficulty:** Beginner (copy-paste formulas)
**📊 Result:** Live financial model with auto-updating KPIs

---

## 🚀 Quick Start (3 Steps)

### Step 1: Create New Google Sheet (2 min)

1. Go to https://sheets.google.com
2. Click **+ Blank** spreadsheet
3. Rename: "SaaSOdoo Financial Dashboard"

### Step 2: Import All Sheets (10 min)

Import these CSV files **in order**:

```
1. GS_0_Dashboard.csv          → Dashboard (rename sheet to "DASHBOARD")
2. GS_1_Assumptions.csv        → 1. Assumptions
3. GS_2_Customer_Mix.csv       → 2. Customer Mix
4. GS_3_Revenue_Model.csv      → 3. Revenue Model
5. GS_4_Cost_Model.csv         → 4. Cost Model
6. GS_5_PL_Statement.csv       → 5. P&L Statement
7. GS_6_Cash_Flow.csv          → 6. Cash Flow
8. GS_7_KPI_Dashboard.csv      → 7. KPIs
9. GS_8_Unit_Economics.csv     → 8. Unit Economics
```

**How to import each file:**
1. File → Import → Upload
2. Select CSV file
3. Import location: **"Insert new sheet(s)"**
4. Separator type: **"Comma"**
5. Click **Import data**
6. Rename sheet tab to match name above (remove "GS_X_" prefix)

### Step 3: Apply Formatting (5 min)

**Essential formatting:**

1. **DASHBOARD sheet:**
   - Select all → Format → Number → Automatic
   - Header row: Bold, dark gray background, white text

2. **1. Assumptions sheet:**
   - Column B (values): Light blue background (#CFE2F3)
   - Add note: "Edit blue cells only"

3. **All sheets:**
   - Freeze top row: View → Freeze → 1 row
   - Auto-resize columns: Select all → Right-click column header → Resize columns → Fit to data

---

## ✅ You're Done! Now What?

### Monthly Update Routine (5 min)

**At the end of each month:**

1. **Go to "1. Assumptions"** sheet
   - Update actual churn rate (if different)
   - Update actual CAC (marketing spend / new customers)

2. **Go to "2. Customer Mix"** sheet
   - Fill in next month's row:
     - Column B: New customers acquired
     - Column C: Churned customers
   - Everything else auto-calculates!

3. **Go to "DASHBOARD"** sheet
   - Change "Analysis Month" to current month
   - Review alerts (red/yellow flags)

4. **Export snapshot** (optional)
   - File → Download → PDF
   - Save as: "SaaSOdoo_Financial_Month_XX.pdf"

---

## 📊 Understanding Your Dashboard

### Key Metrics Explained

**MRR (Monthly Recurring Revenue):**
- Total predictable revenue per month
- **Goal:** Grow 15-20% month-over-month

**LTV:CAC Ratio:**
- Lifetime Value ÷ Customer Acquisition Cost
- **Good:** >3:1 (you make $3 for every $1 spent acquiring)
- **Great:** >5:1

**Gross Margin %:**
- (Revenue - COGS) / Revenue
- **Target:** >70% for SaaS

**Churn Rate:**
- % of customers who cancel each month
- **Good:** <5%
- **Great:** <3%

**Cash Balance:**
- Money in the bank
- **Danger zone:** <$1,000
- **Safe:** >$5,000

---

## 🎨 Conditional Formatting (Optional but Recommended)

### Apply These Rules:

**1. Cash Balance Alert (Sheet: 6. Cash Flow)**
- Select column F (Ending Cash)
- Format → Conditional formatting
- Format cells if: `Custom formula is` → `=F2<0`
- Formatting style: Red background
- Add another rule: `=F2<1000` → Yellow background

**2. Status Indicators (Sheet: 7. KPIs)**
- Select column D (Status)
- Format → Conditional formatting
- Format cells if: `Text contains` → `✓`
- Formatting style: Green text
- Add rule: `Text contains` → `⚠` → Yellow text
- Add rule: `Text contains` → `🔴` → Red text

**3. Metrics vs Target (Sheet: DASHBOARD)**
- Select "Status" column
- Same rules as above

---

## 📈 Create Charts (Optional - Visual Impact)

### Chart 1: MRR Growth Line Chart

**Data:**
- Sheet: `3. Revenue Model`
- X-axis: Column A (Month 1-36)
- Y-axis: Column J (Total MRR)

**How to create:**
1. Select columns A and J (Month 1-36 rows)
2. Insert → Chart
3. Chart type: Line chart
4. Customize:
   - Title: "MRR Growth (36 Months)"
   - Vertical axis: "Monthly Recurring Revenue ($)"
   - Horizontal axis: "Month"
5. Move chart to DASHBOARD sheet (top right)

---

### Chart 2: Customer Mix Stacked Area

**Data:**
- Sheet: `2. Customer Mix`
- X-axis: Column A (Month)
- Series: Columns I, J, K, L (Hustler, SME, Business, Enterprise counts)

**How to create:**
1. Select columns A, I, J, K, L (Month 1-36 rows)
2. Insert → Chart
3. Chart type: Stacked area chart
4. Customize:
   - Title: "Customer Acquisition by Tier"
   - Legend: Right side
   - Colors: Blue, Green, Orange, Red
5. Move to DASHBOARD sheet (middle)

---

### Chart 3: Cash Flow Waterfall (Advanced)

**Data:**
- Sheet: `6. Cash Flow` (Quarterly Summary section)
- Categories: Starting Cash, Revenue, Costs, Ending Cash

**How to create:**
1. Select quarterly summary data (rows 41-52)
2. Insert → Chart
3. Chart type: Waterfall chart
4. Customize:
   - Title: "Quarterly Cash Flow"
   - Colors: Green (positive), Red (negative)

---

## 🔧 Troubleshooting

### Issue: #REF! errors everywhere

**Cause:** Sheet names don't match formula references
**Fix:**
1. Check sheet names exactly match:
   - "1. Assumptions" (with space and period)
   - "2. Customer Mix"
   - etc.
2. Rename sheets if needed (right-click tab → Rename)

---

### Issue: Formulas showing as text (not calculating)

**Cause:** Google Sheets imported as text
**Fix:**
1. Select all cells with formulas
2. Data → Split text to columns → Separator: None
3. Or: Click cell, press F2 (edit), then Enter (forces recalculation)

---

### Issue: Numbers showing as text

**Cause:** Wrong number format
**Fix:**
1. Select cells
2. Format → Number → Currency ($)
3. Or: Format → Number → Percent (%)

---

### Issue: Charts not updating with new data

**Cause:** Chart range is fixed
**Fix:**
1. Click chart → 3-dot menu → Edit chart
2. Setup → Data range
3. Extend range to row 50 (covers 36 months + headers)

---

## 💡 Pro Tips

### 1. Use Named Ranges for Easier Formulas

**Instead of:** `='1. Assumptions'!B3`
**Use:** `=Assumptions_HustlerPrice`

**How to:**
1. Data → Named ranges
2. Click + Add a range
3. Name: `Assumptions_HustlerPrice`
4. Range: `'1. Assumptions'!B3`
5. Done

**Create these common named ranges:**
- `Current_MRR` → Last row of MRR in Revenue Model
- `Current_Customers` → Last row in Customer Mix
- `Current_Cash` → Last row in Cash Flow

---

### 2. Set Up Email Alerts

**Get notified when cash is low:**

1. Tools → Notification rules
2. Notify me when: "A user submits a form" (No - skip this)
3. Or use Google Apps Script (advanced):

```javascript
function checkCashBalance() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('6. Cash Flow');
  var cash = sheet.getRange('F38').getValue(); // Month 36 cash

  if (cash < 1000) {
    MailApp.sendEmail({
      to: 'your-email@example.com',
      subject: '🚨 SaaSOdoo: Low Cash Alert',
      body: 'Cash balance is below $1,000. Current: $' + cash
    });
  }
}
```

Set trigger: Edit → Current project's triggers → Add trigger (run weekly)

---

### 3. Version Control

**Create monthly snapshots:**

1. File → Make a copy
2. Name: "SaaSOdoo Financial - Jan 2025 Snapshot"
3. Keep in same Google Drive folder
4. Update "Master" copy each month
5. Compare snapshots to see changes over time

---

### 4. Share with Team

**View-only for most:**
- Share → Add people → Role: Viewer

**Edit access for finance:**
- Role: Editor
- Protect sheets: Data → Protected sheets and ranges
- Lock all except "2. Customer Mix" (where actuals are entered)

---

## 📚 Next Steps

After setup, read these guides:

1. **`Google_Sheets_Setup_Instructions.md`** - Detailed formatting & charts
2. **`Financial_Model_Summary.md`** - Understanding the business model
3. **`Quick_Reference_Pricing_And_Pods.md`** - Infrastructure & pricing cheat sheet

---

## 🆘 Need Help?

**Common questions:**

**Q: Can I change pricing in Assumptions without breaking formulas?**
A: Yes! Change cells B3-B6 (pricing). All sheets auto-update.

**Q: How do I add Month 37 and beyond?**
A: Copy formulas from Month 36 row, paste to Month 37 row. Update month number in column A.

**Q: Can I export this to Excel?**
A: Yes. File → Download → Microsoft Excel (.xlsx). Most formulas work, but check conditional formatting.

**Q: How do I reset to defaults?**
A: Re-import the CSV files (they have the original assumptions).

---

## ✅ Checklist: Is Everything Working?

- [ ] All 9 sheets imported and renamed
- [ ] DASHBOARD shows metrics (not errors)
- [ ] Change "Analysis Month" to 6 → numbers update
- [ ] Go to Assumptions, change Hustler price to $10 → MRR increases
- [ ] Check 6. Cash Flow → Month 12 shows positive cash
- [ ] Check 7. KPIs → Status shows ✓ or ⚠ (not formulas)
- [ ] Created at least 1 chart (MRR growth)
- [ ] Applied conditional formatting to Cash Balance

**All checked? You're ready to use the model!**

---

## 🎯 Monthly Business Review Template

**Use this every month:**

1. **Update actuals** (5 min)
   - New customers, churned customers, actual CAC

2. **Review DASHBOARD** (5 min)
   - Are we on track? (green checkmarks)
   - Any red/yellow alerts?

3. **Deep dive problem areas** (10 min)
   - If churn high: Check 2. Customer Mix (which tier churning most?)
   - If cash low: Check 6. Cash Flow (where is money going?)
   - If LTV:CAC low: Check 8. Unit Economics (need to reduce CAC or improve retention?)

4. **Make decisions** (10 min)
   - Should we increase prices?
   - Should we pause hiring?
   - Should we cut marketing spend?
   - Do we need to raise funding?

5. **Update team** (5 min)
   - Share DASHBOARD screenshot
   - Highlight wins and challenges
   - Assign action items

**Total time:** 35 minutes/month

---

**🚀 Ready to launch? Change "Analysis Month" to 1 and start tracking your journey to 1,000 customers!**
