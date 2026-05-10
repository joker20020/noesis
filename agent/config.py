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
    # QQ — NapCatQQ OneBot v11 reverse WebSocket
    qq_enabled: bool = False
    qq_host: str = "0.0.0.0"
    qq_port: int = 8080
    qq_napcat_http: str = "http://127.0.0.1:3000"
    # Telegram
    telegram_enabled: bool = False
    telegram_token: str = ""
    telegram_allowed_users: str = ""  # comma-separated user IDs
    # Discord
    discord_enabled: bool = False
    discord_token: str = ""
    discord_channels: str = ""  # comma-separated channel IDs


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
