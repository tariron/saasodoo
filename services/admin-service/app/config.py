from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    # App config
    app_name: str = "SaaSOdoo Admin Service"
    debug: bool = False
    log_level: str = "INFO"

    # Database - service-specific user pattern
    db_service_user: str = "admin_service"
    db_service_password: str
    postgres_host: str = "postgres-cluster-pooler-rw.saasodoo.svc.cluster.local"
    postgres_port: int = 5432
    db_name: str = "admin"
    db_pool_min_size: int = 5
    db_pool_max_size: int = 20

    # Redis (via Sentinel for sessions)
    redis_sentinel_enabled: bool = True
    redis_sentinel_host: str = "rfs-redis-cluster.saasodoo.svc.cluster.local"
    redis_sentinel_port: int = 26379
    redis_sentinel_master: str = "mymaster"
    redis_db: int = 2

    # JWT
    admin_jwt_secret: str
    admin_jwt_algorithm: str = "HS256"
    admin_access_token_expire_minutes: int = 15
    admin_refresh_token_expire_days: int = 7
    jwt_access_token_expires_minutes: int = 15  # Alias for auth service
    jwt_refresh_token_expires_days: int = 7     # Alias for auth service

    # Service URLs (Kubernetes DNS)
    user_service_url: str = "http://user-service.saasodoo.svc.cluster.local:8001"
    instance_service_url: str = "http://instance-service.saasodoo.svc.cluster.local:8003"
    billing_service_url: str = "http://billing-service.saasodoo.svc.cluster.local:8004"
    database_service_url: str = "http://database-service.saasodoo.svc.cluster.local:8005"

    # CORS
    cors_origins: list[str] = [
        "http://admin.109.199.108.243.nip.io",
        "https://admin.109.199.108.243.nip.io"
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False
    )

    @property
    def database_url(self) -> str:
        """Build PostgreSQL connection string"""
        if not self.db_service_password:
            raise ValueError(
                "DB_SERVICE_PASSWORD must be set. "
                "Admin service requires specific database credentials."
            )
        return (
            f"postgresql://{self.db_service_user}:{self.db_service_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.db_name}"
        )


settings = Settings()
