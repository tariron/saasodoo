"""
Database Allocation Service
Core business logic for allocating PostgreSQL databases to Odoo instances
"""

import os
import secrets
import string
from typing import Optional, Dict, Any, List
from datetime import datetime
import asyncpg
import structlog
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.db_server import DBServer, ServerType, ServerStatus, HealthStatus, AllocationStrategy

logger = structlog.get_logger(__name__)


class DatabaseAllocationService:
    """Service for allocating databases to Odoo instances"""

    def __init__(self, db_session: Session):
        """
        Initialize allocation service

        Args:
            db_session: SQLAlchemy database session
        """
        self.db_session = db_session
        self.postgres_admin_user = os.getenv("POSTGRES_ADMIN_USER", "postgres")
        self.postgres_admin_password = os.getenv("POSTGRES_ADMIN_PASSWORD", "")

    def allocate_database_for_instance(
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
        db_server = self._find_available_shared_pool()

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
                   db_server=db_server.name,
                   db_name=db_name)

        # Create database on the selected server
        try:
            db_password = self._create_database_on_server(db_server, db_name)

            # Increment instance count and update allocation tracking
            db_server.increment_instance_count(self.db_session)

            logger.info("Database allocated successfully",
                       instance_id=instance_id,
                       db_server=db_server.name,
                       db_name=db_name,
                       capacity=f"{db_server.current_instances}/{db_server.max_instances}")

            return {
                "db_server_id": str(db_server.id),
                "db_host": db_server.host,
                "db_port": db_server.port,
                "db_name": db_name,
                "db_user": f"{db_name}_user",
                "db_password": db_password
            }

        except Exception as e:
            logger.error("Failed to create database",
                        instance_id=instance_id,
                        db_server=db_server.name,
                        error=str(e))
            raise

    def _find_available_shared_pool(self) -> Optional[DBServer]:
        """
        Find an available shared database pool

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
            DBServer if available pool found, None otherwise
        """
        try:
            stmt = (
                select(DBServer)
                .where(DBServer.server_type == ServerType.SHARED)
                .where(DBServer.status == ServerStatus.ACTIVE)
                .where(DBServer.health_status.in_([HealthStatus.HEALTHY, HealthStatus.UNKNOWN]))
                .where(DBServer.current_instances < DBServer.max_instances)
                .where(DBServer.allocation_strategy == AllocationStrategy.AUTO)
                .order_by(DBServer.priority.asc(), DBServer.current_instances.asc())
                .limit(1)
            )

            result = self.db_session.execute(stmt)
            db_server = result.scalar_one_or_none()

            if db_server:
                logger.info("Found available shared pool",
                           pool_name=db_server.name,
                           capacity=f"{db_server.current_instances}/{db_server.max_instances}",
                           priority=db_server.priority)
            else:
                logger.info("No available shared pools found")

            return db_server

        except Exception as e:
            logger.error("Error finding available pool", error=str(e))
            return None

    def _create_database_on_server(self, db_server: DBServer, db_name: str) -> str:
        """
        Create a PostgreSQL database and dedicated user on the specified server

        Args:
            db_server: Target database server
            db_name: Name of the database to create

        Returns:
            Generated password for the database user

        Raises:
            Exception: If database creation fails
        """
        import asyncio

        logger.info("Creating database on server",
                   db_server=db_server.name,
                   db_name=db_name)

        # Generate secure random password
        password = self._generate_password()
        db_user = f"{db_name}_user"

        # Run async database creation
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                self._async_create_database(
                    host=db_server.host,
                    port=db_server.port,
                    db_name=db_name,
                    db_user=db_user,
                    db_password=password
                )
            )
            return password
        finally:
            loop.close()

    async def _async_create_database(
        self,
        host: str,
        port: int,
        db_name: str,
        db_user: str,
        db_password: str
    ) -> None:
        """
        Asynchronously create database and user with privileges

        Args:
            host: PostgreSQL server hostname
            port: PostgreSQL server port
            db_name: Database name to create
            db_user: Database user to create
            db_password: Password for the user
        """
        # Connect to postgres default database as admin
        conn = await asyncpg.connect(
            host=host,
            port=port,
            user=self.postgres_admin_user,
            password=self.postgres_admin_password,
            database='postgres'
        )

        try:
            # Create database (cannot be in transaction)
            await conn.execute(f'CREATE DATABASE "{db_name}"')
            logger.info("Database created", db_name=db_name)

            # Create user with password
            await conn.execute(
                f"CREATE USER {db_user} WITH PASSWORD '{db_password}'"
            )
            logger.info("Database user created", db_user=db_user)

            # Grant all privileges on database
            await conn.execute(
                f'GRANT ALL PRIVILEGES ON DATABASE "{db_name}" TO {db_user}'
            )

        except asyncpg.exceptions.DuplicateDatabaseError:
            logger.warning("Database already exists", db_name=db_name)
            # Database exists, assume user exists too, just return password
        except Exception as e:
            logger.error("Failed to create database", db_name=db_name, error=str(e))
            raise
        finally:
            await conn.close()

        # Connect to new database to grant schema privileges
        conn = await asyncpg.connect(
            host=host,
            port=port,
            user=self.postgres_admin_user,
            password=self.postgres_admin_password,
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

    def get_db_server_by_id(self, server_id: str) -> Optional[DBServer]:
        """
        Get database server by ID

        Args:
            server_id: UUID of the server

        Returns:
            DBServer instance or None
        """
        try:
            stmt = select(DBServer).where(DBServer.id == server_id)
            result = self.db_session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error("Error fetching db_server", server_id=server_id, error=str(e))
            return None

    def get_all_db_servers(
        self,
        status: Optional[str] = None,
        server_type: Optional[str] = None
    ) -> List[DBServer]:
        """
        Get all database servers with optional filtering

        Args:
            status: Filter by status (optional)
            server_type: Filter by server type (optional)

        Returns:
            List of DBServer instances
        """
        try:
            stmt = select(DBServer)

            if status:
                stmt = stmt.where(DBServer.status == ServerStatus(status))
            if server_type:
                stmt = stmt.where(DBServer.server_type == ServerType(server_type))

            stmt = stmt.order_by(DBServer.created_at.desc())

            result = self.db_session.execute(stmt)
            return list(result.scalars().all())

        except Exception as e:
            logger.error("Error fetching db_servers", error=str(e))
            return []

    def get_pool_statistics(self) -> Dict[str, Any]:
        """
        Get aggregated statistics about database pools

        Returns:
            Dictionary with pool statistics
        """
        try:
            # Count by status
            status_stats = (
                self.db_session.query(
                    DBServer.status,
                    func.count(DBServer.id).label('count'),
                    func.sum(DBServer.current_instances).label('total_instances'),
                    func.sum(DBServer.max_instances).label('total_capacity')
                )
                .group_by(DBServer.status)
                .all()
            )

            # Total pools
            total_pools = self.db_session.query(func.count(DBServer.id)).scalar()

            # Active pools
            active_pools = (
                self.db_session.query(func.count(DBServer.id))
                .filter(DBServer.status == ServerStatus.ACTIVE)
                .scalar()
            )

            # Format results
            by_status = []
            for status, count, instances, capacity in status_stats:
                by_status.append({
                    'status': status.value if status else None,
                    'count': count or 0,
                    'total_instances': instances or 0,
                    'total_capacity': capacity or 0
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
