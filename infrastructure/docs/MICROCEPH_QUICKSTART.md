# MicroCeph Quick Start Guide

## Single-Node Testing (5 Minutes)

### One-Command Setup

```bash
cd /home/tariron/Projects/saasodoo
sudo bash infrastructure/scripts/setup-microceph-single-node.sh
```

This automated script will:
- ✅ Install MicroCeph
- ✅ Create 50GB storage (loop device)
- ✅ Enable CephFS filesystem
- ✅ Mount at `/mnt/cephfs`
- ✅ Create all 11 volume directories

### Start SaaSodoo with CephFS

```bash
# Stop current stack
docker compose -f infrastructure/compose/docker-compose.dev.yml down

# Start with CephFS-backed volumes
docker compose -f infrastructure/compose/docker-compose.ceph.yml up -d

# Verify services
docker compose -f infrastructure/compose/docker-compose.ceph.yml ps
```

### Verify Everything Works

```bash
# Check CephFS mount
df -h /mnt/cephfs

# Check Ceph health (may show HEALTH_WARN for single node - this is OK)
sudo ceph health

# Test database
docker exec saasodoo-postgres psql -U odoo_user -d odoo -c "SELECT version();"

# Test API endpoints
curl http://localhost:8001/health  # user-service
curl http://localhost:8004/health  # billing-service
```

---

## What Changed?

### Before (Local Volumes)
```yaml
volumes:
  postgres-data:
    driver: local
```

### After (CephFS-Backed)
```yaml
volumes:
  postgres-data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /mnt/cephfs/postgres_data
```

**Result**: Data is now stored on CephFS distributed filesystem instead of local disk.

---

## Troubleshooting

### Issue: "HEALTH_WARN: insufficient standby MDS"
**Solution**: This is normal for single-node testing. Ignore it.

### Issue: Permission denied
```bash
sudo chmod -R 777 /mnt/cephfs/*
```

### Issue: Mount fails
```bash
# Check if MDS is running
sudo ceph mds stat

# Check logs
sudo journalctl -u snap.microceph.daemon -f
```

### Issue: Start fresh
```bash
# Unmount and remove everything
sudo umount /mnt/cephfs
sudo snap remove microceph --purge

# Re-run setup script
sudo bash infrastructure/scripts/setup-microceph-single-node.sh
```

---

## Production 3-Node Setup

See: `MICROCEPH_MIGRATION.md` for complete production deployment guide.

**Key Differences**:
- Install on 3 nodes instead of 1
- Use real disks (`/dev/sdb`) instead of loop device
- Automatic replica=3 (no size=1 override needed)
- Mount CephFS on all 3 nodes
- Deploy Docker Swarm stack

---

## Commands Reference

### Check Status
```bash
sudo microceph status          # Cluster overview
sudo ceph health              # Health status
sudo ceph fs status           # CephFS status
df -h /mnt/cephfs            # Check mount
```

### Manage Services
```bash
# Stop stack
docker compose -f infrastructure/compose/docker-compose.ceph.yml down

# Start stack
docker compose -f infrastructure/compose/docker-compose.ceph.yml up -d

# View logs
docker compose -f infrastructure/compose/docker-compose.ceph.yml logs -f

# Check specific service
docker compose -f infrastructure/compose/docker-compose.ceph.yml logs postgres
```

### Data Operations
```bash
# List volumes
ls -lah /mnt/cephfs/

# Check volume size
du -sh /mnt/cephfs/*

# Backup specific volume
sudo tar czf postgres_backup.tar.gz -C /mnt/cephfs postgres_data/
```

---

## File Locations

- **Setup Script**: `infrastructure/scripts/setup-microceph-single-node.sh`
- **Docker Compose**: `infrastructure/compose/docker-compose.ceph.yml`
- **Full Documentation**: `infrastructure/docs/MICROCEPH_MIGRATION.md`
- **Comparison Guide**: `infrastructure/docs/STORAGE_SOLUTIONS_COMPARISON.md`
- **Mount Point**: `/mnt/cephfs/`
- **Volume Directories**: `/mnt/cephfs/{postgres_data,redis_data,...}`

---

## Testing Checklist

- [ ] MicroCeph installed (`sudo microceph status`)
- [ ] CephFS mounted (`df -h /mnt/cephfs`)
- [ ] All 11 volume directories exist (`ls /mnt/cephfs/`)
- [ ] Docker stack starts (`docker compose ps`)
- [ ] Postgres accessible (`docker exec ... psql`)
- [ ] Services healthy (`curl localhost:8001/health`)
- [ ] Data persists after restart

---

**Total Time**: ~5 minutes automated setup + 2 minutes verification = **7 minutes** to test!
