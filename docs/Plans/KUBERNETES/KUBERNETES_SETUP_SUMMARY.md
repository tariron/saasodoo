# Kubernetes Infrastructure Setup - What Was Requested

## Original Request

The user requested to start implementing Kubernetes migration for the SaaSOdoo project in WSL using Kubernetes in Docker Desktop. The key requirements were:

1. **Use existing Kubernetes infrastructure** - Kubernetes is already running in Docker Desktop, so skip:
   - RKE2 installation
   - Rook-Ceph setup (CephFS already mounted at `/mnt/cephfs`)
   - MetalLB (Docker Desktop has built-in LoadBalancer)

2. **Create a secondary local registry** - To avoid affecting the existing registry at `registry.62.171.153.219.nip.io`
   - Local registry at `localhost:5001`
   - Isolated for Kubernetes testing

3. **Follow the proper directory structure** - As specified in the migration plan, NOT basic Kubernetes manifests

4. **Create production-ready manifests** with:
   - Proper RBAC (ServiceAccounts, Roles, RoleBindings)
   - Separate numbered files per service (01-deployment.yaml, 02-service.yaml, 03-ingressroute.yaml)
   - ConfigMaps and Secrets (not hardcoded values)
   - PersistentVolumes using existing CephFS
   - Ingress routes (not basic combined Ingress)

5. **DO NOT create Kubernetes Python client** - Skip the code changes to replace Docker SDK (this was explicitly stated)

## What Was Initially Done Wrong

The assistant initially:
- Created basic Kubernetes manifests (combined Deployment+Service in single files)
- Created a basic combined `ingress.yaml` file
- Mixed Docker Desktop basic patterns with the RKE2 migration plan
- Combined resources in single files instead of following the numbered structure

## What Was Corrected

After clarification, the assistant:

1. **Split all services into numbered files**:
   ```
   services/user-service/
   ├── 01-deployment.yaml
   ├── 02-service.yaml
   └── 03-ingressroute.yaml
   ```

2. **Created ALL missing services** that were in docker-compose but not in initial manifests:
   - notification-service
   - database-service
   - database-worker
   - mailhog

3. **Organized infrastructure properly**:
   ```
   infrastructure/
   ├── 00-namespace.yaml
   ├── 01-rbac.yaml
   ├── databases/
   │   ├── postgres.yaml
   │   ├── redis.yaml
   │   ├── rabbitmq.yaml
   │   └── killbill.yaml
   ├── secrets/
   │   ├── 00-secrets.yaml
   │   └── 01-configmap.yaml
   ├── storage/
   │   ├── 00-storageclass.yaml
   │   └── 01-persistent-volumes.yaml
   └── networking/
       └── ingress.yaml (kept for reference, services use individual routes)
   ```

4. **Updated deployment scripts** to work with numbered file structure

## Final Deliverables

### Infrastructure Components
✅ Namespace and RBAC with proper ServiceAccounts
✅ ConfigMaps for all non-sensitive configuration
✅ Secrets template (with warnings not to commit)
✅ StorageClass and PersistentVolumes for CephFS hostPath
✅ Database StatefulSets (PostgreSQL, Redis, RabbitMQ, KillBill)

### Application Services (All with Numbered Files)
✅ user-service
✅ billing-service
✅ instance-service (with 00-pvcs.yaml for shared storage)
✅ instance-worker (Deployment only, no Service)
✅ notification-service
✅ database-service
✅ database-worker (Deployment only)
✅ frontend-service
✅ mailhog

### Scripts
✅ build-and-push.sh (builds and pushes to localhost:5001)
✅ deploy.sh (deploys in correct order, handles numbered files)
✅ teardown.sh (cleans up all resources)

### Registry
✅ docker-compose.local-registry.yml (secondary registry on port 5001)

## Key Architectural Decisions

1. **hostPath volumes** instead of Rook-Ceph CSI driver (since CephFS is already mounted)
2. **NGINX Ingress** (Docker Desktop standard) instead of Traefik IngressRoutes
3. **Individual Ingress per service** instead of one centralized Ingress file
4. **ServiceAccounts with RBAC**:
   - `instance-service-sa` - Can manage Pods (for Odoo instances)
   - `database-service-sa` - Can manage database pools
   - `saasodoo-service-sa` - General services

5. **Numbered file structure** for easy maintenance:
   - `00-*` - Prerequisites (PVCs, etc.)
   - `01-*` - Deployments/StatefulSets
   - `02-*` - Services
   - `03-*` - Ingress routes

## What Was Explicitly Excluded

As per user request:
- ❌ Kubernetes Python client implementation (code changes to instance-service)
- ❌ RKE2 cluster installation scripts
- ❌ Rook-Ceph operator installation
- ❌ MetalLB installation
- ❌ Actual conversion of Docker SDK calls to Kubernetes API calls

## Usage Instructions

```bash
# 1. Start secondary local registry
cd infrastructure/orchestration/kubernetes/registry
docker compose -f docker-compose.local-registry.yml up -d

# 2. Build and push all images
cd ../
./scripts/build-and-push.sh

# 3. Deploy to Kubernetes
./scripts/deploy.sh

# 4. Add hosts entries
sudo bash -c 'cat >> /etc/hosts << EOF
127.0.0.1 api.saasodoo.local
127.0.0.1 app.saasodoo.local
127.0.0.1 billing.saasodoo.local
127.0.0.1 rabbitmq.saasodoo.local
127.0.0.1 mail.saasodoo.local
127.0.0.1 notification.saasodoo.local
EOF'

# 5. Verify deployment
kubectl get pods -n saasodoo
kubectl get ingress -n saasodoo
```

## Important Notes

1. **Secrets are templates** - The `00-secrets.yaml` file contains placeholder values and should NOT be committed with real credentials. Use `kubectl create secret` or a secrets management tool in production.

2. **Instance-service still uses Docker SDK** - The manifests are ready, but the code in `instance-service` still uses `docker` library. It needs to be updated to use `kubernetes` Python client to actually manage Pods instead of containers.

3. **CephFS quota management** - The current setup uses hostPath with the existing CephFS mount. Quota management via `setfattr` should still work but may need adjustment for Kubernetes.

4. **Resource limits** - All deployments have resource requests/limits set. Adjust based on your WSL resource allocation.

5. **NGINX Ingress Controller required** - Must be installed separately:
   ```bash
   kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.8.2/deploy/static/provider/cloud/deploy.yaml
   ```

## Migration Path from Docker Swarm

The manifests preserve all functionality from `docker-compose.ceph.yml`:
- ✅ Same environment variables
- ✅ Same service structure
- ✅ Same volume mounts
- ✅ Same networking (service discovery)
- ✅ Same health checks
- ✅ Same resource limits

The main difference is orchestration mechanism:
- **Swarm**: Docker Compose format, Traefik labels, Docker SDK
- **Kubernetes**: YAML manifests, Ingress resources, Kubernetes API (to be implemented)
