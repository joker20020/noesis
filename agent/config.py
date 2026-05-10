from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="INFOCAP_LLM_", env_file=".env", extra="ignore",
    )
    provider: str = "openai"
    model: str = "gpt-4o"
    api_key: str = ""
    base_url: str = ""
    max_tokens: int = 4096
    temperature: float = 0.0


class Neo4jConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="INFOCAP_NEO4J_", env_file=".env", extra="ignore",
    )
    uri: str = "bolt://localhost:7687"
    user: str = "neo4j"
    password: str = "infocap123"


class PlatformConfig(BaseSettings):
    """Per-platform enable/disable + credentials. All from .env."""
    model_config = SettingsConfigDict(
        env_prefix="INFOCAP_PLATFORM_", env_file=".env", extra="ignore",
    )
    # Web UI (always on via uvicorn)
    web_enabled: bool = True
    # WeChat — OpenClaw Gateway v3 protocol
    wechat_enabled: bool = False
    wechat_gateway_host: str = "127.0.0.1"
    wechat_gateway_port: int = 18789
    # QQ — Tencent official botpy SDK
    qq_enabled: bool = False
    qq_app_id: str = ""
    qq_app_secret: str = ""
    qq_allowed_users: str = ""
    # Telegram
    telegram_enabled: bool = False
    telegram_token: str = ""
    telegram_allowed_users: str = ""  # comma-separated user IDs
    # Discord — discord.py
    discord_enabled: bool = False
    discord_token: str = ""
    discord_channels: str = ""  # comma-separated channel IDs
    # Feishu — lark-oapi SDK
    feishu_enabled: bool = False
    feishu_app_id: str = ""
    feishu_app_secret: str = ""


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="INFOCAP_", env_file=".env", extra="ignore",
    )
    llm: LLMConfig = LLMConfig()
    neo4j: Neo4jConfig = Neo4jConfig()
    platform: PlatformConfig = PlatformConfig()
    context_budget_tokens: int = 30000
    workspace_dir: str = "./workspace"
    skills_dir: str = "./skills"
    archive_dir: str = "./archives"
    max_subagent_rounds: int = 20
    subconscious_idle_seconds: int = 300
    subconscious_timer_seconds: int = 1800
