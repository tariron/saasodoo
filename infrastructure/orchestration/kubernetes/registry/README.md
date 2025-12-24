# Local Kubernetes Registry

This directory contains a secondary Docker registry for Kubernetes development and testing.

## Purpose

- **Isolation**: Separate from production registry (`registry.62.171.153.219.nip.io`)
- **K8s Testing**: Used exclusively for Kubernetes manifest testing
- **Local Development**: Push/pull images locally without affecting production

## Usage

### Start the Registry

```bash
docker compose -f infrastructure/orchestration/kubernetes/registry/docker-compose.local-registry.yml up -d
```

### Stop the Registry

```bash
docker compose -f infrastructure/orchestration/kubernetes/registry/docker-compose.local-registry.yml down
```

### Check Registry Status

```bash
docker compose -f infrastructure/orchestration/kubernetes/registry/docker-compose.local-registry.yml ps
```

### Access Registry

- **URL**: `localhost:5001`
- **Health Check**: `http://localhost:5001/v2/`
- **List Images**: `curl http://localhost:5001/v2/_catalog`

## Tagging and Pushing Images

### Tag an existing image

```bash
docker tag compose-user-service:latest localhost:5001/user-service:latest
```

### Push to local registry

```bash
docker push localhost:5001/user-service:latest
```

## Configure Kubernetes to Use Local Registry

For Kubernetes in Docker Desktop (WSL), add to `/etc/hosts`:

```
127.0.0.1 local-k8s-registry
```

Then use `local-k8s-registry:5001` in your Kubernetes manifests.

## Registry Storage

Images are stored in `./registry-data/` (gitignored)
