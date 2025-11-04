# Ceph Cluster Manager Script

## Overview
This script automates the removal and installation of a Ceph cluster on the manager node (10.0.0.2).

## Location
`/root/ceph-cluster-manager.sh`

## Usage

### Full Reinstall (Remove + Install)
```bash
./ceph-cluster-manager.sh --reinstall
```

### Remove Cluster Only
```bash
./ceph-cluster-manager.sh --remove
```

### Install Cluster Only
```bash
./ceph-cluster-manager.sh --install
```

### Show Help
```bash
./ceph-cluster-manager.sh --help
```

## What the Script Does

### Removal Phase
1. Finds and removes all existing Ceph clusters
2. Cleans up configuration files in `/etc/ceph`
3. Removes data directories in `/var/lib/ceph`
4. Uninstalls cephadm binary and packages
5. Removes repository files

### Installation Phase
1. Installs dependencies (python3, lvm2, podman)
2. Downloads and installs cephadm
3. Verifies network configuration (10.0.0.2)
4. Tests connectivity to nodes 10.0.0.1 and 10.0.0.3
5. Bootstraps Ceph cluster with:
   - Manager IP: 10.0.0.2
   - Cluster network: 10.0.0.0/22
6. Displays cluster information
7. Saves details to `/root/ceph-cluster-info.txt`

## After Installation

### 1. Copy SSH Key to Other Nodes
The SSH public key is saved in `/etc/ceph/ceph.pub`. Copy it to the other nodes:

```bash
# Display the key
cat /etc/ceph/ceph.pub

# Copy to other nodes (if SSH password auth is enabled)
ssh-copy-id -i /etc/ceph/ceph.pub root@10.0.0.1
ssh-copy-id -i /etc/ceph/ceph.pub root@10.0.0.3
```

Or manually add the key to `/root/.ssh/authorized_keys` on each node.

### 2. Add Nodes to Cluster
```bash
ceph orch host add node1 10.0.0.1
ceph orch host add node3 10.0.0.3
```

### 3. List Hosts
```bash
ceph orch host ls
```

### 4. Create OSDs (Directory-based for testing)
```bash
# Create directory on each node first
mkdir -p /var/lib/ceph/osd

# Then add OSDs
ceph orch daemon add osd node1:/var/lib/ceph/osd
ceph orch daemon add osd node3:/var/lib/ceph/osd
```

Or for disk-based OSDs:
```bash
# List available devices
ceph orch device ls

# Add all available devices as OSDs
ceph orch apply osd --all-available-devices
```

### 5. Check Cluster Status
```bash
ceph -s
ceph orch ps
ceph osd tree
```

### 6. Access Dashboard
The dashboard URL and credentials are displayed after installation and saved in `/root/ceph-cluster-info.txt`.

## Useful Commands

### Check Ceph Status
```bash
cephadm shell -- ceph -s
```

### View Cluster Configuration
```bash
cat /etc/ceph/ceph.conf
```

### List Running Services
```bash
ceph orch ps
```

### View Logs
```bash
ceph -W cephadm
journalctl -u ceph-*.service -f
```

### Enable Additional Services

#### Object Storage (RGW)
```bash
ceph orch apply rgw myrgw --placement="3"
```

#### File System (CephFS)
```bash
# Create MDS service
ceph orch apply mds myfs --placement="3"

# Create CephFS
ceph fs volume create myfs
```

#### Block Storage (RBD)
RBD is enabled by default. Create a pool:
```bash
ceph osd pool create rbd 32 32
ceph osd pool application enable rbd rbd
```

## Configuration Details

- **Manager IP**: 10.0.0.2
- **Cluster Network**: 10.0.0.0/22
- **Ceph Version**: Reef (18.2.7)
- **Container Runtime**: Podman/Docker
- **Dashboard Port**: 8443 (HTTPS)

## Troubleshooting

### Check Bootstrap Logs
```bash
cat /tmp/ceph-bootstrap.log
```

### Verify Network
```bash
ip addr show | grep 10.0.0.2
ping -c 2 10.0.0.1
ping -c 2 10.0.0.3
```

### Check Running Containers
```bash
podman ps
```

### Check Ceph Services
```bash
systemctl list-units | grep ceph
```

### Restart Manager
```bash
ceph mgr fail
```

## Notes

- The script must be run as root
- Ensure 10.0.0.2 is configured on the eth1 interface
- Nodes 10.0.0.1 and 10.0.0.3 must be reachable on the private network
- Bootstrap process takes 5-10 minutes
- All cluster information is saved to `/root/ceph-cluster-info.txt`

## Support

For more information, visit:
- Official Ceph Documentation: https://docs.ceph.com/
- Cephadm Documentation: https://docs.ceph.com/en/latest/cephadm/
