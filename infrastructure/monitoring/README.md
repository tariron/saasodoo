# SaaSOdoo Monitoring Stack

Comprehensive monitoring solution for the SaaSOdoo platform using Prometheus, Grafana, and AlertManager.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Monitoring Stack                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│  │  Prometheus  │───▶│ AlertManager │───▶│   Grafana    │          │
│  │   (Metrics)  │    │  (Alerting)  │    │ (Dashboard)  │          │
│  └──────┬───────┘    └──────────────┘    └──────────────┘          │
│         │                                                           │
│         ▼                                                           │
│  ┌──────────────────────────────────────────────────────────┐      │
│  │                   ServiceMonitors                         │      │
│  ├──────────────┬──────────────┬──────────────┬────────────┤      │
│  │ user-service │billing-service│instance-service│ postgres  │      │
│  │ notification │database-service│instance-worker│ rabbitmq  │      │
│  │              │              │              │   redis    │      │
│  └──────────────┴──────────────┴──────────────┴────────────┘      │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Components

| Component | Version | Purpose |
|-----------|---------|---------|
| Prometheus Operator | v0.79.0 | Manages Prometheus CRDs |
| Prometheus | v3.1.0 | Metrics collection |
| AlertManager | v0.28.0 | Alert routing |
| Grafana | v11.4.0 | Visualization |

## Quick Start

### Prerequisites

1. Install Prometheus Operator:
```bash
kubectl apply --server-side -f https://raw.githubusercontent.com/prometheus-operator/prometheus-operator/v0.79.0/bundle.yaml
```

2. Wait for operator to be ready:
```bash
kubectl wait --for=condition=Available --timeout=300s deployment/prometheus-operator
```

### Deploy Monitoring Stack

```bash
# 1. Create namespace and RBAC
kubectl apply -f infrastructure/monitoring/prometheus/00-namespace.yaml
kubectl apply -f infrastructure/monitoring/prometheus/02-rbac.yaml

# 2. Deploy Prometheus
kubectl apply -f infrastructure/monitoring/prometheus/03-prometheus.yaml

# 3. Deploy ServiceMonitors
kubectl apply -f infrastructure/monitoring/prometheus/04-servicemonitors.yaml

# 4. Deploy AlertManager
kubectl apply -f infrastructure/monitoring/prometheus/05-alertmanager.yaml

# 5. Deploy Alerting Rules
kubectl apply -f infrastructure/monitoring/prometheus/06-alerting-rules.yaml

# 6. Deploy Grafana
kubectl apply -f infrastructure/monitoring/grafana/

# 7. Wait for pods
kubectl wait --for=condition=Ready --timeout=300s pods -l app.kubernetes.io/name=prometheus -n monitoring
kubectl wait --for=condition=Ready --timeout=300s pods -l app.kubernetes.io/name=grafana -n monitoring
```

### Access URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| Grafana | http://grafana.62.171.153.219.nip.io | admin / SaasOdoo2024! |
| Prometheus | http://prometheus.62.171.153.219.nip.io | - |
| AlertManager | http://alertmanager.62.171.153.219.nip.io | - |

## Directory Structure

```
monitoring/
├── prometheus/
│   ├── 00-namespace.yaml          # Monitoring namespace
│   ├── 01-operator.yaml           # Operator installation docs
│   ├── 02-rbac.yaml               # ServiceAccount & RBAC
│   ├── 03-prometheus.yaml         # Prometheus CR + Service
│   ├── 04-servicemonitors.yaml    # Service discovery configs
│   ├── 05-alertmanager.yaml       # AlertManager CR + config
│   └── 06-alerting-rules.yaml     # PrometheusRules for alerts
├── grafana/
│   ├── 00-configmap.yaml          # Grafana configuration
│   ├── 01-secret.yaml             # Admin credentials
│   ├── 02-pvc.yaml                # Persistent storage
│   ├── 03-deployment.yaml         # Grafana deployment
│   ├── 04-service.yaml            # ClusterIP service
│   ├── 05-ingressroute.yaml       # Traefik routes
│   ├── 06-dashboards-saasodoo.yaml    # Platform dashboards
│   ├── 07-dashboards-kubernetes.yaml  # Cluster dashboards
│   └── 08-dashboards-infrastructure.yaml # DB/Queue dashboards
└── README.md
```

## Dashboards

### Pre-installed Dashboards

| Dashboard | UID | Description |
|-----------|-----|-------------|
| SaaSOdoo Platform Overview | `saasodoo-overview` | Service health, queues, request rates |
| Kubernetes Cluster | `kubernetes-cluster` | Nodes, pods, resource usage |
| PostgreSQL (CNPG) | `postgresql-cnpg` | Connections, replication, queries |
| RabbitMQ | `rabbitmq` | Queues, messages, connections |

### Accessing Dashboards

1. Open Grafana: http://grafana.62.171.153.219.nip.io
2. Login with admin credentials
3. Navigate to Dashboards → Browse
4. Select folder: SaaSOdoo, Kubernetes, or Infrastructure

## Alerting Rules

### Severity Levels

| Severity | Response Time | Notification |
|----------|---------------|--------------|
| `critical` | Immediate | PagerDuty/Slack (immediate) |
| `warning` | Hours | Email/Slack (batched) |
| `info` | Days | Dashboard only |

### Configured Alerts

#### Application Alerts
- `ServiceDown` - Service not responding
- `HighErrorRate` - Error rate > 5%
- `HighLatency` - P95 latency > 1s
- `PodRestartingTooOften` - Pod restarted > 3 times/hour

#### Instance Provisioning Alerts
- `InstanceProvisioningFailed` - Celery task failures
- `InstanceProvisioningBacklog` - Queue depth > 10
- `CeleryWorkerDown` - Worker not running

#### PostgreSQL Alerts
- `PostgreSQLDown` - Database unreachable
- `PostgreSQLReplicationLag` - Lag > 30s
- `PostgreSQLHighConnections` - > 80% connections used
- `PostgreSQLDeadlocks` - Deadlocks detected

#### RabbitMQ Alerts
- `RabbitMQNodeDown` - Node unreachable
- `RabbitMQQueueMessagesHigh` - Queue depth > 1000
- `RabbitMQMemoryHigh` - Memory > 80%

#### Kubernetes Alerts
- `NodeNotReady` - Node in NotReady state
- `PodCrashLooping` - Pod in CrashLoopBackOff
- `PVCAlmostFull` - PVC > 85% used
- `HighCPUUsage` / `HighMemoryUsage` - Resource > 90%

## Configuration

### Adding New ServiceMonitors

To monitor a new service, create a ServiceMonitor:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: my-service
  namespace: saasodoo
  labels:
    prometheus: saasodoo  # Required for discovery
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: my-service
  endpoints:
    - port: http
      path: /metrics
      interval: 30s
```

### Adding Custom Alerts

Create a PrometheusRule:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: my-alerts
  namespace: monitoring
  labels:
    prometheus: saasodoo  # Required for discovery
spec:
  groups:
    - name: my-service
      rules:
        - alert: MyServiceAlert
          expr: my_metric > 100
          for: 5m
          labels:
            severity: warning
          annotations:
            summary: "Something happened"
```

### Configuring Alert Receivers

Edit the AlertManager secret to add receivers:

```yaml
# In 05-alertmanager.yaml, update the secret
receivers:
  - name: 'slack-critical'
    slack_configs:
      - api_url: 'https://hooks.slack.com/services/xxx'
        channel: '#alerts-critical'
        send_resolved: true

  - name: 'pagerduty-critical'
    pagerduty_configs:
      - service_key: 'your-service-key'
        send_resolved: true
```

## Metrics Exposed by Services

Each SaaSOdoo service should expose Prometheus metrics at `/metrics`:

### FastAPI Services (prometheus-fastapi-instrumentator)

```python
# In main.py
from prometheus_fastapi_instrumentator import Instrumentator

Instrumentator().instrument(app).expose(app)
```

Metrics exposed:
- `http_requests_total` - Request count by method, path, status
- `http_request_duration_seconds` - Request latency histogram
- `http_requests_in_progress` - Current in-flight requests

### Celery Workers (celery-prometheus-exporter)

```python
# In worker startup
from prometheus_client import start_http_server
start_http_server(9090)
```

Metrics exposed:
- `celery_task_sent_total` - Tasks sent
- `celery_task_received_total` - Tasks received
- `celery_task_succeeded_total` - Tasks completed
- `celery_task_failed_total` - Tasks failed
- `celery_task_runtime_seconds` - Task execution time

## Storage

| Component | Storage Class | Size | Retention |
|-----------|--------------|------|-----------|
| Prometheus | rook-cephfs | 50Gi | 15 days |
| AlertManager | rook-cephfs | 5Gi | N/A |
| Grafana | rook-cephfs | 10Gi | N/A |

## Troubleshooting

### Prometheus not scraping targets

1. Check ServiceMonitor labels match Prometheus selector:
```bash
kubectl get servicemonitor -n saasodoo -o yaml | grep -A5 labels
```

2. Verify target is discovered:
```bash
kubectl port-forward -n monitoring svc/prometheus 9090:9090
# Open http://localhost:9090/targets
```

### Alerts not firing

1. Check PrometheusRule is discovered:
```bash
kubectl get prometheusrules -n monitoring
```

2. Verify rule syntax:
```bash
kubectl port-forward -n monitoring svc/prometheus 9090:9090
# Open http://localhost:9090/rules
```

### Grafana dashboards not loading

1. Check dashboard ConfigMaps are mounted:
```bash
kubectl exec -n monitoring deploy/grafana -- ls /var/lib/grafana/dashboards/saasodoo
```

2. Check Grafana logs:
```bash
kubectl logs -n monitoring -l app.kubernetes.io/name=grafana --tail=100
```

## Maintenance

### Backup Grafana Dashboards

```bash
# Export all dashboards
kubectl exec -n monitoring deploy/grafana -- \
  grafana-cli admin export-dashboard --all /tmp/dashboards-backup
kubectl cp monitoring/$(kubectl get pod -n monitoring -l app.kubernetes.io/name=grafana -o jsonpath='{.items[0].metadata.name}'):/tmp/dashboards-backup ./dashboards-backup
```

### Compact Prometheus TSDB

Prometheus auto-compacts, but to force:
```bash
kubectl exec -n monitoring prometheus-prometheus-0 -- \
  promtool tsdb compact /prometheus
```

### Upgrade Components

1. Update image versions in manifests
2. Apply changes:
```bash
kubectl apply -f infrastructure/monitoring/prometheus/
kubectl apply -f infrastructure/monitoring/grafana/
```

## Next Steps

- [ ] Configure Slack/PagerDuty receivers for production
- [ ] Add Loki for log aggregation
- [ ] Add Tempo for distributed tracing
- [ ] Configure long-term storage with Thanos
- [ ] Set up Grafana OIDC/OAuth authentication
