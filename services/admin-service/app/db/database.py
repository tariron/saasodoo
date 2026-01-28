import asyncpg
from typing import Optional, AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.config import settings


class AdminDatabase:
    """Async PostgreSQL connection for admin database"""

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        self.engine = None
        self.async_session_maker = None

    async def initialize(self):
        """Create and test connection pool"""
        try:
            # Create asyncpg pool for health checks
            self.pool = await asyncpg.create_pool(
                dsn=settings.database_url,
                min_size=settings.db_pool_min_size,
                max_size=settings.db_pool_max_size,
            )

            # Test connection
            async with self.pool.acquire() as conn:
                result = await conn.fetchval('SELECT 1')
                if result != 1:
                    raise RuntimeError("Database health check failed")

            # Create SQLAlchemy async engine for ORM queries
            # Convert asyncpg:// to postgresql+asyncpg://
            sqlalchemy_url = settings.database_url.replace("postgresql://", "postgresql+asyncpg://")
            self.engine = create_async_engine(
                sqlalchemy_url,
                pool_size=settings.db_pool_min_size,
                max_overflow=settings.db_pool_max_size - settings.db_pool_min_size,
                echo=False
            )

            # Create session factory
            self.async_session_maker = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )

            print(f"✓ Admin database initialized (db={settings.db_name}, "
                  f"user={settings.db_service_user})")
        except Exception as e:
            print(f"✗ Failed to initialize admin database: {e}")
            raise

    async def close(self):
        """Close connection pool gracefully"""
        if self.pool:
            await self.pool.close()
            print("✓ Admin database pool closed")
        if self.engine:
            await self.engine.dispose()
            print("✓ SQLAlchemy engine disposed")

    def get_pool(self) -> asyncpg.Pool:
        """Get connection pool for health checks"""
        if not self.pool:
            raise RuntimeError("Database pool not initialized. Call initialize() first.")
        return self.pool


# Global singleton instance
admin_db = AdminDatabase()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for SQLAlchemy async sessions"""
    if not admin_db.async_session_maker:
        raise RuntimeError("Database not initialized. Call initialize() first.")

    async with admin_db.async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_db_pool() -> asyncpg.Pool:
    """FastAPI dependency for raw database pool (for health checks)"""
    return admin_db.get_pool()
