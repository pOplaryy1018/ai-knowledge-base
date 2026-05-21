"""应用配置 ── 使用 pydantic-settings 从环境变量/.env 读取配置"""

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # ── 数据库 ──
    database_url: str = ""

    # ── Redis ──
    redis_url: str = ""

    # ── JWT ──
    jwt_secret_key: str = ""
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


settings = Settings()
