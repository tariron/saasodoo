Here is the comprehensive guide based on the Cloudpepper documentation provided, formatted in clean, structured Markdown.

***

# Odoo & PostgreSQL Performance Tuning and Server Sizing Guide

**Source:** Cloudpepper (Updated Nov 2025)

## Table of Contents
1. [Introduction](#introduction)
2. [Server Sizing Guide](#step-1-server-sizing-guide-hardware-requirements)
3. [Odoo Configuration Tuning](#step-2-odoo-configuration-tuning)
4. [PostgreSQL Performance Tuning](#step-3-postgresql-performance-tuning)
5. [Sample Configuration Profiles](#step-4-sample-configuration-profiles)

---

## Introduction

The goal of this guide is to optimize Odoo and PostgreSQL to run faster, handle more users, and maintain stability under load.

**The Golden Rule of Resources:**
> **Keep CPU and RAM usage below 80%.**
> Brief spikes are harmless, but consistent usage above 80% creates bottlenecks. If usage hits 100%, reducing the number of workers often stabilizes performance.

---

## Step 1: Server Sizing Guide (Hardware Requirements)

Before tuning, ensure you have the correct hardware capabilities. Use these steps to determine the CPU and RAM required based on your user base.

### 1. Calculate Required Workers
Start by counting **concurrent users** (people actively clicking/saving at the exact same time). If unsure, estimate 20–40% of total users.

*   **Rule of Thumb:** 1 Worker ≈ 6 Concurrent Users (or ~5,000 daily website visitors).
*   **Minimum:** Odoo requires **at least 2 workers** to generate PDF reports properly.

| Users | Calculation | Required Workers |
| :--- | :--- | :--- |
| **1–6 Concurrent** | 6 ÷ 6 = 1 (Round up to min) | **2** |
| **20 Concurrent** | 20 ÷ 6 = 3.33 | **4** |
| **55 Concurrent** | 55 ÷ 6 = 9.1 | **10** |

### 2. Calculate CPU Cores
Divide the calculated workers by 2 and round up.
*   **Formula:** `Workers ÷ 2 = Minimum Cores`
*   *Note: Bare metal (dedicated) cores outperform vCPUs. Count physical cores, not threads.*

### 3. Calculate RAM
Plan for memory usage per worker plus system overhead.
*   **Standard Usage:** 0.5 GB per worker.
*   **Heavy Usage (MRP, Studio, Large Reports):** 1–2 GB per worker.
*   **System Overhead:** Add 1–2 GB for OS and PostgreSQL.

### Quick Reference Sizing Table

| Concurrent Users | Workers Required* | Minimum CPU Cores | Recommended RAM |
| :--- | :--- | :--- | :--- |
| **1 – 6** | 2 | 1 | 1 – 2 GB |
| **7 – 12** | 2 | 1 | 2 – 4 GB |
| **13 – 24** | 4 | 2 | 4 – 8 GB |
| **37 – 60** | 10 | 5 | 8 – 32 GB |

*\*Note: Even for 1 user, 2 workers are required for PDF generation functionality.*

---

## Step 2: Odoo Configuration Tuning

Once the server is sized, you must configure the `odoo.conf` file to utilize the hardware effectively.

### Understanding Odoo Workers
*   **HTTP Workers:** Handle user activity (loading pages, invoices, sales).
*   **Cron Workers (`max_cron_threads`):** Handle background jobs.
*   **Long-polling Worker:** Handles chat and live notifications (low CPU, higher RAM).

### Calculating Max Workers (Hardware Limit)
If sizing based on available hardware (rather than user count), use these formulas:

1.  **Standard Limit Rule:**
    `Total Workers (HTTP + Cron) = (CPU Cores × 2) + 1`
2.  **Heavy Load / Conservative Rule:**
    (Best for large imports or massive reports)
    `HTTP Workers = Number of CPU Cores`

### Memory Limits (`limit_memory_soft`)
Each worker consumes RAM. Ensure the total does not exceed available physical RAM.
*   **Idle:** ~80–200 MB
*   **Average:** ~300–400 MB
*   **Heavy:** 1 GB+

**Calculation Example (2 Cores, 4GB RAM):**
> Formula: (2 cores × 2) + 1 = **5 Workers** (4 HTTP + 1 Cron).
> Plus 1 Long-polling worker = 6 processes total.
> RAM Usage: 6 × 300MB = ~1.8 GB (Safe for a 4GB server).

### Essential Odoo Parameters (`odoo.conf`)

| Parameter | Default | Recommended | Explanation |
| :--- | :--- | :--- | :--- |
| `workers` | 0 | **(Cores × 2) + 1** | Set > 0 for Multiprocess mode. 0 is for dev only. |
| `max_cron_threads` | 1 | **1** (or 2-3 for heavy background tasks) | Dedicated workers for scheduled jobs. |
| `limit_time_cpu` | 60s | **60s** | Max CPU time per request. Prevents infinite loops. |
| `limit_time_real` | 120s | **120s** | Max wall-clock time. Buffer for DB/Network waits. |
| `limit_memory_soft` | 2048MB | **2048 MB** (or lower for small RAM) | Worker restarts gracefully after finishing job if limit hit. |
| `limit_memory_hard` | 2560MB | **2560 MB** | Worker is killed immediately if this limit is hit. |
| `db_maxconn` | 64 | **32** (Safe ceiling) | Max DB connections per worker. |

---

## Step 3: PostgreSQL Performance Tuning

PostgreSQL defaults are often too low for Odoo. Tuning these improves speed significantly.

### 3.1 Memory Parameters

| Parameter | Recommended Value | Description |
| :--- | :--- | :--- |
| `shared_buffers` | **15-20% of Total RAM** | DB Page Cache. (Up to 40% on dedicated DB servers). |
| `effective_cache_size` | **50-70% of Total RAM** | Hint for the query planner. Approx 2-3x shared_buffers. |
| `work_mem` | **8MB - 32MB** | RAM per sort/hash operation. Increase carefully; too high causes swapping. |
| `maintenance_work_mem` | **~1/16 of Total RAM** | Used for VACUUM and index builds (e.g., 256MB for 4GB RAM). |

### 3.2 Checkpoints & WAL (Write Ahead Log)
Smoothing checkpoints reduces I/O spikes (server stalling).

| Parameter | Recommended Value | Impact |
| :--- | :--- | :--- |
| `checkpoint_completion_target` | **0.9** | Spreads writes out to avoid freezing. |
| `checkpoint_timeout` | **15 - 30 min** | Default (5min) is too frequent. |
| `min_wal_size` | **1 GB - 2 GB** | Increases buffer before forcing a checkpoint. |
| `max_wal_size` | **2 GB - 4 GB** | (Up to 10GB if disk space allows). |

### 3.3 Connectivity & SSD Optimization

| Parameter | Value | Notes |
| :--- | :--- | :--- |
| `max_connections` | **50 - 100** | Start with 50. Use Pgbouncer for high concurrency. |
| `random_page_cost` | **1.1** | Set this if using **SSD/NVMe**. |
| `effective_io_concurrency` | **200** | For NVMe drives (Set to 64 for SATA SSD). |
| `jit` | **off** | JIT slows down Odoo’s many small queries. |

### 3.4 Autovacuum (Prevents Table Bloat)
*   **Action:** Enable Autovacuum.
*   **Large Tables:** Lower `autovacuum_vacuum_scale_factor` to **0.05** (or **0.02** for extreme churn tables like `mail_message`).
*   **Workers:** Increase `autovacuum_max_workers` to **5** on larger servers.

---

## Step 4: Sample Configuration Profiles

Use these preset configurations based on your server size.

### Small Server
**Specs:** 2 vCPU / 4 GB RAM (NVMe SSD)

```ini
# PostgreSQL Config
shared_buffers = 768MB
effective_cache_size = 2.0GB
work_mem = 8MB
maintenance_work_mem = 256MB
checkpoint_timeout = 15min
checkpoint_completion_target = 0.9
min_wal_size = 1GB
max_wal_size = 2GB
max_connections = 50
max_worker_processes = 2
max_parallel_workers = 2
max_parallel_workers_per_gather = 1
random_page_cost = 1.1
effective_io_concurrency = 200
jit = off
```

### Medium Server
**Specs:** 4 vCPU / 8 GB RAM (NVMe SSD)

```ini
# PostgreSQL Config
shared_buffers = 1.5GB
effective_cache_size = 5GB
work_mem = 16MB
maintenance_work_mem = 512MB
checkpoint_timeout = 20min
checkpoint_completion_target = 0.9
min_wal_size = 1GB
max_wal_size = 4GB
max_connections = 100
max_worker_processes = 4
max_parallel_workers = 4
max_parallel_workers_per_gather = 2
random_page_cost = 1.1
effective_io_concurrency = 200
jit = off
```

### Large Server
**Specs:** 8 vCPU / 16 GB RAM (NVMe SSD)

```ini
# PostgreSQL Config
shared_buffers = 3GB
effective_cache_size = 10GB
work_mem = 32MB
maintenance_work_mem = 1GB
checkpoint_timeout = 30min
checkpoint_completion_target = 0.9
min_wal_size = 2GB
max_wal_size = 8GB
max_connections = 100
max_worker_processes = 8
max_parallel_workers = 8
max_parallel_workers_per_gather = 4
random_page_cost = 1.1
effective_io_concurrency = 200
jit = off
```

### Extra Large Server
**Specs:** 16 Dedicated Cores / 128 GB RAM (NVMe SSD)

```ini
# PostgreSQL Config
shared_buffers = 32GB           # ~25% of RAM
effective_cache_size = 96GB     # ~3x shared_buffers
work_mem = 32MB                 # 64MB for reporting sessions
maintenance_work_mem = 2GB

checkpoint_timeout = 30min
checkpoint_completion_target = 0.9
min_wal_size = 2GB
max_wal_size = 12GB

max_connections = 100
max_worker_processes = 16
max_parallel_workers = 16
max_parallel_workers_per_gather = 6

random_page_cost = 1.1
effective_io_concurrency = 200
jit = off

# Aggressive Autovacuum for large instances
autovacuum_max_workers = 5
autovacuum_vacuum_scale_factor = 0.05
autovacuum_analyze_scale_factor = 0.05
autovacuum_vacuum_cost_limit = 1000
autovacuum_vacuum_cost_delay = 5ms
```