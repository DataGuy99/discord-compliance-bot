"""
Environment configuration with Pydantic validation.
Ensures all required environment variables are set at startup.
"""

import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


class Settings(BaseSettings):
    """
    Application settings with validation.

    All required environment variables must be set, or the application will fail at startup.
    """

    # Application
    ENVIRONMENT: str = Field(default="production", description="Environment: development, staging, production")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")

    # Database
    DATABASE_URL: str = Field(..., description="PostgreSQL connection URL")

    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379", description="Redis URL for rate limiting")
    REDIS_VECTOR_URL: str = Field(default="redis://localhost:6379/0", description="Redis URL for vector store")

    # xAI API
    XAI_API_KEY: str = Field(..., description="xAI API key for Grok-4")
    XAI_BASE_URL: str = Field(default="https://api.x.ai/v1", description="xAI API base URL")

    # Admin
    ADMIN_TOKEN: str = Field(..., description="Admin API token (required for security)")

    # CORS
    CORS_ORIGINS: str = Field(default="https://discord.com", description="Comma-separated CORS origins")

    # RAG
    EMBED_DIM: int = Field(default=384, description="Embedding dimension")

    # Discord (optional for Heroku API)
    DISCORD_BOT_TOKEN: Optional[str] = Field(None, description="Discord bot token")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment value"""
        allowed = ["development", "staging", "production", "test"]
        if v not in allowed:
            raise ValueError(f"ENVIRONMENT must be one of {allowed}")
        return v

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Convert postgres:// to postgresql+asyncpg:// for Heroku compatibility"""
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+asyncpg://", 1)
        return v

    @field_validator("CORS_ORIGINS")
    @classmethod
    def validate_cors_origins(cls, v: str) -> str:
        """Ensure CORS origins are properly formatted"""
        return v.strip()


# Global settings instance
settings = Settings()