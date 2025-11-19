# SaaSOdoo Comprehensive Financial Model Guide
**Building Your Excel-Based Financial Model**

Version: 2.0
Date: 2025-11-19
Purpose: Step-by-step guide to build a comprehensive financial model in Excel

---

## Table of Contents

1. [Overview & Purpose](#overview--purpose)
2. [Model Architecture](#model-architecture)
3. [Core Assumptions](#core-assumptions)
4. [Infrastructure Tables](#infrastructure-tables)
5. [Revenue Tables](#revenue-tables)
6. [Cost Tables](#cost-tables)
7. [Financial Metrics](#financial-metrics)
8. [Technical Metrics](#technical-metrics)
9. [Decision Triggers & Milestones](#decision-triggers--milestones)
10. [Dashboard Design](#dashboard-design)
11. [Scenario Planning](#scenario-planning)

---

## Overview & Purpose

### What This Model Does

This financial model is designed to:
- **Link infrastructure costs to customer count** (pod-based costing)
- **Forecast revenue** based on customer acquisition and pricing tiers
- **Calculate profitability** at different scales
- **Track technical capacity** (RAM, CPU, storage) against customer demand
- **Trigger decisions** when reaching milestones (e.g., "migrate to next pod at 35 customers")
- **Support scenario planning** (what if churn is higher? what if pricing changes?)

### Key Principle: Pod-Based Cost Model

Unlike traditional SaaS models where costs scale linearly, SaaSOdoo uses **stepped infrastructure costs**:
- 1-50 customers = $21/month (MVP Pod)
- 51-150 customers = $141/month (Growth Pod)
- 151-500 customers = $447/month (Scale Pod)

Your financial model must **automatically select the right pod** based on customer count.

---

## Model Architecture

### Recommended Workbook Structure

Create an Excel workbook with the following sheets (tabs):

| Sheet Name | Purpose | References |
|------------|---------|------------|
| **1. Assumptions** | All inputs and assumptions | Referenced by all other sheets |
| **2. Pod Specs** | Infrastructure specifications by phase | Used by Cost Model |
| **3. Customer Mix** | Distribution of customers across tiers | Used by Revenue Model |
| **4. Revenue Model** | Monthly revenue projections (36 months) | Core financial output |
| **5. Cost Model** | Infrastructure + COGS by customer tier | Core financial output |
| **6. OpEx Model** | Operating expenses by category | Core financial output |
| **7. P&L** | Profit & Loss statement (monthly + annual) | Combines Revenue, Costs, OpEx |
| **8. Cash Flow** | Cash flow projections | Uses P&L + timing adjustments |
| **9. Unit Economics** | LTV, CAC, payback period, etc. | Calculated metrics |
| **10. Technical Metrics** | CPU, RAM, storage utilization | Capacity planning |
| **11. Decision Dashboard** | Visual dashboard with triggers | Summary of all sheets |
| **12. Scenarios** | What-if analysis | Copies of key assumptions |

---

## Core Assumptions

### SHEET 1: Assumptions

This is your **control panel**. All other sheets reference this sheet for inputs.

#### Table 1A: Pricing Assumptions

**Columns:**
- Tier Name (Hustler, SME, Business, Enterprise)
- Monthly Price ($)
- Annual Price ($)
- Annual Discount (%)
- Trial Duration (days)
- Default Trial Enabled (Yes/No)

**Rows:** One row per pricing tier

**Example:**
```
| Tier      | Monthly | Annual | Discount | Trial Days | Trial Enabled |
|-----------|---------|--------|----------|------------|---------------|
| Hustler   | 8       | 80     | 16.7%    | 14         | Yes           |
| SME       | 18      | 180    | 16.7%    | 14         | Yes           |
| Business  | 35      | 350    | 16.7%    | 14         | Yes           |
| Enterprise| 75      | 750    | 16.7%    | 0          | No            |
```

**Calculations:**
- **Annual Discount %**: Calculate as `(Monthly Price × 12 - Annual Price) / (Monthly Price × 12)`
- **Monthly Equivalent (Annual)**: `Annual Price / 12`

---

#### Table 1B: Resource Allocation by Tier

**Columns:**
- Tier Name
- Advertised vCPU
- Advertised RAM (GB)
- Advertised Storage (GB)
- Actual Average RAM Usage (MB)
- Actual Average CPU Usage (cores)
- Actual Average Storage Usage (GB)
- Overselling Ratio RAM
- Overselling Ratio CPU

**Rows:** One row per tier

**Example:**
```
| Tier     | vCPU | RAM  | Storage | Avg RAM | Avg CPU | Avg Storage | Oversell RAM | Oversell CPU |
|----------|------|------|---------|---------|---------|-------------|--------------|--------------|
| Hustler  | 1    | 2GB  | 10GB    | 400MB   | 0.2     | 5GB         | 5:1          | 5:1          |
| SME      | 2    | 4GB  | 20GB    | 800MB   | 0.4     | 12GB        | 5:1          | 5:1          |
| Business | 4    | 8GB  | 50GB    | 1600MB  | 0.8     | 30GB        | 5:1          | 5:1          |
```

**Calculations:**
- **Overselling Ratio**: `Advertised Resource / Actual Average Usage`
  - Example: Hustler RAM = 2GB / 0.4GB = 5:1
- **These ratios determine how many customers you can fit on each pod**

---

#### Table 1C: Growth Assumptions

**Columns:**
- Metric Name
- Year 1 Value
- Year 2 Value
- Year 3 Value
- Notes

**Rows:**
- Starting Customers
- New Customers Per Month (Avg)
- Monthly Churn Rate (%)
- Annual Plan Adoption Rate (%)
- Trial to Paid Conversion Rate (%)
- Customer Mix - Hustler (%)
- Customer Mix - SME (%)
- Customer Mix - Business (%)
- Customer Mix - Enterprise (%)

**Example:**
```
| Metric                      | Year 1 | Year 2 | Year 3 | Notes                    |
|-----------------------------|--------|--------|--------|--------------------------|
| Starting Customers          | 0      | 150    | 500    | End of previous year     |
| New Customers/Month (Avg)   | 12.5   | 29     | 42     | Accelerates over time    |
| Monthly Churn Rate          | 4.2%   | 3.0%   | 2.5%   | Improves with maturity   |
| Annual Plan Adoption        | 20%    | 25%    | 30%    | Incentivize annual plans |
| Trial → Paid Conversion     | 25%    | 30%    | 35%    | Improves with product    |
| Customer Mix - Hustler      | 60%    | 50%    | 40%    | Decreases as you mature  |
| Customer Mix - SME          | 35%    | 40%    | 45%    | Sweet spot               |
| Customer Mix - Business     | 5%     | 9%     | 13%    | Upsells over time        |
| Customer Mix - Enterprise   | 0%     | 1%     | 2%     | Future expansion         |
```

**Calculations:**
- **Customer Mix must sum to 100%** for each year
- **Churn Rate**: Industry benchmark is 3-5% monthly for SMB SaaS
- **Annual Plan Adoption**: Higher is better for cash flow

---

#### Table 1D: Cost Assumptions

**Columns:**
- Cost Category
- Year 1 ($/month)
- Year 2 ($/month)
- Year 3 ($/month)
- Unit Type (fixed/variable/step)

**Rows:**
- Payment Processing Fee (%)
- Support Cost per Hustler Customer ($/mo)
- Support Cost per SME Customer ($/mo)
- Support Cost per Business Customer ($/mo)
- Backup Cost per GB ($/mo)
- Bandwidth Cost per GB ($/mo)
- Platform Overhead per Customer ($/mo)

**Example:**
```
| Cost Category               | Year 1 | Year 2 | Year 3 | Unit Type |
|-----------------------------|--------|--------|--------|-----------|
| Payment Processing Fee      | 2.5%   | 2.5%   | 2.2%   | Variable  |
| Support - Hustler           | 1.00   | 0.80   | 0.60   | Variable  |
| Support - SME               | 2.00   | 1.70   | 1.50   | Variable  |
| Support - Business          | 5.00   | 4.50   | 4.00   | Variable  |
| Support - Enterprise        | 15.00  | 13.00  | 12.00  | Variable  |
| Backup Cost per GB          | 0.03   | 0.03   | 0.03   | Variable  |
| Bandwidth per GB            | 0.02   | 0.02   | 0.02   | Variable  |
| Platform Overhead/Customer  | 0.50   | 0.45   | 0.40   | Variable  |
```

**Calculations:**
- **Support costs decrease over time** due to improved documentation, self-service, automation
- **Payment processing may decrease** as you negotiate volume discounts

---

#### Table 1E: Operating Expense Assumptions

**Columns:**
- Expense Category
- Year 1 ($/month avg)
- Year 2 ($/month avg)
- Year 3 ($/month avg)
- Scaling Trigger

**Rows:**
- Software & Services
- Personnel - Technical
- Personnel - Support
- Personnel - Sales & Marketing
- Personnel - Admin/Finance
- Marketing & Advertising
- Legal & Compliance
- Office & Misc

**Example:**
```
| Category              | Year 1 | Year 2 | Year 3 | Trigger                        |
|-----------------------|--------|--------|--------|--------------------------------|
| Software & Services   | 50     | 100    | 200    | Monitoring, email, analytics   |
| Personnel - Technical | 500    | 2000   | 4500   | Hire at $2k MRR, $5k MRR       |
| Personnel - Support   | 300    | 800    | 1500   | Hire at $1k MRR, $4k MRR       |
| Personnel - Sales/Mktg| 0      | 500    | 1500   | Hire at $8k MRR                |
| Personnel - Admin     | 0      | 0      | 500    | Hire at 750+ customers         |
| Marketing & Ads       | 250    | 1000   | 2000   | Scale with revenue             |
| Legal & Compliance    | 100    | 300    | 500    | One-time + recurring           |
| Office & Misc         | 0      | 0      | 300    | If hiring office space         |
```

**Calculations:**
- **Personnel costs are stepped functions** (hire when you hit MRR trigger)
- **Marketing scales with revenue** (maintain 10-15% of revenue for growth mode)

---

## Infrastructure Tables

### SHEET 2: Pod Specs

This sheet defines **infrastructure configurations** for each growth phase.

#### Table 2A: Pod Specifications

**Columns:**
- Pod Name
- Customer Range (Min)
- Customer Range (Max)
- Node Type
- Node Description
- Quantity
- vCPU per Node
- RAM per Node (GB)
- Storage per Node (GB)
- Price per Node ($/month)
- Extended Cost (Quantity × Price)

**Rows:** One row per node type per pod

**Example:**
```
| Pod   | Min | Max | Node Type      | Description        | Qty | vCPU | RAM | Storage | Price | Extended |
|-------|-----|-----|----------------|--------------------|-----|------|-----|---------|-------|----------|
| MVP-A | 0   | 25  | STORAGE VPS 10 | CephFS storage     | 3   | 2    | 4   | 300     | 4.95  | 14.85    |
| MVP-A | 0   | 25  | CLOUD VPS 20   | Compute            | 1   | 6    | 12  | 100     | 7.95  | 7.95     |
| MVP-A | 0   | 25  | Private Network| Network            | 4   | -    | -   | -       | 2.99  | 11.96    |
| MVP-A | 0   | 25  | FTP Backup     | 100GB backup       | 1   | -    | -   | 100     | 5.79  | 5.79     |
| MVP-B | 0   | 50  | CLOUD VPS 30   | Compute + Storage  | 1   | 8    | 24  | 200     | 15.00 | 15.00    |
| MVP-B | 0   | 50  | FTP Backup     | 100GB backup       | 1   | -    | -   | 100     | 5.79  | 5.79     |
| Growth| 51  | 150 | CLOUD VPS 40   | Compute            | 2   | 12   | 48  | 250     | 26.00 | 52.00    |
| Growth| 51  | 150 | STORAGE VPS 30 | CephFS storage     | 3   | 6    | 18  | 1000    | 15.00 | 45.00    |
| Growth| 51  | 150 | CLOUD VPS 20   | Platform services  | 1   | 6    | 12  | 100     | 7.95  | 7.95     |
| Growth| 51  | 150 | Private Network| Network            | 6   | -    | -   | -       | 2.99  | 17.94    |
| Growth| 51  | 150 | FTP Backup     | 500GB backup       | 1   | -    | -   | 500     | 18.39 | 18.39    |
| Scale | 151 | 500 | CLOUD VDS M    | Physical CPU       | 4   | 4    | 32  | 240     | 68.99 | 275.96   |
| Scale | 151 | 500 | STORAGE VPS 40 | CephFS storage     | 3   | 8    | 30  | 1200    | 26.00 | 78.00    |
| Scale | 151 | 500 | CLOUD VPS 30   | Platform           | 1   | 8    | 24  | 200     | 15.00 | 15.00    |
| Scale | 151 | 500 | CLOUD VPS 10   | Load balancer      | 1   | 3    | 8   | 75      | 4.95  | 4.95     |
| Scale | 151 | 500 | Private Network| Network            | 9   | -    | -   | -       | 2.99  | 26.91    |
| Scale | 151 | 500 | FTP Backup     | 2TB backup         | 1   | -    | -   | 2000    | 45.99 | 45.99    |
```

**Calculations:**
- **Extended Cost**: `Quantity × Price per Node`
- **Total Pod Cost**: Sum all Extended Costs for that pod

---

#### Table 2B: Pod Summary

**Columns:**
- Pod Name
- Customer Range
- Total Monthly Cost
- Total vCPU (compute nodes only)
- Total RAM (compute nodes only, GB)
- Total Storage (GB)
- System Overhead RAM (GB)
- Available RAM for Customers (GB)
- Max Hustler Capacity (based on RAM)
- Max SME Capacity
- Max Business Capacity
- Recommended Mixed Capacity
- Revenue at Capacity ($)
- Infrastructure Margin at Capacity (%)

**Rows:** One row per pod option

**Example:**
```
| Pod   | Range    | Cost  | vCPU | RAM | Storage | Overhead | Avail RAM | Max Hustler | Max SME | Max Business | Mixed | Revenue | Margin |
|-------|----------|-------|------|-----|---------|----------|-----------|-------------|---------|--------------|-------|---------|--------|
| MVP-A | 0-25     | 40.55 | 6    | 12  | 900     | 3        | 9         | 22          | 11      | 5            | 25    | 364     | 89%    |
| MVP-B | 0-50     | 20.79 | 8    | 24  | 200     | 4        | 20        | 50          | 25      | 12           | 35    | 509     | 96%    |
| Growth| 51-150   | 141.28| 24   | 96  | 3000    | 16       | 80        | 200         | 100     | 50           | 150   | 2182    | 94%    |
| Scale | 151-500  | 446.81| 16   | 128 | 4200    | 20       | 108       | 270         | 135     | 67           | 500   | 7275    | 94%    |
```

**Calculations:**
- **Total vCPU**: Sum of vCPU across all compute nodes (exclude storage, network, backup)
- **Total RAM**: Sum of RAM across all compute nodes
- **System Overhead**: Approximately 15-20% of total RAM for OS, platform services
- **Available RAM**: `Total RAM - System Overhead`
- **Max Hustler Capacity**: `(Available RAM × 1024 MB) / Average Hustler RAM Usage`
  - Example: `(20 GB × 1024) / 400 MB = 51.2` → round to 50
- **Max SME Capacity**: `(Available RAM × 1024) / Average SME RAM Usage`
- **Max Business Capacity**: `(Available RAM × 1024) / Average Business RAM Usage`
- **Recommended Mixed Capacity**: Conservative estimate based on 60% Hustler, 35% SME, 5% Business mix
  - Formula: `Available RAM / ((0.6 × Hustler RAM) + (0.35 × SME RAM) + (0.05 × Business RAM))`
- **Revenue at Capacity**: `(Recommended Mixed Capacity) × (Weighted Average ARPU)`
- **Infrastructure Margin**: `(Revenue at Capacity - Total Monthly Cost) / Revenue at Capacity`

---

#### Table 2C: Pod Selection Logic (Helper Table)

**Columns:**
- Current Customer Count (input)
- Selected Pod Name
- Monthly Infrastructure Cost
- Remaining Capacity (customers)
- Capacity Utilization (%)
- Next Pod Trigger (customers)
- Estimated Months Until Migration

**Rows:** One row (dynamic)

**Example:**
```
| Current Customers | Selected Pod | Cost   | Remaining | Utilization | Next Trigger | Months to Migration |
|-------------------|--------------|--------|-----------|-------------|--------------|---------------------|
| 45                | MVP-B        | 20.79  | -10       | 129%        | 51           | 0.6                 |
```

**Calculations:**
- **Selected Pod**: Use IF/VLOOKUP to match customer count to pod range
  - Logic: "If customers between Min and Max, select this pod"
- **Monthly Infrastructure Cost**: Lookup from Table 2B based on Selected Pod
- **Remaining Capacity**: `Pod Max Capacity - Current Customer Count`
- **Capacity Utilization**: `Current Customer Count / Pod Max Capacity`
- **Next Pod Trigger**: The customer count where you need to migrate (Max of current pod + 1)
- **Months Until Migration**: `(Next Pod Trigger - Current Customers) / Avg New Customers Per Month`

---

## Revenue Tables

### SHEET 3: Customer Mix

#### Table 3A: Monthly Customer Mix Projection

**Columns:**
- Month (1-36)
- Date (optional, for reference)
- New Customers Added
- Churned Customers
- **Total Customers (End of Month)**
- Hustler Count
- Hustler %
- SME Count
- SME %
- Business Count
- Business %
- Enterprise Count
- Enterprise %

**Rows:** 36 rows (one per month for 3 years)

**Example (Months 1-6):**
```
| Month | Date    | New | Churned | Total | Hustler | H%  | SME | S%  | Business | B%  | Enterprise | E%  |
|-------|---------|-----|---------|-------|---------|-----|-----|-----|----------|-----|------------|-----|
| 1     | Jan-26  | 5   | 0       | 5     | 4       | 80% | 1   | 20% | 0        | 0%  | 0          | 0%  |
| 2     | Feb-26  | 7   | 0       | 12    | 8       | 67% | 4   | 33% | 0        | 0%  | 0          | 0%  |
| 3     | Mar-26  | 10  | 1       | 21    | 14      | 67% | 6   | 29% | 1        | 5%  | 0          | 0%  |
| 4     | Apr-26  | 12  | 1       | 32    | 21      | 66% | 10  | 31% | 1        | 3%  | 0          | 0%  |
| 5     | May-26  | 15  | 2       | 45    | 28      | 62% | 15  | 33% | 2        | 4%  | 0          | 0%  |
| 6     | Jun-26  | 18  | 3       | 60    | 38      | 63% | 19  | 32% | 3        | 5%  | 0          | 0%  |
```

**Calculations:**
- **Total Customers**: `Previous Month Total + New Customers - Churned Customers`
- **Churned Customers**: `Previous Month Total × Monthly Churn Rate`
  - Lookup churn rate from Assumptions sheet based on which year you're in
- **Tier Distribution**: Apply percentages from Assumptions (Table 1C)
  - **Hustler Count**: `Total Customers × Hustler %`
  - **SME Count**: `Total Customers × SME %`
  - **Business Count**: `Total Customers × Business %`
  - **Enterprise Count**: `Total Customers × Enterprise %`
- **Validation**: Ensure `Hustler % + SME % + Business % + Enterprise % = 100%`

---

### SHEET 4: Revenue Model

#### Table 4A: Monthly Recurring Revenue (MRR)

**Columns:**
- Month
- Date
- Total Customers
- Hustler Revenue
- SME Revenue
- Business Revenue
- Enterprise Revenue
- **Total MRR**
- **Month-over-Month Growth ($)**
- **Month-over-Month Growth (%)**
- **Annual Run Rate (ARR)**

**Rows:** 36 rows (one per month)

**Example:**
```
| Month | Date    | Customers | Hustler | SME  | Business | Enterprise | MRR  | MoM $ | MoM % | ARR   |
|-------|---------|-----------|---------|------|----------|------------|------|-------|-------|-------|
| 1     | Jan-26  | 5         | 32      | 18   | 0        | 0          | 50   | -     | -     | 600   |
| 2     | Feb-26  | 12        | 64      | 72   | 0        | 0          | 136  | 86    | 172%  | 1632  |
| 3     | Mar-26  | 21        | 112     | 108  | 35       | 0          | 255  | 119   | 88%   | 3060  |
| 4     | Apr-26  | 32        | 168     | 180  | 35       | 0          | 383  | 128   | 50%   | 4596  |
| 5     | May-26  | 45        | 224     | 270  | 70       | 0          | 564  | 181   | 47%   | 6768  |
| 6     | Jun-26  | 60        | 304     | 342  | 105      | 0          | 751  | 187   | 33%   | 9012  |
```

**Calculations:**
- **Hustler Revenue**: `Hustler Count × Hustler Monthly Price`
  - Pull Hustler Count from Customer Mix sheet
  - Pull Monthly Price from Assumptions
- **SME Revenue**: `SME Count × SME Monthly Price`
- **Business Revenue**: `Business Count × Business Monthly Price`
- **Enterprise Revenue**: `Enterprise Count × Enterprise Monthly Price`
- **Total MRR**: `SUM(Hustler Revenue, SME Revenue, Business Revenue, Enterprise Revenue)`
- **MoM Growth ($)**: `Current Month MRR - Previous Month MRR`
- **MoM Growth (%)**: `MoM Growth ($) / Previous Month MRR`
- **ARR (Annual Run Rate)**: `MRR × 12`

---

#### Table 4B: Annual Subscriptions

**Columns:**
- Month
- New Annual Subscriptions (count)
- Annual Subscription Revenue (cash received this month)
- Cumulative Annual Subscribers
- % of Total Customers on Annual Plans

**Rows:** 36 rows

**Example:**
```
| Month | New Annual Subs | Annual Revenue Cash | Cumulative Annual | % Annual |
|-------|-----------------|---------------------|-------------------|----------|
| 1     | 1               | 80                  | 1                 | 20%      |
| 2     | 1               | 180                 | 2                 | 17%      |
| 3     | 2               | 430                 | 4                 | 19%      |
| 4     | 2               | 510                 | 6                 | 19%      |
| 5     | 3               | 690                 | 9                 | 20%      |
| 6     | 4               | 900                 | 13                | 22%      |
```

**Calculations:**
- **New Annual Subscriptions**: `New Customers × Annual Plan Adoption Rate`
  - Apply tier mix to determine how many are Hustler ($80), SME ($180), Business ($350)
- **Annual Revenue Cash**: Sum of all annual payments received this month
  - Example: 1 Hustler annual ($80) + 1 SME annual ($180) = $260
- **Cumulative Annual Subscribers**: Running total of customers on annual plans
- **% Annual**: `Cumulative Annual Subscribers / Total Customers`

---

#### Table 4C: Total Revenue (MRR + Annual)

**Columns:**
- Month
- MRR (recurring monthly subscriptions)
- Annual Subscription Cash (prepayments)
- **Total Cash Revenue**
- Cumulative Revenue (running total)

**Rows:** 36 rows

**Example:**
```
| Month | MRR  | Annual Cash | Total Cash | Cumulative |
|-------|------|-------------|------------|------------|
| 1     | 50   | 80          | 130        | 130        |
| 2     | 136  | 180         | 316        | 446        |
| 3     | 255  | 430         | 685        | 1131       |
| 4     | 383  | 510         | 893        | 2024       |
| 5     | 564  | 690         | 1254       | 3278       |
| 6     | 751  | 900         | 1651       | 4929       |
```

**Calculations:**
- **Total Cash Revenue**: `MRR + Annual Subscription Cash`
- **Cumulative Revenue**: Running sum of Total Cash Revenue
  - `Previous Month Cumulative + Current Month Total Cash`

---

## Cost Tables

### SHEET 5: Cost Model

#### Table 5A: Infrastructure Costs (Pod-Based)

**Columns:**
- Month
- Total Customers (from Customer Mix)
- **Selected Pod**
- **Monthly Infrastructure Cost**
- Cost Per Customer (infrastructure)
- Cumulative Infrastructure Spend

**Rows:** 36 rows

**Example:**
```
| Month | Customers | Selected Pod | Infra Cost | Cost/Customer | Cumulative |
|-------|-----------|--------------|------------|---------------|------------|
| 1     | 5         | MVP-B        | 20.79      | 4.16          | 20.79      |
| 2     | 12        | MVP-B        | 20.79      | 1.73          | 41.58      |
| 3     | 21        | MVP-B        | 20.79      | 0.99          | 62.37      |
| 4     | 32        | MVP-B        | 20.79      | 0.65          | 83.16      |
| 5     | 45        | MVP-B        | 20.79      | 0.46          | 103.95     |
| 6     | 60        | Growth       | 141.28     | 2.35          | 245.23     |
```

**Calculations:**
- **Selected Pod**: Use IF logic or VLOOKUP
  - If Customers <= 50: "MVP-B"
  - If Customers between 51-150: "Growth"
  - If Customers between 151-500: "Scale"
- **Monthly Infrastructure Cost**: Lookup from Pod Specs (Table 2B) based on Selected Pod
- **Cost Per Customer**: `Monthly Infrastructure Cost / Total Customers`
- **Cumulative Infrastructure Spend**: Running sum

---

#### Table 5B: Variable COGS by Tier

**Columns:**
- Month
- Tier (Hustler/SME/Business/Enterprise)
- Customer Count
- Storage Cost (total for all customers in tier)
- Backup Cost
- Bandwidth Cost
- Payment Processing Cost
- Support Cost (allocated)
- Platform Overhead
- **Total COGS for Tier**
- **COGS per Customer**

**Rows:** 36 months × 4 tiers = 144 rows (or separate tables per tier)

**Example for Month 6 - Hustler Tier:**
```
| Month | Tier    | Count | Storage | Backup | Bandwidth | Payment | Support | Overhead | Total COGS | COGS/Cust |
|-------|---------|-------|---------|--------|-----------|---------|---------|----------|------------|-----------|
| 6     | Hustler | 38    | 7.60    | 5.70   | 1.90      | 7.60    | 38.00   | 15.20    | 76.00      | 2.00      |
| 6     | SME     | 19    | 9.50    | 5.70   | 1.90      | 8.55    | 38.00   | 12.35    | 76.00      | 4.00      |
| 6     | Business| 3     | 4.50    | 2.25   | 0.60      | 2.64    | 15.00   | 3.51     | 28.50      | 9.50      |
```

**Calculations for each tier:**
- **Storage Cost**: `Customer Count × Storage Usage × Cost per GB`
  - Example Hustler: `38 × 5 GB × $0.03/GB = $5.70`
- **Backup Cost**: `Customer Count × (Storage Usage × 1.5 for compression) × Backup Cost per GB`
- **Bandwidth Cost**: Estimate based on typical Odoo usage (10-20 GB/customer/month)
  - `Customer Count × Avg GB × Cost per GB`
- **Payment Processing**: `Tier Revenue × Payment Processing %`
  - Example: Hustler Revenue = 38 × $8 = $304; Processing = $304 × 2.5% = $7.60
- **Support Cost**: `Customer Count × Support Cost per Customer (from Assumptions)`
  - Example: `38 × $1.00 = $38.00`
- **Platform Overhead**: `Customer Count × Platform Overhead per Customer`
- **Total COGS**: Sum all costs
- **COGS per Customer**: `Total COGS / Customer Count`

---

#### Table 5C: Monthly COGS Summary

**Columns:**
- Month
- Infrastructure Cost (from Table 5A)
- Hustler COGS (from Table 5B)
- SME COGS
- Business COGS
- Enterprise COGS
- **Total COGS**
- Total Revenue (from Revenue Model)
- **Gross Profit**
- **Gross Margin %**

**Rows:** 36 rows

**Example:**
```
| Month | Infra | Hustler | SME  | Business | Enterprise | Total COGS | Revenue | Gross Profit | Margin % |
|-------|-------|---------|------|----------|------------|------------|---------|--------------|----------|
| 6     | 21    | 76      | 76   | 29       | 0          | 202        | 751     | 549          | 73%      |
| 12    | 141   | 180     | 260  | 90       | 0          | 671        | 1936    | 1265         | 65%      |
| 24    | 141   | 500     | 800  | 517      | 150        | 2108       | 7275    | 5167         | 71%      |
| 36    | 447   | 800     | 1350 | 1495     | 300        | 4392       | 14550   | 10158        | 70%      |
```

**Calculations:**
- **Total COGS**: `Infrastructure + SUM(all tier COGS)`
- **Gross Profit**: `Total Revenue - Total COGS`
- **Gross Margin %**: `Gross Profit / Total Revenue`

---

### SHEET 6: OpEx Model

#### Table 6A: Operating Expenses by Category

**Columns:**
- Month
- Software & Services
- Personnel - Technical
- Personnel - Support
- Personnel - Sales & Marketing
- Personnel - Admin
- Marketing & Advertising
- Legal & Compliance
- Office & Miscellaneous
- **Total OpEx**

**Rows:** 36 rows

**Example:**
```
| Month | Software | Tech  | Support | Sales | Admin | Marketing | Legal | Office | Total OpEx |
|-------|----------|-------|---------|-------|-------|-----------|-------|--------|------------|
| 1     | 50       | 0     | 0       | 0     | 0     | 200       | 100   | 0      | 350        |
| 2     | 50       | 0     | 0       | 0     | 0     | 200       | 0     | 0      | 250        |
| 3     | 50       | 0     | 0       | 0     | 0     | 250       | 0     | 0      | 300        |
| 4     | 50       | 0     | 300     | 0     | 0     | 250       | 0     | 0      | 600        |
| 9     | 50       | 500   | 300     | 0     | 0     | 500       | 0     | 0      | 1350       |
| 18    | 100      | 2000  | 800     | 500   | 0     | 1000      | 300   | 0      | 4700       |
| 36    | 200      | 4500  | 1500    | 1500  | 500   | 2000      | 500   | 300    | 11000      |
```

**Calculations:**
- **Each category uses IF logic based on triggers**
  - Example for Technical Personnel:
    - IF MRR < $2,000: $0
    - IF MRR >= $2,000 AND < $5,000: $500 (part-time)
    - IF MRR >= $5,000: $2,000 (full-time developer)
    - IF MRR >= $10,000: $4,500 (3 developers + DevOps)
- **Marketing & Advertising**: Can be a % of revenue (10-15%) or fixed budget
  - Formula: `MAX(Fixed Budget, Revenue × 10%)`
- **Legal & Compliance**: Often one-time costs in certain months
  - Month 1: Entity formation ($500)
  - Month 6: Trademark filing ($300)
  - Ongoing: $50/month for compliance services

---

## Financial Metrics

### SHEET 7: P&L (Profit & Loss)

#### Table 7A: Monthly P&L

**Columns:**
- Month
- Date
- **Revenue**
  - MRR
  - Annual Prepayments
  - Total Revenue
- **Cost of Goods Sold**
  - Infrastructure
  - Variable COGS
  - Total COGS
- **Gross Profit**
- **Gross Margin %**
- **Operating Expenses**
  - Software
  - Personnel
  - Marketing
  - Other
  - Total OpEx
- **EBITDA (Earnings Before Interest, Tax, Depreciation, Amortization)**
- **EBITDA Margin %**
- **Net Profit** (assuming no interest/tax initially)
- **Net Margin %**

**Rows:** 36 rows + quarterly/annual summaries

**Example:**
```
| Month | Revenue | COGS | Gross Profit | Margin % | OpEx  | EBITDA | EBITDA % | Net Profit | Net % |
|-------|---------|------|--------------|----------|-------|--------|----------|------------|-------|
| 1     | 130     | 76   | 54           | 42%      | 350   | -296   | -228%    | -296       | -228% |
| 6     | 1651    | 202  | 1449         | 88%      | 850   | 599    | 36%      | 599        | 36%   |
| 12    | 4120    | 671  | 3449         | 84%      | 1350  | 2099   | 51%      | 2099       | 51%   |
| 24    | 11730   | 2108 | 9622         | 82%      | 4700  | 4922   | 42%      | 4922       | 42%   |
| 36    | 22800   | 4392 | 18408        | 81%      | 11000 | 7408   | 32%      | 7408       | 32%   |
```

**Calculations:**
- **Gross Profit**: `Revenue - COGS`
- **Gross Margin %**: `Gross Profit / Revenue`
- **EBITDA**: `Gross Profit - Total OpEx`
- **EBITDA Margin %**: `EBITDA / Revenue`
- **Net Profit**: `EBITDA` (initially same, later subtract interest/taxes)
- **Net Margin %**: `Net Profit / Revenue`

---

#### Table 7B: Annual P&L Summary

**Columns:**
- Year
- Total Revenue
- Total COGS
- Gross Profit
- Gross Margin %
- Total OpEx
- EBITDA
- EBITDA Margin %
- Net Profit
- Net Margin %

**Rows:** 3 rows (Year 1, 2, 3)

**Example:**
```
| Year | Revenue | COGS   | Gross Profit | Margin % | OpEx   | EBITDA  | EBITDA % | Net Profit | Net % |
|------|---------|--------|--------------|----------|--------|---------|----------|------------|-------|
| 1    | 24,300  | 7,290  | 17,010       | 70%      | 14,652 | 2,358   | 9.7%     | 2,358      | 9.7%  |
| 2    | 105,000 | 31,500 | 73,500       | 70%      | 58,092 | 15,408  | 14.7%    | 15,408     | 14.7% |
| 3    | 350,000 | 105,000| 245,000      | 70%      | 127,764| 117,236 | 33.5%    | 117,236    | 33.5% |
```

**Calculations:**
- **Sum all monthly values for each year**
- **Margins calculated from annual totals**

---

### SHEET 8: Cash Flow

#### Table 8A: Monthly Cash Flow Statement

**Columns:**
- Month
- **Cash from Operations**
  - Revenue (cash received)
  - COGS paid
  - OpEx paid
  - Net Cash from Operations
- **Cash from Investing** (if any equipment/assets)
- **Cash from Financing** (if taking loans/investment)
- **Net Change in Cash**
- **Beginning Cash Balance**
- **Ending Cash Balance**
- **Months of Runway** (Ending Cash / Avg Monthly Burn)

**Rows:** 36 rows

**Example:**
```
| Month | Revenue | COGS Paid | OpEx Paid | Net Operating | Investing | Financing | Net Change | Begin Cash | End Cash | Runway |
|-------|---------|-----------|-----------|---------------|-----------|-----------|------------|------------|----------|--------|
| 1     | 130     | -76       | -350      | -296          | 0         | 1000      | 704        | 1000       | 1704     | 4.8    |
| 2     | 316     | -83       | -250      | -17           | 0         | 0         | -17        | 1704       | 1687     | 6.7    |
| 3     | 685     | -91       | -300      | 294           | 0         | 0         | 294        | 1687       | 1981     | 6.6    |
| 6     | 1651    | -202      | -850      | 599           | 0         | 0         | 599        | 3200       | 3799     | 4.5    |
| 12    | 4120    | -671      | -1350     | 2099          | 0         | 0         | 2099       | 7500       | 9599     | 7.1    |
```

**Calculations:**
- **Net Cash from Operations**: `Revenue - COGS Paid - OpEx Paid`
- **Net Change in Cash**: `Net Operating + Investing + Financing`
- **Ending Cash**: `Beginning Cash + Net Change`
- **Months of Runway**: `Ending Cash / Average Monthly Burn Rate`
  - Burn Rate = Average of last 3 months' negative cash flow (if any)
  - If profitable, show "N/A" or ">12"

---

### SHEET 9: Unit Economics

#### Table 9A: Unit Economics Dashboard

**Columns:**
- Metric Name
- Formula Description
- Year 1 Value
- Year 2 Value
- Year 3 Value
- Industry Benchmark
- Status (Good/Fair/Poor)

**Rows:** Key metrics

**Example:**
```
| Metric                    | Formula                                      | Year 1 | Year 2 | Year 3 | Benchmark   | Status    |
|---------------------------|----------------------------------------------|--------|--------|--------|-------------|-----------|
| ARPU ($/month)            | Weighted avg of tier prices × mix            | 14.55  | 14.55  | 14.55  | $10-50      | Good      |
| Monthly Churn Rate (%)    | Churned / Total customers                    | 4.2%   | 3.0%   | 2.5%   | 3-5%        | Good      |
| Customer Lifetime (mo)    | 1 / Monthly Churn                            | 24     | 33     | 40     | 18-36       | Good      |
| Gross Margin (%)          | (Revenue - COGS) / Revenue                   | 70%    | 70%    | 70%    | 70-85%      | Good      |
| LTV ($)                   | ARPU × Lifetime × Gross Margin               | 244    | 336    | 408    | $200-1000   | Fair      |
| CAC ($)                   | Marketing Spend / New Customers              | 60     | 50     | 45     | $50-200     | Good      |
| LTV:CAC Ratio             | LTV / CAC                                    | 4.1    | 6.7    | 9.1    | >3:1        | Excellent |
| Payback Period (months)   | CAC / (ARPU × Gross Margin)                  | 4.1    | 3.4    | 3.1    | <12         | Excellent |
| Annual Retention (%)      | (1 - Monthly Churn)^12                       | 60%    | 70%    | 78%    | 80-95%      | Fair      |
| Net Revenue Retention (%) | (Retained + Expansion - Contraction) / Start | 102%   | 105%   | 110%   | >100%       | Good      |
| Magic Number              | Net New ARR / Sales & Mkt Spend              | 0.8    | 1.2    | 1.5    | >0.75       | Good      |
| Rule of 40                | Growth Rate % + EBITDA Margin %              | 48%    | 62%    | 43%    | >40%        | Excellent |
```

**Calculation Details:**

1. **ARPU (Average Revenue Per User)**
   - Formula: `(Hustler % × Hustler Price) + (SME % × SME Price) + (Business % × Business Price) + (Enterprise % × Enterprise Price)`
   - Example: `(50% × $8) + (40% × $18) + (9% × $35) + (1% × $75) = $14.55`

2. **Monthly Churn Rate**
   - Formula: `Average Monthly Churned Customers / Average Total Customers`
   - Calculate average across the year

3. **Customer Lifetime**
   - Formula: `1 / Monthly Churn Rate`
   - Example: `1 / 0.042 = 23.8 months`

4. **LTV (Lifetime Value)**
   - Formula: `ARPU × Customer Lifetime × Gross Margin %`
   - Example: `$14.55 × 24 months × 70% = $244.44`

5. **CAC (Customer Acquisition Cost)**
   - Formula: `Total Marketing & Sales Spend / Total New Customers Acquired`
   - Example: `$7,200 / 120 new customers = $60`

6. **LTV:CAC Ratio**
   - Formula: `LTV / CAC`
   - Benchmark: >3:1 is good, >5:1 is excellent

7. **Payback Period**
   - Formula: `CAC / (ARPU × Gross Margin)`
   - Example: `$60 / ($14.55 × 70%) = 5.9 months`

8. **Annual Retention Rate**
   - Formula: `(1 - Monthly Churn Rate) ^ 12`
   - Example: `(1 - 0.042)^12 = 0.60 = 60%`

9. **Net Revenue Retention (NRR)**
   - Formula: `(Starting MRR + Expansion - Churn) / Starting MRR`
   - Tracks revenue retention including upgrades/downgrades
   - >100% means expansion exceeds churn

10. **Magic Number**
    - Formula: `Net New ARR (this quarter) / Sales & Marketing Spend (last quarter)`
    - Measures sales efficiency
    - >0.75 is efficient, >1.0 is highly efficient

11. **Rule of 40**
    - Formula: `Revenue Growth Rate % + EBITDA Margin %`
    - Example: `150% growth + 10% EBITDA = 160 (excellent for early stage)`
    - Benchmark: >40 is healthy SaaS

---

## Technical Metrics

### SHEET 10: Technical Metrics

#### Table 10A: Infrastructure Utilization

**Columns:**
- Month
- Total Customers
- Selected Pod
- **RAM Metrics**
  - Total Pod RAM (GB)
  - Used RAM (based on customer mix, MB)
  - Available RAM (GB)
  - RAM Utilization (%)
- **CPU Metrics**
  - Total Pod vCPU
  - Used vCPU (based on customer mix)
  - Available vCPU
  - CPU Utilization (%)
- **Storage Metrics**
  - Total Storage (GB)
  - Used Storage (GB)
  - Available Storage (GB)
  - Storage Utilization (%)

**Rows:** 36 rows

**Example:**
```
| Month | Customers | Pod    | Total RAM | Used RAM  | Avail RAM | RAM % | Total CPU | Used CPU | Avail | CPU % | Total Storage | Used  | Avail | Storage % |
|-------|-----------|--------|-----------|-----------|-----------|-------|-----------|----------|-------|-------|---------------|-------|-------|-----------|
| 1     | 5         | MVP-B  | 24        | 2000 MB   | 22        | 8%    | 8         | 1.0      | 7.0   | 13%   | 200           | 25    | 175   | 13%       |
| 6     | 60        | MVP-B  | 24        | 24000 MB  | 0         | 100%  | 8         | 12.0     | -4.0  | 150%  | 200           | 300   | -100  | 150%      |
| 7     | 77        | Growth | 96        | 30800 MB  | 66        | 32%   | 24        | 15.4     | 8.6   | 64%   | 3000          | 385   | 2615  | 13%       |
| 24    | 500       | Scale  | 128       | 160000 MB | -32       | 125%  | 16        | 100.0    | -84   | 625%  | 4200          | 2500  | 1700  | 60%       |
```

**Calculations:**

1. **Used RAM**
   - Formula: `(Hustler Count × Hustler Avg RAM) + (SME Count × SME Avg RAM) + (Business Count × Business Avg RAM) + (Enterprise Count × Enterprise Avg RAM)`
   - Example Month 6: `(38 × 400 MB) + (19 × 800 MB) + (3 × 1600 MB) = 15,200 + 15,200 + 4,800 = 35,200 MB`
   - Convert to GB: `35,200 MB / 1024 = 34.4 GB`

2. **Available RAM**
   - Formula: `Total Pod RAM - System Overhead - (Used RAM in GB)`
   - System Overhead from Pod Specs table

3. **RAM Utilization %**
   - Formula: `(Used RAM in GB) / (Total Pod RAM - System Overhead) × 100%`

4. **Used vCPU**
   - Formula: `(Hustler Count × Hustler Avg CPU) + (SME Count × SME Avg CPU) + ...`

5. **CPU Utilization %**
   - Formula: `Used vCPU / Total Pod vCPU × 100%`

6. **Used Storage**
   - Formula: `(Hustler Count × Hustler Avg Storage) + (SME Count × SME Avg Storage) + ...`

7. **Storage Utilization %**
   - Formula: `Used Storage / Total Storage × 100%`

**Alert Flags:**
- If RAM Utilization > 80%: **Flag for migration**
- If CPU Utilization > 70%: **Flag for scaling**
- If Storage Utilization > 80%: **Flag for expansion**

---

#### Table 10B: Service Level Metrics

**Columns:**
- Month
- **Uptime Metrics**
  - Target Uptime (%)
  - Actual Uptime (%)
  - Downtime (hours)
  - Incidents (count)
- **Performance Metrics**
  - Avg Response Time (ms)
  - P95 Response Time (ms)
  - Avg Page Load Time (s)
- **Support Metrics**
  - Support Tickets Created
  - Avg Resolution Time (hours)
  - First Response Time (hours)
  - Customer Satisfaction (CSAT %)
- **Reliability Metrics**
  - Failed Deployments (count)
  - Backup Success Rate (%)
  - Data Loss Incidents (count)

**Rows:** 36 rows

**Example:**
```
| Month | Target | Actual | Downtime | Incidents | Avg Resp | P95 Resp | Load Time | Tickets | Res Time | CSAT |
|-------|--------|--------|----------|-----------|----------|----------|-----------|---------|----------|------|
| 1     | 99.0%  | 98.5%  | 3.6      | 2         | 250      | 450      | 2.1       | 15      | 12       | 85%  |
| 6     | 99.5%  | 99.3%  | 1.5      | 1         | 200      | 380      | 1.8       | 90      | 8        | 88%  |
| 12    | 99.7%  | 99.6%  | 0.9      | 1         | 180      | 320      | 1.5       | 225     | 6        | 92%  |
| 24    | 99.9%  | 99.8%  | 0.4      | 0         | 150      | 280      | 1.2       | 750     | 4        | 95%  |
| 36    | 99.95% | 99.9%  | 0.2      | 0         | 120      | 240      | 1.0       | 1500    | 3        | 97%  |
```

**Calculations:**
- **Downtime (hours)**: `(100% - Actual Uptime %) × Hours in Month`
  - Example: `(100% - 99.5%) × 720 hours = 3.6 hours`
- **Support Tickets**: Estimate based on customer count
  - Rule of thumb: 5-10 tickets per month per 100 customers in early stages
  - Formula: `Total Customers × 0.15` (15% of customers submit 1 ticket/month)
- **CSAT (Customer Satisfaction)**: Track via post-resolution surveys
  - Target: >90% by Year 2

---

#### Table 10C: Technical Health Score

**Columns:**
- Month
- Infrastructure Score (0-100)
- Performance Score (0-100)
- Reliability Score (0-100)
- Support Score (0-100)
- **Overall Technical Health (0-100)**
- Status (Red/Yellow/Green)

**Rows:** 36 rows

**Example:**
```
| Month | Infra Score | Perf Score | Reliability | Support | Overall | Status |
|-------|-------------|------------|-------------|---------|---------|--------|
| 1     | 75          | 70         | 80          | 75      | 75      | Yellow |
| 6     | 85          | 82         | 88          | 85      | 85      | Green  |
| 12    | 90          | 88         | 92          | 90      | 90      | Green  |
| 24    | 95          | 92         | 95          | 93      | 94      | Green  |
| 36    | 98          | 95         | 98          | 96      | 97      | Green  |
```

**Scoring Logic:**

1. **Infrastructure Score**
   - RAM Utilization: 0-60% = 100 points, 60-80% = 80 points, 80-100% = 50 points, >100% = 0 points
   - CPU Utilization: Same logic
   - Storage Utilization: Same logic
   - Average the three

2. **Performance Score**
   - Uptime: Match to target = 100, -0.1% = -10 points
   - Avg Response Time: <200ms = 100, 200-400ms = 80, >400ms = 50
   - Average the metrics

3. **Reliability Score**
   - Incidents: 0 = 100, 1 = 90, 2 = 80, 3+ = 50
   - Backup Success: 100% = 100, 99% = 90, <99% = 50
   - Data Loss: 0 = 100, 1+ = 0

4. **Support Score**
   - CSAT: Use as percentage (95% CSAT = 95 points)
   - Resolution Time: <6 hours = 100, 6-12 hours = 80, >12 hours = 60

5. **Overall Technical Health**
   - Formula: `(Infra + Perf + Reliability + Support) / 4`

6. **Status**
   - Green: >85
   - Yellow: 70-85
   - Red: <70

---

## Decision Triggers & Milestones

### SHEET 11: Decision Dashboard (Part 1)

#### Table 11A: Infrastructure Decision Triggers

**Columns:**
- Trigger Name
- Trigger Condition
- Current Value
- Threshold
- Status (OK/Warning/Action Required)
- Recommended Action
- Estimated Timeline
- Estimated Cost

**Rows:** Key triggers

**Example:**
```
| Trigger                  | Condition           | Current | Threshold | Status          | Action                    | Timeline    | Cost   |
|--------------------------|---------------------|---------|-----------|-----------------|---------------------------|-------------|--------|
| Pod Migration - Growth   | Customers >= 51     | 45      | 51        | OK              | Prepare CephFS migration  | 2 months    | +$120  |
| RAM Utilization          | RAM Usage >= 80%    | 68%     | 80%       | OK              | Monitor weekly            | -           | -      |
| CPU Utilization          | CPU Usage >= 70%    | 55%     | 70%       | OK              | Monitor weekly            | -           | -      |
| Storage Utilization      | Storage >= 80%      | 45%     | 80%       | OK              | -                         | -           | -      |
| Pod Migration - Scale    | Customers >= 151    | 45      | 151       | OK              | Plan VDS migration        | 12+ months  | +$306  |
| Backup Failure           | Success Rate < 99%  | 100%    | 99%       | OK              | -                         | -           | -      |
| Uptime SLA Breach        | Uptime < Target     | 99.5%   | 99.5%     | OK              | -                         | -           | -      |
```

**Calculation Logic:**
- **Current Value**: Pull from Technical Metrics sheet
- **Status**:
  - "OK": Current < 90% of Threshold
  - "Warning": Current between 90-100% of Threshold
  - "Action Required": Current >= Threshold
- **Recommended Action**: Pre-defined based on trigger type
- **Estimated Cost**: Difference between current pod cost and next pod cost

---

#### Table 11B: Financial Decision Triggers

**Columns:**
- Trigger Name
- Trigger Condition
- Current Value
- Threshold
- Status
- Recommended Action
- Impact

**Rows:** Key triggers

**Example:**
```
| Trigger                  | Condition           | Current | Threshold | Status          | Action                        | Impact         |
|--------------------------|---------------------|---------|-----------|-----------------|-------------------------------|----------------|
| Break-Even (Bootstrap)   | MRR >= $1,747       | $564    | $1,747    | OK              | Continue customer acquisition | Profitability  |
| Hire Part-Time Support   | MRR >= $1,000       | $564    | $1,000    | OK              | Prepare job description       | +$300/mo OpEx  |
| Hire Full-Time Developer | MRR >= $3,000       | $564    | $3,000    | OK              | -                             | +$1,500/mo OpEx|
| Hire Full-Time Support   | MRR >= $4,000       | $564    | $4,000    | OK              | -                             | +$800/mo OpEx  |
| Cash Runway Warning      | Runway < 6 months   | 8.2     | 6         | OK              | -                             | Liquidity risk |
| Churn Rate Alert         | Churn > 5%          | 4.2%    | 5.0%      | OK              | Monitor retention initiatives | Revenue impact |
| CAC Efficiency           | CAC > $80           | $60     | $80       | OK              | Optimize marketing channels   | Profitability  |
| LTV:CAC Ratio            | LTV:CAC < 3:1       | 4.1:1   | 3:1       | OK              | -                             | Unit economics |
| Gross Margin             | Margin < 65%        | 70%     | 65%       | OK              | -                             | Profitability  |
| Annual Plan Adoption     | Annual % < 15%      | 20%     | 15%       | OK              | -                             | Cash flow      |
```

---

#### Table 11C: Milestone Tracker

**Columns:**
- Milestone Name
- Target Date
- Target Metric
- Actual Date
- Actual Metric
- Status (Not Started/In Progress/Achieved/Missed)
- Notes

**Rows:** Key milestones for 36 months

**Example:**
```
| Milestone                  | Target Date | Target Metric      | Actual Date | Actual Metric | Status        | Notes                          |
|----------------------------|-------------|--------------------|-------------|---------------|---------------|--------------------------------|
| First Paying Customer      | Month 1     | 1 customer         | -           | -             | Not Started   | -                              |
| 10 Customers               | Month 3     | 10 customers       | -           | -             | Not Started   | Validation milestone           |
| Product-Market Fit         | Month 6     | 30 customers, >95% retention | - | -      | Not Started   | Key validation                 |
| Break-Even (Bootstrap)     | Month 7-9   | $1,747 MRR         | -           | -             | Not Started   | Critical financial milestone   |
| Migrate to Growth Pod      | Month 9     | 51+ customers      | -           | -             | Not Started   | Infrastructure scaling         |
| Hire Part-Time Support     | Month 9     | $1,000 MRR         | -           | -             | Not Started   | Begin building team            |
| 150 Customers (Year 1 Goal)| Month 12    | 150 customers      | -           | -             | Not Started   | Year 1 target                  |
| Hire FT Developer          | Month 15    | $3,000 MRR         | -           | -             | Not Started   | Team expansion                 |
| Migrate to Scale Pod       | Month 22    | 151+ customers     | -           | -             | Not Started   | Major infrastructure upgrade   |
| 500 Customers (Year 2 Goal)| Month 24    | 500 customers      | -           | -             | Not Started   | Year 2 target                  |
| 1,000 Customers (Year 3)   | Month 36    | 1,000 customers    | -           | -             | Not Started   | Year 3 target                  |
| $10k MRR                   | Month 30    | $10,000 MRR        | -           | -             | Not Started   | Significant revenue milestone  |
```

---

## Dashboard Design

### SHEET 12: Executive Dashboard

This is your **visual summary** sheet. Use charts, conditional formatting, and summary tables.

#### Section A: Top-Line Metrics (Current Month)

Create a **dashboard header** with key metrics in large, bold cells:

**Layout:**
```
┌─────────────────────────────────────────────────────────────────────────┐
│                     SAASODOO FINANCIAL DASHBOARD                        │
│                        Month: [Current Month]                            │
└─────────────────────────────────────────────────────────────────────────┘

┌──────────────────┬──────────────────┬──────────────────┬──────────────────┐
│  Total Customers │       MRR        │   Gross Margin   │    Cash Balance  │
│      [150]       │    [$1,936]      │      [70%]       │     [$9,599]     │
│  ↑ 25 (+20%)     │  ↑ $566 (+41%)   │   ↑ 2%           │   ↑ $2,099       │
└──────────────────┴──────────────────┴──────────────────┴──────────────────┘

┌──────────────────┬──────────────────┬──────────────────┬──────────────────┐
│    LTV:CAC       │  Monthly Churn   │     Uptime       │  Technical Health│
│     [4.1:1]      │     [4.2%]       │    [99.6%]       │      [90/100]    │
│  Status: Good ✓  │ Status: Fair ⚠   │  Status: Good ✓  │  Status: Green ✓ │
└──────────────────┴──────────────────┴──────────────────┴──────────────────┘
```

**Formatting:**
- Use **large font** (18-24pt) for primary numbers
- Use **conditional formatting**:
  - Green for positive trends (↑ +20%)
  - Red for negative trends (↓ -10%)
- Include **month-over-month change** below each metric

---

#### Section B: Revenue & Customer Growth Chart

**Chart Type:** Combination chart (Line + Column)
- **Columns**: Total Customers (right axis)
- **Line**: MRR (left axis)
- **X-axis**: Months 1-36

**Data Source:**
- Pull from Revenue Model sheet (Table 4A)

**Labels:**
- Y-axis left: "MRR ($)"
- Y-axis right: "Customers"
- Title: "Revenue & Customer Growth"

**Annotations:**
- Mark milestones (e.g., "Break-Even", "Pod Migration", "Hire Developer")

---

#### Section C: Customer Mix Pie Chart

**Chart Type:** Pie chart or Donut chart
- **Slices**: Hustler, SME, Business, Enterprise
- **Values**: Current month customer count
- **Colors**: Assign distinct colors to each tier

**Data Source:**
- Pull from Customer Mix sheet (latest month)

**Labels:**
- Show percentage and count (e.g., "Hustler: 60 (40%)")

---

#### Section D: Profit & Loss Summary (YTD)

**Table:**
```
| Metric                  | YTD (Year 1)  | YTD (Year 2)  | YTD (Year 3)  |
|-------------------------|---------------|---------------|---------------|
| Total Revenue           | $24,300       | $105,000      | $350,000      |
| Total COGS              | $7,290        | $31,500       | $105,000      |
| Gross Profit            | $17,010       | $73,500       | $245,000      |
| Gross Margin %          | 70%           | 70%           | 70%           |
| Operating Expenses      | $14,652       | $58,092       | $127,764      |
| EBITDA                  | $2,358        | $15,408       | $117,236      |
| EBITDA Margin %         | 9.7%          | 14.7%         | 33.5%         |
| Net Profit              | $2,358        | $15,408       | $117,236      |
| Net Margin %            | 9.7%          | 14.7%         | 33.5%         |
```

**Formatting:**
- Use **conditional formatting** for margins
  - Green: >20%
  - Yellow: 10-20%
  - Red: <10%

---

#### Section E: Cash Flow Waterfall Chart

**Chart Type:** Waterfall chart
- **Starting Point**: Beginning Cash
- **Positive bars**: Revenue
- **Negative bars**: COGS, OpEx
- **Ending Point**: Ending Cash

**Data Source:**
- Pull from Cash Flow sheet (current month or quarter)

**Title:** "Monthly Cash Flow (Month [X])"

---

#### Section F: Technical Health Gauges

**Chart Type:** Gauge charts (speedometer style)
- **RAM Utilization**: 0-100%, with zones (0-60% green, 60-80% yellow, 80-100% red)
- **CPU Utilization**: Same
- **Storage Utilization**: Same
- **Overall Technical Health**: 0-100 score

**Data Source:**
- Pull from Technical Metrics sheet (Table 10A, 10C)

**Layout:** 2x2 grid of gauges

---

#### Section G: Decision Alerts Table

**Table:**
```
| Alert Type        | Status          | Action Required                  | Timeline    |
|-------------------|-----------------|----------------------------------|-------------|
| Pod Migration     | Warning ⚠       | Migrate to Growth Pod in 2 weeks | 2 weeks     |
| Hire Support      | Action Required | Hire part-time support now       | Immediate   |
| RAM Utilization   | OK ✓            | Continue monitoring              | -           |
| Churn Rate        | OK ✓            | -                                | -           |
```

**Data Source:**
- Pull from Decision Dashboard sheet (Tables 11A, 11B)

**Filtering:**
- Only show alerts with "Warning" or "Action Required" status
- Suppress "OK" statuses to reduce clutter

---

#### Section H: Unit Economics Scorecard

**Table:**
```
| Metric           | Current  | Target   | Status | Trend  |
|------------------|----------|----------|--------|--------|
| LTV ($)          | $244     | $300     | Fair   | ↑      |
| CAC ($)          | $60      | $50      | Good   | ↓      |
| LTV:CAC Ratio    | 4.1:1    | >3:1     | Good ✓ | ↑      |
| Payback (months) | 4.1      | <6       | Good ✓ | ↓      |
| Churn (%)        | 4.2%     | <3.5%    | Fair   | ↓      |
| Gross Margin (%) | 70%      | >70%     | Good ✓ | →      |
```

**Data Source:**
- Pull from Unit Economics sheet (Table 9A)

**Formatting:**
- Use traffic light colors (Green/Yellow/Red) for Status column
- Use arrow symbols (↑↓→) for Trend column

---

## Scenario Planning

### SHEET 13: Scenarios

#### Table 13A: Scenario Assumptions

Create **three scenarios**: Base Case, Pessimistic, Optimistic

**Columns:**
- Assumption Name
- Base Case
- Pessimistic Case
- Optimistic Case

**Rows:**
- New Customers/Month (Year 1)
- Monthly Churn Rate (Year 1)
- Average Pricing (ARPU)
- CAC
- Gross Margin %
- Personnel Hiring Trigger (MRR)

**Example:**
```
| Assumption                  | Base Case | Pessimistic | Optimistic |
|-----------------------------|-----------|-------------|------------|
| New Customers/Month (Yr 1)  | 12.5      | 8           | 18         |
| Monthly Churn Rate (Yr 1)   | 4.2%      | 6.0%        | 3.0%       |
| ARPU                        | $14.55    | $12.00      | $16.50     |
| CAC                         | $60       | $80         | $45        |
| Gross Margin %              | 70%       | 65%         | 75%        |
| Hire Support Trigger (MRR)  | $1,000    | $1,500      | $800       |
```

---

#### Table 13B: Scenario Outcomes (Year 1)

**Columns:**
- Metric
- Base Case
- Pessimistic Case
- Optimistic Case

**Rows:**
- Ending Customers
- Ending MRR
- Annual Revenue
- COGS
- Gross Profit
- OpEx
- Net Profit
- Ending Cash
- LTV:CAC Ratio
- Break-Even Month

**Example:**
```
| Metric            | Base Case | Pessimistic | Optimistic |
|-------------------|-----------|-------------|------------|
| Ending Customers  | 150       | 96          | 216        |
| Ending MRR        | $1,936    | $1,152      | $3,564     |
| Annual Revenue    | $24,300   | $14,800     | $38,500    |
| COGS              | $7,290    | $5,180      | $9,625     |
| Gross Profit      | $17,010   | $9,620      | $28,875    |
| OpEx              | $14,652   | $13,200     | $16,800    |
| Net Profit        | $2,358    | -$3,580     | $12,075    |
| Ending Cash       | $9,599    | $1,420      | $19,075    |
| LTV:CAC Ratio     | 4.1:1     | 2.4:1       | 6.8:1      |
| Break-Even Month  | 9         | Never (Yr1) | 6          |
```

**Calculations:**
- **Re-run your Revenue, Cost, and P&L formulas** using the scenario assumptions
- Highlight which scenario requires external funding (Pessimistic shows negative cash)

---

#### Table 13C: Sensitivity Analysis

**Purpose:** See how changes in ONE variable affect Net Profit

**Table Structure:**
- **Rows**: Variable being changed (e.g., Monthly Churn Rate)
- **Columns**: -20%, -10%, Base, +10%, +20%
- **Cells**: Resulting Net Profit (Year 1)

**Example:**
```
Sensitivity of Year 1 Net Profit to Key Variables:

Variable: New Customers/Month
| Change     | -20%   | -10%  | Base   | +10%  | +20%  |
|------------|--------|-------|--------|-------|-------|
| Value      | 10     | 11.25 | 12.5   | 13.75 | 15    |
| Net Profit | -$732  | $813  | $2,358 | $3,903| $5,448|

Variable: Monthly Churn Rate
| Change     | -20%   | -10%  | Base   | +10%  | +20%  |
|------------|--------|-------|--------|-------|-------|
| Value      | 3.4%   | 3.8%  | 4.2%   | 4.6%  | 5.0%  |
| Net Profit | $3,558 | $2,958| $2,358 | $1,758| $1,158|

Variable: ARPU
| Change     | -20%   | -10%  | Base   | +10%  | +20%  |
|------------|--------|-------|--------|-------|-------|
| Value      | $11.64 | $13.10| $14.55 | $16.01| $17.46|
| Net Profit | -$2,007| $176  | $2,358 | $4,541| $6,723|
```

**Visualization:**
- Create a **Tornado Chart** to show which variables have the biggest impact
- Sort by magnitude of change from largest to smallest

---

## Additional Recommendations

### Data Validation & Error Checking

Create a **Validation sheet** with checks:

**Table: Model Health Checks**
```
| Check Name                  | Formula                                  | Expected | Actual | Status |
|-----------------------------|------------------------------------------|----------|--------|--------|
| Customer Mix Sums to 100%   | SUM(Hustler% + SME% + Business% + Ent%) | 100%     | 100%   | ✓      |
| Total Customers = Sum Tiers | Total Customers = SUM(tiers)             | TRUE     | TRUE   | ✓      |
| Revenue = MRR + Annual      | Total Revenue = MRR + Annual             | TRUE     | TRUE   | ✓      |
| COGS < Revenue (every month)| MIN(Gross Margin) > 0                    | TRUE     | TRUE   | ✓      |
| No Negative Cash            | MIN(Cash Balance) >= 0                   | TRUE     | FALSE  | ✗      |
| Break-Even Achieved         | Net Profit > 0 for 3 consecutive months  | By M9    | By M7  | ✓      |
```

---

### Naming Conventions

Use **clear, consistent names**:
- **Sheet names**: Short, descriptive (e.g., "Assumptions", "Revenue Model")
- **Table names**: Use Excel's Table feature and name tables (e.g., "tbl_PodSpecs", "tbl_MRR")
- **Cell names**: Name key inputs (e.g., "MonthlyChurnRate_Y1", "ARPU_Base")

**Benefits:**
- Easier to reference in formulas (e.g., `=ARPU_Base * CustomerCount` instead of `=C5 * D12`)
- Self-documenting model
- Reduces errors when copying formulas

---

### Version Control

Maintain multiple versions as you update actuals:

**File naming:**
- `SaaSOdoo_Financial_Model_v1.0_2026-01-15_Baseline.xlsx`
- `SaaSOdoo_Financial_Model_v1.1_2026-02-01_Actuals_Month1.xlsx`
- `SaaSOdoo_Financial_Model_v2.0_2026-07-01_Updated_Assumptions.xlsx`

**Track changes:**
- Add a "Change Log" sheet documenting what changed and why
- Example: "2026-02-01: Updated M1 actuals - 7 customers (vs 5 projected), MRR $95 (vs $50 projected)"

---

### Monthly Review Process

**Recommended workflow:**

1. **Update Actuals** (5th of each month)
   - Enter actual customer count, revenue, costs, churn
   - Compare to projections

2. **Review Variances** (6th of month)
   - Identify where actuals differ from projections
   - Understand why (e.g., higher churn due to poor onboarding)

3. **Update Assumptions** (7th of month, if needed)
   - If variances persist for 3+ months, update assumptions
   - Example: If actual churn is 6% for 3 months, change assumption from 4.2% to 6%

4. **Re-forecast** (8th of month)
   - With updated assumptions, re-run projections for remaining months
   - Adjust plans (e.g., delay hiring if revenue is below projections)

5. **Present to Stakeholders** (10th of month)
   - Share Executive Dashboard with team/advisors/investors
   - Discuss key decisions and actions

---

## Summary: How to Build This in Excel

### Step-by-Step Build Process

1. **Week 1: Set up structure**
   - Create all 13 sheets
   - Set up Assumptions sheet with all inputs
   - Create Pod Specs tables

2. **Week 2: Build revenue model**
   - Customer Mix projection (36 months)
   - MRR calculation
   - Annual subscription logic
   - Link to Assumptions

3. **Week 3: Build cost model**
   - Pod selection logic (IF statements)
   - Variable COGS by tier
   - COGS summary
   - Link to Assumptions and Customer Mix

4. **Week 4: Build P&L and cash flow**
   - Monthly P&L (revenue - COGS - OpEx)
   - Annual summaries
   - Cash flow statement
   - Link all sheets together

5. **Week 5: Add metrics and dashboards**
   - Unit Economics calculations
   - Technical Metrics tables
   - Decision Triggers with conditional formatting
   - Executive Dashboard with charts

6. **Week 6: Scenarios and validation**
   - Build scenario tables
   - Create sensitivity analysis
   - Add validation checks
   - Test all formulas

7. **Week 7: Polish and document**
   - Format for readability
   - Add charts and conditional formatting
   - Write formula documentation
   - Create user guide

---

## Key Formulas to Implement

**You will need to create Excel formulas for:**

1. **Customer Count**: `Previous Total + New - (Previous Total × Churn Rate)`

2. **Pod Selection**: `IF(Customers <= 50, "MVP-B", IF(Customers <= 150, "Growth", "Scale"))`

3. **MRR**: `SUMPRODUCT(Customer Counts, Tier Prices)`

4. **RAM Utilization**: `SUMPRODUCT(Customer Counts, Avg RAM Usage) / (Total Pod RAM - Overhead)`

5. **Gross Margin**: `(Revenue - COGS) / Revenue`

6. **LTV**: `ARPU × (1 / Churn Rate) × Gross Margin`

7. **Conditional Formatting**: Use Excel's built-in rules for traffic lights, data bars, color scales

8. **VLOOKUP/INDEX-MATCH**: To pull data between sheets (e.g., look up pod cost based on customer count)

---

## Conclusion

This guide provides a **comprehensive blueprint** for building a financial model that:
- ✅ Links infrastructure costs to customer count (pod-based)
- ✅ Forecasts revenue, costs, and profitability over 36 months
- ✅ Tracks technical capacity and triggers infrastructure scaling decisions
- ✅ Calculates all key SaaS metrics (LTV, CAC, churn, etc.)
- ✅ Provides a visual dashboard for decision-making
- ✅ Supports scenario planning and sensitivity analysis

**Next Steps:**
1. Create the Excel workbook following the table structures described above
2. Start with **Assumptions** and **Pod Specs** sheets (foundational)
3. Build **Revenue Model** and **Cost Model** next (core calculations)
4. Add **P&L**, **Cash Flow**, and **Metrics** (financial outputs)
5. Finish with **Dashboard** and **Scenarios** (decision support)
6. Update monthly with actuals and refine assumptions

**Remember:** The model is a living document. As you gain real customer data, continuously refine your assumptions to make it more accurate.

Good luck building your financial model! 🚀
