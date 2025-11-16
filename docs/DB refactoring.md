COMPLETE PLAN: POSTGRES1 vs POSTGRES2 SEPARATION
OBJECTIVE
Separate database servers so that:

postgres1: Platform databases (auth, billing, instance, communication)
postgres2: Odoo instance databases (odoo_customer_instance_*)
Instance metadata records stay in postgres1's instance database
Instance actual Odoo databases go to postgres2
CURRENT STATE
Database Connection Types:
1. Platform Metadata (instance database)

Purpose: Store instance records, status, metadata
Current Host: POSTGRES_HOST (single server)
User: instance_service (service-specific)
Database: instance
Used By:
InstanceDatabase class (routes) - 1 location
Task helpers (13 locations) - duplicated code
2. Admin Operations (postgres database)

Purpose: CREATE/DROP Odoo customer databases
Current Host: POSTGRES_HOST (single server)
User: POSTGRES_USER (admin - inconsistent: 'saasodoo' or 'odoo_user')
Database: postgres
Used By: Task functions (3 locations)
3. Odoo Instance Operations (customer databases)

Purpose: Manage Odoo application tables (ir_module_module, etc.)
Current Host: POSTGRES_HOST (single server)
User: POSTGRES_USER (admin)
Database: Customer-specific (e.g., odoo_customer123_abc)
Used By: Task functions (2 locations)
PROBLEM
All three types use POSTGRES_HOST → Can't separate servers

SOLUTION ARCHITECTURE
Environment Variables:
# Platform databases (postgres1)
PLATFORM_POSTGRES_HOST=postgres1
PLATFORM_POSTGRES_PORT=5432
PLATFORM_POSTGRES_DB=instance
PLATFORM_POSTGRES_USER=instance_service
PLATFORM_POSTGRES_PASSWORD=xxx

# Odoo instance databases (postgres2)  
ODOO_POSTGRES_HOST=postgres2
ODOO_POSTGRES_PORT=5432
ODOO_POSTGRES_DEFAULT_DB=postgres
ODOO_POSTGRES_ADMIN_USER=odoo_admin
ODOO_POSTGRES_ADMIN_PASSWORD=xxx
Two Manager Classes (both in instance-service/app/utils/database.py):
1. PlatformDatabaseManager (refactored InstanceDatabase)

Connection pool for platform instance database
Connects to postgres1
Used by: Routes + Tasks (for platform metadata)
Methods: All current InstanceDatabase methods
2. OdooInstanceDatabaseManager (new)

Connection helpers for Odoo databases
Connects to postgres2
Used by: Tasks only (for database creation/management)
Methods:
get_admin_connection() - Admin connection to postgres DB
get_instance_db_connection(db_name) - Connection to specific Odoo DB
close_connection(conn) - Cleanup helper
STEP-BY-STEP IMPLEMENTATION PLAN
PHASE 1: Environment Variables
Step 1.1: Update docker-compose.dev.yml
instance-service section:

environment:
  # Platform Database Configuration (postgres1)
  PLATFORM_POSTGRES_HOST: postgres1
  PLATFORM_POSTGRES_PORT: 5432
  PLATFORM_POSTGRES_DB: instance
  DB_SERVICE_USER: ${POSTGRES_INSTANCE_SERVICE_USER:-instance_service}
  DB_SERVICE_PASSWORD: ${POSTGRES_INSTANCE_SERVICE_PASSWORD:-instance_service_secure_pass_change_me}
  
  # Odoo Instance Database Configuration (postgres2)
  ODOO_POSTGRES_HOST: postgres2
  ODOO_POSTGRES_PORT: 5432
  ODOO_POSTGRES_DEFAULT_DB: postgres
  ODOO_POSTGRES_ADMIN_USER: ${ODOO_POSTGRES_ADMIN_USER:-odoo_admin}
  ODOO_POSTGRES_ADMIN_PASSWORD: ${ODOO_POSTGRES_ADMIN_PASSWORD:-odoo_admin_secure_pass}
instance-worker section:

environment:
  # Same as instance-service
  PLATFORM_POSTGRES_HOST: postgres1
  PLATFORM_POSTGRES_PORT: 5432
  PLATFORM_POSTGRES_DB: instance
  DB_SERVICE_USER: ${POSTGRES_INSTANCE_SERVICE_USER:-instance_service}
  DB_SERVICE_PASSWORD: ${POSTGRES_INSTANCE_SERVICE_PASSWORD:-instance_service_secure_pass_change_me}
  
  ODOO_POSTGRES_HOST: postgres2
  ODOO_POSTGRES_PORT: 5432
  ODOO_POSTGRES_DEFAULT_DB: postgres
  ODOO_POSTGRES_ADMIN_USER: ${ODOO_POSTGRES_ADMIN_USER:-odoo_admin}
  ODOO_POSTGRES_ADMIN_PASSWORD: ${ODOO_POSTGRES_ADMIN_PASSWORD:-odoo_admin_secure_pass}
Files: 1 file Complexity: Low

PHASE 2: Update Database Manager Classes
Step 2.1: Refactor InstanceDatabase → PlatformDatabaseManager
File: services/instance-service/app/utils/database.py

Changes:

Rename class InstanceDatabase → PlatformDatabaseManager
Update connection parameters to use PLATFORM_POSTGRES_* instead of POSTGRES_*
Keep all existing methods unchanged:
initialize()
close()
create_instance()
get_instance()
update_instance()
update_instance_status()
All query methods
Connection change:

# OLD
host=os.getenv('POSTGRES_HOST', 'postgres')
database=os.getenv('POSTGRES_DB', 'instance')

# NEW
host=os.getenv('PLATFORM_POSTGRES_HOST', 'postgres')
database=os.getenv('PLATFORM_POSTGRES_DB', 'instance')
Files: 1 file Complexity: Low Risk: Low (just renaming + env vars)

Step 2.2: Create OdooInstanceDatabaseManager class
File: services/instance-service/app/utils/database.py (same file, add new class)

New Class Structure:

class OdooInstanceDatabaseManager:
    """
    Manages connections to postgres2 for Odoo instance databases
    Used by Celery tasks for admin operations
    """
    
    @staticmethod
    async def get_platform_connection():
        """
        Get connection to platform database (postgres1)
        For tasks that need to query/update instance metadata
        Returns: asyncpg.Connection
        """
        # Connects to postgres1, instance DB, instance_service user
        
    @staticmethod
    async def get_admin_connection():
        """
        Get admin connection to postgres database (postgres2)
        For CREATE/DROP DATABASE operations
        Returns: asyncpg.Connection
        """
        # Connects to postgres2, postgres DB, odoo_admin user
        
    @staticmethod
    async def get_instance_db_connection(database_name: str):
        """
        Get connection to specific Odoo instance database (postgres2)
        For managing Odoo tables (ir_module_module, etc.)
        Args:
            database_name: The Odoo instance database name
        Returns: asyncpg.Connection
        """
        # Connects to postgres2, customer DB, odoo_admin user
        
    @staticmethod
    async def close_connection(conn):
        """
        Close a connection
        Args:
            conn: asyncpg.Connection to close
        """
Files: 1 file (same as above) Complexity: Medium Risk: Low (new code, doesn't affect existing)

PHASE 3: Update Routes
Step 3.1: Update route imports
Files to update:

services/instance-service/app/routes/instances.py
services/instance-service/app/routes/admin.py
services/instance-service/app/routes/monitoring.py
Change:

# OLD
from app.utils.database import InstanceDatabase

# NEW
from app.utils.database import PlatformDatabaseManager
Files: 3 files Complexity: Low Risk: Low (simple rename)

Step 3.2: Update main.py
File: services/instance-service/app/main.py

Changes:

# OLD
from app.utils.database import InstanceDatabase
instance_db = InstanceDatabase()
await instance_db.initialize()

# NEW
from app.utils.database import PlatformDatabaseManager
platform_db = PlatformDatabaseManager()
await platform_db.initialize()
Files: 1 file Complexity: Low Risk: Low

Step 3.3: Update service layer
File: services/instance-service/app/services/instance_service.py

Change:

# OLD
from app.utils.database import InstanceDatabase

# NEW
from app.utils.database import PlatformDatabaseManager
Files: 1 file Complexity: Low Risk: Low

PHASE 4: Update Task Files - Platform Operations
This is the biggest change - consolidating duplicated code.

Step 4.1: Create shared task helpers
File: services/instance-service/app/tasks/helpers.py (NEW FILE)

Purpose: Centralize duplicated task helper functions

Functions to create:

async def get_instance_from_db(instance_id: str) -> Dict[str, Any]:
    """
    Fetch instance record from platform database (postgres1)
    Replaces 3 duplicated _get_instance_from_db() functions
    """
    # Uses OdooInstanceDatabaseManager.get_platform_connection()

async def update_instance_status(instance_id: str, status: InstanceStatus, error_message: str = None):
    """
    Update instance status in platform database (postgres1)
    Replaces 4 duplicated _update_instance_status() functions
    """
    # Uses OdooInstanceDatabaseManager.get_platform_connection()

async def update_instance_network_info(instance_id: str, container_info: Dict[str, Any]):
    """
    Update instance network info in platform database (postgres1)
    Replaces 3 duplicated _update_instance_network_info() functions
    """
    # Uses OdooInstanceDatabaseManager.get_platform_connection()
Files: 1 new file Complexity: Medium Risk: Low (consolidates existing code)

Step 4.2: Update provisioning.py
File: services/instance-service/app/tasks/provisioning.py

Changes:

Import shared helpers:

from app.tasks.helpers import (
    get_instance_from_db,
    update_instance_status,
    update_instance_network_info
)
from app.utils.database import OdooInstanceDatabaseManager
Remove duplicate functions:

Delete _get_instance_from_db() (lines 203-244)
Delete _update_instance_status() (lines 247-266)
Delete _update_instance_network_info() (lines 473-500)
Update _create_odoo_database() (lines 269-306):

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
Update _cleanup_failed_provisioning() (lines 529-557):

# Same change - use OdooInstanceDatabaseManager.get_admin_connection()
Update all calls to helper functions:

# OLD
instance = await _get_instance_from_db(instance_id)

# NEW  
instance = await get_instance_from_db(instance_id)
Files: 1 file Complexity: High (many changes) Risk: Medium (but well-tested duplicates)

Step 4.3: Update lifecycle.py
File: services/instance-service/app/tasks/lifecycle.py

Changes:

Import shared helpers
Remove duplicate functions:
Delete _get_instance_from_db() (lines 435-476)
Delete _update_instance_status() (lines 479-498)
Delete _update_instance_network_info() (lines 525-552)
Update all calls to use shared helpers
Files: 1 file Complexity: Medium Risk: Medium

Step 4.4: Update maintenance.py
File: services/instance-service/app/tasks/maintenance.py

Changes:

Import shared helpers

Remove duplicate functions:

Delete _get_instance_from_db() (lines 750-789)
Delete _update_instance_status() (lines 792-811)
Delete _update_instance_network_info() (lines 1113-1140)
Update _recreate_database() (lines 847-870):

# Use OdooInstanceDatabaseManager.get_admin_connection()
Update _restore_database_permissions() (lines 873-911):

# OLD
conn = await asyncpg.connect(
    database=database_name,
    user=os.getenv('POSTGRES_USER', 'odoo_user'),
    ...
)

# NEW
conn = await OdooInstanceDatabaseManager.get_instance_db_connection(database_name)
Update _reset_odoo_database_state() (lines 914-1001):

# Same - use OdooInstanceDatabaseManager.get_instance_db_connection()
Files: 1 file Complexity: High Risk: Medium

Step 4.5: Update monitoring.py
File: services/instance-service/app/tasks/monitoring.py

Changes:

Import OdooInstanceDatabaseManager

Update _get_db_connection() (line 122):

# Use OdooInstanceDatabaseManager.get_platform_connection()
Update _query_instance_id_by_hex() (lines 89-111):

# Use OdooInstanceDatabaseManager.get_platform_connection()
Update _update_instance_status_from_event() (lines 378-452):

# Use OdooInstanceDatabaseManager.get_platform_connection()
Update _reconcile_instance_statuses() (lines 475-602):

# Use OdooInstanceDatabaseManager.get_platform_connection()
Files: 1 file Complexity: Medium Risk: Medium

PHASE 5: Infrastructure Setup
Step 5.1: Set up postgres2 server
Actions:

Deploy second PostgreSQL instance (postgres2)
Configure for Odoo instance databases
Create admin user (odoo_admin)
Set up networking between services and postgres2
Files: Infrastructure configuration Complexity: High (infrastructure) Risk: High (new infrastructure)

Step 5.2: Update docker-compose network configuration
Ensure:

Both instance-service and instance-worker can reach postgres1 and postgres2
Network configuration allows cross-server communication
Files: 1 file (docker-compose.dev.yml) Complexity: Medium Risk: Medium

PHASE 6: Testing & Validation
Step 6.1: Unit tests
Test coverage:

PlatformDatabaseManager connects to postgres1
OdooInstanceDatabaseManager.get_platform_connection() → postgres1
OdooInstanceDatabaseManager.get_admin_connection() → postgres2
OdooInstanceDatabaseManager.get_instance_db_connection() → postgres2
Files: Test files Complexity: Medium

Step 6.2: Integration tests
Test scenarios:

Create instance → metadata in postgres1, database in postgres2
Update instance status → updates postgres1
Provision instance → creates DB in postgres2
Delete instance → removes from both postgres1 and postgres2
Complexity: High

Step 6.3: Migration testing
Test existing instances:

Existing instance records in postgres1 still work
Can connect to existing Odoo DBs (if migrating from single postgres)
Billing webhooks still trigger correct updates
Complexity: High Risk: High

SUMMARY
Files to Modify:
| File | Changes | Complexity | Risk | |------|---------|------------|------| | docker-compose.dev.yml | Add env vars | Low | Low | | app/utils/database.py | Refactor + new class | Medium | Low | | app/main.py | Rename InstanceDatabase | Low | Low | | app/routes/instances.py | Update import | Low | Low | | app/routes/admin.py | Update import | Low | Low | | app/routes/monitoring.py | Update import | Low | Low | | app/services/instance_service.py | Update import | Low | Low | | app/tasks/helpers.py | NEW - shared helpers | Medium | Low | | app/tasks/provisioning.py | Remove dupes, use managers | High | Medium | | app/tasks/lifecycle.py | Remove dupes, use managers | Medium | Medium | | app/tasks/maintenance.py | Remove dupes, use managers | High | Medium | | app/tasks/monitoring.py | Use manager | Medium | Medium |

Total: 12 files (1 new)

Connection Mapping:
| Operation Type | Current Server | New Server | Manager Method | |---------------|----------------|------------|----------------| | Instance metadata CRUD | postgres | postgres1 | PlatformDatabaseManager (pool) | | Instance status updates | postgres | postgres1 | OdooInstanceDatabaseManager.get_platform_connection() | | CREATE/DROP databases | postgres | postgres2 | OdooInstanceDatabaseManager.get_admin_connection() | | Odoo table operations | postgres | postgres2 | OdooInstanceDatabaseManager.get_instance_db_connection() |

Benefits:
✅ Clear separation: Platform data vs customer data
✅ Scalability: Scale postgres1 and postgres2 independently
✅ Security: Different credentials for platform vs Odoo admin
✅ HA flexibility: Different HA strategies for each postgres
✅ Code consolidation: Removes 10+ duplicate functions
✅ Maintainability: Single source of truth for connections
✅ Flexibility: Easy to point to different servers per environment

Risks:
⚠️ Breaking change: Requires infrastructure changes
⚠️ Migration complexity: Moving existing Odoo DBs to postgres2
⚠️ Testing burden: Need comprehensive test coverage
⚠️ Deployment coordination: Both postgres servers must be ready

Recommended Rollout:
Phase 1-2: Environment vars + database managers (dev environment)
Phase 3-4: Update routes + tasks (test thoroughly)
Phase 5: Set up postgres2 infrastructure
Phase 6: Full integration testing
Deploy: Staged rollout with rollback plan
Is this complete plan clear? Any part you want me to elaborate on?