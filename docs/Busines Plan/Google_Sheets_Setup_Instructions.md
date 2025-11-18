# SaaSOdoo Financial Dashboard - Google Sheets Setup Guide

**Version:** 1.0 | **Setup Time:** 15-20 minutes

---

## Quick Start

### Option 1: Import Pre-Built Template (Fastest)

1. **Open Google Sheets:** https://sheets.google.com
2. **Create new spreadsheet:** "SaaSOdoo Financial Dashboard"
3. **Import each sheet file** in order:
   - File → Import → Upload → Select file
   - Import location: "Insert new sheet(s)"
   - Separator type: "Tab" (for .tsv files) or "Comma" (for .csv files)

4. **Files to import** (in this order):
   - `GS_1_Assumptions.csv`
   - `GS_2_Customer_Mix.csv`
   - `GS_3_Revenue_Model.csv`
   - `GS_4_Cost_Model.csv`
   - `GS_5_PL_Statement.csv`
   - `GS_6_Cash_Flow.csv`
   - `GS_7_KPI_Dashboard.csv`
   - `GS_8_Unit_Economics.csv`

5. **Apply formatting** (see below)

---

### Option 2: Manual Setup (Full Control)

Follow the detailed instructions in each sheet section below.

---

## Sheet Structure Overview

```
📊 SaaSOdoo Financial Dashboard
├── 📋 DASHBOARD (Summary - Build Last)
├── 🎛️ 1. Assumptions (USER INPUT)
├── 👥 2. Customer Mix
├── 💰 3. Revenue Model
├── 💸 4. Cost Model
├── 📊 5. P&L Statement
├── 💵 6. Cash Flow
├── 📈 7. KPIs
└── 🔢 8. Unit Economics
```

---

## Color Coding System

**Apply these colors for visual clarity:**

| Color | Use Case | Hex Code |
|-------|----------|----------|
| 🟦 **Light Blue** | Input cells (user edits these) | #CFE2F3 |
| 🟩 **Light Green** | Calculated results (formulas) | #D9EAD3 |
| 🟨 **Light Yellow** | Important metrics/KPIs | #FFF2CC |
| 🟥 **Light Red** | Warnings/thresholds exceeded | #F4CCCC |
| ⬜ **White** | Reference data (rarely changes) | #FFFFFF |
| ⬛ **Dark Gray** | Headers | #666666 (white text) |

---

## Conditional Formatting Rules

### 1. KPI Status Indicators

**Good Performance (Green):**
- LTV:CAC > 3
- Gross Margin > 65%
- Monthly Churn < 5%
- MRR Growth > 10%

**Warning (Yellow):**
- LTV:CAC 2-3
- Gross Margin 50-65%
- Monthly Churn 5-7%
- MRR Growth 5-10%

**Critical (Red):**
- LTV:CAC < 2
- Gross Margin < 50%
- Monthly Churn > 7%
- MRR Growth < 5%

### 2. Cash Flow Alerts

**Format cells with formula:**
```
=IF(CashBalance < 0, TRUE, FALSE)
→ Red background if negative
```

### 3. Target Achievement

**Format cells with formula:**
```
=IF(Actual >= Target, TRUE, FALSE)
→ Green if met/exceeded, Red if missed
```

---

## Number Formatting Standards

| Cell Type | Format | Example |
|-----------|--------|---------|
| **Currency** | $#,##0.00 | $1,234.56 |
| **Percentage** | 0.0% | 12.5% |
| **Whole Numbers** | #,##0 | 1,234 |
| **Decimals (2 places)** | #,##0.00 | 1,234.56 |
| **Month Labels** | MMM-YY | Jan-25 |

---

## Key Formulas Reference

### Revenue Calculations

**MRR by Tier:**
```
=CustomerCount * PricePerMonth
```

**Total MRR:**
```
=SUM(HustlerMRR, SMEMRR, BusinessMRR, EnterpriseMRR)
```

**Churn Calculation:**
```
=ChurnedCustomers / StartingCustomers
```

**Net New Customers:**
```
=NewCustomers - ChurnedCustomers
```

---

### Cost Calculations

**Infrastructure Cost per Customer:**
```
=TotalInfrastructureCost / TotalCustomers
```

**COGS per Tier:**
```
=InfraCost + StorageCost + BackupCost + BandwidthCost + PaymentProcessing + SupportCost + PlatformOverhead
```

**Gross Profit:**
```
=Revenue - COGS
```

**Gross Margin %:**
```
=GrossProfit / Revenue
```

---

### Unit Economics

**LTV (Lifetime Value):**
```
=ARPU * CustomerLifetimeMonths * GrossMarginPercent
```

**Customer Lifetime (months):**
```
=1 / MonthlyChurnRate
```

**LTV:CAC Ratio:**
```
=LTV / CAC
```

**Payback Period (months):**
```
=CAC / (ARPU * GrossMarginPercent)
```

---

### Cash Flow

**Monthly Cash In:**
```
=MonthlyRevenue + AnnualPrepayments
```

**Monthly Cash Out:**
```
=COGS + OperatingExpenses
```

**Net Cash Flow:**
```
=CashIn - CashOut
```

**Ending Cash Balance:**
```
=PreviousMonthBalance + NetCashFlow
```

---

## Data Validation Setup

### 1. Customer Tier Dropdown

**Column:** Customer Mix sheet, "Tier" column
**List:** Hustler, SME, Business, Enterprise

### 2. Month Selector

**Column:** Wherever you select analysis month
**List:** Month 1, Month 2, ..., Month 36

### 3. Percentage Inputs

**Validation:** Number between 0 and 1
**Error message:** "Please enter a percentage as a decimal (e.g., 0.05 for 5%)"

---

## Chart Recommendations

### Chart 1: MRR Growth Over Time (Line Chart)

**Data:**
- X-axis: Month (1-36)
- Y-axis: MRR ($)
- Series: Total MRR, Target MRR

**Location:** Dashboard sheet

---

### Chart 2: Customer Acquisition by Tier (Stacked Area)

**Data:**
- X-axis: Month (1-36)
- Y-axis: Customer Count
- Series: Hustler, SME, Business, Enterprise (stacked)

**Location:** Dashboard sheet

---

### Chart 3: Revenue by Tier (Stacked Column)

**Data:**
- X-axis: Month (quarters: Q1, Q2, Q3...)
- Y-axis: Revenue ($)
- Series: Hustler Revenue, SME Revenue, Business Revenue, Enterprise Revenue

**Location:** Revenue Model sheet

---

### Chart 4: Gross Margin Trend (Combo Chart)

**Data:**
- X-axis: Month
- Y-axis 1: Revenue & COGS ($) - Columns
- Y-axis 2: Gross Margin (%) - Line

**Location:** P&L Statement sheet

---

### Chart 5: Cash Flow Waterfall (Waterfall Chart)

**Data:**
- Categories: Starting Cash, Revenue, COGS, OpEx, Ending Cash
- Values: Monthly amounts

**Location:** Cash Flow sheet

---

### Chart 6: Unit Economics Gauges

**Create 3 gauge charts:**

**LTV:CAC Ratio:**
- Min: 0, Max: 10
- Red zone: 0-2
- Yellow zone: 2-3
- Green zone: 3-10

**Gross Margin %:**
- Min: 0%, Max: 100%
- Red: 0-50%
- Yellow: 50-65%
- Green: 65-100%

**Payback Period (months):**
- Min: 0, Max: 24
- Green: 0-6
- Yellow: 6-12
- Red: 12-24

**Location:** KPI Dashboard sheet

---

## Dashboard Layout (Sheet 1)

**Create this summary view:**

```
┌─────────────────────────────────────────────────────────┐
│  📊 SAASODOO FINANCIAL DASHBOARD                        │
│  Last Updated: [Auto-date]                              │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  KEY METRICS (Current Month)                            │
│  ┌──────────┬──────────┬──────────┬──────────┐          │
│  │   MRR    │ Customers│   CAC    │   LTV    │          │
│  │  $X,XXX  │   XXX    │   $XX    │   $XXX   │          │
│  └──────────┴──────────┴──────────┴──────────┘          │
│                                                          │
│  ┌──────────┬──────────┬──────────┬──────────┐          │
│  │ LTV:CAC  │Gross Mrg │  Churn   │ Payback  │          │
│  │   X.X:1  │   XX%    │   X.X%   │  X.X mo  │          │
│  └──────────┴──────────┴──────────┴──────────┘          │
│                                                          │
├─────────────────────────────────────────────────────────┤
│  📈 MRR GROWTH CHART (Line chart here)                  │
│                                                          │
│                                                          │
├─────────────────────────────────────────────────────────┤
│  👥 CUSTOMER MIX (Stacked area chart here)              │
│                                                          │
│                                                          │
├─────────────────────────────────────────────────────────┤
│  💵 FINANCIAL SUMMARY (Year 1, 2, 3)                    │
│  ┌──────────┬──────────┬──────────┬──────────┐          │
│  │  Metric  │  Year 1  │  Year 2  │  Year 3  │          │
│  ├──────────┼──────────┼──────────┼──────────┤          │
│  │ Revenue  │ $XX,XXX  │ $XXX,XXX │ $XXX,XXX │          │
│  │ COGS     │ $XX,XXX  │ $XX,XXX  │ $XX,XXX  │          │
│  │ OpEx     │ $XX,XXX  │ $XX,XXX  │ $XXX,XXX │          │
│  │ Profit   │ $X,XXX   │ $XX,XXX  │ $XXX,XXX │          │
│  │ Margin   │  XX%     │  XX%     │  XX%     │          │
│  └──────────┴──────────┴──────────┴──────────┘          │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## Cell Reference Map

**For cross-sheet formulas, use named ranges:**

### Define Named Ranges:

1. **Go to Data → Named ranges**

2. **Create these named ranges:**

| Name | Range | Sheet |
|------|-------|-------|
| `Assumptions_HustlerPrice` | B3 | 1. Assumptions |
| `Assumptions_SMEPrice` | B4 | 1. Assumptions |
| `Assumptions_BusinessPrice` | B5 | 1. Assumptions |
| `Assumptions_ChurnRate` | B10 | 1. Assumptions |
| `Assumptions_CAC` | B11 | 1. Assumptions |
| `Assumptions_GrossMargin` | B12 | 1. Assumptions |
| `CurrentMRR` | Last row of MRR column | 3. Revenue Model |
| `CurrentCustomers` | Last row of Total Customers | 2. Customer Mix |
| `CurrentCash` | Last row of Cash Balance | 6. Cash Flow |

**Usage in formulas:**
```
=Assumptions_HustlerPrice * HustlerCustomerCount
```

Instead of:
```
='1. Assumptions'!B3 * '2. Customer Mix'!B15
```

---

## Monthly Update Workflow

**At the end of each month:**

1. **Go to "1. Assumptions" sheet**
   - Update actual customer counts (if different from projections)
   - Update actual churn rate
   - Update actual CAC (marketing spend / new customers)

2. **Go to "2. Customer Mix" sheet**
   - Fill in next month's row:
     - New customers by tier
     - Churned customers
     - Formulas auto-calculate totals

3. **Check "7. KPIs" sheet**
   - Review red/yellow alerts
   - Compare actual vs. target

4. **Update "DASHBOARD" sheet**
   - Month selector dropdown → current month
   - All metrics auto-update

5. **Export reports** (if needed)
   - File → Download → PDF
   - Share with team/investors

---

## Troubleshooting Common Issues

### Issue 1: #REF! errors after import

**Cause:** Cell references broken during import
**Fix:** Check that all sheet names match exactly (including spaces)

### Issue 2: Formulas not calculating

**Cause:** Imported as text instead of formulas
**Fix:**
1. Select cell
2. Press F2 (edit mode)
3. Press Enter
4. Or: Find & Replace `=` with `=` (forces recalculation)

### Issue 3: Currency showing as text

**Cause:** Wrong number format
**Fix:** Select cells → Format → Number → Currency ($)

### Issue 4: Percentages showing as 0.05 instead of 5%

**Cause:** Wrong number format
**Fix:** Select cells → Format → Number → Percent

### Issue 5: Charts not updating with new data

**Cause:** Chart range is fixed
**Fix:**
1. Click chart → 3-dot menu → Edit chart
2. Setup → Data range
3. Change to dynamic range or use named range

---

## Advanced Features (Optional)

### 1. Scenario Analysis

**Create 3 scenarios:**
- Best case (20% better acquisition, 30% lower churn)
- Base case (current assumptions)
- Worst case (20% slower acquisition, 30% higher churn)

**How to:**
1. Duplicate "1. Assumptions" sheet 3 times
2. Name them: Assumptions_Best, Assumptions_Base, Assumptions_Worst
3. Adjust values in each
4. Use dropdown to switch between scenarios in dashboard

### 2. Sensitivity Table

**Test impact of price changes:**
- Data → What-if analysis → Create data table
- Row input: Hustler price ($6, $8, $10, $12)
- Column input: SME price ($15, $18, $20, $25)
- Output: Year 1 profit

### 3. Goal Seek

**Find break-even customer count:**
- Extensions → Add-ons → Get add-ons → "Goal Seek"
- Set cell: Net Profit (target $0)
- By changing: Total Customers
- Result: Break-even customer count

### 4. Automated Alerts

**Get notified when metrics go red:**
1. Tools → Notification rules
2. Condition: "A cell formula in this sheet is updated"
3. Notify me: "With email - daily digest"
4. Set up alerts for:
   - Cash balance < $1,000
   - Churn rate > 5%
   - CAC > $100

---

## Sharing & Collaboration

### Share with Team

**View-only for most:**
- Click Share → Add people
- Dropdown: "Viewer" (can't edit)

**Edit access for finance lead:**
- Role: "Editor" (can update actuals)
- Protected ranges: Lock "Assumptions" sheet except for actuals

### Version Control

**Create monthly snapshots:**
1. File → Make a copy
2. Name: "SaaSOdoo Financial - Jan 2025 Snapshot"
3. Keep in same folder
4. Update "Master" copy each month

### Link to Other Docs

**Add links in Dashboard sheet:**
- Business plan doc
- Customer interview notes
- Marketing campaign tracker
- Pricing research

---

## Next Steps After Setup

✅ **Week 1:** Set up sheets, import data, test formulas
✅ **Week 2:** Validate assumptions with customer interviews
✅ **Week 3:** Adjust pricing based on feedback
✅ **Week 4:** Finalize model, share with advisors

**Monthly routine:**
1. Update actuals
2. Review KPIs
3. Adjust assumptions if needed
4. Export snapshot
5. Share with team

---

## Support & Resources

**Google Sheets Help:**
- Templates: https://sheets.google.com/template/gallery
- Function list: https://support.google.com/docs/table/25273
- Formulas tutorial: Search "Google Sheets formulas tutorial"

**Financial Model Best Practices:**
- Keep it simple (you'll actually use it)
- Update monthly (garbage in = garbage out)
- One source of truth (don't duplicate in multiple docs)
- Document assumptions (why did you choose 4% churn?)

---

**Ready to build? Start with importing the CSV files I'll create next!**
