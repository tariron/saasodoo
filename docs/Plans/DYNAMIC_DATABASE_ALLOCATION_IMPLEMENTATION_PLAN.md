# Dynamic Database Allocation Implementation Plan

## Project Overview

**Objective**: Implement a dynamic PostgreSQL server allocation system that automatically provisions database pools in Docker Swarm as needed, eliminating the hardcoded `postgres2` server and enabling flexible scaling.

**Business Requirements**:
- Support both shared database pools (Standard/Free plans) and dedicated database servers (Premium/Enterprise plans)
- Automatically provision new pools when capacity is reached
- Enable seamless upgrades from shared to dedicated database infrastructure
- Maintain zero or minimal downtime during migrations
- Provide cost-effective multi-tenancy through shared pools

**Technical Scope**:
- New microservice: `database-service` (port 8005)
- Dynamic PostgreSQL provisioning via Docker Swarm
- CephFS-backed persistent storage
- Celery-based async task processing
- HTTP API for database allocation
- Database migration tooling for plan upgrades

---

## Architecture Components

### 1. Database Service (New Microservice)

**Purpose**: Dedicated service responsible for all PostgreSQL infrastructure management, separate from Odoo instance management.

**Responsibilities**:
- Allocate database servers for new Odoo instances
- Provision new PostgreSQL pools when capacity is exhausted
- Monitor health of database pools
- Manage database migrations during plan upgrades
- Track capacity and utilization metrics

**Technology Stack**:
- FastAPI for REST API endpoints
- SQLAlchemy for database ORM
- Celery for async task processing
- Docker SDK for Swarm service management
- asyncpg for PostgreSQL operations

**Dependencies**:
- Shares `instance` database with instance-service (for db_servers table)
- Requires access to Docker socket (`/var/run/docker.sock`)
- Requires CephFS mount at `/mnt/cephfs`
- Communicates with RabbitMQ for Celery tasks
- Uses Redis for caching and coordination

---

### 2. Database Schema

#### Table: `db_servers`

**Purpose**: Central registry of all PostgreSQL server pools (both shared and dedicated).

**Key Fields**:

**Identity & Connection**:
- `id`: UUID primary key
- `name`: Unique server name (e.g., "postgres-pool-1", "postgres-dedicated-abc123")
- `host`: DNS hostname (Docker service name)
- `port`: PostgreSQL port (default 5432)

**Server Type & Capacity**:
- `server_type`: Enum ('platform', 'shared', 'dedicated')
- `max_instances`: Maximum databases this server can host
- `current_instances`: Current number of databases hosted

**Docker Swarm Metadata**:
- `swarm_service_id`: Docker service ID for lifecycle management
- `swarm_service_name`: Service name in Swarm
- `node_placement`: Placement constraint (e.g., "node.labels.role==database")

**Status Tracking**:
- `status`: Lifecycle state ('provisioning', 'initializing', 'active', 'full', 'maintenance', 'error', 'deprovisioning')
- `health_status`: Health check result ('healthy', 'degraded', 'unhealthy', 'unknown')
- `last_health_check`: Timestamp of last health verification
- `health_check_failures`: Counter for consecutive failures

**Resource Configuration**:
- `cpu_limit`: CPU allocation (e.g., "2" cores)
- `memory_limit`: RAM allocation (e.g., "4G")
- `storage_path`: CephFS mount path for data persistence
- `allocated_storage_gb`: Current storage usage

**PostgreSQL Configuration**:
- `postgres_version`: Version number (e.g., "16")
- `postgres_image`: Full Docker image tag (e.g., "postgres:16-alpine")

**Allocation Strategy**:
- `allocation_strategy`: 'auto' (automatic allocation) or 'manual' (admin-controlled)
- `priority`: Lower number = higher priority for allocation

**Dedicated Server Tracking**:
- `dedicated_to_customer_id`: UUID of customer (only for dedicated servers)
- `dedicated_to_instance_id`: UUID of instance (only for dedicated servers)

**Audit Fields**:
- `provisioned_by`: Service or user that created this server
- `provisioned_at`: Creation timestamp
- `last_allocated_at`: Last time a database was allocated
- `created_at`, `updated_at`: Standard timestamps

**Indexes**:
- Composite index on (server_type, status, current_instances, priority) for fast allocation queries
- Index on swarm_service_id for Docker operations
- Index on health_status for monitoring queries

---

#### Table: `instances` (Modified)

**New Fields Added**:
- `db_server_id`: Foreign key to db_servers table
- `db_host`: Denormalized hostname for quick access
- `db_port`: Database port
- `db_name`: Database name
- `plan_tier`: Subscription tier ('free', 'starter', 'standard', 'professional', 'premium', 'enterprise')
- `requires_dedicated_db`: Boolean flag indicating if instance needs dedicated server

**Purpose**: Links Odoo instances to their database servers and tracks plan requirements.

---

## Implementation Stages

---

## STAGE 1: Foundation Setup

**Goal**: Create basic infrastructure without touching existing systems. All components can be tested independently.

**Duration Estimate**: Foundation work

**Testing Strategy**: Unit tests, schema validation, isolated service testing

---

### Stage 1.1: Database Schema Creation

**What It Does**:
Creates the `db_servers` table and modifies `instances` table to support dynamic allocation.

**SQL Migration Script**:
- Creates `db_servers` table with all constraints, indexes, and check constraints
- Adds foreign key columns to `instances` table
- Creates trigger for auto-updating `updated_at` timestamp
- Includes rollback scripts for safety

**Dependencies**:
- Access to `instance` database
- Database migration tool or manual SQL execution

**Testing**:
- Run migration in test environment
- Verify all indexes created
- Test foreign key constraints
- Verify trigger functionality
- Run rollback and re-apply to ensure idempotency

**Acceptance Criteria**:
- `db_servers` table exists with all columns
- `instances` table has new columns
- Can insert sample data successfully
- Constraints enforce data integrity

---

### Stage 1.2: Database Service Project Structure

**What It Does**:
Creates the skeleton of the new database-service microservice with all directories, configuration files, and placeholder code.

**Directory Structure Created**:
```
services/database-service/
├── app/
│   ├── __init__.py
│   ├── main.py (FastAPI application)
│   ├── models/
│   │   ├── __init__.py
│   │   └── db_server.py (SQLAlchemy model)
│   ├── services/
│   │   ├── __init__.py
│   │   └── db_allocation_service.py (allocation logic)
│   ├── tasks/
│   │   ├── __init__.py
│   │   ├── provisioning_tasks.py (async provisioning)
│   │   └── monitoring_tasks.py (health checks)
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── allocation.py (allocation endpoints)
│   │   └── admin.py (admin endpoints)
│   ├── utils/
│   │   ├── __init__.py
│   │   └── docker_client.py (copied from instance-service)
│   └── celery_config.py
├── Dockerfile
├── requirements.txt
├── .env.example
└── tests/
```

**Configuration Files**:
- Environment variables for database connection, Docker socket, CephFS paths
- Celery configuration for queue names and task routing
- Logging configuration
- Docker health check configuration

**Dependencies**:
- Python 3.11+
- FastAPI, SQLAlchemy, Celery
- Docker SDK for Python
- asyncpg for PostgreSQL operations

**Testing**:
- Service starts without errors
- Health endpoint responds
- Database connection works
- Celery worker connects to RabbitMQ
- Docker client can connect to Swarm

**Acceptance Criteria**:
- Service runs in development mode
- All imports resolve
- Health check returns 200 OK
- Logs are structured and readable

---

### Stage 1.3: SQLAlchemy Model Implementation

**What It Does**:
Implements the `DBServer` model class that maps to the `db_servers` table, with all business logic methods.

**Model Methods**:

**`is_available()`**:
- Checks if server is in 'active' status
- Verifies health_status is 'healthy' or 'unknown'
- Confirms current_instances < max_instances
- Returns boolean indicating availability

**`is_full()`**:
- Compares current_instances to max_instances
- Returns boolean indicating if at capacity

**`get_capacity_percentage()`**:
- Calculates (current_instances / max_instances) * 100
- Returns float percentage of capacity used

**`increment_instance_count()`**:
- Increments current_instances by 1
- Updates last_allocated_at timestamp
- If reaches max_instances, changes status to 'full'
- Commits transaction

**`decrement_instance_count()`**:
- Decrements current_instances by 1
- If was 'full' and now has capacity, changes status to 'active'
- Commits transaction

**`to_dict()`**:
- Converts model to JSON-serializable dictionary
- Includes computed fields (capacity_percentage, is_available)
- Formats timestamps as ISO strings

**Dependencies**:
- SQLAlchemy Base class from shared utilities
- Database session management

**Testing**:
- Unit tests for all methods
- Test state transitions (active ↔ full)
- Test boundary conditions (at capacity)
- Test timestamp updates

**Acceptance Criteria**:
- All methods work correctly
- Model can be queried, created, updated, deleted
- Constraints are enforced
- State transitions are correct

---

### Stage 1.4: Docker Client Utility

**What It Does**:
Copies and adapts the existing `docker_client.py` from instance-service to work with database-service, adding PostgreSQL-specific methods.

**Key Methods**:

**`create_postgres_pool_service()`**:
- **Purpose**: Creates a new PostgreSQL server as a Docker Swarm service
- **Parameters**: pool_name, postgres_password, storage_path, cpu_limit, memory_limit, max_instances
- **Process**:
  - Calculates PostgreSQL tuning parameters based on max_instances and resources
  - Configures max_connections, shared_buffers, effective_cache_size
  - Creates ContainerSpec with PostgreSQL image and environment variables
  - Configures Resources (CPU/memory limits and reservations)
  - Sets Placement constraints to 'node.labels.role==database'
  - Configures health check (pg_isready command)
  - Creates Mount specification for CephFS bind mount
  - Sets restart policy and update config
  - Creates Swarm service via Docker API
  - Returns service_id and service_name
- **Dependencies**: Docker SDK, Docker Swarm cluster
- **Error Handling**: Catches APIError, validates service creation

**`wait_for_service_ready()`**:
- **Purpose**: Polls service until it becomes healthy
- **Parameters**: service_id, timeout (default 180 seconds), check_interval (default 5 seconds)
- **Process**:
  - Queries service tasks every check_interval seconds
  - Checks task state: 'running', 'failed', 'starting'
  - If health check defined, waits for 'healthy' status
  - Times out after specified duration
  - Returns True if healthy, False if failed or timeout
- **Dependencies**: Docker SDK service API
- **Logging**: Debug logs for each check, info on success/failure

**`remove_service()`**:
- **Purpose**: Removes a Docker Swarm service
- **Parameters**: service_id (ID or name)
- **Process**:
  - Gets service by ID
  - Calls service.remove()
  - Handles NotFound gracefully
- **Returns**: True if successful, False otherwise

**`get_service_info()`**:
- **Purpose**: Retrieves detailed service information
- **Parameters**: service_id
- **Returns**: Dictionary with service_id, name, created_at, updated_at, replicas, tasks
- **Use Case**: Debugging, monitoring, health checks

**`update_service_resources()`**:
- **Purpose**: Updates CPU/memory limits without recreating service
- **Parameters**: service_id, cpu_limit (optional), memory_limit (optional)
- **Process**:
  - Gets current service spec
  - Updates TaskTemplate Resources
  - Calls service.update()
  - Triggers rolling update
- **Use Case**: Scaling resources up/down based on load

**Helper Methods**:

**`_parse_memory()`**:
- Converts memory strings ("4G", "2048M") to bytes
- Handles G (gigabytes), M (megabytes), K (kilobytes)

**`_calculate_shared_buffers()`**:
- Calculates PostgreSQL shared_buffers as 25% of total memory
- Returns formatted string (e.g., "1024MB")

**`_calculate_cache_size()`**:
- Calculates effective_cache_size as 75% of total memory
- Returns formatted string

**Dependencies**:
- Docker SDK (docker-py library)
- Access to `/var/run/docker.sock`
- Swarm mode enabled

**Testing**:
- Mock Docker SDK for unit tests
- Integration tests with real Docker Swarm (test environment)
- Test service creation, health check, removal
- Test error scenarios (no capacity, network issues)

**Acceptance Criteria**:
- Can create PostgreSQL services successfully
- Health checks work reliably
- Error handling covers common failures
- Logging provides useful debugging information

---

## STAGE 2: Core Allocation Logic

**Goal**: Implement the database allocation system that can find and use existing pools.

**Duration Estimate**: Core business logic

**Testing Strategy**: Unit tests with mocked database, integration tests with test database

---

### Stage 2.1: Database Allocation Service

**What It Does**:
Implements the core business logic for allocating databases to Odoo instances. This is the brain of the system.

**Class: `DatabaseAllocationService`**

**Constructor**:
- **Parameters**: database session (SQLAlchemy)
- **Initializes**: Database connection, logger, database manager utility
- **Purpose**: Sets up service with required dependencies

---

**Method: `allocate_database_for_instance()`**

**Purpose**: Main entry point for database allocation. Called by instance-service when creating a new Odoo instance.

**Parameters**:
- `instance_id`: UUID of the Odoo instance
- `customer_id`: UUID of the customer
- `plan_tier`: Subscription plan level (e.g., "standard", "premium")
- `require_dedicated`: Boolean flag (optional, overrides plan_tier logic)

**Process Flow**:
1. Logs allocation request with instance and customer details
2. Determines if dedicated server required based on:
   - Explicit require_dedicated flag, OR
   - Plan tier is 'premium' or 'enterprise'
3. If dedicated required:
   - Returns None (caller must provision dedicated server first)
   - Logs that dedicated provisioning needed
4. If shared allowed:
   - Calls `_find_available_shared_pool()`
   - If no pool found: Returns None (caller must provision new pool)
   - If pool found: Proceeds to database creation
5. Generates database name: `odoo_{customer_id_sanitized}_{instance_id_first_8_chars}`
6. Calls `_create_database_on_server()` to create DB on selected pool
7. Retrieves instance record from database
8. Updates instance record with:
   - `db_server_id`: ID of allocated pool
   - `db_host`: Hostname of pool
   - `db_port`: Port (usually 5432)
   - `db_name`: Generated database name
9. Calls `db_server.increment_instance_count()` to update pool capacity
10. Commits all changes to database
11. Returns dictionary containing:
    - `db_server_id`: UUID of allocated server
    - `db_host`: Connection hostname
    - `db_port`: Connection port
    - `db_name`: Database name
    - `db_user`: Database username
    - `db_password`: Generated password (TODO: move to Infisical)

**Returns**:
- Dictionary with database configuration if successful
- None if provisioning required (no available pools)

**Dependencies**:
- `_find_available_shared_pool()` for pool selection
- `_create_database_on_server()` for database creation
- Instance model for updating records
- Database transaction management

**Error Handling**:
- Database errors: Log and raise
- No pool available: Return None gracefully
- Database creation failure: Raise with details

**Testing**:
- Test with available pool (happy path)
- Test with no available pools (returns None)
- Test with dedicated required (returns None)
- Test database name generation
- Test instance record updates
- Test transaction rollback on failure

**Acceptance Criteria**:
- Successfully allocates from existing pool
- Correctly identifies when provisioning needed
- Updates all database records accurately
- Returns correct connection information

---

**Method: `_find_available_shared_pool()`**

**Purpose**: Queries database to find a shared pool with available capacity. Implements smart selection logic.

**Parameters**: None (operates on class state)

**Process Flow**:
1. Constructs SQL query with filters:
   - `server_type = 'shared'`
   - `status = 'active'`
   - `health_status IN ('healthy', 'unknown')`
   - `current_instances < max_instances`
2. Orders results by:
   - `priority ASC` (lower priority number = higher priority)
   - `current_instances ASC` (prefer less-loaded pools)
3. Limits to first result (most suitable pool)
4. Executes query and returns DBServer object

**Returns**:
- DBServer object if suitable pool found
- None if no pools available

**Algorithm Logic**:
- **Priority-based**: Allows administrative control (mark certain pools as preferred)
- **Load-balanced**: Among same priority, selects least-loaded pool
- **Health-aware**: Excludes unhealthy or degraded pools
- **Capacity-aware**: Only considers pools with free slots

**Dependencies**:
- SQLAlchemy query builder
- DBServer model
- Database session

**Error Handling**:
- Database query errors: Log and return None
- Multiple results: Takes first (ORDER BY ensures correct one)

**Testing**:
- Test with multiple pools (verifies ordering)
- Test with no pools (returns None)
- Test with all pools full (returns None)
- Test priority-based selection
- Test load-based selection
- Test health filtering

**Acceptance Criteria**:
- Selects least-loaded pool correctly
- Respects priority ordering
- Filters unhealthy pools
- Returns None when appropriate

---

**Method: `_create_database_on_server()`**

**Purpose**: Creates a new PostgreSQL database and dedicated user on the specified server using async PostgreSQL connections.

**Parameters**:
- `db_server`: DBServer object representing target PostgreSQL server
- `db_name`: Name of database to create

**Process Flow**:
1. Logs database creation attempt
2. Retrieves admin credentials:
   - Currently: From environment variables
   - Future: From Infisical secrets manager
3. Generates secure random password for database user (32 characters, URL-safe)
4. Generates database username: `{db_name}_user`
5. Establishes async connection to PostgreSQL:
   - Connects to `postgres` default database
   - Uses admin credentials
   - Target host from db_server.host
6. Executes CREATE DATABASE command:
   - Cannot be in transaction (PostgreSQL requirement)
   - Uses double quotes for name safety
7. Creates dedicated database user:
   - Executes CREATE USER with generated password
   - User name matches database: `{db_name}_user`
8. Grants privileges:
   - GRANT ALL PRIVILEGES ON DATABASE
   - GRANT ALL ON SCHEMA public
   - Sets default privileges for future tables
9. Closes connection to default database
10. Reconnects to newly created database
11. Grants schema-level privileges:
    - Ensures user can create tables
    - Sets up default privileges for objects
12. Closes connection
13. Returns generated password

**Returns**:
- String: Generated password for database user

**Dependencies**:
- asyncpg library for async PostgreSQL operations
- secrets module for password generation
- DBServer model for connection details
- Secrets manager (future: Infisical integration)

**Error Handling**:
- **DuplicateDatabaseError**: Database already exists
  - Logs warning
  - Generates new password (assumes user also exists)
  - Returns password (non-fatal)
- **Connection errors**: Raise with details
- **SQL errors**: Raise with query details
- **Always closes connections**: Uses try/finally blocks

**Security Considerations**:
- Passwords are cryptographically random (32 bytes)
- URL-safe encoding (no special chars issues)
- Uses parameterized queries where possible
- Credentials never logged
- TODO: Store passwords in Infisical, not return them

**Testing**:
- Test successful database creation
- Test user creation and privileges
- Test duplicate database handling
- Test connection failures
- Test SQL execution errors
- Verify password generation randomness
- Verify privileges are correct

**Acceptance Criteria**:
- Database created successfully
- User can connect with generated credentials
- User has required privileges
- Handles errors gracefully
- Returns password securely

---

**Method: `provision_dedicated_db_for_instance()`**

**Purpose**: Provisions a completely dedicated PostgreSQL server for a single premium customer. Used during plan upgrades.

**Parameters**:
- `instance_id`: UUID of Odoo instance
- `customer_id`: UUID of customer
- `plan_tier`: Subscription tier (e.g., "premium")

**Process Flow**:
1. Generates unique server name: `postgres-dedicated-{customer_id_first_8}`
2. Defines CephFS storage path: `/mnt/cephfs/postgres_dedicated/{server_name}`
3. Creates CephFS directory structure:
   - Creates base directory with mode 0o755
   - Creates data subdirectory
   - Sets ownership to postgres user (UID 999)
4. Generates secure admin password
5. Creates DBServer record in database:
   - `server_type = 'dedicated'`
   - `max_instances = 1` (only one database allowed)
   - `current_instances = 0`
   - `status = 'provisioning'`
   - `dedicated_to_customer_id = customer_id`
   - `dedicated_to_instance_id = instance_id`
   - Stores storage_path reference
6. Calls `docker_client.create_postgres_pool_service()`:
   - Higher resources: cpu_limit="4", memory_limit="8G"
   - Mounts dedicated CephFS path
   - Places on database nodes
7. Updates DBServer record with swarm_service_id
8. Changes status to 'initializing'
9. Waits for service health check (via `wait_for_service_ready()`)
10. On success:
    - Updates status to 'active'
    - Updates health_status to 'healthy'
    - Logs success
11. On failure:
    - Updates status to 'error'
    - Updates health_status to 'unhealthy'
    - Logs error details

**Returns**:
- DBServer object representing the new dedicated server

**Dependencies**:
- CephFS filesystem access
- Docker Swarm service creation
- Database transaction management
- Password generation utility
- Logging

**Resource Allocation**:
- **CPU**: 4 cores (vs 2 for shared pools)
- **Memory**: 8GB (vs 4GB for shared pools)
- **Storage**: Dedicated CephFS directory (isolated from other customers)
- **Network**: Same overlay network for service discovery

**Error Handling**:
- CephFS directory creation failure: Raise exception
- Docker service creation failure: Update status to 'error', raise
- Health check timeout: Update status to 'error'
- All failures logged with full context

**Testing**:
- Test successful dedicated server provisioning
- Test CephFS directory creation
- Test Docker service creation
- Test health check wait
- Test failure scenarios
- Verify resource allocation
- Verify isolation from other servers

**Acceptance Criteria**:
- Dedicated server created successfully
- Only one database can be hosted (enforced by max_instances=1)
- Resources are dedicated (4 CPU, 8GB RAM)
- CephFS path is isolated
- Health check passes before returning
- Database record accurately reflects state

---

**Method: `get_db_server_by_id()`**

**Purpose**: Retrieves a database server by its UUID.

**Parameters**: `server_id` (UUID string)

**Returns**: DBServer object or None if not found

**Use Case**: Looking up server details for instance operations

---

**Method: `get_all_db_servers()`**

**Purpose**: Lists all database servers with optional status filtering.

**Parameters**: `status` (optional string)

**Returns**: List of DBServer objects

**Use Case**: Admin dashboard, monitoring, capacity planning

---

**Method: `get_pool_statistics()`**

**Purpose**: Aggregates statistics about database pools for monitoring and reporting.

**Returns**: Dictionary containing:
- `by_status`: Array of {status, count, total_instances, total_capacity}
- `total_pools`: Total number of servers
- `active_pools`: Number of active servers

**Use Case**: Dashboard metrics, capacity planning, alerting

---

### Stage 2.2: API Endpoints (Allocation)

**What It Does**:
Exposes HTTP REST API endpoints for database allocation. These are called by instance-service.

**File**: `app/routes/allocation.py`

---

**Endpoint: `POST /api/database/allocate`**

**Purpose**: Main allocation endpoint called by instance-service when creating a new Odoo instance.

**Request Body**:
```
{
    "instance_id": "uuid",
    "customer_id": "uuid",
    "plan_tier": "standard" | "premium" | etc.
}
```

**Process Flow**:
1. Validates request body (required fields present)
2. Creates DatabaseAllocationService instance
3. Calls `allocate_database_for_instance()`
4. Checks return value:
   - If allocation object returned: SUCCESS
   - If None returned: PROVISIONING NEEDED
5. Returns appropriate response

**Response (Success - Pool Found)**:
```
{
    "status": "allocated",
    "db_server_id": "uuid",
    "db_host": "postgres-pool-1",
    "db_port": 5432,
    "db_name": "odoo_customer123_abc456",
    "db_user": "odoo_customer123_abc456_user",
    "db_password": "generated_password"
}
```

**Response (Provisioning Needed - No Pool)**:
```
{
    "status": "provisioning",
    "message": "No pools available, provisioning new pool",
    "retry_after": 30
}
```

**HTTP Status Codes**:
- 200 OK: Allocation successful or provisioning initiated
- 400 Bad Request: Invalid request body
- 500 Internal Server Error: Allocation logic failed

**Dependencies**:
- DatabaseAllocationService
- FastAPI request validation
- Database session management

**Error Handling**:
- Validation errors: Return 400 with details
- Database errors: Return 500, log stack trace
- Service errors: Return 500 with safe message

**Authentication**: None currently (internal service-to-service call)
**Future**: Add API key authentication

**Testing**:
- Test successful allocation (pool exists)
- Test provisioning response (no pools)
- Test invalid request body
- Test database errors
- Test concurrent requests
- Load testing for performance

**Acceptance Criteria**:
- Returns correct response for each scenario
- HTTP status codes are appropriate
- Response time < 500ms (when pool exists)
- Handles errors gracefully
- Logs all requests for audit

---

**Endpoint: `POST /api/database/provision-dedicated`**

**Purpose**: Provisions a dedicated PostgreSQL server for premium customers. Called during plan upgrades.

**Request Body**:
```
{
    "instance_id": "uuid",
    "customer_id": "uuid",
    "plan_tier": "premium"
}
```

**Process Flow**:
1. Validates premium/enterprise plan requirement
2. Calls `provision_dedicated_db_for_instance()`
3. Waits for provisioning to complete (this endpoint blocks)
4. Returns dedicated server details

**Response (Success)**:
```
{
    "status": "provisioned",
    "db_server_id": "uuid",
    "db_host": "postgres-dedicated-abc123",
    "message": "Dedicated server provisioned successfully"
}
```

**Timing**: Takes 2-3 minutes (blocks until complete)

**HTTP Status Codes**:
- 200 OK: Dedicated server provisioned
- 400 Bad Request: Plan doesn't support dedicated
- 500 Internal Server Error: Provisioning failed

**Note**: This is a long-running request. Consider implementing as async task in production.

---

### Stage 2.3: Admin API Endpoints

**What It Does**:
Provides administrative endpoints for monitoring, debugging, and managing database pools.

**File**: `app/routes/admin.py`

**Authentication**: Should require admin authentication (implement using API keys or JWT)

---

**Endpoint: `GET /api/database/admin/pools`**

**Purpose**: Lists all database pools with their current status and capacity.

**Query Parameters**:
- `status` (optional): Filter by status
- `server_type` (optional): Filter by type ('shared', 'dedicated')

**Response**:
```
{
    "pools": [
        {
            "id": "uuid",
            "name": "postgres-pool-1",
            "server_type": "shared",
            "status": "active",
            "health_status": "healthy",
            "current_instances": 35,
            "max_instances": 50,
            "capacity_percentage": 70.0,
            "created_at": "2025-01-01T00:00:00Z"
        },
        ...
    ],
    "total_count": 5
}
```

**Use Case**: Admin dashboard, monitoring, capacity planning

---

**Endpoint: `GET /api/database/admin/pools/{pool_id}`**

**Purpose**: Retrieves detailed information about a specific pool.

**Response**: Includes all pool details plus:
- Docker service information
- Recent health check results
- List of databases hosted on this pool
- Resource usage metrics

---

**Endpoint: `POST /api/database/admin/pools/{pool_id}/health-check`**

**Purpose**: Triggers an immediate health check on a specific pool.

**Process**:
1. Attempts to connect to PostgreSQL
2. Executes test query
3. Checks response time
4. Updates health_status in database
5. Returns result

**Use Case**: Manual health verification, debugging connection issues

---

**Endpoint: `GET /api/database/admin/stats`**

**Purpose**: Returns aggregated statistics about all database pools.

**Response**:
```
{
    "total_pools": 5,
    "active_pools": 4,
    "total_capacity": 250,
    "total_used": 123,
    "overall_utilization": 49.2,
    "by_status": {
        "active": 4,
        "full": 1,
        "error": 0
    },
    "by_type": {
        "shared": 4,
        "dedicated": 1
    }
}
```

**Use Case**: Dashboard overview, capacity planning alerts

---

**Testing for Admin Endpoints**:
- Test authentication (should reject unauthenticated requests)
- Test filtering and pagination
- Test detailed pool information retrieval
- Test manual health check triggers
- Test statistics accuracy

---

## STAGE 3: Asynchronous Provisioning

**Goal**: Implement Celery tasks for provisioning new pools in the background without blocking API requests.

**Duration Estimate**: Async task implementation

**Testing Strategy**: Celery task testing, integration with RabbitMQ, end-to-end provisioning tests

---

### Stage 3.1: Celery Configuration

**What It Does**:
Configures Celery for database-service with appropriate queues, routing, and worker settings.

**File**: `app/celery_config.py`

**Configuration Elements**:

**Broker**: RabbitMQ connection
- URL: `amqp://user:pass@rabbitmq:5672/saasodoo`
- Virtual host: `saasodoo`
- Heartbeat: 30 seconds

**Result Backend**: Redis
- URL: `redis://redis:6379/0`
- Result expiration: 24 hours

**Task Queues**:
- `database_provisioning`: High-priority provisioning tasks
- `database_monitoring`: Periodic health checks
- `database_maintenance`: Cleanup and optimization tasks

**Task Routing**:
- All `provision_*` tasks → `database_provisioning` queue
- All `health_check_*` tasks → `database_monitoring` queue
- All `cleanup_*` tasks → `database_maintenance` queue

**Worker Settings**:
- Concurrency: 2 (database provisioning is I/O-bound, not CPU-bound)
- Task time limit: 600 seconds (10 minutes) soft, 720 seconds (12 minutes) hard
- Task acknowledgment: Late (acks_late=True for reliability)
- Prefetch multiplier: 1 (process one provisioning task at a time)

**Retry Policy**:
- Max retries: 3 for provisioning tasks
- Retry backoff: Exponential (2^retry seconds)
- Retry errors: Docker API errors, connection timeouts

**Periodic Tasks (Celery Beat)**:
- Health check all pools: Every 5 minutes
- Cleanup failed pools: Daily at 2 AM
- Capacity reporting: Every hour

**Dependencies**:
- Celery library
- RabbitMQ broker
- Redis backend
- Shared database session

**Testing**:
- Test worker starts and connects
- Test task routing to correct queues
- Test retry mechanisms
- Test periodic task scheduling
- Test task result storage

---

### Stage 3.2: Pool Provisioning Task

**What It Does**:
Celery task that provisions a new shared PostgreSQL pool. Runs in background, can take 2-3 minutes.

**Task**: `provision_database_pool()`

**Parameters**: None (provisions next sequential pool)

**Process Flow**:

**Step 1: Preparation**
- Queries database to get next pool number (count existing + 1)
- Generates pool name: `postgres-pool-{number}`
- Defines CephFS storage path: `/mnt/cephfs/postgres_pools/pool-{number}`
- Logs provisioning start with all details

**Step 2: CephFS Directory Setup**
- Creates base directory on CephFS with mode 0o755
- Creates `data` subdirectory
- Sets ownership to postgres user (UID 999, GID 999)
- Logs directory creation success
- If fails: Logs error, raises exception (task will retry)

**Step 3: Credential Generation**
- Generates secure admin password (32 characters, URL-safe)
- Future: Store in Infisical instead of environment

**Step 4: Database Record Creation**
- Creates DBServer record:
  - name: Pool name
  - host: Pool name (Docker DNS)
  - server_type: 'shared'
  - max_instances: 50 (from config)
  - current_instances: 0
  - status: 'provisioning'
  - storage_path: CephFS path
  - postgres_version: "16"
  - postgres_image: "postgres:16-alpine"
- Commits to database
- Logs record creation

**Step 5: Docker Service Creation**
- Calls `docker_client.create_postgres_pool_service()`:
  - Pool name
  - Admin password
  - Storage path (CephFS mount)
  - Resources: 2 CPU, 4GB RAM
  - Max instances: 50
  - Node placement: role=database
- Receives service_id from Docker
- Updates DBServer record with:
  - swarm_service_id: Returned service ID
  - status: 'initializing'
- Commits changes
- Logs service creation success
- If fails: Updates status to 'error', logs, raises

**Step 6: Health Check Wait**
- Calls `docker_client.wait_for_service_ready()`:
  - service_id from previous step
  - timeout: 180 seconds (3 minutes)
  - check_interval: 10 seconds
- Polls every 10 seconds for service health
- Checks task state and health status
- Logs progress at each check

**Step 7: Finalization**
- If health check passes:
  - Updates status: 'active'
  - Updates health_status: 'healthy'
  - Logs successful provisioning
  - Returns DBServer.id
- If health check fails:
  - Updates status: 'error'
  - Updates health_status: 'unhealthy'
  - Logs failure with details
  - Raises exception (may retry if configured)

**Step 8: Notification** (Future)
- Send notification to admin dashboard
- Trigger webhook for instance-service
- Update metrics/monitoring

**Error Handling**:
- CephFS errors: Retry up to 3 times (may be temporary mount issue)
- Docker errors: Retry if transient, fail if permanent
- Database errors: Retry for connection issues, fail for constraint violations
- Always logs full error context
- Updates status to 'error' before raising

**Retry Logic**:
- Automatic retry on: Connection timeouts, Docker API transient errors
- Max retries: 3
- Backoff: 4, 16, 64 seconds (exponential)
- No retry on: Invalid configuration, CephFS permission errors

**Monitoring**:
- Logs at each major step
- Records timing for performance tracking
- Updates database status for UI visibility
- Stores error messages in metadata field

**Dependencies**:
- DockerClientWrapper for service creation
- CephFS mounted on worker node
- Database access for record updates
- RabbitMQ for task queue

**Testing**:
- Test successful provisioning end-to-end
- Test CephFS directory creation
- Test Docker service creation
- Test health check wait
- Test retry on transient failures
- Test permanent failure handling
- Test concurrent provisioning (should handle safely)
- Measure timing (should complete in 2-3 minutes)

**Acceptance Criteria**:
- Pool created and healthy within 3 minutes
- CephFS directory exists with correct permissions
- Docker service running and responding to health checks
- Database record accurate reflects state
- Errors are logged comprehensively
- Retries work on transient failures

---

### Stage 3.3: Health Monitoring Task

**What It Does**:
Periodic Celery task that checks health of all active database pools. Runs every 5 minutes via Celery Beat.

**Task**: `health_check_db_pools()`

**Trigger**: Celery Beat schedule (every 5 minutes)

**Parameters**: None (checks all active pools)

**Process Flow**:

**Step 1: Query Active Pools**
- Queries database for all pools where:
  - status IN ('active', 'full', 'initializing')
  - Excludes 'error', 'deprovisioning', 'maintenance'
- Orders by last_health_check ASC (check oldest first)
- Logs number of pools to check

**Step 2: Iterate Through Pools**
For each pool:

**Step 2a: Connection Test**
- Attempts to connect to PostgreSQL:
  - Host: db_server.host
  - Port: db_server.port
  - User: admin_user
  - Password: From Infisical/env
  - Database: 'postgres'
- Timeout: 5 seconds
- Logs connection attempt

**Step 2b: Query Test**
- Executes simple query: `SELECT 1`
- Measures response time
- Verifies result is correct

**Step 2c: Version Check**
- Executes: `SELECT version()`
- Verifies PostgreSQL version matches db_server.postgres_version
- Logs if version mismatch detected

**Step 2d: Database Count Verification**
- Queries: `SELECT count(*) FROM pg_database WHERE datname LIKE 'odoo_%'`
- Compares to db_server.current_instances
- Logs if mismatch (potential sync issue)

**Step 3: Update Health Status**
- If all checks pass:
  - health_status: 'healthy'
  - health_check_failures: 0 (reset counter)
  - last_health_check: NOW()
- If any check fails:
  - health_status: 'degraded' (if failures < 3)
  - health_status: 'unhealthy' (if failures >= 3)
  - health_check_failures: +1
  - last_health_check: NOW()
- Commits changes to database

**Step 4: Status Updates**
- If pool was 'initializing' and now healthy:
  - Change status to 'active'
  - Log promotion to active
- If pool failures >= 3 and status is 'active':
  - Change status to 'error'
  - Log status change
  - Trigger alert (future)

**Step 5: Summary Report**
- Logs overall health summary:
  - Total pools checked
  - Healthy count
  - Degraded count
  - Unhealthy count
  - Average response time
- Stores metrics for monitoring

**Error Handling**:
- Connection timeout: Mark as failed check, continue to next pool
- Query error: Mark as failed check, log details
- Database update error: Log error but don't fail entire task
- Never raises exception (allows task to complete for other pools)

**Recovery Actions**:
- If pool becomes unhealthy:
  - Stop allocating new databases to it
  - Existing databases continue to work
  - Admin notified (future)
  - Automatic remediation (future: restart service)

**Metrics Collected**:
- Connection time per pool
- Query response time
- Database count accuracy
- Health check success rate
- Failure patterns

**Dependencies**:
- asyncpg for PostgreSQL connections
- Database session for updates
- Secrets manager for credentials

**Testing**:
- Test with all healthy pools
- Test with one unhealthy pool
- Test with connection timeouts
- Test with query failures
- Test failure counter increment
- Test status transitions
- Verify task doesn't fail if one pool errors

**Acceptance Criteria**:
- All pools checked within 30 seconds
- Health status accurately reflects state
- Failed pools marked appropriately
- Metrics are collected
- Task completes even if pools are down
- Database records updated atomically

---

### Stage 3.4: Cleanup Task

**What It Does**:
Periodic task that removes failed pools and cleans up orphaned resources. Runs daily at 2 AM.

**Task**: `cleanup_failed_pools()`

**Trigger**: Celery Beat schedule (daily at 2:00 AM)

**Process Flow**:

**Step 1: Identify Failed Pools**
- Queries database for pools where:
  - status = 'error'
  - last_health_check < 24 hours ago (not just temporarily down)
  - current_instances = 0 (no active databases)

**Step 2: Remove Docker Services**
- For each failed pool:
  - Calls `docker_client.remove_service(swarm_service_id)`
  - Verifies removal succeeded
  - Logs removal

**Step 3: Clean CephFS Directories**
- Checks if storage_path exists
- Verifies directory is empty or contains only PostgreSQL data
- Optionally archives data before deletion
- Removes directory: `shutil.rmtree(storage_path)`
- Logs cleanup

**Step 4: Update Database Records**
- Updates pool status to 'deprovisioned'
- Sets deleted_at timestamp
- Records deletion_reason: "automatic_cleanup_failed_pool"
- Or: Deletes record entirely (configurable)

**Step 5: Orphaned Service Cleanup**
- Queries Docker for services with label 'app=saasodoo' and 'component=database-pool'
- Cross-references with db_servers table
- Removes services not in database (orphaned)

**Dependencies**:
- Docker client
- CephFS access
- Database session

**Testing**:
- Test with failed pools
- Test with pools that have databases (should skip)
- Test Docker service removal
- Test CephFS cleanup
- Test orphaned service detection

---

## STAGE 4: Integration with Instance Service

**Goal**: Connect instance-service to database-service for seamless database allocation during instance creation.

**Duration Estimate**: Integration and testing

**Testing Strategy**: End-to-end instance creation tests, integration tests between services

---

### Stage 4.1: HTTP Client for Database Service

**What It Does**:
Creates a utility class in instance-service that communicates with database-service API.

**File**: `instance-service/app/utils/database_service_client.py`

**Class**: `DatabaseServiceClient`

**Purpose**: Abstracts HTTP communication with database-service, handles retries, timeouts, and error responses.

---

**Method: `allocate_database()`**

**Purpose**: Requests database allocation from database-service.

**Parameters**:
- `instance_id`: UUID of Odoo instance
- `customer_id`: UUID of customer
- `plan_tier`: Subscription plan level

**Process Flow**:
1. Constructs request payload
2. Makes POST request to `http://database-service:8005/api/database/allocate`
3. Sets timeout: 10 seconds (just for API call, not provisioning)
4. Parses JSON response
5. Returns response object

**Response Handling**:
- Status 200 + status='allocated': Returns database config dict
- Status 200 + status='provisioning': Returns None (caller handles retry)
- Status 400/500: Raises exception with error details

**Retry Logic**:
- Retries on: Connection errors, timeouts
- Max retries: 3
- Backoff: 1, 2, 4 seconds
- No retry on: 4xx client errors

**Error Handling**:
- Connection refused: Raises ServiceUnavailableError
- Timeout: Raises TimeoutError
- HTTP errors: Raises HTTPError with status code

**Dependencies**:
- httpx or requests library (async HTTP client)
- Environment variable: DATABASE_SERVICE_URL

**Testing**:
- Test successful allocation
- Test provisioning response
- Test connection errors
- Test timeout handling
- Test HTTP error codes
- Mock database-service responses

---

**Method: `provision_dedicated_server()`**

**Purpose**: Requests provisioning of dedicated database server for premium customers.

**Parameters**: Same as allocate_database

**Returns**: Dictionary with dedicated server details

**Timeout**: 300 seconds (5 minutes) - this is a long-running operation

**Note**: Blocks until dedicated server is provisioned. Consider making async in future.

---

**Method: `get_pool_status()`**

**Purpose**: Checks if a pool provisioning is complete.

**Parameters**: None

**Returns**: Status information about database pools

**Use Case**: Polling to check if provisioning finished

---

### Stage 4.2: Modified Instance Creation Flow

**What It Does**:
Updates instance-service to use database-service for allocation instead of hardcoded postgres2.

**File**: `instance-service/app/services/instance_service.py`

**Method: `create_instance()` - MODIFIED**

**Changes Made**:

**Before** (Old Logic):
- Hardcoded DB_HOST=postgres2
- Assumed postgres2 always available
- No capacity checking
- No allocation logic

**After** (New Logic):

**Step 1: Create Instance Record**
- Creates instance record in database
- Sets status: 'creating'
- Records customer_id, plan_tier
- Commits record

**Step 2: Request Database Allocation**
- Calls `database_service_client.allocate_database()`:
  - Passes instance_id, customer_id, plan_tier
  - Receives response or None

**Step 3: Handle Response**

**Case A: Database Allocated Immediately**
- Response contains db_config (pool exists with capacity)
- Updates instance record:
  - db_server_id: From response
  - db_host: From response
  - db_port: From response
  - db_name: From response
- Proceeds immediately to Step 5 (Odoo provisioning)

**Case B: Provisioning Needed**
- Response is None (no pools available)
- Updates instance status: 'waiting_for_database'
- Queues Celery task: `wait_for_database_and_provision.delay(instance_id)`
- Returns to user with status 'waiting_for_database'
- User sees: "Provisioning database infrastructure, please wait..."

**Step 4: Wait for Provisioning** (Case B only)
- Celery task polls database-service every 10 seconds
- Calls `allocate_database()` repeatedly
- Maximum wait time: 5 minutes (30 attempts × 10 seconds)
- Once pool ready, receives db_config
- Updates instance record with db details
- Proceeds to Odoo provisioning

**Step 5: Queue Odoo Provisioning**
- Queues Celery task: `provision_odoo_instance.delay()`:
  - Passes instance_id
  - Passes db_config (host, name, credentials)
- Task creates Docker Swarm service for Odoo
- Environment variables now use dynamic values:
  - DB_HOST: db_config['db_host']
  - DB_NAME: db_config['db_name']
  - DB_USER: db_config['db_user']
  - DB_PASSWORD: db_config['db_password']

**Step 6: Return Response**
- Returns instance object to caller
- Status depends on path taken:
  - 'provisioning' if pool existed (fast path)
  - 'waiting_for_database' if pool being created (slow path)

**Error Handling**:
- Database service unavailable: Retry 3 times, then fail
- Database allocation fails: Mark instance as 'error'
- Provisioning timeout: Mark instance 'error', notify user
- All errors logged with full context

**Dependencies**:
- DatabaseServiceClient for API calls
- Modified Celery tasks for waiting
- Updated Odoo provisioning task for dynamic DB config

**Testing**:
- Test with available pool (fast path)
- Test with no pools (slow path)
- Test database service unavailable
- Test allocation failures
- Test provisioning timeout
- Test end-to-end instance creation
- Load test with multiple concurrent creations

**Acceptance Criteria**:
- Instance creation succeeds in both scenarios
- Database details correctly stored
- Odoo connects to correct database
- User receives appropriate status updates
- Errors handled gracefully

---

### Stage 4.3: Celery Task Updates

**What It Does**:
Updates instance-service Celery tasks to handle dynamic database allocation and waiting.

**New Task**: `wait_for_database_and_provision()`

**Purpose**: Handles the waiting period when database pool is being provisioned.

**Parameters**: `instance_id` (UUID)

**Process Flow**:
1. Retrieves instance record from database
2. Enters polling loop:
   - Calls `database_service_client.allocate_database()`
   - If allocation succeeds: Exit loop
   - If still provisioning: Sleep 10 seconds, retry
   - Max attempts: 30 (5 minutes total)
3. Updates instance record with db_config
4. Queues `provision_odoo_instance.delay()` to continue
5. If timeout: Updates instance status to 'error'

**Modified Task**: `provision_odoo_instance()` - UPDATED

**Changes**:
- Accepts `db_config` parameter (instead of assuming postgres2)
- Uses dynamic environment variables:
  - DB_HOST from db_config
  - DB_NAME from db_config
  - DB_USER from db_config
  - DB_PASSWORD from db_config
- Everything else remains the same (Odoo container creation logic)

**Dependencies**:
- DatabaseServiceClient
- Original Docker provisioning logic
- Database access for instance updates

**Testing**:
- Test wait loop with mock responses
- Test timeout handling
- Test successful allocation after wait
- Test Odoo provisioning with dynamic config
- Verify environment variables set correctly

---

## STAGE 5: Plan Upgrade & Migration

**Goal**: Enable customers to upgrade from Standard (shared DB) to Premium (dedicated DB) plans with automatic database migration.

**Duration Estimate**: Migration system

**Testing Strategy**: Test migrations with real data, verify zero data loss, measure downtime

---

### Stage 5.1: Upgrade Detection & Triggering

**What It Does**:
Detects plan upgrades in billing-service and triggers database migration in instance-service.

**Location**: `billing-service/app/services/subscription_service.py`

**Modified Method**: `handle_subscription_change()` - UPDATED

**Changes Made**:

**Step 1: Detect Upgrade Type**
- Compares old_plan to new_plan
- Determines if upgrade requires database migration:
  - Standard → Premium: YES (shared to dedicated)
  - Professional → Enterprise: YES (shared to dedicated)
  - Free → Standard: NO (both use shared)
- Checks plan configuration: `plan.requires_dedicated_db`

**Step 2: Trigger Migration if Needed**
- If migration required:
  - Calls instance-service API: `POST /api/instance/{id}/upgrade-plan`
  - Passes old_plan, new_plan, requires_dedicated_db=True
  - Receives acknowledgment
- If no migration required:
  - Just updates billing records
  - Continues normal flow

**Step 3: User Notification**
- Sends email: "Your plan upgrade is processing, database migration in progress"
- Estimates downtime: "5-15 minutes of maintenance"
- Provides status page link

**Dependencies**:
- Instance-service HTTP client
- Plan configuration database
- Email notification service

**Testing**:
- Test Standard → Premium upgrade detection
- Test upgrades that don't need migration
- Test notification sending
- Test instance-service API call

---

### Stage 5.2: Database Migration Task

**What It Does**:
Performs the actual database migration from shared pool to dedicated server. This is complex and critical.

**Location**: `instance-service/app/tasks/migration_tasks.py`

**New Task**: `migrate_to_dedicated_db()`

**Parameters**:
- `instance_id`: UUID of instance being upgraded
- `customer_id`: UUID of customer
- `old_plan`: Previous plan tier
- `new_plan`: New plan tier

**Process Flow**:

---

**Phase 1: Preparation**

**Step 1: Validate Migration**
- Retrieves instance record
- Verifies current DB is on shared pool
- Checks new plan requires dedicated
- Validates instance is in 'running' state
- Logs migration start

**Step 2: Update Status**
- Sets instance.status = 'migrating'
- Sets instance.migration_start_time = NOW()
- Commits database
- Sends notification to user

---

**Phase 2: Dedicated Server Provisioning**

**Step 3: Request Dedicated Server**
- Calls `database_service_client.provision_dedicated_server()`:
  - Passes instance_id, customer_id
  - This blocks for 2-3 minutes while server provisions
- Receives dedicated server details:
  - new_db_server_id
  - new_db_host
  - new_db_port
- Logs dedicated server ready

**Step 4: Create Database on Dedicated Server**
- Database-service already created the server
- Now need to create database on it
- Calls database-service: `POST /api/database/create-database`:
  - Passes new_db_server_id, db_name
  - Database-service creates empty database
- Receives new_db_credentials

---

**Phase 3: Data Migration**

**Step 5: Put Odoo in Maintenance Mode**
- Scales Odoo service to 0 replicas:
  - Calls `docker_client.stop_service(instance.service_name)`
  - Waits for service to stop (15 seconds max)
- Logs maintenance mode started
- USER DOWNTIME BEGINS HERE

**Step 6: Dump Old Database**
- Connects to old database (shared pool):
  - Host: instance.db_host (old)
  - Database: instance.db_name (old)
- Executes pg_dump:
  - Format: Custom (-Fc for compression)
  - Output: `/tmp/migration_{instance_id}.dump`
  - Includes: Schema + data
  - Options: --no-owner --no-acl (for security)
- Logs dump size and duration
- Typical time: 1-5 minutes depending on data size

**Step 7: Restore to New Database**
- Connects to new database (dedicated server):
  - Host: new_db_host
  - Database: new_db_name
- Executes pg_restore:
  - Input: `/tmp/migration_{instance_id}.dump`
  - Options: --no-owner --clean --if-exists
- Logs restore progress
- Typical time: 1-5 minutes

**Step 8: Verify Data Integrity**
- Connects to both old and new databases
- Compares row counts for critical tables:
  - res_partner (contacts)
  - res_users (users)
  - sale_order (sales)
  - account_move (invoices)
- Compares database sizes
- Verifies Odoo version compatibility
- If mismatch found: ABORT and rollback
- Logs verification results

---

**Phase 4: Reconfiguration**

**Step 9: Update Odoo Service Configuration**
- Retrieves Odoo service from Docker Swarm
- Updates environment variables:
  - DB_HOST: new_db_host (dedicated server)
  - DB_NAME: new_db_name (same name, different server)
  - DB_USER: new_db_user
  - DB_PASSWORD: new_db_password
- Calls `service.update(env={...})`
- Forces service update to apply changes

**Step 10: Restart Odoo Service**
- Scales service back to 1 replica
- Calls `docker_client.start_service(instance.service_name)`
- Waits for service to be healthy (60 seconds max)
- Calls Odoo health check endpoint
- Logs service restart success
- USER DOWNTIME ENDS HERE

**Step 11: Verify Odoo Connection**
- Attempts to connect to Odoo web UI
- Verifies login page loads
- Tests database connectivity from Odoo
- Logs connection test results

---

**Phase 5: Cleanup & Finalization**

**Step 12: Update Instance Record**
- Updates instance table:
  - db_server_id: new_db_server_id (dedicated)
  - db_host: new_db_host
  - db_port: new_db_port
  - requires_dedicated_db: True
  - status: 'running'
  - migration_completed_at: NOW()
- Commits changes

**Step 13: Update Pool Counters**
- Old shared pool:
  - Decrements current_instances by 1
  - If was 'full', changes to 'active'
- New dedicated server:
  - Increments current_instances to 1
  - Should already be 1 (max_instances=1 for dedicated)

**Step 14: Drop Old Database**
- Connects to old shared pool
- Terminates any remaining connections to old database
- Executes: DROP DATABASE "{old_db_name}"
- Executes: DROP USER "{old_db_user}"
- Frees up space on shared pool
- Logs cleanup success

**Step 15: Clean Temporary Files**
- Removes: `/tmp/migration_{instance_id}.dump`
- Removes any other temp files
- Logs cleanup

**Step 16: Send Completion Notification**
- Emails customer: "Migration complete, your instance is now on dedicated infrastructure"
- Includes: Total downtime (typically 5-15 minutes)
- Provides: New dedicated server details
- Links to: Status page showing successful migration

**Step 17: Record Migration Metrics**
- Logs metrics to monitoring:
  - Total migration time
  - Downtime duration
  - Database size
  - Data transfer time
  - Success/failure status
- Stores in migration_history table (if exists)

---

**Error Handling & Rollback**:

**Rollback Scenarios**:
1. Dedicated server provisioning fails
2. Database dump fails
3. Database restore fails
4. Data verification fails
5. Odoo restart fails

**Rollback Process**:
- Keep Odoo pointed to OLD database (still works)
- Remove newly created dedicated server (if provisioned)
- Update instance status: 'migration_failed'
- Record error details in instance.metadata
- Send notification: "Migration failed, your instance is still running on shared infrastructure"
- Admin can retry manually or investigate

**No Data Loss**:
- Old database remains untouched until final step (DROP)
- Only drop after verification succeeds
- Dump file kept temporarily in case manual recovery needed

---

**Dependencies**:
- DatabaseServiceClient for dedicated provisioning
- Docker client for Odoo service management
- pg_dump and pg_restore utilities
- asyncpg for database operations
- File system access for temp dumps

**Testing**:
- Test with small database (< 100 MB)
- Test with large database (> 1 GB)
- Test with active connections (should handle)
- Test rollback scenarios at each phase
- Measure downtime for different data sizes
- Test data integrity verification
- Test concurrent migrations (should handle safely)

**Acceptance Criteria**:
- Migration completes successfully
- Downtime < 15 minutes for databases < 1 GB
- Zero data loss
- Odoo connects to new database
- Old database cleaned up
- User notified appropriately
- Rollback works if migration fails
- Metrics captured for monitoring

---

### Stage 5.3: API Endpoint for Upgrade

**What It Does**:
Provides HTTP endpoint in instance-service for triggering plan upgrades with migrations.

**Location**: `instance-service/app/routes/instances.py`

**New Endpoint**: `POST /api/instance/{instance_id}/upgrade-plan`

**Purpose**: Called by billing-service when customer upgrades plan to trigger database migration if needed.

**Request Body**:
```
{
    "old_plan": "standard",
    "new_plan": "premium",
    "requires_dedicated_db": true
}
```

**Process Flow**:
1. Validates instance exists
2. Validates instance is in runnable state (not already migrating)
3. Checks if migration required:
   - If requires_dedicated_db=True: Queue migration task
   - If False: Just update plan_tier, no migration
4. Queues `migrate_to_dedicated_db.delay(instance_id, ...)`
5. Returns acknowledgment immediately (doesn't wait)

**Response (Success)**:
```
{
    "status": "migration_queued",
    "instance_id": "uuid",
    "message": "Database migration initiated, estimated time 5-15 minutes",
    "estimated_completion": "2025-01-01T12:15:00Z"
}
```

**HTTP Status Codes**:
- 202 Accepted: Migration queued successfully
- 400 Bad Request: Invalid plan or instance not eligible
- 404 Not Found: Instance doesn't exist
- 409 Conflict: Instance already migrating
- 500 Internal Server Error: Failed to queue task

**Authentication**: Should verify request comes from billing-service (API key or JWT)

**Testing**:
- Test upgrade triggering
- Test invalid instance ID
- Test concurrent upgrade attempts
- Test request validation
- Integration test with billing-service

---

### Stage 5.4: Downgrade Handling (Optional)

**What It Does**:
Handles downgrades from Premium (dedicated) back to Standard (shared pool). Optional feature.

**Decision Point**: Do you want to allow downgrades?

**Option A: Block Downgrades**
- Simplest approach
- Return error: "Downgrades not supported, contact support"
- Requires manual intervention by admin
- Avoids complexity of reverse migration

**Option B: Allow Downgrades with Migration**
- Mirrors upgrade process in reverse
- Provisions or finds available shared pool
- Migrates database: dedicated → shared
- Updates instance configuration
- Removes dedicated server
- More complex, more user-friendly

**Recommendation**: Start with Option A (block), add Option B later if needed.

**If Implementing Option B**:
- New task: `migrate_to_shared_pool()`
- Similar process to upgrade migration
- Finds available shared pool (or provisions)
- Dumps dedicated database
- Restores to shared pool
- Updates configuration
- Removes dedicated server

---

## STAGE 6: Testing & Validation

**Goal**: Comprehensive testing of all components to ensure system works reliably in production.

**Duration Estimate**: Testing phase

**Testing Strategy**: Unit tests, integration tests, load tests, chaos engineering

---

### Stage 6.1: Unit Tests

**What It Does**:
Tests individual components in isolation with mocked dependencies.

**Test Files**:
- `tests/test_models.py`: DBServer model tests
- `tests/test_allocation_service.py`: Allocation logic tests
- `tests/test_docker_client.py`: Docker wrapper tests
- `tests/test_tasks.py`: Celery task tests

**Coverage Target**: > 80%

**Key Test Cases**:

**DBServer Model**:
- Test is_available() with various states
- Test increment/decrement instance counts
- Test capacity calculations
- Test state transitions (active → full → active)

**DatabaseAllocationService**:
- Test finding available pool
- Test when no pools available
- Test pool selection algorithm (priority, load balancing)
- Test database creation
- Test error handling

**Docker Client**:
- Mock Docker SDK
- Test service creation calls
- Test health check polling
- Test service removal
- Test error scenarios

**Celery Tasks**:
- Test provision_database_pool with mocks
- Test health check task
- Test migration task
- Test error handling and retries

---

### Stage 6.2: Integration Tests

**What It Does**:
Tests interactions between components with real dependencies (test database, test Docker).

**Test Environment**:
- Separate test database
- Docker Swarm test cluster (or Docker Compose)
- Test RabbitMQ and Redis
- Test CephFS mount (or local directory)

**Test Scenarios**:

**End-to-End Instance Creation**:
1. Call allocation API (no pools exist)
2. Verify provisioning response
3. Wait for pool provisioning
4. Call allocation API again
5. Verify database allocated
6. Verify database accessible
7. Create Odoo instance
8. Verify Odoo connects to database

**Pool Capacity Limits**:
1. Create pool with max_instances=3
2. Allocate 3 databases
3. Verify pool marked as 'full'
4. Attempt 4th allocation
5. Verify new pool provisioned

**Health Monitoring**:
1. Create healthy pool
2. Stop pool service
3. Run health check task
4. Verify pool marked unhealthy
5. Restart pool service
6. Run health check task
7. Verify pool marked healthy again

**Plan Upgrade Migration**:
1. Create instance on shared pool
2. Add test data to database
3. Trigger upgrade to premium
4. Wait for migration
5. Verify data migrated correctly
6. Verify Odoo works on dedicated server
7. Verify old database cleaned up

---

### Stage 6.3: Load Testing

**What It Does**:
Tests system behavior under heavy load to identify bottlenecks and ensure scalability.

**Tools**: Locust, JMeter, or custom scripts

**Test Scenarios**:

**Concurrent Instance Creations**:
- Simulate 50 concurrent instance creation requests
- Measure: Response times, success rate, database pool creation
- Verify: No race conditions, all instances get databases
- Target: < 5% failure rate

**Pool Provisioning Performance**:
- Create 10 pools sequentially
- Measure time per pool
- Verify: Consistent timing, no degradation
- Target: < 3 minutes per pool

**Health Check Scalability**:
- Create 100 database pools
- Run health check task
- Measure: Total time, memory usage
- Target: < 2 minutes for 100 pools

**API Throughput**:
- Send 1000 allocation requests/minute
- Measure: Response times, error rate
- Verify: System remains responsive
- Target: < 500ms p95 response time

---

### Stage 6.4: Chaos Engineering

**What It Does**:
Tests system resilience by deliberately causing failures.

**Failure Scenarios**:

**Docker Service Failures**:
- Kill PostgreSQL pool service mid-provisioning
- Verify: Task handles failure, updates status correctly
- Recovery: Admin can retry or system auto-retries

**Network Partitions**:
- Block network to database-service
- Verify: Instance-service handles timeout gracefully
- Recovery: Retries once network restored

**CephFS Mount Failures**:
- Unmount CephFS during provisioning
- Verify: Task fails with clear error message
- Recovery: Remount CephFS, retry provisioning

**Database Connection Failures**:
- Stop PostgreSQL during allocation
- Verify: Allocation fails gracefully, no corruption
- Recovery: System recovers once PostgreSQL restarted

**Celery Worker Crashes**:
- Kill worker during migration
- Verify: Task marked as failed, not stuck
- Recovery: Restart worker, admin can retry migration

---

## STAGE 7: Deployment & Monitoring

**Goal**: Deploy to production and set up monitoring/alerting.

**Duration Estimate**: Deployment and operational readiness

---

### Stage 7.1: Docker Compose Configuration

**What It Does**:
Updates docker-compose.ceph.yml with database-service and removes postgres2.

**Changes to Make**:

**Remove**:
- Entire `postgres2` service definition
- `POSTGRES2_*` environment variables from other services

**Add**:

**database-service**:
- Image: Built from services/database-service/
- Port: 8005
- Environment variables: DB connection, Docker socket, CephFS paths
- Volumes: Docker socket, CephFS mount
- Networks: saasodoo-network
- Deploy constraints: node.role == manager
- Traefik labels for API routing

**database-worker**:
- Same image as database-service
- Command: celery -A app.celery_config worker
- Queues: database_provisioning, database_monitoring
- Same volumes and environment as service
- No ports exposed
- Deploy: 1 replica on manager node

**Configuration**:
```yaml
services:
  database-service:
    image: registry.${BASE_DOMAIN}/database-service:latest
    environment:
      # Database
      POSTGRES_HOST: postgres
      POSTGRES_DB: instance
      DB_SERVICE_USER: instance_service
      DB_SERVICE_PASSWORD: ${POSTGRES_INSTANCE_SERVICE_PASSWORD}

      # Docker
      DOCKER_HOST: unix:///var/run/docker.sock

      # CephFS
      CEPHFS_MOUNT_PATH: /mnt/cephfs

      # Pool Configuration
      DB_POOL_MAX_INSTANCES: 50
      DB_POOL_CPU_LIMIT: 2
      DB_POOL_MEMORY_LIMIT: 4G

      # RabbitMQ
      RABBITMQ_HOST: rabbitmq

      # Redis
      REDIS_HOST: redis
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - /mnt/cephfs:/mnt/cephfs:rw
    networks:
      - saasodoo-network
    deploy:
      replicas: 1
      placement:
        constraints:
          - node.role == manager
      labels:
        - "traefik.enable=true"
        - "traefik.http.routers.database.rule=Host(`api.${BASE_DOMAIN}`) && PathPrefix(`/database`)"
        - "traefik.http.services.database.loadbalancer.server.port=8005"
```

---

### Stage 7.2: Node Labeling

**What It Does**:
Labels Docker Swarm nodes to indicate which can host database pools.

**Commands**:
```bash
# Label manager node (if it should host databases)
docker node update --label-add role=database <manager-node-id>

# Label worker nodes that can host databases
docker node update --label-add role=database <worker-1-id>
docker node update --label-add role=database <worker-2-id>

# Verify labels
docker node inspect <node-id> --format '{{.Spec.Labels}}'
```

**Requirements**:
- Nodes must have CephFS mounted at /mnt/cephfs
- Sufficient CPU and memory for PostgreSQL pools
- Reliable network connectivity

---

### Stage 7.3: CephFS Directory Structure

**What It Does**:
Prepares CephFS filesystem with proper directory structure.

**Commands**:
```bash
# Create base directories
mkdir -p /mnt/cephfs/postgres_pools
mkdir -p /mnt/cephfs/postgres_dedicated

# Set permissions
chmod 755 /mnt/cephfs/postgres_pools
chmod 755 /mnt/cephfs/postgres_dedicated

# Verify
ls -la /mnt/cephfs/
```

**Note**: Individual pool directories created automatically by provisioning task.

---

### Stage 7.4: Monitoring Setup

**What It Does**:
Sets up monitoring dashboards and alerts for database infrastructure.

**Metrics to Monitor**:

**Pool Health**:
- Number of active pools
- Number of unhealthy pools
- Total capacity vs used capacity
- Health check success rate

**Provisioning Performance**:
- Time to provision new pool (average, p95, p99)
- Provisioning success rate
- Provisioning failures by reason

**Allocation Performance**:
- Database allocation latency
- Allocation success rate
- Queue length for provisioning tasks

**Resource Usage**:
- CPU usage per pool
- Memory usage per pool
- Disk usage per pool
- Network I/O

**Migration Metrics**:
- Migrations in progress
- Migration success rate
- Average migration downtime
- Migration failures by reason

**Grafana Dashboards**:
- Database Infrastructure Overview
- Pool Capacity Planning
- Migration Status
- Health Check History

**Prometheus Queries**:
```
# Active pools
count(db_servers{status="active"})

# Capacity utilization
sum(db_servers_current_instances) / sum(db_servers_max_instances) * 100

# Unhealthy pools
count(db_servers{health_status="unhealthy"})
```

---

### Stage 7.5: Alerting Rules

**What It Does**:
Defines alerts for critical situations requiring admin intervention.

**Alert Conditions**:

**Critical Alerts** (Page immediately):
- All pools unhealthy
- Provisioning failing repeatedly (> 3 failures in 1 hour)
- Migration stuck (running > 1 hour)
- No available capacity (all pools full, provisioning failed)

**Warning Alerts** (Email/Slack):
- Capacity > 80% across all pools
- Pool unhealthy for > 15 minutes
- Provisioning slow (> 5 minutes)
- Health check failing for specific pool

**Info Alerts** (Log only):
- New pool provisioned
- Migration completed
- Pool capacity reached 50%

---

### Stage 7.6: Runbook Documentation

**What It Does**:
Documents operational procedures for common scenarios.

**Runbook Topics**:

**Provisioning New Pool**:
- When: Automatic or manual trigger
- How: API call or admin command
- Expected time: 2-3 minutes
- Troubleshooting: Check CephFS, Docker, node capacity

**Handling Unhealthy Pool**:
- Detection: Health check alerts
- Investigation: Check logs, service status
- Resolution: Restart service, check database
- Escalation: If restart doesn't help

**Manual Migration**:
- When: User requests or plan change
- Process: API call to trigger migration
- Monitoring: Watch task progress
- Rollback: If migration fails

**Emergency Procedures**:
- All pools down: Restart services, check network
- CephFS unavailable: Check Ceph cluster health
- Database corruption: Restore from backup

---

## STAGE 8: Production Rollout

**Goal**: Safely deploy to production with gradual rollout and rollback capability.

---

### Stage 8.1: Deployment Strategy

**Phased Rollout**:

**Phase 1: Deploy Infrastructure** (No traffic)
- Deploy database-service and worker
- Deploy with 0 replicas initially
- Verify services start correctly
- No impact on existing instances

**Phase 2: Migrate Platform Database**
- Run database migrations (add db_servers table)
- Verify schema changes applied
- Test queries on new tables
- Keep postgres2 running (fallback)

**Phase 3: Create First Pool** (Manual)
- Manually provision first shared pool
- Verify pool becomes healthy
- Test database creation on pool
- Keep postgres2 as fallback

**Phase 4: Enable for New Instances** (Gradual)
- Scale database-service to 1 replica
- Configure instance-service to try database-service first, fallback to postgres2
- Monitor first 10 new instances
- If issues: Disable and rollback

**Phase 5: Migrate Existing Instances** (Optional)
- Plan migration of existing instances from postgres2 to pools
- Migrate in batches (10 at a time)
- Monitor for issues after each batch
- Can take weeks to complete

**Phase 6: Decommission postgres2** (Final)
- Once all instances migrated
- Remove postgres2 from docker-compose
- Archive postgres2 data
- Complete!

---

### Stage 8.2: Rollback Plan

**If Issues Detected**:

**Level 1: Disable New Allocations**
- Scale database-service to 0 replicas
- All new instances use postgres2 (existing code path)
- Existing pools continue running
- No data loss

**Level 2: Rollback Database Schema**
- Run rollback migration (drop db_servers table)
- Remove foreign keys from instances
- Return to previous schema

**Level 3: Full Rollback**
- Remove database-service containers
- Restore docker-compose to previous version
- All instances back on postgres2
- Requires deployment

**Rollback Triggers**:
- Provisioning failure rate > 10%
- Health check failures > 20%
- User-reported database connection issues
- Migration failures > 5%

---

## STAGE 9: Documentation & Training

**Goal**: Document the system for future maintainers and operational staff.

---

### Stage 9.1: Architecture Documentation

**Documents to Create**:

**System Architecture**:
- Component diagram
- Data flow diagrams
- Deployment architecture
- Network topology

**Database Schema**:
- ERD diagrams
- Table descriptions
- Index explanations
- Relationship mappings

**API Documentation**:
- OpenAPI/Swagger specs
- Authentication requirements
- Rate limits
- Example requests/responses

**Operational Procedures**:
- Deployment guide
- Monitoring guide
- Troubleshooting guide
- Runbook procedures

---

### Stage 9.2: Code Documentation

**Docstring Standards**:
- All classes: Purpose, responsibilities, dependencies
- All methods: Parameters, return values, side effects, error handling
- Complex algorithms: Explanation of logic
- Configuration: Available options and defaults

**README Files**:
- services/database-service/README.md: Setup, development, testing
- docs/ARCHITECTURE.md: Overall system design
- docs/DEPLOYMENT.md: Production deployment guide
- docs/TROUBLESHOOTING.md: Common issues and solutions

---

## Summary

This implementation plan provides a comprehensive, staged approach to implementing dynamic database allocation with both shared pools and dedicated servers. Each stage is:

✅ **Testable**: Clear acceptance criteria and testing strategy
✅ **Incremental**: Can be developed and deployed one stage at a time
✅ **Reversible**: Rollback plans for each stage
✅ **Monitorable**: Metrics and logging at each step
✅ **Documented**: Clear explanations without implementation details

The plan enables:
- Automatic scaling of database infrastructure
- Support for multiple subscription tiers
- Seamless upgrades from shared to dedicated databases
- Operational monitoring and alerting
- Production-ready deployment strategy

**Estimated Total Timeline**: 4-6 weeks for complete implementation and testing.
