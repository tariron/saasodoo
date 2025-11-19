# Kubernetes Migration Plan - Docker Swarm to K3s

## Overview
Migrate SaaS Odoo platform from Docker Swarm to K3s to support 10,000+ Odoo instances with minimal code changes, leveraging existing CephFS storage and microservices architecture.

## Phase 1: Infrastructure Setup (Week 1)

### Step 1.1: K3s Cluster Installation
- Install K3s on 3 control plane nodes (HA setup)
- Join 5-10 worker nodes initially
- Keep built-in Traefik enabled (default)
- Configure kubectl access

**Test**: `kubectl get nodes` shows all nodes Ready, `kubectl get pods -n kube-system` shows traefik pod running

### Step 1.2: Storage Integration
- Deploy Rook-Ceph operator
- Configure CephFS CSI driver
- Create StorageClasses for CephFS with quota support
- Test PVC provisioning

**Test**: Create test PVC, mount to pod, write/read data, verify quota enforcement

### Step 1.3: Networking & Traefik Configuration
- Configure built-in Traefik via HelmChartConfig
- Convert existing middlewares (CORS, rate-limiting, security headers) to Traefik CRDs
- Configure cert-manager for TLS (optional)
- Set up MetalLB if needed (or use built-in servicelb)
- Create test IngressRoutes

**Test**: Deploy test service with IngressRoute, verify external access and middleware application

### Step 1.4: Secrets Management
- Create Kubernetes Secrets from .env files
- Deploy Sealed Secrets controller (optional, for GitOps)
- Migrate all credentials to Kubernetes Secrets

**Test**: Deploy pod that reads secrets, verify values match .env

---

## Phase 2: Supporting Services Migration (Week 2)

### Step 2.1: PostgreSQL Migration
- Deploy PostgreSQL StatefulSet with Ceph PVC
- Configure initdb scripts via ConfigMaps
- Create Services for each database (auth, instance, billing)
- Migrate data from Docker volumes

**Test**: Connect from test pod, verify all databases exist, run CRUD operations

### Step 2.2: Redis & RabbitMQ Migration
- Deploy Redis as StatefulSet with persistence
- Deploy RabbitMQ Operator or StatefulSet
- Configure vhost and users
- Verify data persistence across pod restarts

**Test**: Write data to Redis, restart pod, verify data persists; send/receive RabbitMQ messages

### Step 2.3: Monitoring Stack Migration
- Deploy Prometheus Operator with ServiceMonitors
- Deploy Grafana with dashboards
- Configure Elasticsearch + Kibana (optional)
- Set up alerting rules

**Test**: Verify metrics collection, test Grafana dashboards, trigger test alert

### Step 2.4: KillBill Stack Migration
- Deploy MariaDB StatefulSet for KillBill
- Deploy KillBill as Deployment
- Deploy Kaui admin interface
- Configure webhooks to billing-service

**Test**: Access Kaui UI, create test account/subscription, verify webhook delivery

---

## Phase 3: Microservices Migration (Week 3)

### Step 3.1: Convert Docker Compose to Kubernetes
- Use Kompose to generate initial manifests
- Create Helm charts or Kustomize overlays
- Define Deployments for all 5 services
- Create Services and Ingresses

**Test**: `kubectl apply` all manifests successfully, no errors

### Step 3.2: User Service Migration
- Deploy user-service Deployment
- Configure environment variables via ConfigMaps/Secrets
- Create Service and Ingress
- Mount shared schemas as ConfigMap

**Test**: Call health endpoint, test auth endpoints, verify database connectivity

### Step 3.3: Billing Service Migration
- Deploy billing-service Deployment
- Configure KillBill connection
- Set up Paynow integration
- Verify webhook endpoints

**Test**: Create subscription via API, verify in KillBill, test webhook flow

### Step 3.4: Instance Service Migration
- Deploy instance-service Deployment
- Deploy instance-worker as separate Deployment
- Mount Docker socket (temporary, will replace)
- Configure RabbitMQ queues

**Test**: Call instance API endpoints, verify Celery worker connectivity, test task execution

### Step 3.5: Frontend & Notification Services
- Deploy frontend-service Deployment
- Deploy notification-service Deployment
- Configure SMTP (MailHog)
- Set up Ingress routes

**Test**: Access frontend UI, send test notification, verify email in MailHog

---

## Phase 4: Instance Service Kubernetes Integration (Week 4)

### Step 4.1: Update Instance Service Code
- Replace Docker SDK with Kubernetes Python client
- Update provisioning tasks to create Deployments
- Implement namespace-per-instance or labeled approach
- Update monitoring tasks for Kubernetes pods

**Test**: Create instance via API, verify Deployment created, pod running, accessible

### Step 4.2: Resource Management
- Create ResourceQuota templates
- Define LimitRanges for Odoo instances
- Implement CephFS subvolume provisioning
- Configure NetworkPolicies for isolation

**Test**: Create instance, verify resource limits enforced, test quota enforcement, verify network isolation

### Step 4.3: Instance Lifecycle Operations
- Update start/stop operations (scale deployment 0↔1)
- Update backup/restore with CephFS snapshots
- Implement instance upgrades (rolling updates)
- Add instance health monitoring

**Test**: Stop/start instance, backup/restore data, upgrade Odoo version, verify monitoring alerts

### Step 4.4: Odoo Instance Template
- Create Odoo Deployment template with placeholders
- Configure Services for each instance (NodePort/LoadBalancer)
- Set up Ingress per instance (subdomain routing)
- Define persistent volume claims

**Test**: Provision 10 test instances, verify all accessible via unique URLs

---

## Phase 5: Auto-Scaling & Optimization (Week 5)

### Step 5.1: Horizontal Pod Autoscaling
- Deploy metrics-server
- Create HPAs for microservices
- Configure custom metrics (optional)
- Set scaling policies

**Test**: Generate load, verify pods scale up; remove load, verify scale down

### Step 5.2: Cluster Autoscaling
- Configure cluster-autoscaler (if cloud)
- Set node pool configurations
- Define scale-up/down policies
- Test node provisioning

**Test**: Deploy many instances to trigger node scale-up, verify new nodes join

### Step 5.3: Performance Optimization
- Enable pod anti-affinity for HA
- Configure topology spread constraints
- Implement pod priority classes
- Optimize resource requests/limits

**Test**: Run load tests, verify even pod distribution, test pod eviction priorities

### Step 5.4: Instance Provisioning Performance
- Implement instance pre-warming (pod pool)
- Add caching for frequent operations
- Optimize database queries
- Tune Celery worker concurrency

**Test**: Measure provisioning time, target <2 minutes for new instance

---

## Phase 6: Production Readiness (Week 6)

### Step 6.1: Backup & Disaster Recovery
- Deploy Velero for cluster backups
- Configure CephFS snapshot schedules
- Test backup restoration procedures
- Document recovery runbook

**Test**: Delete namespace, restore from backup, verify all data intact

### Step 6.2: Security Hardening
- Enable RBAC for all services
- Implement Pod Security Standards
- Configure network policies
- Scan images for vulnerabilities

**Test**: Attempt unauthorized access, verify denials; run security audit

### Step 6.3: Monitoring & Alerting
- Create custom Grafana dashboards
- Set up AlertManager rules
- Configure PagerDuty/Slack integration
- Implement log aggregation

**Test**: Trigger various alerts, verify notifications received

### Step 6.4: Documentation & Training
- Document deployment procedures
- Create troubleshooting guides
- Train team on kubectl/K9s
- Write incident response playbook

**Test**: Have team member deploy service using docs only

---

## Phase 7: Migration & Validation (Week 7)

### Step 7.1: Gradual Traffic Migration
- Set up parallel environment (Swarm + K3s)
- Migrate 10% of instances to K3s
- Monitor for issues
- Gradually increase to 100%

**Test**: Compare metrics between Swarm and K3s instances, verify parity

### Step 7.2: Load Testing
- Run load tests simulating 1,000 instances
- Test provisioning 100 instances concurrently
- Validate resource utilization
- Identify bottlenecks

**Test**: Provision 1,000 instances, all healthy and accessible within SLA

### Step 7.3: Chaos Engineering
- Deploy chaos-mesh or similar
- Simulate node failures
- Test pod evictions
- Validate auto-healing

**Test**: Kill random pods/nodes, verify automatic recovery

### Step 7.4: Final Validation
- Run full integration test suite
- Verify all APIs functional
- Test billing flow end-to-end
- Validate monitoring and alerting

**Test**: Complete user journey from signup to instance provisioning to billing

---

## Phase 8: Scale to 10,000 Instances (Week 8+)

### Step 8.1: Cluster Expansion
- Add worker nodes to reach target capacity
- Configure node labels/taints for workload isolation
- Implement node pools (if cloud)

**Test**: Verify all nodes join cluster, ready for workloads

### Step 8.2: Gradual Scaling
- Scale to 1,000 instances (Week 8)
- Scale to 5,000 instances (Week 9)
- Scale to 10,000 instances (Week 10)
- Monitor and optimize at each milestone

**Test**: At each milestone, verify cluster stability, response times within SLA

### Step 8.3: Performance Tuning
- Optimize etcd performance
- Tune Kubernetes API server
- Adjust controller manager settings
- Configure admission webhooks efficiently

**Test**: Measure API server latency, ensure <100ms for 95th percentile

### Step 8.4: Decommission Swarm
- Verify all instances migrated
- Backup Swarm configuration
- Shutdown Swarm cluster
- Celebrate!

**Test**: Verify zero instances on Swarm, all traffic on K3s

---

## Rollback Plan

At any phase, if critical issues arise:
1. Stop new migrations to K3s
2. Route traffic back to Swarm
3. Investigate and fix issues
4. Resume migration when stable

---

## Success Metrics

- All 10,000 instances running on K3s
- Instance provisioning time: <2 minutes
- API response time: <200ms (p95)
- Cluster availability: >99.9%
- Zero data loss during migration
- Cost reduction: 20-30% (better resource utilization)

---

## Key Considerations for 10,000 Instances

### Architecture Decisions

**Instance Isolation Strategy:**
- Use shared namespace with unique labels (not namespace-per-instance)
- Namespace-per-instance hits etcd limits around 1,000-2,000 namespaces
- Label-based approach: `app=odoo, instance-id=<uuid>, customer-id=<id>`

**Resource Allocation:**
- 50-100 worker nodes (200 instances per node)
- Each worker: 32-64GB RAM, 16+ cores
- Control plane: 3 nodes with 16GB RAM, 8 cores each
- etcd: Separate 3-node cluster (recommended for scale)

**Storage Strategy:**
- CephFS with subvolume per instance
- StorageClass with `reclaimPolicy: Retain`
- Quota enforcement via CephFS quotas (you already have this)
- Snapshot schedule for backups

**Networking:**
- Use NodePort or LoadBalancer per instance
- Or single Ingress with host-based routing: `<instance-id>.yourdomain.com`
- NetworkPolicy for instance isolation
- Consider service mesh (Istio/Linkerd) for advanced traffic management

### Performance Optimizations

**etcd Tuning:**
- Increase `--quota-backend-bytes` to 8GB
- Use fast SSD storage
- Monitor etcd metrics closely
- Consider separate etcd cluster

**API Server Tuning:**
- Increase `--max-requests-inflight` and `--max-mutating-requests-inflight`
- Use `--watch-cache-sizes` for frequently watched resources
- Enable API priority and fairness

**Controller Manager:**
- Tune `--concurrent-deployment-syncs` and similar flags
- Adjust `--kube-api-qps` and `--kube-api-burst`

**Kubelet:**
- Increase `--max-pods` per node (default 110, can go to 250)
- Tune `--image-pull-progress-deadline`
- Adjust `--eviction-hard` thresholds

### Code Changes Required

**Instance Service (app/services/instance_service.py):**
```python
# Replace Docker SDK
from kubernetes import client, config

# Instead of: docker_client.containers.run(...)
# Use: k8s_apps_v1.create_namespaced_deployment(...)
```

**Instance Worker (app/tasks/provisioning.py):**
```python
# Replace Docker operations with K8s operations
# create_instance() → create Deployment manifest
# start_instance() → scale Deployment to 1
# stop_instance() → scale Deployment to 0
# delete_instance() → delete Deployment + PVC
```

**Minimal changes needed:**
- Docker SDK → Kubernetes Python client (kubernetes package)
- Container creation → Deployment creation
- Volume mounts → PVC creation
- Network creation → Service creation
- Health checks remain similar (readinessProbe, livenessProbe)

### Migration Timeline Summary

- **Weeks 1-3**: Infrastructure + core services (no production impact)
- **Weeks 4-6**: Instance service refactoring + production readiness
- **Week 7**: Parallel run + validation (both Swarm and K3s)
- **Weeks 8-10**: Gradual scaling to 10,000 instances
- **Total**: 10-12 weeks for complete migration

### Cost Comparison

**Docker Swarm (Current):**
- Less efficient resource utilization
- Manual scaling
- Limited auto-healing
- Simpler but less features

**K3s (Future):**
- 20-30% better resource utilization (more instances per node)
- Auto-scaling (HPA + cluster autoscaler)
- Auto-healing and self-recovery
- Better monitoring and observability
- Larger ecosystem and community

**Estimated savings:** $2,000-5,000/month at 10,000 instances scale

---

## Appendix A: Traefik Configuration Migration

### Why Use K3s Built-in Traefik?

**Benefits:**
- Automatically maintained and updated with K3s
- Native Kubernetes integration via CRDs
- Less operational overhead
- Optimized and tested for K3s
- Your current config is simple enough to migrate easily

### Converting Your Docker Traefik Config to K3s

**Step 1: Configure Traefik via HelmChartConfig**

Create `/var/lib/rancher/k3s/server/manifests/traefik-config.yaml`:
```yaml
apiVersion: helm.cattle.io/v1
kind: HelmChartConfig
metadata:
  name: traefik
  namespace: kube-system
spec:
  valuesContent: |-
    dashboard:
      enabled: true
    logs:
      general:
        level: INFO
        format: json
      access:
        enabled: true
        format: json
    metrics:
      prometheus:
        enabled: true
        addEntryPointsLabels: true
        addServicesLabels: true
```

**Step 2: Convert Middlewares to Kubernetes CRDs**

Your existing middlewares from `infrastructure/traefik/traefik.yml` become:

```yaml
# Security Headers Middleware
apiVersion: traefik.containo.us/v1alpha1
kind: Middleware
metadata:
  name: security-headers
  namespace: default
spec:
  headers:
    frameDeny: true
    browserXssFilter: true
    contentTypeNosniff: true
---
# Rate Limiting Middleware
apiVersion: traefik.containo.us/v1alpha1
kind: Middleware
metadata:
  name: rate-limit
  namespace: default
spec:
  rateLimit:
    average: 50
    burst: 100
---
# CORS Middleware for APIs
apiVersion: traefik.containo.us/v1alpha1
kind: Middleware
metadata:
  name: api-cors
  namespace: default
spec:
  headers:
    accessControlAllowMethods:
      - GET
      - OPTIONS
      - PUT
      - POST
      - DELETE
      - PATCH
    accessControlAllowOriginList:
      - "*"
    accessControlAllowHeaders:
      - "*"
    accessControlMaxAge: 86400
---
# Basic Auth Middleware
apiVersion: traefik.containo.us/v1alpha1
kind: Middleware
metadata:
  name: basic-auth
  namespace: default
spec:
  basicAuth:
    secret: traefik-auth-secret
---
# Strip Prefix Middlewares
apiVersion: traefik.containo.us/v1alpha1
kind: Middleware
metadata:
  name: strip-user-prefix
  namespace: default
spec:
  stripPrefix:
    prefixes:
      - /user
---
apiVersion: traefik.containo.us/v1alpha1
kind: Middleware
metadata:
  name: strip-billing-prefix
  namespace: default
spec:
  stripPrefix:
    prefixes:
      - /billing
---
apiVersion: traefik.containo.us/v1alpha1
kind: Middleware
metadata:
  name: strip-instance-prefix
  namespace: default
spec:
  stripPrefix:
    prefixes:
      - /instance
```

**Step 3: Convert Docker Labels to IngressRoute**

Instead of Docker labels like:
```yaml
labels:
  - "traefik.http.routers.user-service.rule=Host(`api.${BASE_DOMAIN}`) && PathPrefix(`/user`)"
  - "traefik.http.routers.user-service.middlewares=user-strip"
```

You create IngressRoute resources:
```yaml
apiVersion: traefik.containo.us/v1alpha1
kind: IngressRoute
metadata:
  name: user-service
  namespace: default
spec:
  entryPoints:
    - web
  routes:
    - match: Host(`api.localhost`) && PathPrefix(`/user`)
      kind: Rule
      services:
        - name: user-service
          port: 8001
      middlewares:
        - name: strip-user-prefix
        - name: api-cors
        - name: security-headers
---
apiVersion: traefik.containo.us/v1alpha1
kind: IngressRoute
metadata:
  name: billing-service
  namespace: default
spec:
  entryPoints:
    - web
  routes:
    - match: Host(`api.localhost`) && PathPrefix(`/billing`)
      kind: Rule
      services:
        - name: billing-service
          port: 8004
      middlewares:
        - name: strip-billing-prefix
        - name: api-cors
---
apiVersion: traefik.containo.us/v1alpha1
kind: IngressRoute
metadata:
  name: instance-service
  namespace: default
spec:
  entryPoints:
    - web
  routes:
    - match: Host(`api.localhost`) && PathPrefix(`/instance`)
      kind: Rule
      services:
        - name: instance-service
          port: 8003
      middlewares:
        - name: strip-instance-prefix
        - name: api-cors
---
apiVersion: traefik.containo.us/v1alpha1
kind: IngressRoute
metadata:
  name: frontend-service
  namespace: default
spec:
  entryPoints:
    - web
  routes:
    - match: Host(`app.localhost`)
      kind: Rule
      services:
        - name: frontend-service
          port: 3000
```

**Step 4: Access Traefik Dashboard**

```bash
# Port-forward to access dashboard
kubectl port-forward -n kube-system $(kubectl get pods -n kube-system -l app.kubernetes.io/name=traefik -o name) 9000:9000

# Access at http://localhost:9000/dashboard/
```

### Migration Checklist

- [ ] Remove Swarm provider section from traefik.yml (lines 23-27)
- [ ] Convert all middlewares to Traefik CRDs
- [ ] Create IngressRoute for each microservice
- [ ] Test each route individually
- [ ] Verify middlewares applied correctly
- [ ] Enable TLS with cert-manager (production)
- [ ] Update DNS records to point to K3s cluster
