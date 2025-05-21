# Migration Guide
## Odoo SaaS Platform

**Version:** 1.0  
**Date:** May 20, 2025  

This guide provides detailed instructions for migrating your Odoo SaaS platform between servers. The process is designed to be straightforward with minimal downtime.

## Pre-Migration Checklist

- [ ] Source server is running correctly
- [ ] Destination server meets the minimum requirements
- [ ] SSH access to both servers
- [ ] DNS access to update records
- [ ] Enough storage on destination server for all tenant data
- [ ] Maintenance window communicated to users

## 1. Preparation

### 1.1 Set Up Environment Variables

On the source server:

```bash
# Set environment variables
export SOURCE_SERVER="source-server-ip"
export DEST_SERVER="destination-server-ip"
export PLATFORM_DIR="/opt/odoo-saas-kit"
export MIGRATION_DIR="$PLATFORM_DIR/migration"
export MIGRATION_DATE=$(date +%Y%m%d)

# Create migration directory
mkdir -p $MIGRATION_DIR
```

### 1.2 Install Required Tools on Destination Server

```bash
# SSH into destination server and install requirements
ssh ubuntu@$DEST_SERVER << 'EOF'
  # Install MicroK8s
  sudo snap install microk8s --classic
  sudo usermod -a -G microk8s ubuntu
  sudo chown -R ubuntu ~/.kube
  
  # Wait for MicroK8s to start
  microk8s status --wait-ready
  
  # Enable required addons
  microk8s enable dns ingress metrics-server storage registry
  
  # Install required packages
  sudo apt-get update
  sudo apt-get install -y python3-pip jq rsync
  pip install flask flask-cors pyyaml kubernetes supabase gunicorn
EOF
```

## 2. Export Configurations

### 2.1 Export Kubernetes Resources

```bash
# Create script to export all resources
cat > $MIGRATION_DIR/export-resources.sh << 'EOL'
#!/bin/bash

# Export all namespaces with tenant label
kubectl get ns -l managed-by=odoo-saas -o json > namespaces.json

# Loop through each namespace and export resources
for ns in $(kubectl get ns -l managed-by=odoo-saas -o jsonpath='{.items[*].metadata.name}'); do
  mkdir -p "$ns"
  
  # Export deployments
  kubectl get deployments -n $ns -o json > "$ns/deployments.json"
  
  # Export services
  kubectl get svc -n $ns -o json > "$ns/services.json"
  
  # Export persistent volume claims
  kubectl get pvc -n $ns -o json > "$ns/pvcs.json"
  
  # Export configmaps
  kubectl get configmaps -n $ns -o json > "$ns/configmaps.json"
  
  # Export secrets (note: these will need to be manually handled for security)
  kubectl get secrets -n $ns -o json | jq 'del(.items[].data)' > "$ns/secrets-structure.json"
  
  # Export ingress
  kubectl get ingress -n $ns -o json > "$ns/ingress.json"
  
  # Export network policies
  kubectl get netpol -n $ns -o json > "$ns/netpol.json"
done

# Export system namespace resources
kubectl get deployments -n saas-system -o json > "saas-system-deployments.json"
kubectl get svc -n saas-system -o json > "saas-system-services.json"
kubectl get pvc -n saas-system -o json > "saas-system-pvcs.json"
kubectl get cronjobs -n saas-system -o json > "saas-system-cronjobs.json"

# Export traefik config
kubectl get -n traefik deployments,services,configmaps -o json > "traefik-resources.json"

EOL

# Make the script executable and run it
chmod +x $MIGRATION_DIR/export-resources.sh
cd $MIGRATION_DIR
./export-resources.sh
```

### 2.2 Export Platform Code and Data

```bash
# Create tarball of application code
cd $PLATFORM_DIR
tar -czf $MIGRATION_DIR/platform-code.tar.gz --exclude="migration" --exclude=".git" .

# Export tenant database list
kubectl get ns -l managed-by=odoo-saas -o jsonpath='{.items[*].metadata.name}' | tr ' ' '\n' > $MIGRATION_DIR/tenant-list.txt
```

## 3. Backup Tenant Data

### 3.1 Create Comprehensive Backup Script

```bash
# Create backup script
cat > $MIGRATION_DIR/backup-all-tenants.sh << 'EOL'
#!/bin/bash

BACKUP_DIR="tenant-backups"
mkdir -p $BACKUP_DIR

# Get list of tenant namespaces
TENANTS=$(kubectl get ns -l managed-by=odoo-saas -o jsonpath='{.items[*].metadata.name}')

for TENANT in $TENANTS; do
  echo "Backing up tenant $TENANT..."
  TENANT_ID=${TENANT#tenant-}
  TENANT_BACKUP_DIR="$BACKUP_DIR/$TENANT_ID"
  mkdir -p "$TENANT_BACKUP_DIR"
  
  # Get PostgreSQL pod
  PG_POD=$(kubectl get pods -n $TENANT -l app=postgresql -o jsonpath='{.items[0].metadata.name}')
  
  # Backup PostgreSQL database
  if [ ! -z "$PG_POD" ]; then
    echo "  Backing up database..."
    kubectl exec -n $TENANT $PG_POD -- pg_dump -U postgres -d postgres | gzip > "$TENANT_BACKUP_DIR/database.sql.gz"
  else
    echo "  WARNING: No PostgreSQL pod found for $TENANT"
  fi
  
  # Get Odoo pod
  ODOO_POD=$(kubectl get pods -n $TENANT -l app=odoo -o jsonpath='{.items[0].metadata.name}')
  
  # Backup Odoo filestore
  if [ ! -z "$ODOO_POD" ]; then
    echo "  Backing up Odoo filestore..."
    kubectl cp $TENANT/$ODOO_POD:/opt/bitnami/odoo/data/filestore/ "$TENANT_BACKUP_DIR/filestore/"
  else
    echo "  WARNING: No Odoo pod found for $TENANT"
  fi
  
  # Export tenant-specific secrets (encrypted)
  echo "  Exporting secrets..."
  kubectl get secrets -n $TENANT -o json > "$TENANT_BACKUP_DIR/secrets.json"
  
  echo "  Backup complete for $TENANT"
done

# Backup central database if exists
SYSTEM_PG_POD=$(kubectl get pods -n saas-system -l app=postgresql -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ ! -z "$SYSTEM_PG_POD" ]; then
  echo "Backing up system database..."
  mkdir -p "$BACKUP_DIR/system"
  kubectl exec -n saas-system $SYSTEM_PG_POD -- pg_dump -U postgres -d postgres | gzip > "$BACKUP_DIR/system/database.sql.gz"
fi

# Backup existing platform backups if available
BACKUP_PVC=$(kubectl get pvc -n saas-system tenant-backups-pvc -o jsonpath='{.metadata.name}' 2>/dev/null)
if [ ! -z "$BACKUP_PVC" ]; then
  echo "Copying existing backup data..."
  TEMP_POD="backup-access-$(date +%s)"
  kubectl run $TEMP_POD -n saas-system --image=alpine --restart=Never -- sleep 3600
  kubectl wait --for=condition=Ready pod -n saas-system $TEMP_POD
  kubectl cp $TEMP_POD:/backups/ "$BACKUP_DIR/existing-backups/"
  kubectl delete pod -n saas-system $TEMP_POD
fi

echo "All tenant backups completed."
EOL

# Make the script executable and run it
chmod +x $MIGRATION_DIR/backup-all-tenants.sh
cd $MIGRATION_DIR
./backup-all-tenants.sh
```

### 3.2 Create Archive of All Exported Data

```bash
# Create a single archive with all data
cd $MIGRATION_DIR
tar -czf odoo-saas-migration-$MIGRATION_DATE.tar.gz tenant-backups *.json */
```

## 4. Transfer Data to New Server

```bash
# Transfer the archive to the new server
scp $MIGRATION_DIR/odoo-saas-migration-$MIGRATION_DATE.tar.gz ubuntu@$DEST_SERVER:/tmp/

# Transfer platform code
scp $MIGRATION_DIR/platform-code.tar.gz ubuntu@$DEST_SERVER:/tmp/
```

## 5. Set Up New Server

```bash
# SSH into new server and set up the platform
ssh ubuntu@$DEST_SERVER << 'EOF'
  # Create platform directory
  sudo mkdir -p /opt/odoo-saas-kit
  sudo chown ubuntu:ubuntu /opt/odoo-saas-kit
  
  # Extract platform code
  tar -xzf /tmp/platform-code.tar.gz -C /opt/odoo-saas-kit
  
  # Extract migration data
  mkdir -p /opt/odoo-saas-kit/migration
  tar -xzf /tmp/odoo-saas-migration-*.tar.gz -C /opt/odoo-saas-kit/migration
  
  # Set up kubectl config
  mkdir -p ~/.kube
  microk8s config > ~/.kube/config
  
  # Install Traefik
  cd /opt/odoo-saas-kit/kubernetes/traefik
  bash install.sh
  cd ../..
  
  # Create backup storage
  kubectl apply -f kubernetes/backup/storage.yaml
EOF
```

## 6. Restore Platform Components

### 6.1 Restore System Components

```bash
# Create restoration script for system components
cat > $MIGRATION_DIR/restore-system.sh << 'EOL'
#!/bin/bash

# Restore saas-system namespace
kubectl create namespace saas-system

# Apply system deployments
kubectl apply -f saas-system-deployments.json
kubectl apply -f saas-system-services.json
kubectl apply -f saas-system-pvcs.json
kubectl apply -f saas-system-cronjobs.json

# Restore system database if exists
SYSTEM_BACKUP="tenant-backups/system/database.sql.gz"
if [ -f "$SYSTEM_BACKUP" ]; then
  echo "Waiting for system database pod to be ready..."
  kubectl wait --for=condition=Ready pod -l app=postgresql -n saas-system --timeout=300s
  
  # Get PostgreSQL pod
  PG_POD=$(kubectl get pods -n saas-system -l app=postgresql -o jsonpath='{.items[0].metadata.name}')
  
  # Restore database
  cat $SYSTEM_BACKUP | gunzip | kubectl exec -i -n saas-system $PG_POD -- psql -U postgres
fi

# Restore existing backups if available
BACKUP_DIR="tenant-backups/existing-backups"
if [ -d "$BACKUP_DIR" ] && [ "$(ls -A $BACKUP_DIR)" ]; then
  echo "Restoring existing backups..."
  
  # Create temporary pod to access backup PVC
  TEMP_POD="backup-restore-$(date +%s)"
  kubectl run $TEMP_POD -n saas-system --image=alpine --restart=Never -- sleep 3600
  kubectl wait --for=condition=Ready pod -n saas-system $TEMP_POD
  
  # Copy backups
  kubectl cp $BACKUP_DIR/ saas-system/$TEMP_POD:/backups/
  kubectl delete pod -n saas-system $TEMP_POD
fi
EOL

# Make the system restore script executable
chmod +x $MIGRATION_DIR/restore-system.sh

# Create tenant restoration script
cat > $MIGRATION_DIR/restore-tenants.sh << 'EOL'
#!/bin/bash

BACKUP_DIR="tenant-backups"

# For each tenant directory in backup
for TENANT_DIR in $BACKUP_DIR/*; do
  if [ -d "$TENANT_DIR" ] && [ "$(basename $TENANT_DIR)" != "system" ] && [ "$(basename $TENANT_DIR)" != "existing-backups" ]; then
    TENANT_ID=$(basename $TENANT_DIR)
    NAMESPACE="tenant-$TENANT_ID"
    echo "Restoring tenant $TENANT_ID to namespace $NAMESPACE..."
    
    # Create namespace
    kubectl create namespace $NAMESPACE
    kubectl label namespace $NAMESPACE managed-by=odoo-saas tenant-id=$TENANT_ID
    
    # Apply tenant-specific resources
    if [ -f "$NAMESPACE/deployments.json" ]; then
      kubectl apply -f "$NAMESPACE/deployments.json"
    fi
    
    if [ -f "$NAMESPACE/services.json" ]; then
      kubectl apply -f "$NAMESPACE/services.json"
    fi
    
    if [ -f "$NAMESPACE/pvcs.json" ]; then
      kubectl apply -f "$NAMESPACE/pvcs.json"
    fi
    
    if [ -f "$NAMESPACE/ingress.json" ]; then
      kubectl apply -f "$NAMESPACE/ingress.json"
    fi
    
    if [ -f "$NAMESPACE/netpol.json" ]; then
      kubectl apply -f "$NAMESPACE/netpol.json"
    fi
    
    # Wait for pods to be created
    echo "  Waiting for PostgreSQL pod..."
    kubectl wait --for=condition=Ready pod -l app=postgresql -n $NAMESPACE --timeout=300s
    
    # Restore PostgreSQL database if backup exists
    if [ -f "$TENANT_DIR/database.sql.gz" ]; then
      echo "  Restoring database..."
      
      # Get PostgreSQL pod
      PG_POD=$(kubectl get pods -n $NAMESPACE -l app=postgresql -o jsonpath='{.items[0].metadata.name}')
      
      # Restore database
      cat "$TENANT_DIR/database.sql.gz" | gunzip | kubectl exec -i -n $NAMESPACE $PG_POD -- psql -U postgres
    fi
    
    # Scale up Odoo if it's set to 0 replicas
    ODOO_REPLICAS=$(kubectl get deployment -n $NAMESPACE odoo -o jsonpath='{.spec.replicas}')
    if [ "$ODOO_REPLICAS" = "0" ]; then
      kubectl scale deployment -n $NAMESPACE odoo --replicas=1
    fi
    
    # Wait for Odoo pod
    echo "  Waiting for Odoo pod..."
    kubectl wait --for=condition=Ready pod -l app=odoo -n $NAMESPACE --timeout=300s
    
    # Restore Odoo filestore if exists
    if [ -d "$TENANT_DIR/filestore" ]; then
      echo "  Restoring filestore..."
      
      # Get Odoo pod
      ODOO_POD=$(kubectl get pods -n $NAMESPACE -l app=odoo -o jsonpath='{.items[0].metadata.name}')
      
      # Copy filestore
      kubectl cp "$TENANT_DIR/filestore/" $NAMESPACE/$ODOO_POD:/opt/bitnami/odoo/data/filestore/
      
      # Restart Odoo pod for changes to take effect
      kubectl delete pod -n $NAMESPACE $ODOO_POD
    fi
    
    echo "  Tenant $TENANT_ID restored successfully"
  fi
done

echo "All tenants restored successfully."
EOL

# Make the tenant restore script executable
chmod +x $MIGRATION_DIR/restore-tenants.sh

# Copy and run the restore scripts on the destination server
scp $MIGRATION_DIR/restore-system.sh $MIGRATION_DIR/restore-tenants.sh ubuntu@$DEST_SERVER:/opt/odoo-saas-kit/migration/

ssh ubuntu@$DEST_SERVER << 'EOF'
  cd /opt/odoo-saas-kit/migration
  ./restore-system.sh
  ./restore-tenants.sh
  
  # Start the backend service
  cd /opt/odoo-saas-kit/backend
  nohup gunicorn -b 0.0.0.0:5000 app:app > /opt/odoo-saas-kit/app.log 2>&1 &
EOF
```

## 7. Update DNS Records

Update your DNS records to point to the new server:

1. Log in to your DNS provider's control panel
2. Update the A record for your domain to point to the new server's IP address
3. If using wildcard DNS (recommended), update the wildcard record as well:
   ```
   *.yourdomain.com -> New-Server-IP
   ```
4. Wait for DNS propagation (can take up to 24 hours)

## 8. Verification Checks

### 8.1 Check All Tenant Namespaces

```bash
ssh ubuntu@$DEST_SERVER << 'EOF'
  # Check all namespaces
  kubectl get ns -l managed-by=odoo-saas
  
  # Check all pods across tenant namespaces
  for ns in $(kubectl get ns -l managed-by=odoo-saas -o jsonpath='{.items[*].metadata.name}'); do
    echo "Namespace: $ns"
    kubectl get pods -n $ns
    echo "---"
  done
  
  # Check ingress
  kubectl get ingress --all-namespaces
  
  # Check persistent volumes
  kubectl get pv
EOF
```

### 8.2 Test Tenant Access

1. Access the admin dashboard at `yourdomain.com`
2. Log in with admin credentials
3. Verify all tenants are listed and in "Running" state
4. Access several tenant instances through their subdomains to verify functionality
5. Create a test tenant to verify provisioning still works
6. Create a test backup and verify it's stored correctly

## 9. Post-Migration Tasks

### 9.1 Check and Clean Up Source Server

Once you've verified everything is working correctly on the new server:

```bash
# Check which tenants should be cleaned up (optional)
kubectl get ns -l managed-by=odoo-saas

# Back up the migration directory for safekeeping
cp -r $MIGRATION_DIR /backup/odoo-saas-migration-$MIGRATION_DATE

# If you want to shut down the source server completely (optional)
# First stop all services
microk8s stop
```

### 9.2 Documentation Update

Update your internal documentation to reflect:
1. The new server IP and details
2. The date of migration
3. Any issues encountered and their resolutions
4. Updated access information

## Troubleshooting

### Common Issues

#### Pods Not Starting After Migration

Check for events and logs:

```bash
kubectl describe pod -n <namespace> <pod-name>
kubectl logs -n <namespace> <pod-name>
```

Common solutions:
- PVC binding issues: Check if storage class exists and PVCs are bound
- Secret missing: Check if all required secrets were migrated
- Network policies: Temporarily disable network policies to test connectivity

#### Database Restore Fails

Check PostgreSQL logs:

```bash
kubectl logs -n <namespace> <postgresql-pod-name>
```

Common solutions:
- Database version mismatch: Ensure both servers use the same PostgreSQL version
- Not enough resources: Check CPU/memory limits and temporarily increase if needed

#### DNS Issues

- Verify DNS records have propagated using online tools
- Check Traefik logs for any routing issues:
  ```bash
  kubectl logs -n traefik <traefik-pod-name>
  ```

## Migration Script

For convenience, the entire migration process can be automated with this script:

```bash
#!/bin/bash
# Full migration script - save as migrate.sh
# Usage: ./migrate.sh <source-server-ip> <destination-server-ip>

SOURCE_SERVER=$1
DEST_SERVER=$2

if [ -z "$SOURCE_SERVER" ] || [ -z "$DEST_SERVER" ]; then
  echo "Usage: ./migrate.sh <source-server-ip> <destination-server-ip>"
  exit 1
fi

echo "Starting migration from $SOURCE_SERVER to $DEST_SERVER"
export SOURCE_SERVER DEST_SERVER

# 1. Preparation
ssh ubuntu@$SOURCE_SERVER << 'EOF'
  export PLATFORM_DIR="/opt/odoo-saas-kit"
  export MIGRATION_DIR="$PLATFORM_DIR/migration"
  export MIGRATION_DATE=$(date +%Y%m%d)
  mkdir -p $MIGRATION_DIR
EOF

# 2. Set up destination server
echo "Setting up destination server..."
ssh ubuntu@$DEST_SERVER << 'EOF'
  # Install MicroK8s
  sudo snap install microk8s --classic
  sudo usermod -a -G microk8s ubuntu
  sudo chown -R ubuntu ~/.kube
  
  # Wait for MicroK8s to start
  microk8s status --wait-ready
  
  # Enable required addons
  microk8s enable dns ingress metrics-server storage registry
  
  # Install required packages
  sudo apt-get update
  sudo apt-get install -y python3-pip jq rsync
  pip install flask flask-cors pyyaml kubernetes supabase gunicorn
EOF

# 3. Export and backup on source server
echo "Backing up source server data..."
ssh ubuntu@$SOURCE_SERVER << 'EOF'
  export PLATFORM_DIR="/opt/odoo-saas-kit"
  export MIGRATION_DIR="$PLATFORM_DIR/migration"
  export MIGRATION_DATE=$(date +%Y%m%d)
  
  # Export resources script
  cat > $MIGRATION_DIR/export-resources.sh << 'EOL'
#!/bin/bash

# Export all namespaces with tenant label
kubectl get ns -l managed-by=odoo-saas -o json > namespaces.json

# Loop through each namespace and export resources
for ns in $(kubectl get ns -l managed-by=odoo-saas -o jsonpath='{.items[*].metadata.name}'); do
  mkdir -p "$ns"
  
  # Export all resources
  kubectl get deployments -n $ns -o json > "$ns/deployments.json"
  kubectl get svc -n $ns -o json > "$ns/services.json"
  kubectl get pvc -n $ns -o json > "$ns/pvcs.json"
  kubectl get configmaps -n $ns -o json > "$ns/configmaps.json"
  kubectl get secrets -n $ns -o json | jq 'del(.items[].data)' > "$ns/secrets-structure.json"
  kubectl get ingress -n $ns -o json > "$ns/ingress.json"
  kubectl get netpol -n $ns -o json > "$ns/netpol.json"
done

# Export system and traefik resources
kubectl get deployments -n saas-system -o json > "saas-system-deployments.json"
kubectl get svc -n saas-system -o json > "saas-system-services.json"
kubectl get pvc -n saas-system -o json > "saas-system-pvcs.json"
kubectl get cronjobs -n saas-system -o json > "saas-system-cronjobs.json"
kubectl get -n traefik deployments,services,configmaps -o json > "traefik-resources.json"
EOL

  # Backup script
  cat > $MIGRATION_DIR/backup-all-tenants.sh << 'EOL'
#!/bin/bash

BACKUP_DIR="tenant-backups"
mkdir -p $BACKUP_DIR

# Back up each tenant
for TENANT in $(kubectl get ns -l managed-by=odoo-saas -o jsonpath='{.items[*].metadata.name}'); do
  echo "Backing up tenant $TENANT..."
  TENANT_ID=${TENANT#tenant-}
  TENANT_BACKUP_DIR="$BACKUP_DIR/$TENANT_ID"
  mkdir -p "$TENANT_BACKUP_DIR"
  
  # Database backup
  PG_POD=$(kubectl get pods -n $TENANT -l app=postgresql -o jsonpath='{.items[0].metadata.name}')
  if [ ! -z "$PG_POD" ]; then
    kubectl exec -n $TENANT $PG_POD -- pg_dump -U postgres -d postgres | gzip > "$TENANT_BACKUP_DIR/database.sql.gz"
  fi
  
  # Filestore backup
  ODOO_POD=$(kubectl get pods -n $TENANT -l app=odoo -o jsonpath='{.items[0].metadata.name}')
  if [ ! -z "$ODOO_POD" ]; then
    kubectl cp $TENANT/$ODOO_POD:/opt/bitnami/odoo/data/filestore/ "$TENANT_BACKUP_DIR/filestore/"
  fi
  
  # Export secrets
  kubectl get secrets -n $TENANT -o json > "$TENANT_BACKUP_DIR/secrets.json"
done

# Backup system database
SYSTEM_PG_POD=$(kubectl get pods -n saas-system -l app=postgresql -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ ! -z "$SYSTEM_PG_POD" ]; then
  mkdir -p "$BACKUP_DIR/system"
  kubectl exec -n saas-system $SYSTEM_PG_POD -- pg_dump -U postgres -d postgres | gzip > "$BACKUP_DIR/system/database.sql.gz"
fi
EOL

  # Make scripts executable
  chmod +x $MIGRATION_DIR/export-resources.sh $MIGRATION_DIR/backup-all-tenants.sh
  cd $MIGRATION_DIR
  
  # Run export and backup
  ./export-resources.sh
  ./backup-all-tenants.sh
  
  # Export code
  cd $PLATFORM_DIR
  tar -czf $MIGRATION_DIR/platform-code.tar.gz --exclude="migration" --exclude=".git" .
  
  # Create archive
  cd $MIGRATION_DIR
  tar -czf odoo-saas-migration-$MIGRATION_DATE.tar.gz tenant-backups *.json */
EOF

# 4. Transfer data
echo "Transferring data to destination server..."
ssh ubuntu@$SOURCE_SERVER "scp /opt/odoo-saas-kit/migration/odoo-saas-migration-*.tar.gz ubuntu@$DEST_SERVER:/tmp/"
ssh ubuntu@$SOURCE_SERVER "scp /opt/odoo-saas-kit/migration/platform-code.tar.gz ubuntu@$DEST_SERVER:/tmp/"

# 5. Setup on destination server
echo "Setting up platform on destination server..."
ssh ubuntu@$DEST_SERVER << 'EOF'
  # Create platform directory
  sudo mkdir -p /opt/odoo-saas-kit
  sudo chown ubuntu:ubuntu /opt/odoo-saas-kit
  
  # Extract code and data
  tar -xzf /tmp/platform-code.tar.gz -C /opt/odoo-saas-kit
  mkdir -p /opt/odoo-saas-kit/migration
  tar -xzf /tmp/odoo-saas-migration-*.tar.gz -C /opt/odoo-saas-kit/migration
  cd /opt/odoo-saas-kit
  
  # Setup kubectl
  mkdir -p ~/.kube
  microk8s config > ~/.kube/config
  
  # Install Traefik and backup storage
  cd /opt/odoo-saas-kit/kubernetes/traefik
  bash install.sh
  cd ../..
  kubectl apply -f kubernetes/backup/storage.yaml
  
  # Create restore scripts
  cat > migration/restore-system.sh << 'EOL'
#!/bin/bash

# Restore system
kubectl create namespace saas-system
kubectl apply -f saas-system-deployments.json
kubectl apply -f saas-system-services.json
kubectl apply -f saas-system-pvcs.json
kubectl apply -f saas-system-cronjobs.json

# Restore system database if exists
SYSTEM_BACKUP="tenant-backups/system/database.sql.gz"
if [ -f "$SYSTEM_BACKUP" ]; then
  kubectl wait --for=condition=Ready pod -l app=postgresql -n saas-system --timeout=300s
  PG_POD=$(kubectl get pods -n saas-system -l app=postgresql -o jsonpath='{.items[0].metadata.name}')
  cat $SYSTEM_BACKUP | gunzip | kubectl exec -i -n saas-system $PG_POD -- psql -U postgres
fi
EOL

  cat > migration/restore-tenants.sh << 'EOL'
#!/bin/bash

BACKUP_DIR="tenant-backups"

for TENANT_DIR in $BACKUP_DIR/*; do
  if [ -d "$TENANT_DIR" ] && [ "$(basename $TENANT_DIR)" != "system" ] && [ "$(basename $TENANT_DIR)" != "existing-backups" ]; then
    TENANT_ID=$(basename $TENANT_DIR)
    NAMESPACE="tenant-$TENANT_ID"
    echo "Restoring tenant $TENANT_ID..."
    
    # Create namespace
    kubectl create namespace $NAMESPACE
    kubectl label namespace $NAMESPACE managed-by=odoo-saas tenant-id=$TENANT_ID
    
    # Apply resources
    if [ -f "$NAMESPACE/deployments.json" ]; then kubectl apply -f "$NAMESPACE/deployments.json"; fi
    if [ -f "$NAMESPACE/services.json" ]; then kubectl apply -f "$NAMESPACE/services.json"; fi
    if [ -f "$NAMESPACE/pvcs.json" ]; then kubectl apply -f "$NAMESPACE/pvcs.json"; fi
    if [ -f "$NAMESPACE/ingress.json" ]; then kubectl apply -f "$NAMESPACE/ingress.json"; fi
    if [ -f "$NAMESPACE/netpol.json" ]; then kubectl apply -f "$NAMESPACE/netpol.json"; fi
    
    # Wait for database pod
    kubectl wait --for=condition=Ready pod -l app=postgresql -n $NAMESPACE --timeout=300s
    
    # Restore database
    if [ -f "$TENANT_DIR/database.sql.gz" ]; then
      PG_POD=$(kubectl get pods -n $NAMESPACE -l app=postgresql -o jsonpath='{.items[0].metadata.name}')
      cat "$TENANT_DIR/database.sql.gz" | gunzip | kubectl exec -i -n $NAMESPACE $PG_POD -- psql -U postgres
    fi
    
    # Ensure Odoo is running
    ODOO_REPLICAS=$(kubectl get deployment -n $NAMESPACE odoo -o jsonpath='{.spec.replicas}' 2>/dev/null)
    if [ "$ODOO_REPLICAS" = "0" ]; then
      kubectl scale deployment -n $NAMESPACE odoo --replicas=1
    fi
    
    # Wait for Odoo pod
    kubectl wait --for=condition=Ready pod -l app=odoo -n $NAMESPACE --timeout=300s
    
    # Restore filestore
    if [ -d "$TENANT_DIR/filestore" ]; then
      ODOO_POD=$(kubectl get pods -n $NAMESPACE -l app=odoo -o jsonpath='{.items[0].metadata.name}')
      kubectl cp "$TENANT_DIR/filestore/" $NAMESPACE/$ODOO_POD:/opt/bitnami/odoo/data/filestore/
      kubectl delete pod -n $NAMESPACE $ODOO_POD
    fi
  fi
done
EOL

  chmod +x migration/restore-system.sh migration/restore-tenants.sh
  cd migration
  ./restore-system.sh
  ./restore-tenants.sh
  
  # Start backend service
  cd /opt/odoo-saas-kit/backend
  nohup gunicorn -b 0.0.0.0:5000 app:app > /opt/odoo-saas-kit/app.log 2>&1 &
  
  echo "Migration completed. Please update DNS records to point to this server."
EOF

echo "Migration complete!"
echo "Don't forget to update your DNS records to point to the new server: $DEST_SERVER"
echo "Run verification checks to ensure everything is working correctly"
```

Save this script, make it executable (`chmod +x migrate.sh`) and run it with your server IPs:

```bash
./migrate.sh [source-server-ip] [destination-server-ip]
``` 