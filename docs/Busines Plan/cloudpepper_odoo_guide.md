# CloudPepper Odoo Hosting Guide

## Overview

CloudPepper offers **Odoo management and deployment services** but requires you to provide your own cloud infrastructure. They offer two distinct service models:

1. **Managed Odoo Plans** - CloudPepper manages your Odoo instances on your cloud provider
2. **DevOps Plans** - You host on your own servers, CloudPepper provides the management platform

---

## Service Model 1: Managed Odoo Plans

**What You Get:** CloudPepper manages everything, but you pay for both CloudPepper's service AND your chosen cloud provider.

### CloudPepper Management Plans

| Plan | Management Fee | Max Servers | Max Odoo Instances | Capacity (Users) | Capacity (Daily Visitors) | Trial Period |
|------|----------------|-------------|--------------------|-----------------|-----------------------------|--------------|
| **Core** | $0/month | 1 | 1 | Host yourself | Host yourself | Free Forever |
| **Base** | $29/month | 2 | 2 | 25 users | 5k visitors | 14 days |
| **Pro** ⭐ | $49/month | Unlimited | Unlimited | 200 users | 40k visitors | 14 days |
| **Agency** | $250/month | Unlimited | Unlimited | 400 users | 80k visitors | 14 days |


**Supported Odoo Versions:** Community or Enterprise, Versions 11, 12, 13, 14, 15, 16, 17, 18, 19

---

## Service Model 2: DevOps Plans (Infrastructure Options)

CloudPepper provides **4 infrastructure tiers** when using their managed infrastructure:

### CloudPepper Infrastructure Pricing

| Tier | Infrastructure Cost | vCPU Cores | Odoo Workers | RAM | NVMe SSD Storage | CPU Type | Capacity (Users) | Capacity (Visitors) |
|------|---------------------|------------|--------------|-----|------------------|----------|------------------|---------------------|
| **Small** | $41/month | 1 | 2 | 2GB | 50GB | AMD EPYC 3.6GHz | 25 | 5k daily |
| **Medium** ⭐ | $53/month | 2 | 4 | 4GB | 100GB | AMD EPYC 3.6GHz | 100 | 20k daily |
| **Large** | $77/month | 4 | 8 | 8GB | 180GB | AMD EPYC 3.6GHz | 200 | 40k daily |
| **X-Large** | $125/month | 8 | 16 | 16GB | 350GB | AMD EPYC 3.6GHz | 400 | 80k daily |

**Additional Features (All Tiers):**
- 30+ global datacenter locations
- AMD's 3rd Gen EPYC 3.6GHz CPU
- Odoo Community & Enterprise supported
- Versions: 11, 12, 13, 14, 15, 16, 17, 18, 19
- Custom Modules support
- Deploy with GitHub
- Staging Environment included
- Automated Backups
- 900+ Free Odoo Addons
- Cloudpepper Optimization
- A+ Grade SSL Certificates
- SSH Root Access
- Server Monitoring & Healing

---

### Total Cost Calculator (Management + Infrastructure)

| Your Plan | Infra Tier | Management Fee | Infrastructure Cost | **TOTAL/Month** | Best For |
|-----------|-----------|----------------|---------------------|-----------------|----------|
| **Base** | Small | $29 | $41 | **$70** | Startups, 25 users |
| **Base** | Medium | $29 | $53 | **$82** | Small business, 100 users |
| **Base** | Large | $29 | $77 | **$106** | Growing business, 200 users |
| **Base** | X-Large | $29 | $125 | **$154** | Medium business, 400 users |
| **Pro** | Small | $49 | $41 | **$90** | Multiple small instances |
| **Pro** | Medium | $49 | $53 | **$102** | Multiple medium instances |
| **Pro** | Large | $49 | $77 | **$126** | Unlimited servers, 200 users ea |
| **Pro** | X-Large | $49 | $125 | **$174** | Unlimited servers, 400 users ea |
| **Agency** | Medium | $250 | $53 | **$303** | Whitelabel reselling |
| **Agency** | Multiple | $250 | Variable | **$250+** | Multi-client management |

---

## Complete Pricing Structure

### All Plans Feature Comparison

| Feature | Core (Free) | Base ($29) | Pro ($49) | Agency ($250) |
|---------|-------------|------------|-----------|---------------|
| **Monthly Cost** | $0 | $29 | $49 | $250 |
| **Max Servers** | 1 | 2 | Unlimited | Unlimited |
| **Max Odoo Instances** | 1 | 2 | Unlimited | Unlimited |
| **Staging Environments** | 0 | 1 | Unlimited | Unlimited |
| **Host With** | DIY (your server) | Any cloud provider | Any cloud provider | Any cloud provider |
| **Odoo Versions** | 11-19 | 11-19 | 11-19 | 11-19 |
| **Custom Modules** | ✅ SFTP upload | ✅ GitHub | ✅ GitHub | ✅ GitHub |
| **Automated Backups** | ❌ | ✅ $0.02/GB | ✅ S3/SFTP | ✅ Advanced control |
| **External Database** | ❌ | ✅ | ✅ | ✅ |
| **User Management** | ❌ | ✅ Basic | ✅ Advanced | ✅ Advanced + Custom roles |
| **900+ Free Addons** | ❌ | ✅ | ✅ | ✅ |
| **SSL Certificates** | ✅ | ✅ A+ Grade | ✅ A+ Grade | ✅ A+ Grade |
| **SSH Root Access** | ✅ | ✅ | ✅ | ✅ |
| **Monitoring & Healing** | ❌ | ✅ | ✅ | ✅ |
| **Autodeploy Git** | ❌ | ❌ | ✅ Any provider | ✅ Any provider |
| **Whitelabel Portal** | ❌ | ❌ | ❌ | ✅ Branded |
| **Multi-Account Deploy** | ❌ | ❌ | ❌ | ✅ |
| **API Access** | ❌ | ❌ | ❌ | ✅ Full API |
| **Instance Templates** | ❌ | ❌ | ❌ | ✅ |
| **Audit Logs** | ❌ | ❌ | ❌ | ✅ |
| **Support** | Documentation | Email & Chat | Email & Chat | Priority |

---

## Key Differences: CloudPepper vs Traditional Hosting

| Feature | CloudPepper | Traditional Hosting |
|---------|-------------|---------------------|
| **Infrastructure** | You provide (AWS, DO, Vultr, etc.) OR buy from CloudPepper | Included in price |
| **Flexibility** | Choose any cloud provider | Locked to one provider |
| **Scalability** | Unlimited servers (Pro/Agency) | Fixed per plan |
| **Control** | Full SSH root access | Limited access |
| **Pricing Model** | Management fee + Infrastructure | All-in-one price |

---



## Notes

1. **Infrastructure is separate:** You pay CloudPepper for management AND your cloud provider for servers
2. **Multiple cloud providers supported:** AWS, DigitalOcean, Akamai, Vultr, or any other
3. **Odoo license NOT included:** Enterprise licenses purchased separately from Odoo
4. **Storage costs extra:** Backups stored at $0.02/GB
5. **All plans include:** 900+ free Odoo addons, staging environments, automated backups, SSL certificates
6. **CPU = Odoo Workers:** 1 vCPU core = 2 Odoo workers

