from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.config import settings
from app.db.database import admin_db
from app.api import auth, admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management"""
    # Startup
    print(f"Starting {settings.app_name}...")
    await admin_db.initialize()
    yield
    # Shutdown
    print(f"Shutting down {settings.app_name}...")
    await admin_db.close()


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(admin.router)


@app.get("/health")
async def health_check():
    """Health check endpoint for Kubernetes probes"""
    db_status = "connected" if admin_db.pool else "disconnected"
    return {
        "status": "healthy",
        "service": "admin-service",
        "database": db_status
    }


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "SaaSOdoo Admin Service API",
        "version": "1.0.0",
        "docs": "/docs"
    }
