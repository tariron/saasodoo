# MetalLB - Load Balancer for Bare Metal Kubernetes

MetalLB provides LoadBalancer service type support for bare metal Kubernetes clusters.

## Installation

### Step 1: Install MetalLB Core
```bash
# Apply official MetalLB manifests
kubectl apply -f https://raw.githubusercontent.com/metallb/metallb/v0.14.0/config/manifests/metallb-native.yaml

# Wait for MetalLB pods to be ready
kubectl wait --namespace metallb-system \
  --for=condition=ready pod \
  --selector=app=metallb \
  --timeout=90s
```

### Step 2: Apply IP Pool and L2 Advertisement
```bash
# Apply IP address pool and L2 advertisement
kubectl apply -f 02-ipaddresspool.yaml
kubectl apply -f 03-l2advertisement.yaml
```

### Step 3: Verify Installation
```bash
# Check MetalLB pods
kubectl get pods -n metallb-system

# Check IP address pool
kubectl get ipaddresspool -n metallb-system

# Check L2 advertisement
kubectl get l2advertisement -n metallb-system

# Verify LoadBalancer services get external IPs
kubectl get svc -n saasodoo
```

## Configuration

### IP Address Pool
The IP address pool is configured in `02-ipaddresspool.yaml`:
- **Pool Name**: `default-pool`
- **IP Range**: `62.171.153.219/32` (single IP)

To add more IPs, edit the addresses section:
```yaml
spec:
  addresses:
  - 62.171.153.219/32
  - 192.168.1.240-192.168.1.250  # IP range example
```

### L2 Advertisement
L2 mode is configured in `03-l2advertisement.yaml`. This allows MetalLB to respond to ARP requests for the assigned IPs.

## Troubleshooting

### LoadBalancer stuck in Pending
```bash
# Check MetalLB controller logs
kubectl logs -n metallb-system -l app=metallb,component=controller

# Check speaker logs
kubectl logs -n metallb-system -l app=metallb,component=speaker
```

### Service not accessible
```bash
# Verify external IP is assigned
kubectl get svc -A | grep LoadBalancer

# Check MetalLB speaker is running on all nodes
kubectl get pods -n metallb-system -o wide
```

## References
- [MetalLB Documentation](https://metallb.universe.tf/)
- [MetalLB Installation Guide](https://metallb.universe.tf/installation/)
