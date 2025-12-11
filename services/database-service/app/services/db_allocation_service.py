"""
Database Allocation Service
Core business logic for allocating PostgreSQL databases to Odoo instances
"""

import os
import secrets
import string
from typing import Optional, Dict, Any, List
import asyncpg
import structlog

logger = structlog.get_logger(__name__)


class DatabaseAllocationService:
    """Service for allocating databases to Odoo instances using raw asyncpg"""

    def __init__(self, db_session: asyncpg.Connection):
        """
        Initialize allocation service

        Args:
            db_session: asyncpg Connection to platform database
        """
        self.db_session = db_session
        self.postgres_admin_user = os.getenv("POSTGRES_ADMIN_USER", "postgres")
        self.postgres_admin_password = os.getenv("POSTGRES_ADMIN_PASSWORD", "")

    async def allocate_database_for_instance(
        self,
        instance_id: str,
        customer_id: str,
        plan_tier: str,
        require_dedicated: Optional[bool] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Allocate a database for an Odoo instance

        Args:
            instance_id: UUID of the Odoo instance
            customer_id: UUID of the customer
            plan_tier: Subscription plan tier (free, starter, standard, professional, premium, enterprise)
            require_dedicated: Override flag for dedicated database requirement

        Returns:
            Dictionary with database configuration if allocated, None if provisioning needed

        Example return:
            {
                "db_server_id": "uuid",
                "db_host": "postgres-pool-1",
                "db_port": 5432,
                "db_name": "odoo_customer_abc_inst123",
                "db_user": "odoo_customer_abc_inst123_user",
                "db_password": "generated_password"
            }
        """
        logger.info("Database allocation requested",
                   instance_id=instance_id,
                   customer_id=customer_id,
                   plan_tier=plan_tier,
                   require_dedicated=require_dedicated)

        # Determine if dedicated database is required
        needs_dedicated = require_dedicated if require_dedicated is not None else \
            plan_tier.lower() in ('premium', 'enterprise')

        if needs_dedicated:
            logger.info("Dedicated database required - provisioning needed",
                       instance_id=instance_id,
                       plan_tier=plan_tier)
            # Caller must provision dedicated server first
            return None

        # Find available shared pool
        db_server = await self._find_available_shared_pool()

        if not db_server:
            logger.info("No available shared pools - provisioning needed",
                       instance_id=instance_id)
            return None

        # Generate database name
        # Format: odoo_{customer_id_sanitized}_{instance_id_first8}
        customer_id_clean = customer_id.replace('-', '')[:16]
        instance_id_short = instance_id.replace('-', '')[:8]
        db_name = f"odoo_{customer_id_clean}_{instance_id_short}"

        logger.info("Allocating database on shared pool",
                   instance_id=instance_id,
                   db_server=db_server['name'],
                   db_name=db_name)

        # Create database on the selected server
        try:
            db_password = await self._create_database_on_server(db_server, db_name)

            # Increment instance count in database
            await self.db_session.execute("""
                UPDATE db_servers
                SET current_instances = current_instances + 1,
                    updated_at = NOW()
                WHERE id = $1
            """, db_server['id'])

            logger.info("Database allocated successfully",
                       instance_id=instance_id,
                       db_server=db_server['name'],
                       db_name=db_name,
                       capacity=f"{db_server['current_instances'] + 1}/{db_server['max_instances']}")

            return {
                "db_server_id": str(db_server['id']),
                "db_host": db_server['host'],
                "db_port": db_server['port'],
                "db_name": db_name,
                "db_user": f"{db_name}_user",
                "db_password": db_password
            }

        except Exception as e:
            logger.error("Failed to create database",
                        instance_id=instance_id,
                        db_server=db_server['name'],
                        error=str(e))
            raise

    async def _find_available_shared_pool(self):
        """
        Find an available shared database pool using raw SQL

        Selection criteria (in order):
        1. server_type = 'shared'
        2. status = 'active'
        3. health_status IN ('healthy', 'unknown')
        4. current_instances < max_instances
        5. allocation_strategy = 'auto'

        Ordering:
        1. priority ASC (lower number = higher priority)
        2. current_instances ASC (prefer less-loaded pools)

        Returns:
            Database record dict if available pool found, None otherwise
        """
        try:
            query = """
                SELECT id, name, host, port, admin_user, admin_password,
                       server_type, status, health_status, current_instances,
                       max_instances, priority, allocation_strategy
                FROM db_servers
                WHERE server_type = 'shared'
                  AND status = 'active'
                  AND health_status IN ('healthy', 'unknown')
                  AND current_instances < max_instances
                  AND allocation_strategy = 'auto'
                ORDER BY priority ASC, current_instances ASC
                LIMIT 1
            """

            db_server = await self.db_session.fetchrow(query)

            if db_server:
                logger.info("Found available shared pool",
                           pool_name=db_server['name'],
                           capacity=f"{db_server['current_instances']}/{db_server['max_instances']}",
                           priority=db_server['priority'])
            else:
                logger.info("No available shared pools found")

            return db_server

        except Exception as e:
            logger.error("Error finding available pool", error=str(e))
            return None

    async def _create_database_on_server(self, db_server: dict, db_name: str) -> str:
        """
        Create a PostgreSQL database and dedicated user on the specified server

        Args:
            db_server: Target database server record (dict from asyncpg)
            db_name: Name of the database to create

        Returns:
            Generated password for the database user

        Raises:
            Exception: If database creation fails
        """
        logger.info("Creating database on server",
                   db_server=db_server['name'],
                   db_name=db_name)

        # Generate secure random password
        password = self._generate_password()
        db_user = f"{db_name}_user"

        # Create database asynchronously
        await self._async_create_database(
            host=db_server['host'],
            port=db_server['port'],
            admin_user=db_server['admin_user'],
            admin_password=db_server['admin_password'],
            db_name=db_name,
            db_user=db_user,
            db_password=password
        )

        return password

    async def _async_create_database(
        self,
        host: str,
        port: int,
        admin_user: str,
        admin_password: str,
        db_name: str,
        db_user: str,
        db_password: str
    ) -> None:
        """
        Asynchronously create database and user with privileges

        Args:
            host: PostgreSQL server hostname
            port: PostgreSQL server port
            admin_user: Admin username for the pool
            admin_password: Admin password for the pool
            db_name: Database name to create
            db_user: Database user to create
            db_password: Password for the user
        """
        # Connect to postgres default database as admin
        conn = await asyncpg.connect(
            host=host,
            port=port,
            user=admin_user,
            password=admin_password,
            database='postgres'
        )

        try:
            # Step 1: Create user first (must exist before we can assign as owner)
            try:
                await conn.execute(
                    f"CREATE USER {db_user} WITH PASSWORD '{db_password}'"
                )
                logger.info("Database user created", db_user=db_user)
            except asyncpg.exceptions.DuplicateObjectError:
                logger.warning("Database user already exists", db_user=db_user)
                # User exists, that's fine - continue with database creation

            # Step 2: Create database with owner (correct ownership from the start)
            try:
                await conn.execute(f'CREATE DATABASE "{db_name}" OWNER {db_user}')
                logger.info("Database created with owner", db_name=db_name, owner=db_user)
            except asyncpg.exceptions.DuplicateDatabaseError:
                logger.warning("Database already exists", db_name=db_name)
                # Database exists, that's fine - may need to fix ownership though

            # Step 3: Grant all privileges on database (defensive - ensures permissions even if created differently)
            await conn.execute(
                f'GRANT ALL PRIVILEGES ON DATABASE "{db_name}" TO {db_user}'
            )
            logger.info("Database privileges granted", db_user=db_user)

        except Exception as e:
            logger.error("Failed to create database/user", db_name=db_name, db_user=db_user, error=str(e))
            raise
        finally:
            await conn.close()

        # Connect to new database to grant schema privileges
        conn = await asyncpg.connect(
            host=host,
            port=port,
            user=admin_user,
            password=admin_password,
            database=db_name
        )

        try:
            # Grant privileges on public schema
            await conn.execute(f'GRANT ALL ON SCHEMA public TO {db_user}')
            await conn.execute(
                f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO {db_user}'
            )
            await conn.execute(
                f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO {db_user}'
            )
            logger.info("Database privileges granted", db_user=db_user)

        finally:
            await conn.close()

    def _generate_password(self, length: int = 32) -> str:
        """
        Generate a secure random password

        Args:
            length: Length of password to generate

        Returns:
            URL-safe random password
        """
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    async def get_db_server_by_id(self, server_id: str) -> Optional[Dict[str, Any]]:
        """
        Get database server by ID

        Args:
            server_id: UUID of the server

        Returns:
            Database server record as dict or None
        """
        try:
            query = """
                SELECT id, name, host, port, server_type, status, health_status,
                       current_instances, max_instances, storage_path, postgres_version,
                       postgres_image, cpu_limit, memory_limit, allocation_strategy,
                       priority, admin_user, admin_password, swarm_service_id,
                       swarm_service_name, dedicated_to_customer_id, dedicated_to_instance_id,
                       provisioned_by, provisioned_at, created_at, updated_at,
                       last_health_check, health_check_failures
                FROM db_servers
                WHERE id = $1
            """
            return await self.db_session.fetchrow(query, server_id)
        except Exception as e:
            logger.error("Error fetching db_server", server_id=server_id, error=str(e))
            return None

    async def get_all_db_servers(
        self,
        status: Optional[str] = None,
        server_type: Optional[str] = None
    ) -> list:
        """
        Get all database servers with optional filtering

        Args:
            status: Filter by status (optional)
            server_type: Filter by server type (optional)

        Returns:
            List of database server records as dicts
        """
        try:
            # Build query dynamically based on filters
            query = """
                SELECT id, name, host, port, server_type, status, health_status,
                       current_instances, max_instances, storage_path, postgres_version,
                       postgres_image, cpu_limit, memory_limit, allocation_strategy,
                       priority, created_at, updated_at, last_health_check
                FROM db_servers
                WHERE 1=1
            """
            params = []

            if status:
                params.append(status)
                query += f" AND status = ${len(params)}"

            if server_type:
                params.append(server_type)
                query += f" AND server_type = ${len(params)}"

            query += " ORDER BY created_at DESC"

            return await self.db_session.fetch(query, *params)

        except Exception as e:
            logger.error("Error fetching db_servers", error=str(e))
            return []

    async def get_pool_statistics(self) -> Dict[str, Any]:
        """
        Get aggregated statistics about database pools

        Returns:
            Dictionary with pool statistics
        """
        try:
            # Count by status
            status_stats_query = """
                SELECT status,
                       COUNT(id) as count,
                       COALESCE(SUM(current_instances), 0) as total_instances,
                       COALESCE(SUM(max_instances), 0) as total_capacity
                FROM db_servers
                GROUP BY status
            """
            status_stats = await self.db_session.fetch(status_stats_query)

            # Total pools
            total_pools_query = "SELECT COUNT(id) as count FROM db_servers"
            total_result = await self.db_session.fetchrow(total_pools_query)
            total_pools = total_result['count'] if total_result else 0

            # Active pools
            active_pools_query = "SELECT COUNT(id) as count FROM db_servers WHERE status = 'active'"
            active_result = await self.db_session.fetchrow(active_pools_query)
            active_pools = active_result['count'] if active_result else 0

            # Format results
            by_status = []
            for row in status_stats:
                by_status.append({
                    'status': row['status'],
                    'count': row['count'] or 0,
                    'total_instances': row['total_instances'] or 0,
                    'total_capacity': row['total_capacity'] or 0
                })

            return {
                'total_pools': total_pools or 0,
                'active_pools': active_pools or 0,
                'by_status': by_status
            }

        except Exception as e:
            logger.error("Error getting pool statistics", error=str(e))
            return {
                'total_pools': 0,
                'active_pools': 0,
                'by_status': []
            }
