# Migration Guide: Bitnami Odoo to Official Odoo Image

## Overview
This document outlines the code changes required to migrate from Bitnami Odoo Docker image to the official Odoo Docker image.

## Key Differences Between Images

### Bitnami Odoo
- **Image:** `bitnamilegacy/odoo:17`
- **Environment Variables:**
  - `ODOO_DATABASE_HOST`, `ODOO_DATABASE_PORT_NUMBER`, `ODOO_DATABASE_NAME`, `ODOO_DATABASE_USER`, `ODOO_DATABASE_PASSWORD`
  - `ODOO_EMAIL`, `ODOO_PASSWORD` (creates admin user automatically)
  - `ODOO_LOAD_DEMO_DATA`
- **Volume Mount:** `/bitnami/odoo`
- **Behavior:** Automatically creates database and admin user on first run

### Official Odoo
- **Image:** `odoo:17`
- **Environment Variables:**
  - `HOST`, `PORT`, `USER`, `PASSWORD` (database connection only)
  - No admin user creation via env vars
- **Volume Mount:** `/var/lib/odoo`
- **Behavior:** Requires manual database initialization with `-i base` command

## Code Changes

### File: `services/instance-service/app/tasks/provisioning.py`

#### 1. Docker Image Reference (Lines 271, 282)

**Before (Bitnami):**
```python
logger.info("Pulling Bitnami Odoo image", version=odoo_version)
client.images.pull(f'bitnamilegacy/odoo:{odoo_version}')

container = client.containers.run(
    f'bitnamilegacy/odoo:{odoo_version}',
    ...
)
```

**After (Official Odoo):**
```python
logger.info("Pulling official Odoo image", version=odoo_version)
client.images.pull(f'odoo:{odoo_version}')

container = client.containers.run(
    f'odoo:{odoo_version}',
    ...
)
```

#### 2. Environment Variables (Lines 252-257)

**Before (Bitnami):**
```python
environment = {
    'ODOO_DATABASE_HOST': db_info['db_host'],
    'ODOO_DATABASE_PORT_NUMBER': db_info['db_port'],
    'ODOO_DATABASE_NAME': db_info['db_name'],
    'ODOO_DATABASE_USER': db_info['db_user'],
    'ODOO_DATABASE_PASSWORD': db_info['db_password'],
    'ODOO_EMAIL': instance['admin_email'],
    'ODOO_PASSWORD': instance['admin_password'],
    'ODOO_LOAD_DEMO_DATA': 'yes' if instance['demo_data'] else 'no',
}
```

**After (Official Odoo):**
```python
environment = {
    'HOST': db_info['db_host'],
    'PORT': db_info['db_port'],
    'USER': db_info['db_user'],
    'PASSWORD': db_info['db_password'],
}
```

#### 3. Database Initialization Command (Lines 278-280)

**Added for Official Odoo:**
```python
# Initialize database with base module if demo_data is requested, otherwise skip demo data
odoo_command = ['-d', db_info['db_name'], '-i', 'base']
if not instance['demo_data']:
    odoo_command.extend(['--without-demo', 'all'])
```

**Added to container run:**
```python
container = client.containers.run(
    f'odoo:{odoo_version}',
    name=container_name,
    command=odoo_command,  # ← NEW: Add this line
    environment=environment,
    ...
)
```

#### 4. Volume Mount Path (Line 286)

**Before (Bitnami):**
```python
volumes={
    volume_name: {'bind': '/bitnami/odoo', 'mode': 'rw'}
}
```

**After (Official Odoo):**
```python
volumes={
    volume_name: {'bind': '/var/lib/odoo', 'mode': 'rw'}
}
```

#### 5. Admin Password Reference (Line 332)

**Before:**
```python
return {
    ...
    'admin_password': environment['ODOO_PASSWORD']
}
```

**After:**
```python
return {
    ...
    'admin_password': instance['admin_password']
}
```

## Summary of Changes

| Aspect | Bitnami | Official Odoo |
|--------|---------|---------------|
| Docker Image | `bitnamilegacy/odoo:17` | `odoo:17` |
| Database Host Env | `ODOO_DATABASE_HOST` | `HOST` |
| Database Port Env | `ODOO_DATABASE_PORT_NUMBER` | `PORT` |
| Database User Env | `ODOO_DATABASE_USER` | `USER` |
| Database Password Env | `ODOO_DATABASE_PASSWORD` | `PASSWORD` |
| Admin User Creation | Via `ODOO_EMAIL` & `ODOO_PASSWORD` | Manual (defaults to `admin/admin`) |
| Demo Data Control | `ODOO_LOAD_DEMO_DATA` | `--without-demo all` flag |
| Volume Mount | `/bitnami/odoo` | `/var/lib/odoo` |
| Database Init | Automatic | Requires `-i base` command |

## Important Behavioral Differences

### Admin User Creation

**Bitnami:**
- Creates admin user with custom email and password from environment variables
- User can login immediately with credentials from instance creation request

**Official Odoo:**
- Running with `-i base` creates default admin user: `admin/admin`
- Customer must login with `admin/admin` and change password manually
- **Security concern:** Default credentials are known to everyone

### Database Initialization

**Bitnami:**
- Automatically initializes database on first container start
- No special commands needed

**Official Odoo:**
- Requires explicit `-i base` command to initialize database
- Command creates all Odoo tables and base modules
- Container continues running after initialization (unlike `--stop-after-init`)

### Password Storage Issue

**Current Problem (Both Images):**
- Instance table stores `admin_password` in plaintext
- With Bitnami: This is the actual user password
- With Official Odoo: This field is stored but actual password is `admin/admin`

**Recommended Solution:**
1. Generate temporary password during provisioning
2. Show password to user ONCE after instance creation
3. Force password reset on first login (requires custom implementation)
4. Never store final password in your database

## Testing Checklist

After migration, verify:
- [ ] Instance provisioning completes successfully
- [ ] Database is created and initialized with base module
- [ ] Odoo container starts and stays running
- [ ] Can access Odoo at `http://{database_name}.saasodoo.local/`
- [ ] Can login with `admin/admin` credentials
- [ ] Demo data setting is respected (loaded or not loaded)
- [ ] Container has correct Traefik labels
- [ ] Container is connected to `saasodoo-network`
- [ ] Instance shows as `RUNNING` status in database

## Rollback Instructions

To rollback to Bitnami, reverse all changes in `provisioning.py`:

1. Change image back to `bitnamilegacy/odoo:17`
2. Restore Bitnami environment variable names
3. Remove `command=odoo_command` line
4. Change volume mount back to `/bitnami/odoo`
5. Change admin password reference back to `environment['ODOO_PASSWORD']`
6. Rebuild and restart instance-service and instance-worker

## Known Issues with Official Odoo

1. **Default admin credentials:** All instances start with `admin/admin` - security risk
2. **No custom admin user:** Cannot set custom email/password via environment variables
3. **Command persistence:** The `-i base` command runs every container start (not ideal)
4. **Manual password change required:** Customers must change default password themselves

## Recommended Next Steps

1. **Implement password reset flow:**
   - Email customer with temporary `admin/admin` credentials
   - Force password change on first login (requires Odoo customization or module)

2. **Consider two-step initialization:**
   - Step 1: Run container with `-i base --stop-after-init` to initialize DB
   - Step 2: Start new container without `-i` flag for normal operation
   - This prevents re-initialization on every restart

3. **Use Odoo XML-RPC API:**
   - Programmatically create admin user with custom credentials after DB init
   - Requires additional code but gives full control

4. **Evaluate if migration is worth it:**
   - Bitnami works well for your use case
   - Paywall concern is 10 months away
   - Can migrate later when needed

## Decision Recommendation

**Stay with Bitnami for now** because:
- ✅ It works seamlessly with your current architecture
- ✅ Provides better UX (custom admin credentials)
- ✅ Less complex setup
- ✅ You have time before paywall (Sept 2025)
- ✅ Migration path is clear when needed

**Fix the password storage issue instead:**
- Hash passwords before storing in database
- Implement password reset functionality
- This security improvement applies regardless of image choice
