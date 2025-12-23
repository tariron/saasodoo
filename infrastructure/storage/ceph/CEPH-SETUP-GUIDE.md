# Ceph Cluster Setup Guide

Complete guide for setting up a Ceph cluster on Contabo VPS with directory-based OSDs.

## Prerequisites

- **3+ Ubuntu servers** on private network (10.0.0.x)
- **Root SSH access** to all nodes
- **150GB+ disk space** per server
- **Network connectivity** between all nodes

---

## Initial 3-Node Cluster Setup

### Step 1: Bootstrap Manager Node (10.0.0.2)

```bash
# On manager node (10.0.0.2)
cd /root

# Create/reinstall Ceph cluster
./ceph-cluster-manager.sh --reinstall
```

**What this does:**
- Removes any existing Ceph installation
- Installs cephadm
- Bootstraps Ceph cluster on 10.0.0.2
- Creates dashboard (saves credentials to `/root/ceph-cluster-info.txt`)
- Sets up monitoring stack

**Expected output:**
- Cluster ID (FSID)
- Dashboard URL: `https://<hostname>:8443/`
- Dashboard credentials: `admin / <random-password>`

---

### Step 1.5: Configure SSH Keys for Passwordless Access

**IMPORTANT**: This step must be completed before adding worker nodes to ensure Ceph scripts work without password prompts.

#### On Manager Node (10.0.0.2):

**1. Generate SSH key pair:**
```bash
# Generate 4096-bit RSA key for Ceph cluster
ssh-keygen -t rsa -b 4096 -f /etc/ceph/ceph -N "" -C "ceph-$(cat /etc/ceph/ceph.conf | grep fsid | awk '{print $3}')"

# Verify both keys exist
ls -la /etc/ceph/ceph*
```

**2. Configure SSH to use this key:**
```bash
# Create SSH config
mkdir -p ~/.ssh
cat >> ~/.ssh/config << 'EOF'
Host 10.0.0.1 10.0.0.2 10.0.0.3
    IdentityFile /etc/ceph/ceph
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
EOF
chmod 600 ~/.ssh/config
```

**3. Display the public key (you'll need this for workers):**
```bash
cat /etc/ceph/ceph.pub
```

#### On Each Worker Node (10.0.0.1, 10.0.0.3):

**CRITICAL**: The SSH public key MUST be on a single line in authorized_keys. Line wrapping will break authentication.

**Method 1 - Using nano (Recommended):**
```bash
# On each worker, edit authorized_keys with nano (disables line wrapping)
nano -w ~/.ssh/authorized_keys

# Paste the public key from manager (/etc/ceph/ceph.pub)
# It should be ONE complete line starting with "ssh-rsa"
# Press Ctrl+X, Y, Enter to save

# Set correct permissions
chmod 600 ~/.ssh/authorized_keys
chmod 700 ~/.ssh
```

**Method 2 - Using scp from workers:**
```bash
# If you can SSH from worker to manager
scp root@10.0.0.2:/etc/ceph/ceph.pub /tmp/manager_key.pub
cat /tmp/manager_key.pub >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

**4. Verify SSH key was added correctly:**
```bash
# On each worker, check the key fingerprint
ssh-keygen -lf ~/.ssh/authorized_keys

# Should show a 4096-bit RSA key matching the manager's fingerprint
```

#### Back on Manager - Test Passwordless SSH:

```bash
# Test SSH to both workers
ssh root@10.0.0.1 'echo "SSH to worker 1 SUCCESS"'
ssh root@10.0.0.3 'echo "SSH to worker 2 SUCCESS"'

# Test Ceph script (should not ask for password)
cd /root/saasodoo/infrastructure/Ceph
./ceph-operations.sh status
```

**Expected Result**: All SSH commands work without password prompts.

**Troubleshooting**:
- If SSH still asks for password, verify the key fingerprints match
- Ensure authorized_keys has the key on ONE line (not wrapped)
- Check permissions: 600 on authorized_keys, 700 on ~/.ssh directory

---

### Step 2: Prepare Worker Nodes

Run the worker setup script on **each node** (including manager):

```bash
# On 10.0.0.1 (worker 1)
cd /root
./ceph-worker-setup.sh

# On 10.0.0.2 (manager - THIS NODE)
cd /root
./ceph-worker-setup.sh

# On 10.0.0.3 (worker 2)
cd /root
./ceph-worker-setup.sh
```

**What this does:**
- Cleans up old OSD setup (if any)
- Installs dependencies (python3, lvm2, podman)
- Configures SSH access
- Creates 33GB sparse file: `/var/lib/ceph/osd/osd-disk.img`
- Creates loop device (e.g., `/dev/loop2`)
- Makes it persistent across reboots

---

### Step 3: Add Worker Nodes to Cluster

From the **manager node (10.0.0.2)**, add each worker:

```bash
# Add node 1 (prompts for SSH password once)
./ceph-operations.sh add-node 10.0.0.1

# Add node 3 (prompts for SSH password once)
./ceph-operations.sh add-node 10.0.0.3
```

**What this does:**
- Copies SSH key to worker node
- Adds node to Ceph cluster
- Automatically detects loop device
- Attempts to add OSD (may fail - fixed in next step)

---

### Step 4: Add OSDs (Storage)

From the **manager node**, add OSD on each node:

```bash
# Add OSD on node 1
./ceph-operations.sh add-osd vmi2887101

# Add OSD on manager (node 2)
./ceph-operations.sh add-osd vmi2887102

# Add OSD on node 3
./ceph-operations.sh add-osd vmi2887103
```

**What this does:**
- Detects loop device on target node
- Creates OSD spec in raw mode (works with loop devices)
- Deploys OSD daemon
- Takes ~60 seconds to become active

**Wait 60 seconds**, then verify:

```bash
./ceph-operations.sh list-osds
# Should show 3 OSDs
```

---

### Step 5: Setup CephFS Filesystem

From the **manager node**:

```bash
./ceph-operations.sh setup-cephfs
```

**What this does:**
- Deploys MDS (Metadata Server) daemons (3 replicas)
- Creates CephFS volume: `saasodoo_fs`
- Takes ~90 seconds

---

### Step 6: Mount CephFS on All Nodes

From the **manager node**:

```bash
# Mount on manager (local)
./ceph-operations.sh mount-cephfs

# Mount on worker 1
./ceph-operations.sh mount-cephfs 10.0.0.1

# Mount on worker 2
./ceph-operations.sh mount-cephfs 10.0.0.3
```

**What this does:**
- Copies Ceph config and keyring to worker nodes
- Installs ceph-common package
- Mounts CephFS at `/mnt/cephfs`
- Adds to `/etc/fstab` for auto-mount on reboot

---

### Step 7: Create Odoo Storage Directories

From the **manager node**:

```bash
./ceph-operations.sh setup-odoo-storage
```

**What this does:**
Creates these directories in `/mnt/cephfs/`:
- `postgres_data/`
- `redis_data/`
- `rabbitmq_data/`
- `prometheus_data/`
- `killbill_db_data/`
- `odoo_instances/`
- `odoo_backups/`

---

### Step 8: Verify Cluster

```bash
# Check cluster status
./ceph-operations.sh status

# Should show:
# - health: HEALTH_OK
# - 3 monitors
# - 3 OSDs (all up and in)
# - CephFS active

# Verify CephFS mount
df -h /mnt/cephfs

# List Odoo directories
ls -lah /mnt/cephfs/
```

---

## Adding Additional Nodes Later

### When to Add Nodes
- Need more storage capacity
- Want better redundancy
- Scale out performance

### Steps to Add a New Node

#### 1. Prepare the New Node

On the **new node** (e.g., 10.0.0.4):

```bash
# Copy worker setup script to new node
scp root@10.0.0.2:/root/ceph-worker-setup.sh /root/

# Run worker setup
cd /root
./ceph-worker-setup.sh
```

#### 2. Add Node to Cluster

From the **manager node (10.0.0.2)**:

```bash
# Add the new node
./ceph-operations.sh add-node 10.0.0.4
# (Enter SSH password when prompted)
```

#### 3. Add OSD on New Node

```bash
# Add storage
./ceph-operations.sh add-osd <new-hostname>
# Replace <new-hostname> with actual hostname from previous step

# Wait 60 seconds, then verify
./ceph-operations.sh list-osds
```

#### 4. Mount CephFS on New Node

```bash
./ceph-operations.sh mount-cephfs 10.0.0.4
```

#### 5. Verify

```bash
./ceph-operations.sh status
# Should show 4 OSDs now

# On new node, verify mount
ssh root@10.0.0.4 "df -h /mnt/cephfs"
```

---

## Quick Reference Commands

### Cluster Management

```bash
# View cluster status
./ceph-operations.sh status

# List all nodes
./ceph-operations.sh list-nodes

# List all OSDs
./ceph-operations.sh list-osds
```

### Node Operations

```bash
# Add node
./ceph-operations.sh add-node <ip>

# Remove node
./ceph-operations.sh remove-node <hostname>
```

### Storage Operations

```bash
# Add OSD on existing node
./ceph-operations.sh add-osd <hostname>

# Setup CephFS (one-time)
./ceph-operations.sh setup-cephfs

# Mount CephFS on node
./ceph-operations.sh mount-cephfs <ip>

# Create Odoo directories (one-time)
./ceph-operations.sh setup-odoo-storage
```

### Help

```bash
./ceph-operations.sh help
```

---

## Cluster Configuration

### Storage Allocation
- **OSD Size**: 33GB per node (configurable in worker script)
- **Total Storage**: 33GB × number of nodes
- **Replication**: 3x (data stored on 3 different OSDs)
- **Effective Storage**: Total Storage ÷ 3

**Example**: 3 nodes × 33GB = 99GB total, ~33GB usable

### Network
- **Public Network**: 10.0.0.0/22
- **Cluster Network**: 10.0.0.0/22 (same as public)
- **Monitor Port**: 6789
- **Dashboard Port**: 8443 (HTTPS)

### Services
- **MON**: Monitor daemon (one per node, minimum 3)
- **MGR**: Manager daemon (one per node)
- **OSD**: Object Storage Daemon (one per node)
- **MDS**: Metadata Server for CephFS (3 replicas)

---

## File Locations

### Manager Node
- Cluster manager script: `/root/ceph-cluster-manager.sh`
- Operations script: `/root/ceph-operations.sh`
- Cluster info: `/root/ceph-cluster-info.txt`
- Ceph config: `/etc/ceph/ceph.conf`
- Admin keyring: `/etc/ceph/ceph.client.admin.keyring`
- SSH public key: `/etc/ceph/ceph.pub`

### Worker Nodes
- Worker setup script: `/root/ceph-worker-setup.sh`
- OSD image: `/var/lib/ceph/osd/osd-disk.img`
- Loop device: `/dev/loop#` (varies)

### All Nodes
- CephFS mount: `/mnt/cephfs/`
- Odoo data: `/mnt/cephfs/{postgres_data,redis_data,...}`

---

## Troubleshooting

### Cluster Won't Bootstrap

```bash
# Check if old cluster exists
ls /var/lib/ceph/

# Remove completely and retry
./ceph-cluster-manager.sh --remove
./ceph-cluster-manager.sh --reinstall
```

### OSD Won't Add

```bash
# Check if loop device exists on node
ssh root@<node-ip> "losetup -a | grep osd-disk.img"

# If not, run worker setup again
ssh root@<node-ip> "./ceph-worker-setup.sh"

# Then retry adding OSD
./ceph-operations.sh add-osd <hostname>
```

### CephFS Mount Fails

```bash
# Check if filesystem exists
./ceph-operations.sh status | grep fs

# If not, create it
./ceph-operations.sh setup-cephfs

# Check if ceph-common installed on node
ssh root@<node-ip> "dpkg -l | grep ceph-common"

# Retry mount
./ceph-operations.sh mount-cephfs <node-ip>
```

### Check Cluster Health

```bash
# Detailed status
cephadm shell -- ceph health detail

# Check specific services
cephadm shell -- ceph mon stat
cephadm shell -- ceph osd stat
cephadm shell -- ceph fs status
```

### View Logs

```bash
# Recent cluster events
cephadm shell -- ceph -W cephadm --watch-debug

# Service logs
journalctl -u ceph-*.service -f
```

---

## Dashboard Access

Access the Ceph dashboard at: `https://<manager-ip>:8443/`

**Credentials**: See `/root/ceph-cluster-info.txt`

**Dashboard Features**:
- Cluster overview
- OSD status and performance
- Monitor health
- Pool management
- CephFS status
- Performance graphs

---

## Changing OSD Size

To allocate more storage per node:

1. **Edit worker script**:
   ```bash
   nano /root/ceph-worker-setup.sh
   # Change line 21: OSD_SIZE_GB=33
   # To: OSD_SIZE_GB=100 (or desired size)
   ```

2. **Re-run on all nodes**:
   ```bash
   # Worker script automatically cleans up old setup
   ./ceph-worker-setup.sh
   ```

3. **Re-add OSDs**:
   ```bash
   ./ceph-operations.sh add-osd <hostname>
   ```

---

## Removing a Node

```bash
# 1. Remove from cluster (drains data first)
./ceph-operations.sh remove-node <hostname>

# 2. On the node being removed, clean up
ssh root@<node-ip> "umount /mnt/cephfs && losetup -D && rm -rf /var/lib/ceph"
```

---

## Starting Odoo with CephFS

After cluster setup is complete:

```bash
cd /root/saasodoo
docker compose -f infrastructure/compose/docker-compose.ceph.yml up -d
```

All Odoo data will now be stored on CephFS at `/mnt/cephfs/`.

---

## Important Notes

1. **Minimum 3 Nodes**: Ceph requires at least 3 nodes for proper replication
2. **Network Stability**: All nodes must be on the same private network
3. **Time Sync**: Ensure all nodes have synchronized time (NTP)
4. **SSH Keys**: Must be manually configured on manager and distributed to workers (see Step 1.5)
5. **Loop Devices**: Persist across reboots via `/etc/rc.local`
6. **Sparse Files**: OSD files grow dynamically as data is added
7. **Replication**: Data is replicated 3x by default (configurable)
8. **Auto-mount**: CephFS auto-mounts on reboot via `/etc/fstab`

---

## Summary Workflow

**Initial Setup** (3 nodes):
1. `./ceph-cluster-manager.sh --reinstall` (manager)
2. **Configure SSH keys** (manager + all workers) - **Step 1.5**
3. `./ceph-worker-setup.sh` (all 3 nodes)
4. `./ceph-operations.sh add-node <ip>` (2 workers)
5. `./ceph-operations.sh add-osd <hostname>` (all 3 nodes)
6. `./ceph-operations.sh setup-cephfs`
7. `./ceph-operations.sh mount-cephfs [ip]` (all 3 nodes)
8. `./ceph-operations.sh setup-odoo-storage`

**Adding Nodes** (later):
1. `./ceph-worker-setup.sh` (new node)
2. `./ceph-operations.sh add-node <ip>` (from manager)
3. `./ceph-operations.sh add-osd <hostname>` (from manager)
4. `./ceph-operations.sh mount-cephfs <ip>` (from manager)

Done! 🎉
