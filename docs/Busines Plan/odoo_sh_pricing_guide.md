# Odoo.sh Pricing Guide

## Pricing Components
 
Odoo.sh uses a **pay-as-you-go model** based on infrastructure resources. The hosting price does **NOT include the enterprise license**. i.e. 13.60 per user

### Base Configuration Options

| Component | Unit | Price | Range |
|-----------|------|-------|-------|
| **Workers** | per worker | $72.00/month | 1-8 (Shared)<br>4-256 (Dedicated) |
| **Storage** | per GB | $0.25/month | 1 GB minimum<br>512 GB max (Shared)<br>4096 GB max (Dedicated) |
| **Staging Environments** | per environment | $18.00/month | 0-20 |

### Hosting Type

| Type | Monthly Cost | Notes |
|------|--------------|-------|
| **Shared** | Included in worker cost | Suitable for small deployments |
| **Dedicated** | $600.00/month | Required for 9+ workers or high-traffic sites |

---

## Minimum Configurations

### Shared Hosting (Minimum)
```
Workers:    1 × $72.00   = $72.00
Storage:    1 GB × $0.25 = $0.25
Staging:    0 × $18.00   = $0.00
                Total    = $72.25/month
```

### Dedicated Hosting (Minimum)

**Monthly Billing:**
```
Workers:    4 × $72.00     = $288.00
Storage:    1 GB × $0.25   = $0.25
Dedicated:  1 × $600.00    = $600.00
Staging:    0 × $18.00     = $0.00
                Total      = $888.25/month
```

**Annual Billing (with ~20% discount):**
```
Effective monthly rate  = $710.60/month
Annual total           = $8,527.20/year
Savings                = ~$2,131.80/year
```

---

## Dimensioning Guidelines

### Workers
**Definition:** Number of concurrent requests your instance can handle.

**Recommendations:**
- **1 additional worker per 25 back-end users**
- **1 additional worker per 5000 front-end visitors per day**

**Examples:**
- 25 back-end users = 2 workers minimum
- 50 back-end users = 3 workers
- 10,000 daily visitors = 3 workers

### Storage
**Definition:** Total disk space for production + staging instances + 3 backups across different datacenters.

**Recommendations:**
- **Start with 1 GB per user**
- Includes: database, attachments, backups (3x replication)

**Examples:**
- 10 users = 10 GB minimum
- 50 users = 50 GB recommended
- 100 users = 100 GB recommended

### Staging Environments
**Definition:** Additional environments for development and testing (separate from production).

**Recommendations:**
- **0 environments** = Production only (not recommended)
- **1 environment** = Basic testing
- **2-3 environments** = Development + Staging + Testing
- **Each staging environment costs $18/month**

---

## Pricing Examples

### Small Business (10 users)
```
Workers:    2 (Shared)              = $144.00
Storage:    10 GB                   = $2.50
Staging:    1 environment           = $18.00
                        Monthly Total = $164.50
```

### Medium Business (50 users)
```
Workers:    3 (Shared)              = $216.00
Storage:    50 GB                   = $12.50
Staging:    2 environments          = $36.00
                        Monthly Total = $264.50
```

### Large Business (100 users, high traffic)
```
Workers:    8 (Shared max)          = $576.00
Storage:    100 GB                  = $25.00
Staging:    3 environments          = $54.00
                        Monthly Total = $655.00
```

### Enterprise (200 users)
```
Workers:    10 (requires Dedicated) = $720.00
Storage:    200 GB                  = $50.00
Dedicated:  Base fee                = $600.00
Staging:    5 environments          = $90.00
                        Monthly Total = $1,460.00
```

---

## Key Notes

1. **Billing Frequency:** 
   - Monthly: Full price (as shown in examples)
   - Annual: ~20% discount (e.g., Dedicated minimum: $710.60/month instead of $888.25/month)
2. **Currency:** USD ($) or EUR (€)
3. **Shared vs Dedicated:**
   - Shared: Max 8 workers, suitable for most small-medium businesses
   - Dedicated: Required for 9+ workers, provides isolated resources
4. **Enterprise License:** NOT included in hosting price - purchased separately from Odoo
5. **Scaling:** All components can be adjusted as needed
6. **Minimum Configs:** 
   - Shared: $72.25/month (monthly) or ~$58/month (annual)
   - Dedicated: $888.25/month (monthly) or $710.60/month (annual)

---

## Quick Calculator Formula

```
Monthly Cost = (Workers × $72) + (Storage_GB × $0.25) + (Staging × $18) + Dedicated_Fee

Where:
  Dedicated_Fee = $600 if Workers > 8 OR Dedicated selected
  Dedicated_Fee = $0 if Shared hosting
```

---

## Comparison: Shared vs Dedicated

| Feature | Shared | Dedicated |
|---------|--------|-----------|
| **Worker Range** | 1-8 | 4-256 |
| **Base Cost** | $0 | $600/month |
| **Best For** | Small-medium teams | Large enterprises |
| **Resources** | Shared infrastructure | Isolated resources |
| **Min Total Cost** | $72.25/month | $888.25/month |


for 4CPU machine, number of workers = (CPU * 2) + 1
