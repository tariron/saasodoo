from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.admin_user import AdminUser
from app.utils.security import verify_password, create_access_token
from app.config import settings
from app.db.database import admin_db
import asyncpg


class AuthService:
    """Service for admin authentication"""

    @staticmethod
    async def authenticate_user(db: AsyncSession, email: str, password: str) -> Optional[AdminUser]:
        """Authenticate an admin user by email and password"""
        # Query for user
        result = await db.execute(
            select(AdminUser).where(
                AdminUser.email == email,
                AdminUser.is_active == True,
                AdminUser.deleted_at == None
            )
        )
        user = result.scalar_one_or_none()

        if not user:
            return None

        # Verify password
        if not verify_password(password, user.password_hash):
            return None

        # Update last login
        user.last_login_at = datetime.utcnow()
        await db.commit()
        await db.refresh(user)

        return user

    @staticmethod
    def create_tokens_for_user(user: AdminUser) -> Tuple[str, str]:
        """Create access and refresh tokens for user"""
        # Access token (15 minutes)
        access_token_data = {
            "sub": str(user.id),
            "email": user.email,
            "role": user.role,
            "type": "access"
        }
        access_token = create_access_token(
            access_token_data,
            timedelta(minutes=settings.admin_access_token_expire_minutes)
        )

        # Refresh token (7 days)
        refresh_token_data = {
            "sub": str(user.id),
            "email": user.email,
            "type": "refresh"
        }
        refresh_token = create_access_token(
            refresh_token_data,
            timedelta(days=settings.admin_refresh_token_expire_days)
        )

        return access_token, refresh_token

    @staticmethod
    async def create_session(user_id: str, access_token: str, refresh_token: str,
                            ip_address: Optional[str] = None, user_agent: Optional[str] = None) -> str:
        """Create session record in admin_sessions table"""
        pool = admin_db.get_pool()

        async with pool.acquire() as conn:
            session_id = await conn.fetchval(
                """
                INSERT INTO admin_sessions
                    (user_id, access_token, refresh_token, expires_at, ip_address, user_agent)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
                """,
                user_id,
                access_token,
                refresh_token,
                datetime.utcnow() + timedelta(days=settings.admin_refresh_token_expire_days),
                ip_address,
                user_agent
            )

            return str(session_id)
