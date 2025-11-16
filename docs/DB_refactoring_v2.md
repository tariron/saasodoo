COMPLETE PLAN: POSTGRES1 vs POSTGRES2 SEPARATION (SIMPLIFIED)
OBJECTIVE
Separate database servers so that:

postgres1 (POSTGRES_HOST): Platform databases (auth, billing, instance, communication)
postgres2 (ODOO_POSTGRES_HOST): Odoo instance databases (odoo_customer_instance_*)
Instance metadata records stay in postgres1's instance database
Instance actual Odoo databases go to postgres2
SIMPLIFIED APPROACH
Keep existing variables for platform (postgres1):

POSTGRES_HOST → postgres1 (no change needed in most code)
POSTGRES_PORT → 5432
POSTGRES_DB → instance
DB_SERVICE_USER → instance_service
DB_SERVICE_PASSWORD → xxx
Add new variables for Odoo instances (postgres2):

ODOO_POSTGRES_HOST → postgres2 (new)
ODOO_POSTGRES_PORT → 5432 (new, but can default)
ODOO_POSTGRES_DEFAULT_DB → postgres (new)
ODOO_POSTGRES_ADMIN_USER → odoo_admin (new)
ODOO_POSTGRES_ADMIN_PASSWORD → xxx (new)
CONNECTION MAPPING
| Operation Type | Target Server | Host Variable | User Variable | |---------------|---------------|---------------|---------------| | Instance metadata CRUD (routes) | postgres1 | POSTGRES_HOST | DB_SERVICE_USER | | Instance metadata CRUD (tasks) | postgres1 | POSTGRES_HOST | DB_SERVICE_USER | | CREATE/DROP Odoo databases | postgres2 | ODOO_POSTGRES_HOST | ODOO_POSTGRES_ADMIN_USER | | Manage Odoo tables | postgres2 | ODOO_POSTGRES_HOST | ODOO_POSTGRES_ADMIN_USER |

STEP-BY-STEP IMPLEMENTATION PLAN
PHASE 1: Environment Variables
Step 1.1: Update docker-compose.dev.yml
instance-service section:

environment:
  # Platform Database Configuration (postgres1) - UNCHANGED
  POSTGRES_HOST: postgres
  POSTGRES_PORT: 5432
  POSTGRES_DB: instance
  DB_SERVICE_USER: ${POSTGRES_INSTANCE_SERVICE_USER:-instance_service}
  DB_SERVICE_PASSWORD: ${POSTGRES_INSTANCE_SERVICE_PASSWORD:-instance_service_secure_pass_change_me}
  
  # Odoo Instance Database Configuration (postgres2) - NEW
  ODOO_POSTGRES_HOST: postgres2
  ODOO_POSTGRES_PORT: 5432
  ODOO_POSTGRES_DEFAULT_DB: postgres
  ODOO_POSTGRES_ADMIN_USER: ${ODOO_POSTGRES_ADMIN_USER:-odoo_admin}
  ODOO_POSTGRES_ADMIN_PASSWORD: ${ODOO_POSTGRES_ADMIN_PASSWORD:-odoo_admin_secure_pass}
instance-worker section:

environment:
  # Platform Database Configuration (postgres1) - UNCHANGED
  POSTGRES_HOST: postgres
  POSTGRES_PORT: 5432
  POSTGRES_DB: instance
  DB_SERVICE_USER: ${POSTGRES_INSTANCE_SERVICE_USER:-instance_service}
  DB_SERVICE_PASSWORD: ${POSTGRES_INSTANCE_SERVICE_PASSWORD:-instance_service_secure_pass_change_me}
  
  # Keep legacy admin vars for backward compatibility (will be deprecated)
  POSTGRES_USER: ${POSTGRES_USER:-odoo_user}
  POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-secure_password_change_me}
  
  # Odoo Instance Database Configuration (postgres2) - NEW
  ODOO_POSTGRES_HOST: postgres2
  ODOO_POSTGRES_PORT: 5432
  ODOO_POSTGRES_DEFAULT_DB: postgres
  ODOO_POSTGRES_ADMIN_USER: ${ODOO_POSTGRES_ADMIN_USER:-odoo_admin}
  ODOO_POSTGRES_ADMIN_PASSWORD: ${ODOO_POSTGRES_ADMIN_PASSWORD:-odoo_admin_secure_pass}
Files: 1 file
Complexity: Low
Risk: Low

PHASE 2: Update Database Manager Classes
Step 2.1: Keep InstanceDatabase class as-is
File: services/instance-service/app/utils/database.py

NO CHANGES NEEDED - InstanceDatabase already uses:

POSTGRES_HOST (will point to postgres1)
POSTGRES_PORT
POSTGRES_DB
DB_SERVICE_USER
DB_SERVICE_PASSWORD
This handles all platform metadata operations.

Files: 0 files changed
Complexity: None
Risk: None

Step 2.2: Create OdooInstanceDatabaseManager class
File: services/instance-service/app/utils/database.py (add to existing file)

New Class:

class OdooInstanceDatabaseManager:
    """
    Manages connections to postgres2 (ODOO_POSTGRES_HOST) for Odoo instance databases.
    Used by Celery tasks for creating/managing customer Odoo databases.
    """
    
    @staticmethod
    async def get_admin_connection():
        """
        Get admin connection to postgres database on postgres2.
        For CREATE/DROP DATABASE operations.
        
        Returns: asyncpg.Connection
        """
        return await asyncpg.connect(
            host=os.getenv('ODOO_POSTGRES_HOST', 'postgres'),
            port=int(os.getenv('ODOO_POSTGRES_PORT', '5432')),
            database=os.getenv('ODOO_POSTGRES_DEFAULT_DB', 'postgres'),
            user=os.getenv('ODOO_POSTGRES_ADMIN_USER', 'odoo_admin'),
            password=os.getenv('ODOO_POSTGRES_ADMIN_PASSWORD', 'changeme')
        )
        
    @staticmethod
    async def get_instance_db_connection(database_name: str):
        """
        Get connection to specific Odoo instance database on postgres2.
        For managing Odoo-specific tables (ir_module_module, etc.)
        
        Args:
            database_name: The Odoo instance database name
            
        Returns: asyncpg.Connection
        """
        return await asyncpg.connect(
            host=os.getenv('ODOO_POSTGRES_HOST', 'postgres'),
            port=int(os.getenv('ODOO_POSTGRES_PORT', '5432')),
            database=database_name,
            user=os.getenv('ODOO_POSTGRES_ADMIN_USER', 'odoo_admin'),
            password=os.getenv('ODOO_POSTGRES_ADMIN_PASSWORD', 'changeme')
        )
Files: 1 file
Complexity: Low
Risk: Low (new code, doesn't affect existing)

PHASE 3: No Changes Needed for Routes
Files:

app/routes/instances.py - NO CHANGE
app/routes/admin.py - NO CHANGE
app/routes/monitoring.py - NO CHANGE
app/services/instance_service.py - NO CHANGE
app/main.py - NO CHANGE
Reason: They all use InstanceDatabase which already uses POSTGRES_HOST

Files: 0 files
Complexity: None
Risk: None

PHASE 5: Update Task Files - Admin/Odoo Operations (REQUIRED)
These are the ONLY task changes required to separate postgres1 from postgres2.

Step 5.1: Update provisioning.py
File: services/instance-service/app/tasks/provisioning.py

Changes needed: 3 locations

1. Import OdooInstanceDatabaseManager (top of file):

from app.utils.database import OdooInstanceDatabaseManager
2. Update _create_odoo_database() function (around line 273):

# OLD
async def _create_odoo_database(instance: Dict[str, Any]) -> Dict[str, str]:
    """Create dedicated PostgreSQL database for Odoo instance"""
    
    # Connect to PostgreSQL as admin
    admin_conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'postgres'),
        port=5432,
        database='postgres',  # Connect to default DB
        user=os.getenv('POSTGRES_USER', 'saasodoo'),
        password=os.getenv('POSTGRES_PASSWORD', 'saasodoo123')
    )

# NEW
async def _create_odoo_database(instance: Dict[str, Any]) -> Dict[str, str]:
    """Create dedicated PostgreSQL database for Odoo instance on postgres2"""
    
    # Connect to postgres2 as admin
    admin_conn = await OdooInstanceDatabaseManager.get_admin_connection()
Also update the return dict (around line 297-302):

# OLD
return {
    "db_name": database_name,
    "db_user": db_user,
    "db_password": db_password,
    "db_host": os.getenv('POSTGRES_HOST', 'postgres'),
    "db_port": "5432"
}

# NEW
return {
    "db_name": database_name,
    "db_user": db_user,
    "db_password": db_password,
    "db_host": os.getenv('ODOO_POSTGRES_HOST', 'postgres'),
    "db_port": os.getenv('ODOO_POSTGRES_PORT', '5432')
}
3. Update _cleanup_failed_provisioning() function (around line 529):

# OLD
admin_conn = await asyncpg.connect(
    host=os.getenv('POSTGRES_HOST', 'postgres'),
    port=5432,
    database='postgres',
    user=os.getenv('POSTGRES_USER', 'saasodoo'),
    password=os.getenv('POSTGRES_PASSWORD', 'saasodoo123')
)

# NEW
admin_conn = await OdooInstanceDatabaseManager.get_admin_connection()
Files: 1 file
Locations: 3 changes
Complexity: Low
Risk: Low

Step 5.2: Update maintenance.py
File: services/instance-service/app/tasks/maintenance.py

Changes needed: 3 locations

1. Import OdooInstanceDatabaseManager (top of file):

from app.utils.database import OdooInstanceDatabaseManager
2. Update _recreate_database() function (around line 847):

# OLD
admin_conn = await asyncpg.connect(
    host=os.getenv('POSTGRES_HOST', 'postgres'),
    port=5432,
    database='postgres',
    user=os.getenv('POSTGRES_USER', 'odoo_user'),
    password=os.getenv('POSTGRES_PASSWORD', 'secure_password_change_me')
)

# NEW
admin_conn = await OdooInstanceDatabaseManager.get_admin_connection()
3. Update _restore_database_permissions() function (around line 878):

# OLD
conn = await asyncpg.connect(
    host=os.getenv('POSTGRES_HOST', 'postgres'),
    port=5432,
    database=database_name,
    user=os.getenv('POSTGRES_USER', 'odoo_user'),
    password=os.getenv('POSTGRES_PASSWORD', 'secure_password_change_me')
)

# NEW
conn = await OdooInstanceDatabaseManager.get_instance_db_connection(database_name)
4. Update _reset_odoo_database_state() function (around line 919):

# OLD
conn = await asyncpg.connect(
    host=os.getenv('POSTGRES_HOST', 'postgres'),
    port=5432,
    database=database_name,
    user=os.getenv('POSTGRES_USER', 'odoo_user'),
    password=os.getenv('POSTGRES_PASSWORD', 'secure_password_change_me')
)

# NEW
conn = await OdooInstanceDatabaseManager.get_instance_db_connection(database_name)
Files: 1 file
Locations: 4 changes
Complexity: Low
Risk: Low

Step 5.3: Update lifecycle.py
File: services/instance-service/app/tasks/lifecycle.py

NO CHANGES NEEDED - lifecycle.py only does platform database operations (status updates), which still use POSTGRES_HOST.

Files: 0 files
Complexity: None
Risk: None

Step 5.4: Update monitoring.py
File: services/instance-service/app/tasks/monitoring.py

NO CHANGES NEEDED - monitoring.py only queries platform database for instance metadata, which still uses POSTGRES_HOST.

Files: 0 files
Complexity: None
Risk: None

PHASE 6: Infrastructure Setup
Step 6.1: Set up postgres2 server
Actions:

Deploy second PostgreSQL instance (postgres2)
Configure for Odoo instance databases
Create admin user (odoo_admin)
Set up networking between services and postgres2
Infrastructure changes in docker-compose.dev.yml:

  # Add new postgres2 service
  postgres2:
    image: postgres:15-alpine
    container_name: saasodoo-postgres2
    restart: unless-stopped
    environment:
      POSTGRES_DB: postgres
      POSTGRES_USER: ${ODOO_POSTGRES_ADMIN_USER:-odoo_admin}
      POSTGRES_PASSWORD: ${ODOO_POSTGRES_ADMIN_PASSWORD:-odoo_admin_secure_pass}
    volumes:
      - postgres2-data:/var/lib/postgresql/data
    networks:
      - saasodoo-network
    ports:
      - "5433:5432"  # Expose on different host port
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${ODOO_POSTGRES_ADMIN_USER:-odoo_admin}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s
    labels:
      - "traefik.enable=false"

volumes:
  postgres2-data:
    driver: local
Files: 1 file
Complexity: Low
Risk: Low

PHASE 7: Testing & Validation
Step 7.1: Test platform operations (postgres1)
Verify:

Create instance → metadata saved to postgres1
Update instance status → updates postgres1
Query instances → reads from postgres1
All routes work unchanged
Complexity: Low
Risk: Low

Step 7.2: Test Odoo database operations (postgres2)
Verify:

Create instance → database created on postgres2
Database info returned has ODOO_POSTGRES_HOST
Odoo container connects to postgres2
Maintenance operations work on postgres2
Test commands:

# Check instance record in postgres1
docker exec saasodoo-postgres psql -U instance_service -d instance -c \
  "SELECT id, name, database_name, db_host FROM instances WHERE id = 'xxx';"

# Check Odoo database exists in postgres2
docker exec saasodoo-postgres2 psql -U odoo_admin -d postgres -c \
  "\l" | grep odoo_
Complexity: Medium
Risk: Medium

Step 7.3: End-to-end testing
Test scenarios:

Full provision flow:

POST /instances → creates instance record in postgres1
Celery task creates database on postgres2
Container starts and connects to postgres2
Status updates go to postgres1
Maintenance operations:

Backup instance → dumps from postgres2
Restore instance → restores to postgres2
Update version → recreates DB on postgres2
Cleanup:

Delete instance → removes record from postgres1
Cleanup task → drops database from postgres2
Complexity: High
Risk: Medium

SUMMARY
Files to Modify:
| File | Changes | Complexity | Risk | |------|---------|------------|------| | docker-compose.dev.yml | Add postgres2 + env vars | Low | Low | | app/utils/database.py | Add OdooInstanceDatabaseManager | Low | Low | | app/tasks/provisioning.py | Update 3 admin connections | Low | Low | | app/tasks/maintenance.py | Update 4 admin connections | Low | Low | | app/tasks/helpers.py | OPTIONAL - consolidate helpers | Medium | Low |

Total: 3-4 files (1 optional)

Files with NO Changes:
✅ app/main.py - unchanged
✅ app/routes/instances.py - unchanged
✅ app/routes/admin.py - unchanged
✅ app/routes/monitoring.py - unchanged
✅ app/services/instance_service.py - unchanged
✅ app/tasks/lifecycle.py - unchanged
✅ app/tasks/monitoring.py - unchanged
✅ app/utils/database.py::InstanceDatabase - unchanged

Connection Summary:
| Operation | Host Variable | Port | User | Database | Server | |-----------|---------------|------|------|----------|--------| | Platform metadata (routes) | POSTGRES_HOST | 5432 | DB_SERVICE_USER | instance | postgres1 | | Platform metadata (tasks) | POSTGRES_HOST | 5432 | DB_SERVICE_USER | instance | postgres1 | | CREATE/DROP Odoo DB | ODOO_POSTGRES_HOST | 5432 | ODOO_POSTGRES_ADMIN_USER | postgres | postgres2 | | Manage Odoo tables | ODOO_POSTGRES_HOST | 5432 | ODOO_POSTGRES_ADMIN_USER | odoo_* | postgres2 |

Benefits:
✅ Minimal changes: Only 7 connection points to update
✅ Backward compatible: POSTGRES_HOST still works for platform
✅ Clear separation: Platform (postgres1) vs Odoo instances (postgres2)
✅ No route changes: All FastAPI code stays the same
✅ Simple migration: Just point ODOO_POSTGRES_HOST to new server

Recommended Rollout:
✅ Phase 1: Add environment variables (1 file)
✅ Phase 2: Add OdooInstanceDatabaseManager class (1 file)
✅ Phase 5: Update provisioning.py and maintenance.py (2 files)
✅ Phase 6: Deploy postgres2 infrastructure
✅ Phase 7: Test end-to-end
Estimated effort: 2-3 hours coding + testing

Is this simplified plan clearer? Much less work since we're keeping POSTGRES_HOST unchanged!