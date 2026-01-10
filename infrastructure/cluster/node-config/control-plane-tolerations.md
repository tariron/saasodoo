# Control Plane Tolerations Guide

After tainting control plane nodes with `NoSchedule`, certain DaemonSets need tolerations to run on ALL nodes.

## Control Plane Taint Applied

```bash
kubectl taint nodes vmi2887101 vmi2887102 vmi2887103 node-role.kubernetes.io/control-plane:NoSchedule
```

## Components Requiring Tolerations

### Must Run on ALL Nodes (including control plane)

These DaemonSets need the following toleration to run on tainted control plane nodes:

```yaml
tolerations:
  - key: "node-role.kubernetes.io/control-plane"
    operator: "Exists"
    effect: "NoSchedule"
```

| Component | Type | Why |
|-----------|------|-----|
| **Node Exporter** | DaemonSet | Collect metrics from ALL nodes |
| **kube-proxy** | DaemonSet | Already has toleration (RKE2 default) |
| **Canal/Calico CNI** | DaemonSet | Already has toleration (RKE2 default) |

### Example: Node Exporter with Toleration

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: node-exporter
  namespace: monitoring
spec:
  selector:
    matchLabels:
      app: node-exporter
  template:
    metadata:
      labels:
        app: node-exporter
    spec:
      tolerations:
        - key: "node-role.kubernetes.io/control-plane"
          operator: "Exists"
          effect: "NoSchedule"
      containers:
        - name: node-exporter
          image: prom/node-exporter:latest
          ports:
            - containerPort: 9100
```

## Components That Stay on Workers Only

These do NOT need tolerations - they should only run on worker nodes:

| Component | Type | Runs On |
|-----------|------|---------|
| MetalLB Controller | Deployment | Workers |
| MetalLB Speaker | DaemonSet | Workers (handles ingress traffic) |
| Traefik | Deployment/DaemonSet | Workers |
| Prometheus | Deployment | Workers |
| Grafana | Deployment | Workers |
| Cert-manager | Deployment | Workers |
| kube-state-metrics | Deployment | Workers |
| Rook-Ceph Operator | Deployment | Workers |
| Rook-Ceph OSD | DaemonSet | Workers (with node selector) |
| Platform Services | Deployment | Workers |

## Node Labels

Platform worker nodes are labeled for scheduling:

```bash
kubectl label nodes vmi3014979 vmi3014980 vmi3014981 node-role=platform
```

Use nodeSelector or nodeAffinity to target platform workers:

```yaml
nodeSelector:
  node-role: platform
```

## Verification

After tainting, verify only expected pods run on control plane:

```bash
# Should only show kube-system pods (etcd, apiserver, etc.) and node-exporter
kubectl get pods -A -o wide | grep -E "vmi2887101|vmi2887102|vmi2887103"
```
