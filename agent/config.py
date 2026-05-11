import json
from pathlib import Path

from pydantic import BaseModel, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class McpServerConfig(BaseModel):
    name: str
    transport: str = "stdio"
    command: str | None = None
    args: list[str] = []
    url: str | None = None
    env: dict[str, str] = {}


class LLMConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NOESIS_LLM_", env_file=".env", extra="ignore",
    )
    provider: str = "openai"
    model: str = "gpt-4o"
    api_key: str = ""
    base_url: str = ""
    max_tokens: int = 4096
    temperature: float = 0.0


class Neo4jConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NOESIS_NEO4J_", env_file=".env", extra="ignore",
    )
    uri: str = "bolt://localhost:7687"
    user: str = "neo4j"
    password: str = "noesis123"


class PlatformConfig(BaseSettings):
    """Per-platform enable/disable + credentials. All from .env."""
    model_config = SettingsConfigDict(
        env_prefix="NOESIS_PLATFORM_", env_file=".env", extra="ignore",
    )
    # Web UI (always on via uvicorn)
    web_enabled: bool = True
    # WeChat — direct iLink API (QR login, no external deps)
    wechat_enabled: bool = False
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
        env_prefix="NOESIS_", env_file=".env", extra="ignore",
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
    web_host: str = "127.0.0.1"
    web_port: int = 8000
    mcp_servers: list[McpServerConfig] = []

    @model_validator(mode="after")
    def _load_mcp_json(self):
        """Load MCP server config from mcp.json if present.

        mcp.json takes precedence over the NOESIS_MCP_SERVERS env var,
        making it easier to manage multi-server configurations.
        For Docker, mount mcp.json as a volume.
        """
        mcp_path = Path("mcp.json")
        if not mcp_path.exists():
            return self
        try:
            data = json.loads(mcp_path.read_text(encoding="utf-8"))
            servers = data.get("servers", [])
            if servers:
                self.mcp_servers = [McpServerConfig(**s) for s in servers]
                print(f"[Config] Loaded {len(servers)} MCP servers from mcp.json")
        except Exception as e:
            print(f"[Config] Failed to load mcp.json: {e}")
        return self
