from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.db.database import get_db, admin_db
from app.models.schemas import LoginRequest, LoginResponse, AdminUserResponse
from app.services.auth_service import AuthService
from app.utils.security import decode_access_token

router = APIRouter(prefix="/admin/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(credentials: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Admin login endpoint"""
    user = await AuthService.authenticate_user(db, credentials.email, credentials.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create JWT tokens
    access_token, refresh_token = AuthService.create_tokens_for_user(user)

    # Create session in database
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    await AuthService.create_session(
        str(user.id),
        access_token,
        refresh_token,
        ip_address,
        user_agent
    )

    # Build response
    user_response = AdminUserResponse(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        last_login_at=user.last_login_at
    )

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user=user_response
    )


@router.post("/logout")
async def logout(authorization: Optional[str] = Header(None)):
    """Admin logout endpoint - revokes session"""
    if not authorization or not authorization.startswith("Bearer "):
        return {"message": "Logged out successfully"}

    token = authorization.replace("Bearer ", "")

    # Revoke session in database
    pool = admin_db.get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE admin_sessions
            SET revoked_at = NOW()
            WHERE access_token = $1 AND revoked_at IS NULL
            """,
            token
        )

    return {"message": "Logged out successfully"}


@router.get("/me", response_model=AdminUserResponse)
async def get_current_user(authorization: Optional[str] = Header(None)):
    """Get current admin user info from token"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
        )

    token = authorization.replace("Bearer ", "")

    # Decode token
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    # Get session from database to verify it's not revoked
    pool = admin_db.get_pool()
    async with pool.acquire() as conn:
        session = await conn.fetchrow(
            """
            SELECT s.id, s.revoked_at, u.id as user_id, u.email, u.full_name, u.role, u.last_login_at
            FROM admin_sessions s
            JOIN admin_users u ON s.user_id = u.id
            WHERE s.access_token = $1 AND u.is_active = true AND u.deleted_at IS NULL
            """,
            token
        )

        if not session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session not found",
            )

        if session['revoked_at']:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session has been revoked",
            )

    return AdminUserResponse(
        id=str(session['user_id']),
        email=session['email'],
        full_name=session['full_name'],
        role=session['role'],
        last_login_at=session['last_login_at']
    )
