# SaaSOdoo Quick Reference: Pricing & Pod Design

**Version:** 1.0 | **Date:** 2025-11-18

---

## Customer Pricing (Final Recommendation)

| Tier | Monthly | Annual (17% off) | vCPU | RAM | Storage | Target Customer |
|------|---------|------------------|------|-----|---------|-----------------|
| **Hustler** | **$8** | $80 ($6.67/mo) | 1 | 2GB | 10GB | Solo entrepreneurs |
| **SME** | **$18** | $180 ($15/mo) | 2 | 4GB | 20GB | Small businesses |
| **Business** | **$35** | $350 ($29.17/mo) | 4 | 8GB | 50GB | Established companies |

**Gross margins:** 69%, 72%, 67% respectively | **Average:** 70%

---

## Infrastructure Pods (3 Phases)

### MVP Pod (0-50 customers) - **$21/month**
```
1× Contabo CLOUD VPS 30 ($15) - US Central
├── 8 vCPU, 24GB RAM, 200GB NVMe
└── FTP Backup 100GB ($5.79)

Capacity: 30-35 customers
Revenue at capacity: $509 MRR
Margin: 96% ($488 profit)
```

---

### Growth Pod (50-150 customers) - **$141/month**
```
Compute:
├── 2× CLOUD VPS 40 ($52) - 12 vCPU, 48GB RAM each

Storage (CephFS):
└── 3× STORAGE VPS 30 ($45) - 1.5TB usable (replication 2x)

Platform:
├── 1× CLOUD VPS 20 ($7.95) - PostgreSQL, Redis, RabbitMQ
└── Private Network: 6 nodes ($18)
└── FTP Backup 500GB ($18.39)

Capacity: 100-150 customers
Revenue at 150: $2,182 MRR
Margin: 94% ($2,041 profit after infra)
```

---

### Scale Pod (150-500 customers) - **$447/month**
```
Compute (Physical cores):
├── 4× CLOUD VDS M ($276) - 4 physical cores, 32GB RAM each

Storage (CephFS):
└── 3× STORAGE VPS 40 ($78) - 1.8TB usable

Platform & Load Balancer:
├── 1× CLOUD VPS 30 ($15) - Platform services
├── 1× CLOUD VPS 10 ($4.95) - Traefik LB
└── Private Network: 9 nodes ($27)
└── FTP Backup 2TB ($45.99)

Capacity: 400-500 customers
Revenue at 500: $7,275 MRR
Margin: 94% ($6,828 profit after infra)
```

---

## Unit Economics (Average Customer)

| Metric | Value | Benchmark | Status |
|--------|-------|-----------|--------|
| **ARPU** | $14.55/mo | - | - |
| **Customer Lifetime** | 24 months | 18-36 months | ✅ Good |
| **LTV** | $244 | $200-1000 | ✅ Fair |
| **CAC** | $60 | $50-200 | ✅ Good |
| **LTV:CAC** | **4.1:1** | >3:1 | ✅ Excellent |
| **Payback Period** | **4.1 months** | <12 months | ✅ Excellent |
| **Monthly Churn** | 4.2% | 3-5% | ⚠️ Target |
| **Gross Margin** | 70% | 70-85% | ✅ Healthy |

---

## 3-Year Financial Summary

| Year | Customers | MRR (End) | Annual Revenue | Net Profit | Margin |
|------|-----------|-----------|----------------|------------|--------|
| **1** | 150 | $1,936 | $24,300 | $2,358 | 9.7% |
| **2** | 500 | $7,275 | $105,000 | $15,408 | 14.7% |
| **3** | 1,000 | $14,550 | $350,000 | $117,236 | 33.5% |

---

## Break-Even Points

| Phase | Fixed Costs/Mo | Customers Needed | MRR Needed | Timeline |
|-------|----------------|------------------|------------|----------|
| **Year 1 (Bootstrap)** | $1,221 | 120 | $1,747 | Month 7-9 |
| **Year 2 (1 FT Team)** | $4,841 | 476 | $6,926 | Month 22-24 |
| **Year 3 (Full Team)** | $10,647 | 1,046 | $15,219 | Need >1000 customers |

---

## Capacity Planning (Overselling Ratios)

**Conservative Overselling (5:1):**
- Customer gets: 2GB RAM → Actually uses: ~400MB average
- Customer gets: 1 vCPU → Actually uses: ~0.2 cores average
- Customer gets: 10GB storage → Actually uses: ~5GB average

**Pod Capacity:**
| Pod | Total RAM | Available RAM | Customers (Mixed) | Revenue |
|-----|-----------|---------------|-------------------|---------|
| MVP (VPS 30) | 24GB | 20GB | 30-35 | $509 |
| Growth (2×VPS40) | 96GB | 80GB | 100-150 | $2,182 |
| Scale (4×VDS-M) | 128GB | 108GB | 400-500 | $7,275 |

---

## COGS Breakdown (Per Customer)

| Component | Hustler | SME | Business |
|-----------|---------|-----|----------|
| Infrastructure | $0.50 | $1.00 | $2.00 |
| Storage | $0.20 | $0.50 | $1.50 |
| Backup | $0.15 | $0.30 | $0.75 |
| Bandwidth | $0.05 | $0.10 | $0.20 |
| Payment processing | $0.20 | $0.45 | $0.88 |
| Support | $1.00 | $2.00 | $5.00 |
| Platform overhead | $0.40 | $0.65 | $1.17 |
| **TOTAL** | **$2.50** | **$5.00** | **$11.50** |
| **Gross Profit** | **$5.50** | **$13.00** | **$23.50** |

---

## Competitive Positioning

| Provider | Similar Tier | Price | RAM | Storage | Zimbabwe Features |
|----------|--------------|-------|-----|---------|-------------------|
| **SaaSOdoo** | SME | **$18** | 4GB | 20GB | ✅ Ecocash, ZIMRA, Local |
| CloudClusters | Basic | $12.99 | 4GB | 100GB | ❌ None |
| CloudClusters | Professional | $23.99 | 8GB | 160GB | ❌ None |
| CloudPepper | Medium | $82 | 4GB | 100GB | ❌ None |
| Odoo.sh | Minimum | $72.25 | N/A | 1GB | ❌ None |

**Value Proposition:**
- **vs CloudClusters:** Zimbabwe features + WhatsApp support justify 38% premium ($18 vs $13)
- **vs CloudPepper:** 78% cheaper ($18 vs $82) with same features
- **vs Odoo.sh:** 75% cheaper ($18 vs $72) for SME segment
- **vs DIY Contabo:** Save 20 hours/month ($500 time value) for $3-20 extra

---

## Migration Triggers

| Trigger | Action | Timeline |
|---------|--------|----------|
| **30-40 customers** | Migrate from MVP to Growth pod | Month 6-9 |
| **CPU >70% for 7 days** | Add compute node or upgrade tier | Immediate |
| **RAM >80%** | Scale up RAM or add node | Within 48 hours |
| **Storage >80%** | Expand storage VPS | Within 1 week |
| **400+ customers** | Migrate to Scale pod (VDS) | Month 20-24 |

---

## CephFS Requirements

**Minimum for production:**
- 3 storage nodes (for MON quorum)
- Replication factor: 2 (acceptable) or 3 (preferred)
- Private network between nodes (required)
- Each node needs: MON + OSD + MDS

**MVP CephFS Setup (if starting with distributed storage):**
```
3× STORAGE VPS 10 @ $4.95 each = $14.85/month
├── Each: 2 vCPU, 4GB RAM, 300GB SSD
└── Total: 900GB raw = 450GB usable (replication 2x)

+ 1× CLOUD VPS 20 for compute = $7.95/month
+ Private network 4 nodes = $11.96/month
+ Backup = $5.79/month

Total: $40.55/month (still under $50!)
Capacity: 20-25 customers
```

**Recommendation:** Start with local storage MVP ($21) → Migrate to CephFS at 35-50 customers

---

## Key Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Slow customer acquisition** | 💀 Critical | Start with $3k capital buffer, delay hiring |
| **High churn (>5%)** | ⚠️ High | Excellent onboarding, annual plans, proactive support |
| **Underpricing** | ⚠️ High | Add unique value (Ecocash, ZIMRA), quarterly pricing review |
| **Infrastructure cost spike** | ⚠️ Medium | Monitor weekly, set alerts, scale proactively |
| **Founder burnout** | ⚠️ Medium | Hire support at $1k MRR, developer at $3k MRR |

---

## Critical Success Factors

✅ **Customer acquisition:** Need 150 customers by Month 12 to be profitable
✅ **Churn management:** Keep monthly churn <5% (target 4.2% Year 1, 2.5% Year 3)
✅ **CAC efficiency:** Keep CAC <$60 (focus on organic + referrals)
✅ **Pricing discipline:** Don't compete on price alone - Zimbabwe features justify premium
✅ **Cash flow:** Push annual plans (17% discount) to accelerate cash collection

---

## Monthly KPI Targets

| KPI | Month 6 | Month 12 | Month 24 | Month 36 |
|-----|---------|----------|----------|----------|
| Customers | 30 | 150 | 500 | 1,000 |
| MRR | $450 | $1,936 | $7,275 | $14,550 |
| MoM Growth % | 40% | 20% | 15% | 10% |
| Churn % | 5% | 4% | 3% | 2.5% |
| LTV:CAC | 3.1:1 | 4.7:1 | 7.6:1 | 10.7:1 |
| NPS | 45 | 50 | 55 | 60 |

---

## Next Actions

**Week 1-2:**
1. ✅ Validate pricing with 20+ customer interviews
2. ✅ Purchase Contabo VPS 30 (US Central, $15/month)
3. ✅ Set up Google Sheets financial dashboard

**Week 3-4:**
4. ✅ Deploy platform services + monitoring
5. ✅ Configure automated backups
6. ✅ Launch beta to 5 customers (free for 3 months)

**Month 2-3:**
7. ✅ Refine onboarding based on beta feedback
8. ✅ Public launch with 14-day free trial
9. ✅ Target: 10 paying customers by Month 3

**Month 4-6:**
10. ✅ Hire part-time support when hitting $1k MRR
11. ✅ Launch referral program
12. ✅ Target: 30-50 customers by Month 6

---

**Files Created:**
- `/docs/Busines Plan/SaaSOdoo_Financial_Model.csv` - Full spreadsheet model
- `/docs/Busines Plan/Financial_Model_Summary.md` - Detailed analysis
- `/docs/Busines Plan/Quick_Reference_Pricing_And_Pods.md` - This reference sheet
