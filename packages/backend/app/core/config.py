"""应用配置 ── 使用 pydantic-settings 从环境变量/.env 读取配置"""

from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    """全局配置，自动从 .env 和环境变量加载"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── 应用 ──
    app_name: str = "AI 知识库管理平台"
    app_version: str = "0.0.1"
    debug: bool = True
    environment: Literal["development", "production", "test"] = "development"
    seed_admin_password: str = "devpassword"
    embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"
    embedding_cache_dir: str = "./models"
    model_preload: bool = False

    # ── 数据库 ──
    database_url: str = ""

    # ── Redis ──
    redis_url: str = ""

    # ── JWT ──
    jwt_secret_key: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60  # 1 小时
    jwt_refresh_token_expire_days: int = 7      # 7 天

    # ── CORS ──
    allowed_origins: list[str] = [
        "http://localhost:4173",
        "http://localhost:4174",
    ]

    # ── LLM ──
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"

    @model_validator(mode="after")
    def validate_production(self) -> Self:
        if self.environment == "production":
            if len(self.jwt_secret_key) < 32 or self.jwt_secret_key == "dev-secret-change-in-production":
                raise ValueError("Production requires a non-default JWT secret of at least 32 characters")
            if len(self.seed_admin_password) < 12 or self.seed_admin_password == "devpassword":
                raise ValueError("Production requires a non-default administrator password")
            password = make_url(self.database_url).password
            if not password or len(password) < 12 or password == "devpassword":
                raise ValueError("Production requires a non-default database password of at least 12 characters")
            self.debug = False
        return self


settings = Settings()
