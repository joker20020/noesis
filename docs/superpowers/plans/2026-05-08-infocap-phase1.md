# infoCap Phase 1: 核心骨架 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建单 Agent 最小可用闭环：消息入队 → L1路由 → LLM推理(OpenAI/DeepSeek) → 工具调度 → 压缩 → 响应，通过 Web UI 交互。

**Architecture:** 意识循环作为 asyncio 事件循环驱动，LLM 客户端抽象层统一 OpenAI 和 DeepSeek API，12 个原子工具通过统一调度器分发，四阶段压缩管道管理上下文预算，Neo4j 存储记忆节点，FastAPI + WebSocket 提供后端，Next.js 提供前端。

**Tech Stack:** Python 3.11+, Neo4j 5.x (Docker), FastAPI, Playwright, OpenAI SDK, httpx (DeepSeek), Next.js 14+, TypeScript

---

## File Structure

```
infoCap/
├── agent/
│   ├── __init__.py
│   ├── engine.py              # Agent Engine 主入口
│   ├── conscious.py           # 意识循环
│   ├── context.py             # 上下文组装
│   ├── compression.py         # 四阶段压缩管道
│   └── config.py              # 配置管理 (pydantic-settings)
├── llm/
│   ├── __init__.py
│   ├── base.py                # LLM 客户端抽象基类
│   ├── openai_client.py       # OpenAI 适配器
│   └── deepseek_client.py     # DeepSeek 适配器
├── tools/
│   ├── __init__.py
│   ├── dispatcher.py          # 统一工具调度器
│   ├── base.py                # 工具基类 + Schema 定义
│   ├── file_ops.py            # file_read / file_patch / file_write
│   ├── code_run.py            # 代码执行 (subprocess 沙箱)
│   ├── web_interact.py        # web_scan / web_execute_js (Playwright)
│   ├── memory_search.py       # Neo4j 图查询入口
│   ├── skill_manage.py        # Skill 生命周期管理
│   ├── checkpoint.py          # update_working_checkpoint
│   ├── long_term_update.py    # start_long_term_update
│   ├── ask_user.py            # 人工介入
│   └── subagent.py            # 子Agent委派
├── memory/
│   ├── __init__.py
│   ├── neo4j_client.py        # Neo4j Driver 封装
│   ├── graph_models.py        # 节点/关系定义 (dataclass)
│   ├── index.py               # L1 索引管理
│   └── lifecycle.py           # 记忆生命周期 (基础)
├── server/
│   ├── __init__.py
│   ├── main.py                # FastAPI 应用入口
│   ├── ws.py                  # WebSocket handler
│   └── api/
│       ├── __init__.py
│       └── chat.py            # Chat API 路由
├── webui/                     # Next.js 前端 (Task 15-16)
├── docker-compose.yml
├── pyproject.toml
└── tests/
    ├── test_llm/
    ├── test_tools/
    ├── test_memory/
    ├── test_agent/
    └── conftest.py
```

---

### Task 1: 项目骨架搭建

**Files:**
- Create: `pyproject.toml`
- Create: `docker-compose.yml`
- Create: `agent/config.py`
- Create: `agent/__init__.py`
- Create: `llm/__init__.py`
- Create: `tools/__init__.py`
- Create: `memory/__init__.py`
- Create: `server/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write pyproject.toml**

```toml
[project]
name = "infocap"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "neo4j>=5.20.0",
    "openai>=1.30.0",
    "httpx>=0.27.0",
    "pydantic>=2.7.0",
    "pydantic-settings>=2.3.0",
    "fastapi>=0.112.0",
    "uvicorn[standard]>=0.30.0",
    "playwright>=1.44.0",
    "numpy>=1.26.0",
    "shortuuid>=1.0.13",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.2.0",
    "pytest-asyncio>=0.23.0",
    "pytest-mock>=3.14.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Write docker-compose.yml**

```yaml
version: "3.9"
services:
  neo4j:
    image: neo4j:5.20-community
    ports:
      - "7474:7474"   # HTTP
      - "7687:7687"   # Bolt
    environment:
      NEO4J_AUTH: neo4j/infocap123
      NEO4J_PLUGINS: '["apoc", "graph-data-science"]'
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs

volumes:
  neo4j_data:
  neo4j_logs:
```

- [ ] **Step 3: Write agent/config.py**

```python
from pydantic_settings import BaseSettings


class LLMConfig(BaseSettings):
    model_config = {"env_prefix": "INFOCAP_LLM_"}
    provider: str = "openai"       # "openai" | "deepseek"
    model: str = "gpt-4o"
    api_key: str = ""
    base_url: str = ""
    max_tokens: int = 4096
    temperature: float = 0.0


class Neo4jConfig(BaseSettings):
    model_config = {"env_prefix": "INFOCAP_NEO4J_"}
    uri: str = "bolt://localhost:7687"
    user: str = "neo4j"
    password: str = "infocap123"


class Config(BaseSettings):
    model_config = {"env_prefix": "INFOCAP_"}
    llm: LLMConfig = LLMConfig()
    neo4j: Neo4jConfig = Neo4jConfig()
    context_budget_tokens: int = 30000
    workspace_dir: str = "./workspace"
    skills_dir: str = "./skills"
    archive_dir: str = "./archives"
    max_subagent_rounds: int = 20
```

- [ ] **Step 4: Run pip install**

```bash
pip install -e ".[dev]"
playwright install chromium
```

Expected: Dependencies install without errors.

- [ ] **Step 5: Start Neo4j**

```bash
docker compose up -d neo4j
```

Expected: Neo4j available at bolt://localhost:7687, HTTP at http://localhost:7474

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml docker-compose.yml agent/ llm/ tools/ memory/ server/ tests/
git commit -m "feat: project skeleton with config and docker-compose"
```

---

### Task 2: LLM 客户端抽象层 (OpenAI + DeepSeek)

**Files:**
- Create: `llm/base.py`
- Create: `llm/openai_client.py`
- Create: `llm/deepseek_client.py`
- Create: `tests/test_llm/test_clients.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_llm/test_clients.py
import pytest
from llm.openai_client import OpenAIClient
from llm.deepseek_client import DeepSeekClient
from agent.config import LLMConfig


def test_openai_client_creates_with_config():
    config = LLMConfig(provider="openai", model="gpt-4o", api_key="sk-test")
    client = OpenAIClient(config)
    assert client.model == "gpt-4o"


def test_deepseek_client_creates_with_config():
    config = LLMConfig(provider="deepseek", model="deepseek-chat", api_key="sk-test",
                       base_url="https://api.deepseek.com")
    client = DeepSeekClient(config)
    assert client.model == "deepseek-chat"
    assert client.base_url == "https://api.deepseek.com"


def test_both_clients_implement_same_interface():
    from llm.base import LlmClient
    assert issubclass(OpenAIClient, LlmClient)
    assert issubclass(DeepSeekClient, LlmClient)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_llm/test_clients.py -v
```
Expected: FAIL - modules not found

- [ ] **Step 3: Write llm/base.py**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Message:
    role: str        # "system" | "user" | "assistant" | "tool"
    content: str
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LlmResponse:
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class ToolSchema:
    name: str
    description: str
    parameters: dict[str, Any]   # JSON Schema for parameters


class LlmClient(ABC):

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
    ) -> LlmResponse:
        ...
```

- [ ] **Step 4: Write llm/openai_client.py**

```python
from openai import AsyncOpenAI
from llm.base import LlmClient, LlmResponse, Message, ToolCall, ToolSchema
from agent.config import LLMConfig


class OpenAIClient(LlmClient):
    def __init__(self, config: LLMConfig):
        self.model = config.model
        self._client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url or None,
        )
        self._max_tokens = config.max_tokens
        self._temperature = config.temperature

    async def chat(self, messages: list[Message], tools: list[ToolSchema] | None = None) -> LlmResponse:
        msgs = [{"role": m.role, "content": m.content} for m in messages]
        kwargs = {
            "model": self.model,
            "messages": msgs,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
        }
        if tools:
            kwargs["tools"] = [{
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                }
            } for t in tools]

        resp = await self._client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                import json
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments),
                ))
        return LlmResponse(
            content=choice.message.content,
            tool_calls=tool_calls,
        )
```

- [ ] **Step 5: Write llm/deepseek_client.py**

```python
import json
import httpx
from llm.base import LlmClient, LlmResponse, Message, ToolCall, ToolSchema
from agent.config import LLMConfig


class DeepSeekClient(LlmClient):
    def __init__(self, config: LLMConfig):
        self.model = config.model
        self.base_url = config.base_url or "https://api.deepseek.com"
        self._api_key = config.api_key
        self._max_tokens = config.max_tokens
        self._temperature = config.temperature

    async def chat(self, messages: list[Message], tools: list[ToolSchema] | None = None) -> LlmResponse:
        msgs = [{"role": m.role, "content": m.content} for m in messages]
        body = {
            "model": self.model,
            "messages": msgs,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
        }
        if tools:
            body["tools"] = [{
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                }
            } for t in tools]

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]
        tool_calls = []
        if choice["message"].get("tool_calls"):
            for tc in choice["message"]["tool_calls"]:
                tool_calls.append(ToolCall(
                    id=tc["id"],
                    name=tc["function"]["name"],
                    arguments=json.loads(tc["function"]["arguments"]),
                ))
        return LlmResponse(
            content=choice["message"].get("content"),
            tool_calls=tool_calls,
        )
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/test_llm/test_clients.py -v
```
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add llm/ tests/test_llm/
git commit -m "feat: add LLM client abstraction with OpenAI and DeepSeek adapters"
```

---

### Task 3: Neo4j 图模型与客户端

**Files:**
- Create: `memory/neo4j_client.py`
- Create: `memory/graph_models.py`
- Create: `tests/test_memory/test_neo4j.py`

- [ ] **Step 1: Write graph_models.py**

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Union


@dataclass
class Base64Source:
    type: str = "base64"
    media_type: str = ""   # e.g. "image/png", "audio/mp3"
    data: str = ""         # base64-encoded data


@dataclass
class URLSource:
    type: str = "url"
    url: str = ""


@dataclass
class ContentBlock:
    """Aligned with AgentScope ContentBlock types.
    
    TextBlock:      {type: "text", text: str}
    ThinkingBlock:  {type: "thinking", thinking: str}
    ToolUseBlock:   {type: "tool_use", id: str, name: str, input: dict}
    ToolResultBlock:{type: "tool_result", id: str, name: str, output: str | list[ContentBlock]}
    ImageBlock:     {type: "image", source: URLSource | Base64Source}
    AudioBlock:     {type: "audio", source: URLSource | Base64Source}
    VideoBlock:     {type: "video", source: URLSource | Base64Source}
    """
    type: str   # "text" | "thinking" | "tool_use" | "tool_result" | "image" | "audio" | "video"
    # Text/Thinking fields
    text: str | None = None
    thinking: str | None = None
    # Tool fields
    id: str | None = None          # tool call id (matches between tool_use and tool_result)
    name: str | None = None        # tool name
    input: dict[str, Any] | None = None   # tool arguments (AgentScope uses "input")
    output: Any = None             # tool result (str or list[ContentBlock])
    # Multimodal fields
    source: Base64Source | URLSource | None = None


@dataclass
class SkillNode:
    skill_id: str
    name: str
    description: str = ""            # Trigger description for L1 routing
    category: str = ""
    stage: str = "NL"               # "NL" | "SOP" | "CODE" | "DEPRECATED"
    version: int = 1
    dir: str = ""
    usage_count: int = 0
    success_rate: float = 0.0
    activation: float = 1.0
    confidence: float = 0.0
    context_tags: list[str] = field(default_factory=list)
    embeddings: list[float] = field(default_factory=list)  # Semantic embedding vector
    created_at: str = ""
    updated_at: str = ""


@dataclass
class EntityNode:
    """L2 open-world knowledge graph node. Entity types are dynamically defined by the model.
    
    Replaces the older fixed FactNode. entity_type="Fact" is the backwards-compatible subtype.
    Subconscious loop auto-extracts entities from L0 ExecutionSteps.
    """
    entity_id: str
    entity_type: str                     # Model-defined: "Person"|"Service"|"Incident"|"API"|"Config"|"Error"|"Fact"|...
    name: str
    content: str                         # Human-readable description
    properties: dict[str, Any] = field(default_factory=dict)  # Structured attributes
    confidence: float = 1.0
    source: str = ""                     # "execution_verified" | "inferred" | "user_claimed" | "speculative"
    source_trace: list[str] = field(default_factory=list)
    activation: float = 1.0
    created_at: str = ""
    updated_at: str = ""


@dataclass
class SopNode:
    sop_id: str
    content: str
    skill_id: str
    version: int = 1
    precondition: str = ""
    confidence: float = 0.0


@dataclass
class ExecutionStep:
    """Aligned with AgentScope Msg. One message = one step.
    
    Fields map to AgentScope Msg:
      - id -> Msg.id (shortuuid)
      - name -> Msg.name (sender)
      - role -> Msg.role ("system"|"user"|"assistant")
      - content -> Msg.content (list[ContentBlock])
      - metadata -> Msg.metadata
      - timestamp -> Msg.timestamp
      - invocation_id -> Msg.invocation_id
    """
    id: str              # shortuuid message ID
    name: str            # sender name (agent name or tool name)
    role: str            # "system" | "user" | "assistant"
    content: list[ContentBlock] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    invocation_id: str | None = None


@dataclass
class AgentNode:
    agent_id: str
    name: str
    role: str = "default"
    evolution_policy: str = "balanced"
    trust_threshold: float = 0.6
    created_at: str = ""
    updated_at: str = ""


@dataclass
class UserNode:
    user_id: str
    name: str
    preferences: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""


@dataclass
class MetaPatternNode:
    pattern_id: str
    name: str
    description: str
    abstract_steps: list[str] = field(default_factory=list)
    applicable_domains: list[str] = field(default_factory=list)
    source_skills: list[str] = field(default_factory=list)
    usage_count: int = 0
    created_at: str = ""


@dataclass
class SkillCategoryNode:
    name: str
    description: str = ""
    skill_count: int = 0
    created_at: str = ""


@dataclass
class DistillationRequestNode:
    session_id: str
    reason: str          # "subgoal_completed" | "fault_recovery" | "reusable_pattern"
    summary: str
    status: str = "pending"
    created_at: str = ""
    processed_at: str = ""
```

- [ ] **Step 2: Write neo4j_client.py**

```python
from neo4j import AsyncGraphDatabase, AsyncDriver
from agent.config import Neo4jConfig


class Neo4jClient:
    def __init__(self, config: Neo4jConfig):
        self._driver: AsyncDriver = AsyncGraphDatabase.driver(
            config.uri,
            auth=(config.user, config.password),
        )

    async def close(self):
        await self._driver.close()

    async def init_schema(self):
        """创建完整图模型的约束和索引"""
        queries = [
            # 唯一性约束
            "CREATE CONSTRAINT skill_id_unique     IF NOT EXISTS FOR (s:Skill)           REQUIRE s.skill_id IS UNIQUE",
            "CREATE CONSTRAINT agent_id_unique     IF NOT EXISTS FOR (a:Agent)           REQUIRE a.agent_id IS UNIQUE",
            "CREATE CONSTRAINT session_id_unique   IF NOT EXISTS FOR (s:Session)         REQUIRE s.session_id IS UNIQUE",
            "CREATE CONSTRAINT step_id_unique      IF NOT EXISTS FOR (s:ExecutionStep)   REQUIRE s.id IS UNIQUE",
            "CREATE CONSTRAINT entity_id_unique    IF NOT EXISTS FOR (e:Entity)          REQUIRE e.entity_id IS UNIQUE",
            "CREATE CONSTRAINT sop_id_unique       IF NOT EXISTS FOR (s:SOP)             REQUIRE s.sop_id IS UNIQUE",
            "CREATE CONSTRAINT pattern_id_unique   IF NOT EXISTS FOR (p:MetaPattern)     REQUIRE p.pattern_id IS UNIQUE",
            "CREATE CONSTRAINT user_id_unique      IF NOT EXISTS FOR (u:User)            REQUIRE u.user_id IS UNIQUE",
            "CREATE CONSTRAINT category_name_unique IF NOT EXISTS FOR (c:SkillCategory)   REQUIRE c.name IS UNIQUE",
            # 查询索引
            "CREATE INDEX skill_category_idx   IF NOT EXISTS FOR (s:Skill)     ON (s.category)",
            "CREATE INDEX skill_stage_idx      IF NOT EXISTS FOR (s:Skill)     ON (s.stage)",
            "CREATE INDEX skill_activation_idx IF NOT EXISTS FOR (s:Skill)     ON (s.activation)",
            "CREATE INDEX entity_type_idx       IF NOT EXISTS FOR (e:Entity)    ON (e.entity_type)",
            "CREATE INDEX entity_source_idx     IF NOT EXISTS FOR (e:Entity)    ON (e.source)",
            "CREATE INDEX entity_confidence_idx IF NOT EXISTS FOR (e:Entity)    ON (e.confidence)",
            "CREATE INDEX session_status_idx   IF NOT EXISTS FOR (s:Session)   ON (s.status)",
            "CREATE INDEX step_role_idx        IF NOT EXISTS FOR (s:ExecutionStep) ON (s.role)",
            "CREATE INDEX sop_skill_idx        IF NOT EXISTS FOR (s:SOP)       ON (s.skill_id)",
            "CREATE INDEX distillation_status_idx IF NOT EXISTS FOR (d:DistillationRequest) ON (d.status)",
            # 全文索引
            "CREATE FULLTEXT INDEX skill_search IF NOT EXISTS FOR (s:Skill) ON EACH [s.name, s.description]",
            "CREATE FULLTEXT INDEX entity_search IF NOT EXISTS FOR (e:Entity) ON EACH [e.name, e.content]",
        ]
        async with self._driver.session() as session:
            for q in queries:
                await session.run(q)

    async def run(self, query: str, params: dict | None = None) -> list[dict]:
        """执行 Cypher 查询并返回记录列表"""
        async with self._driver.session() as session:
            result = await session.run(query, params or {})
            records = await result.data()
            return records

    async def get_driver(self) -> AsyncDriver:
        return self._driver
```

- [ ] **Step 3: Write tests**

```python
# tests/test_memory/test_neo4j.py
import pytest
from memory.graph_models import (
    SkillNode, EntityNode, ExecutionStep, ContentBlock,
    Base64Source, URLSource,
)


def test_skill_node_creation():
    skill = SkillNode(
        skill_id="test-skill",
        name="Test Skill",
        category="test",
        stage="NL",
        version=1,
        dir="skills/test/test-skill/",
    )
    assert skill.stage == "NL"


def test_entity_node_open_world():
    """L2 Entity nodes support arbitrary types defined by the model."""
    alice = EntityNode(
        entity_id="ent_alice",
        entity_type="Person",
        name="Alice Wang",
        content="后端团队高级工程师，负责 Neo4j 管理",
        properties={
            "email": "alice@example.com",
            "role": "DBA",
            "skills": ["Python", "Go", "Kubernetes"],
        },
        source="user_claimed",
    )
    assert alice.entity_type == "Person"
    assert alice.properties["role"] == "DBA"

    neo4j_svc = EntityNode(
        entity_id="ent_neo4j_main",
        entity_type="Service",
        name="Neo4j 主库",
        content="生产环境 Neo4j 数据库实例",
        properties={"host": "10.0.1.50", "port": 7687, "version": "5.20"},
        source="execution_verified",
    )
    assert neo4j_svc.entity_type == "Service"
    assert neo4j_svc.properties["host"] == "10.0.1.50"

    # Backwards-compatible: entity_type="Fact" == old FactNode
    fact = EntityNode(
        entity_id="fact_legacy",
        entity_type="Fact",
        name="Neo4j 默认端口",
        content="Neo4j 数据库运行在 7687 端口",
        properties={},
        source="execution_verified",
    )
    assert fact.entity_type == "Fact"


def test_execution_step_aligned_with_agentscope_msg():
    step = ExecutionStep(
        id="msg_3xK2mP9q",
        name="infocap",
        role="assistant",
        content=[
            ContentBlock(type="thinking", thinking="需要读取配置文件来了解数据库参数。"),
            ContentBlock(type="tool_use", id="call_001", name="file_read",
                         input={"path": "config.yaml"}),
            ContentBlock(type="tool_result", id="call_001", name="file_read",
                         output="db:\n  host: localhost\n  port: 7687"),
            ContentBlock(type="text", text="Neo4j 运行在 localhost:7687。"),
        ],
        metadata={"session_id": "sess_001", "turn": 3},
        invocation_id="inv_7f2a9b",
    )
    assert step.id == "msg_3xK2mP9q"
    assert step.name == "infocap"
    assert step.role == "assistant"
    assert len(step.content) == 4
    assert step.content[0].type == "thinking"
    assert step.content[0].thinking == "需要读取配置文件来了解数据库参数。"
    assert step.content[1].type == "tool_use"
    assert step.content[1].name == "file_read"
    assert step.content[1].input["path"] == "config.yaml"
    assert step.content[2].type == "tool_result"
    assert step.content[2].output.startswith("db:")
    assert step.content[3].type == "text"
    assert step.content[3].text == "Neo4j 运行在 localhost:7687。"
    assert step.metadata["turn"] == 3


def test_content_block_types_match_agentscope():
    """All AgentScope ContentBlock types."""
    valid_types = {"text", "thinking", "tool_use", "tool_result", "image", "audio", "video"}
    for bt in valid_types:
        block = ContentBlock(type=bt)
        assert block.type in valid_types


def test_text_block():
    block = ContentBlock(type="text", text="Hello")
    assert block.text == "Hello"


def test_thinking_block():
    block = ContentBlock(type="thinking", thinking="需要分析...")
    assert block.thinking == "需要分析..."


def test_image_block_with_base64():
    block = ContentBlock(
        type="image",
        source=Base64Source(media_type="image/png", data="iVBORw0KGgo..."),
    )
    assert block.source.media_type == "image/png"


def test_audio_block_with_url():
    block = ContentBlock(
        type="audio",
        source=URLSource(url="https://example.com/audio.mp3"),
    )
    assert block.source.url == "https://example.com/audio.mp3"
```


@pytest.mark.asyncio
async def test_neo4j_init_schema():
    config = Neo4jConfig()
    client = Neo4jClient(config)
    try:
        await client.init_schema()
    finally:
        await client.close()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_memory/test_neo4j.py -v
```
Expected: PASS (Neo4j must be running)

- [ ] **Step 5: Commit**

```bash
git add memory/ tests/test_memory/
git commit -m "feat: add Neo4j graph models and client with schema initialization"
```

---

### Task 4: 工具基类与调度器

**Files:**
- Create: `tools/base.py`
- Create: `tools/dispatcher.py`
- Create: `tests/test_tools/test_dispatcher.py`

- [ ] **Step 1: Write tools/base.py**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolSchema:
    name: str
    description: str
    parameters: dict[str, Any]    # JSON Schema


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    call_id: str
    name: str
    success: bool
    output: str
    error: str | None = None


class BaseTool(ABC):
    """原子工具基类"""

    @abstractmethod
    def schema(self) -> ToolSchema:
        """返回工具的 JSON Schema 定义"""
        ...

    @abstractmethod
    async def execute(self, call: ToolCall) -> ToolResult:
        """执行工具调用，返回结果"""
        ...

    @property
    def name(self) -> str:
        return self.schema().name
```

- [ ] **Step 2: Write tools/dispatcher.py**

```python
from tools.base import BaseTool, ToolCall, ToolResult


class ToolDispatcher:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool

    def get_schemas(self) -> list[dict]:
        schemas = []
        for tool in self._tools.values():
            s = tool.schema()
            schemas.append({
                "type": "function",
                "function": {
                    "name": s.name,
                    "description": s.description,
                    "parameters": s.parameters,
                }
            })
        return schemas

    async def dispatch(self, call: ToolCall) -> ToolResult:
        tool = self._tools.get(call.name)
        if tool is None:
            return ToolResult(
                call_id=call.id,
                name=call.name,
                success=False,
                output="",
                error=f"Unknown tool: {call.name}",
            )
        try:
            return await tool.execute(call)
        except Exception as e:
            return ToolResult(
                call_id=call.id,
                name=call.name,
                success=False,
                output="",
                error=str(e),
            )

    def tool_names(self) -> list[str]:
        return list(self._tools.keys())
```

- [ ] **Step 3: Write test**

```python
# tests/test_tools/test_dispatcher.py
import pytest
from tools.base import BaseTool, ToolSchema, ToolCall, ToolResult
from tools.dispatcher import ToolDispatcher


class _EchoTool(BaseTool):
    def schema(self):
        return ToolSchema(
            name="echo",
            description="Echoes the message back",
            parameters={
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        return ToolResult(
            call_id=call.id,
            name=call.name,
            success=True,
            output=call.arguments["message"],
        )


@pytest.mark.asyncio
async def test_dispatcher_registers_and_dispatches():
    dispatcher = ToolDispatcher()
    dispatcher.register(_EchoTool())
    result = await dispatcher.dispatch(ToolCall(id="c1", name="echo", arguments={"message": "hello"}))
    assert result.success
    assert result.output == "hello"


@pytest.mark.asyncio
async def test_dispatcher_unknown_tool():
    dispatcher = ToolDispatcher()
    result = await dispatcher.dispatch(ToolCall(id="c1", name="nonexistent", arguments={}))
    assert not result.success
    assert "Unknown tool" in result.error


def test_get_schemas():
    dispatcher = ToolDispatcher()
    dispatcher.register(_EchoTool())
    schemas = dispatcher.get_schemas()
    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "echo"
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_tools/test_dispatcher.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/base.py tools/dispatcher.py tests/test_tools/
git commit -m "feat: add tool base class and dispatcher"
```

---

### Task 5: 文件操作工具 (file_read / file_patch / file_write)

**Files:**
- Create: `tools/file_ops.py`
- Create: `tests/test_tools/test_file_ops.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_tools/test_file_ops.py
import pytest
from tools.file_ops import FileReadTool, FilePatchTool, FileWriteTool
from tools.base import ToolCall


@pytest.mark.asyncio
async def test_file_read_reads_lines(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("line1\nline2\nline3\nline4\nline5\n")
    tool = FileReadTool()
    result = await tool.execute(ToolCall(
        id="c1", name="file_read",
        arguments={"path": str(f), "start": 2, "count": 2},
    ))
    assert result.success
    assert "line3" in result.output
    assert "line4" in result.output


@pytest.mark.asyncio
async def test_file_write_creates_file(tmp_path):
    f = tmp_path / "new.txt"
    tool = FileWriteTool()
    result = await tool.execute(ToolCall(
        id="c1", name="file_write",
        arguments={"path": str(f), "content": "hello world"},
    ))
    assert result.success
    assert f.read_text() == "hello world"


@pytest.mark.asyncio
async def test_file_patch_unique_match(tmp_path):
    f = tmp_path / "patchme.txt"
    f.write_text("old content here\n")
    tool = FilePatchTool()
    result = await tool.execute(ToolCall(
        id="c1", name="file_patch",
        arguments={"path": str(f), "old_content": "old content here", "new_content": "new content"},
    ))
    assert result.success
    assert "new content" in f.read_text()


@pytest.mark.asyncio
async def test_file_patch_no_match_fails(tmp_path):
    f = tmp_path / "patchme.txt"
    f.write_text("something else\n")
    tool = FilePatchTool()
    result = await tool.execute(ToolCall(
        id="c1", name="file_patch",
        arguments={"path": str(f), "old_content": "nonexistent", "new_content": "x"},
    ))
    assert not result.success
    assert "not found" in result.error.lower() or "no match" in result.error.lower()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_tools/test_file_ops.py -v
```
Expected: FAIL

- [ ] **Step 3: Write tools/file_ops.py**

```python
from pathlib import Path
from tools.base import BaseTool, ToolSchema, ToolCall, ToolResult


class FileReadTool(BaseTool):
    def schema(self):
        return ToolSchema(
            name="file_read",
            description="Read file content with optional line range and keyword anchoring",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative file path"},
                    "start": {"type": "integer", "description": "Line number to start reading (1-indexed)"},
                    "count": {"type": "integer", "description": "Number of lines to read"},
                    "keyword": {"type": "string", "description": "Jump to first line containing this keyword"},
                },
                "required": ["path"],
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        path = Path(call.arguments["path"])
        if not path.exists():
            return ToolResult(call_id=call.id, name="file_read", success=False, output="", error=f"File not found: {path}")
        lines = path.read_text(encoding="utf-8").splitlines()
        start = call.arguments.get("start", 1) - 1
        keyword = call.arguments.get("keyword")
        if keyword:
            for i, line in enumerate(lines):
                if keyword in line:
                    start = i
                    break
        count = call.arguments.get("count", len(lines) - start)
        selected = lines[start:start + count]
        output = "\n".join(f"{start + i + 1}\t{line}" for i, line in enumerate(selected))
        return ToolResult(call_id=call.id, name="file_read", success=True, output=output)


class FileWriteTool(BaseTool):
    def schema(self):
        return ToolSchema(
            name="file_write",
            description="Write full content to a file, creating or overwriting",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        path = Path(call.arguments["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(call.arguments["content"], encoding="utf-8")
        return ToolResult(call_id=call.id, name="file_write", success=True, output=f"Written to {path}")


class FilePatchTool(BaseTool):
    def schema(self):
        return ToolSchema(
            name="file_patch",
            description="Replace old_content with new_content. old_content must match exactly one location.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_content": {"type": "string", "description": "Exact content to find and replace"},
                    "new_content": {"type": "string", "description": "Replacement content"},
                },
                "required": ["path", "old_content", "new_content"],
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        path = Path(call.arguments["path"])
        if not path.exists():
            return ToolResult(call_id=call.id, name="file_patch", success=False, output="", error=f"File not found: {path}")
        content = path.read_text(encoding="utf-8")
        old = call.arguments["old_content"]
        count = content.count(old)
        if count == 0:
            return ToolResult(call_id=call.id, name="file_patch", success=False, output="", error="old_content not found in file")
        if count > 1:
            return ToolResult(call_id=call.id, name="file_patch", success=False, output="", error=f"old_content matches {count} locations, must be unique")
        new = call.arguments["new_content"]
        path.write_text(content.replace(old, new, 1), encoding="utf-8")
        return ToolResult(call_id=call.id, name="file_patch", success=True, output="Patch applied successfully")
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_tools/test_file_ops.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/file_ops.py tests/test_tools/test_file_ops.py
git commit -m "feat: add file_read, file_patch, file_write tools"
```

---

### Task 6: 代码执行工具 (code_run)

**Files:**
- Create: `tools/code_run.py`
- Create: `tests/test_tools/test_code_run.py`

- [ ] **Step 1: Write code_run.py**

```python
import asyncio
import os
import tempfile
from pathlib import Path
from tools.base import BaseTool, ToolSchema, ToolCall, ToolResult


class CodeRunTool(BaseTool):
    def __init__(self, workspace_dir: str = "./workspace"):
        self._workspace = Path(workspace_dir)
        self._workspace.mkdir(parents=True, exist_ok=True)

    def schema(self):
        return ToolSchema(
            name="code_run",
            description="Execute Python code in an isolated workspace. One invocation per round.",
            parameters={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to execute"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 30)"},
                },
                "required": ["code"],
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        code = call.arguments["code"]
        timeout = call.arguments.get("timeout", 30)
        script_path = self._workspace / f"_code_run_{os.getpid()}.py"
        script_path.write_text(code, encoding="utf-8")
        try:
            proc = await asyncio.create_subprocess_exec(
                "python", str(script_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._workspace),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            output = stdout.decode("utf-8", errors="replace")
            if stderr:
                output += "\n[stderr]\n" + stderr.decode("utf-8", errors="replace")
            return ToolResult(
                call_id=call.id, name="code_run", success=proc.returncode == 0,
                output=output[:10000],   # Stage 1 截断
                error=None if proc.returncode == 0 else f"Exit code: {proc.returncode}",
            )
        except asyncio.TimeoutError:
            return ToolResult(call_id=call.id, name="code_run", success=False, output="", error=f"Timeout after {timeout}s")
        finally:
            if script_path.exists():
                script_path.unlink()
```

- [ ] **Step 2: Write test**

```python
# tests/test_tools/test_code_run.py
import pytest
from tools.code_run import CodeRunTool
from tools.base import ToolCall


@pytest.mark.asyncio
async def test_code_run_prints_output(tmp_path):
    tool = CodeRunTool(workspace_dir=str(tmp_path))
    result = await tool.execute(ToolCall(
        id="c1", name="code_run",
        arguments={"code": "print('hello from sandbox')"},
    ))
    assert result.success
    assert "hello from sandbox" in result.output


@pytest.mark.asyncio
async def test_code_run_captures_error(tmp_path):
    tool = CodeRunTool(workspace_dir=str(tmp_path))
    result = await tool.execute(ToolCall(
        id="c1", name="code_run",
        arguments={"code": "raise ValueError('test error')"},
    ))
    assert not result.success
    assert "ValueError" in result.output


@pytest.mark.asyncio
async def test_code_run_timeout(tmp_path):
    tool = CodeRunTool(workspace_dir=str(tmp_path))
    result = await tool.execute(ToolCall(
        id="c1", name="code_run",
        arguments={"code": "import time; time.sleep(10)", "timeout": 1},
    ))
    assert not result.success
    assert "Timeout" in result.error
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_tools/test_code_run.py -v
```
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tools/code_run.py tests/test_tools/test_code_run.py
git commit -m "feat: add code_run tool with subprocess sandbox"
```

---

### Task 7: Web 交互工具 (web_scan / web_execute_js)

**Files:**
- Create: `tools/web_interact.py`
- Create: `tests/test_tools/test_web_interact.py`

- [ ] **Step 1: Write web_interact.py**

```python
from tools.base import BaseTool, ToolSchema, ToolCall, ToolResult

try:
    from playwright.async_api import async_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


class WebScanTool(BaseTool):
    """Scan a web page and return semantically extracted content."""

    def __init__(self):
        self._browser = None
        self._context = None

    def schema(self):
        return ToolSchema(
            name="web_scan",
            description="Navigate to a URL and extract the page's main content as structured text. Strips navigation, ads, and hidden elements.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to scan"},
                },
                "required": ["url"],
            },
        )

    async def _ensure_browser(self):
        if not HAS_PLAYWRIGHT:
            raise RuntimeError("Playwright not installed")
        if self._browser is None:
            pw = await async_playwright().start()
            self._browser = await pw.chromium.launch()
            self._context = await self._browser.new_context()

    async def execute(self, call: ToolCall) -> ToolResult:
        await self._ensure_browser()
        url = call.arguments["url"]
        try:
            page = await self._context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            text = await page.evaluate("""() => {
                const main = document.querySelector('main, article, [role="main"]');
                return (main || document.body).innerText;
            }""")
            await page.close()
            output = text[:10000]   # truncate
            return ToolResult(call_id=call.id, name="web_scan", success=True, output=output)
        except Exception as e:
            return ToolResult(call_id=call.id, name="web_scan", success=False, output="", error=str(e))

    async def close(self):
        if self._browser:
            await self._browser.close()
            self._browser = None


class WebExecuteJsTool(BaseTool):
    """Execute JavaScript in the browser and return results + observed changes."""

    def __init__(self, browser_holder: WebScanTool):
        self._browser = browser_holder

    def schema(self):
        return ToolSchema(
            name="web_execute_js",
            description="Execute JavaScript in the current browser page. Returns operation result and observed page changes.",
            parameters={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "JavaScript code to execute"},
                },
                "required": ["code"],
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        await self._browser._ensure_browser()
        code = call.arguments["code"]
        try:
            page = await self._browser._context.new_page()
            result = await page.evaluate(code)
            await page.close()
            return ToolResult(call_id=call.id, name="web_execute_js", success=True, output=str(result)[:8000])
        except Exception as e:
            return ToolResult(call_id=call.id, name="web_execute_js", success=False, output="", error=str(e))
```

- [ ] **Step 2: Write test (mock-based)**

```python
# tests/test_tools/test_web_interact.py
import pytest
from tools.web_interact import WebScanTool, WebExecuteJsTool, HAS_PLAYWRIGHT


def test_web_scan_schema():
    tool = WebScanTool()
    s = tool.schema()
    assert s.name == "web_scan"
    assert "url" in s.parameters["required"]


def test_web_execute_js_schema():
    scan_tool = WebScanTool()
    tool = WebExecuteJsTool(scan_tool)
    s = tool.schema()
    assert s.name == "web_execute_js"
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_tools/test_web_interact.py -v
```
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tools/web_interact.py tests/test_tools/test_web_interact.py
git commit -m "feat: add web_scan and web_execute_js tools via Playwright"
```

---

### Task 8: 记忆管理工具 (memory_search / checkpoint / long_term_update / skill_manage)

**Files:**
- Create: `tools/memory_search.py`
- Create: `tools/checkpoint.py`
- Create: `tools/long_term_update.py`
- Create: `tools/skill_manage.py`
- Create: `tests/test_tools/test_memory_tools.py`

- [ ] **Step 1: Write memory_search.py**

```python
from tools.base import BaseTool, ToolSchema, ToolCall, ToolResult
from memory.neo4j_client import Neo4jClient


class MemorySearchTool(BaseTool):
    def __init__(self, neo4j: Neo4jClient):
        self._neo4j = neo4j

    def schema(self):
        return ToolSchema(
            name="memory_search",
            description="Search Neo4j memory graph with 6 modes: route (find Skills), load (load Skill memories), trace (query execution steps), related (find connected nodes), rag (GraphRAG multi-hop retrieval from current question).",
            parameters={
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "enum": ["route", "load", "trace", "related", "rag"]},
                    "category": {"type": "string", "description": "Filter by Skill category (route mode)"},
                    "stage": {"type": "string", "description": "Filter by Skill stage (route mode)"},
                    "keyword": {"type": "string", "description": "Search keyword (route mode) or question text (rag mode)"},
                    "skill_id": {"type": "string", "description": "Target Skill ID (load/related mode)"},
                    "session_id": {"type": "string", "description": "Target session ID (trace mode)"},
                    "top_k": {"type": "integer", "description": "Max results (default 10)"},
                    "hops": {"type": "integer", "description": "Graph traversal depth for rag mode (default 2, max 3)"},
                    "strategy": {"type": "string", "enum": ["local", "global"], "description": "RAG strategy: local (entity-focused traversal) or global (category aggregation)"},
                },
                "required": ["mode"],
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        mode = call.arguments["mode"]
        try:
            if mode == "route":
                return await self._route(call)
            elif mode == "load":
                return await self._load(call)
            elif mode == "trace":
                return await self._trace(call)
            elif mode == "related":
                return await self._related(call)
            elif mode == "rag":
                return await self._rag(call)
            else:
                return ToolResult(call_id=call.id, name="memory_search", success=False, output="", error=f"Unknown mode: {mode}")
        except Exception as e:
            return ToolResult(call_id=call.id, name="memory_search", success=False, output="", error=str(e))

    async def _route(self, call: ToolCall) -> ToolResult:
        top_k = call.arguments.get("top_k", 10)
        category = call.arguments.get("category", "")
        stage = call.arguments.get("stage", "")
        keyword = call.arguments.get("keyword", "")
        query = "MATCH (s:Skill) WHERE 1=1"
        params = {}
        if category:
            query += " AND s.category = $category"
            params["category"] = category
        if stage:
            query += " AND s.stage = $stage"
            params["stage"] = stage
        if keyword:
            query += " AND (s.name CONTAINS $kw OR s.skill_id CONTAINS $kw)"
            params["kw"] = keyword
        query += " RETURN s ORDER BY s.usage_count DESC LIMIT $top_k"
        params["top_k"] = top_k
        records = await self._neo4j.run(query, params)
        results = [r["s"] for r in records]
        return ToolResult(call_id=call.id, name="memory_search", success=True, output=str(results))

    async def _load(self, call: ToolCall) -> ToolResult:
        skill_id = call.arguments["skill_id"]
        query = """
            MATCH (s:Skill {skill_id: $skill_id})
            OPTIONAL MATCH (s)-[:HAS_SOP]->(sop:SOP)
            OPTIONAL MATCH (s)-[:REFERENCES]->(e:Entity)
            RETURN s, collect(DISTINCT sop) AS sops, collect(DISTINCT e) AS entities
        """
        records = await self._neo4j.run(query, {"skill_id": skill_id})
        if not records:
            return ToolResult(call_id=call.id, name="memory_search", success=False, output="", error=f"Skill not found: {skill_id}")
        return ToolResult(call_id=call.id, name="memory_search", success=True, output=str(records[0]))

    async def _trace(self, call: ToolCall) -> ToolResult:
        session_id = call.arguments["session_id"]
        query = """
            MATCH (s:Session {session_id: $session_id})-[:HAS_STEP]->(step:ExecutionStep)
            RETURN step ORDER BY step.step_index
        """
        records = await self._neo4j.run(query, {"session_id": session_id})
        return ToolResult(call_id=call.id, name="memory_search", success=True, output=str(records))

    async def _related(self, call: ToolCall) -> ToolResult:
        skill_id = call.arguments["skill_id"]
        query = """
            MATCH (s:Skill {skill_id: $skill_id})-[r]->(related)
            RETURN type(r) AS rel_type, related
        """
        records = await self._neo4j.run(query, {"skill_id": skill_id})
        return ToolResult(call_id=call.id, name="memory_search", success=True, output=str(records))

    async def _rag(self, call: ToolCall) -> ToolResult:
        """GraphRAG-style multi-hop retrieval from current question.
        
        Phase 1: keyword-based entity seeding + 1-2 hop traversal + basic scoring.
        Phase 2 TODO: LLM entity extraction, vector similarity enhancement, full 4D scoring.
        Phase 5 TODO: GDS community detection for global search.
        """
        keyword = call.arguments.get("keyword", "")
        hops = call.arguments.get("hops", 2)
        strategy = call.arguments.get("strategy", "local")
        top_k = call.arguments.get("top_k", 10)
        call_id = call.id

        if strategy == "local":
            return await self._rag_local(call_id, keyword, hops, top_k)
        else:
            return await self._rag_global(call_id, keyword, top_k)

    async def _rag_local(self, call_id: str, question: str, hops: int, top_k: int) -> ToolResult:
        # Step 1: Entity seeding via full-text search across Skill + Entity
        seed_query = """
            CALL db.index.fulltext.queryNodes('skill_search', $question) YIELD node AS skill, score
            RETURN skill.skill_id AS id, 'Skill' AS type, score
            UNION ALL
            CALL db.index.fulltext.queryNodes('entity_search', $question) YIELD node AS entity, score
            RETURN entity.entity_id AS id, 'Entity' AS type, score
            ORDER BY score DESC LIMIT 10
        """
        seeds = await self._neo4j.run(seed_query, {"question": question})
        if not seeds:
            return ToolResult(call_id=call_id, name="memory_search", success=True,
                            output="(No relevant memories found in graph.)")

        seed_ids = [s["id"] for s in seeds]

        # Step 2: Multi-hop traversal across L2 open-world graph
        hop_query = f"""
            MATCH (seed)-[*1..{hops}]-(related)
            WHERE (seed:Skill  AND seed.skill_id  IN $seed_ids)
               OR (seed:Entity AND seed.entity_id IN $seed_ids)
               OR (seed:SOP    AND seed.sop_id    IN $seed_ids)
            WITH DISTINCT related, seed
            RETURN labels(related) AS labels, properties(related) AS props,
                   labels(seed) AS seed_labels, properties(seed) AS seed_props
            LIMIT 100
        """
        neighbors = await self._neo4j.run(hop_query, {"seed_ids": seed_ids})

        # Step 3: Basic scoring (frequency + confidence + recency)
        scored = {}
        for row in neighbors:
            props = row["props"]
            node_id = (props.get("skill_id") or props.get("entity_id")
                    or props.get("sop_id") or props.get("id"))
            if node_id is None:
                continue
            label = row["labels"][0] if row["labels"] else "Unknown"
            freq = scored.get(node_id, {}).get("_freq", 0) + 1
            confidence = float(props.get("confidence", 0.5))
            usage = int(props.get("usage_count", 0))
            score = freq * 1.0 + confidence * 2.0 + min(usage / 10.0, 3.0)
            props["_score"] = round(score, 2)
            props["_type"] = label
            scored[node_id] = props
            scored[node_id]["_freq"] = freq

        ranked = sorted(scored.values(), key=lambda x: x["_score"], reverse=True)[:top_k]

        # Step 4: Serialize subgraph as structured text
        lines = [f"## GraphRAG Results (local, {hops}-hop, top {top_k})"]
        lines.append(f"Query: {question[:200]}")
        lines.append(f"Seeds: {len(seeds)} nodes | Traversed: {len(neighbors)} nodes | Output: {len(ranked)} nodes\n")

        by_type = {}
        for node in ranked:
            t = node.get("_type", "Unknown")
            by_type.setdefault(t, []).append(node)

        for typ in ["Skill", "SOP", "Entity", "ExecutionStep", "Session"]:
            items = by_type.get(typ, [])
            if not items:
                continue
            lines.append(f"### {typ}s")
            for item in items:
                name = item.get("name") or item.get("content", "")[:80]
                nid = (item.get("skill_id") or item.get("entity_id")
                    or item.get("sop_id") or item.get("id", ""))
                conf = item.get("confidence", "?")
                score = item.get("_score", 0)
                if typ == "Entity":
                    etype = item.get("entity_type", "?")
                    lines.append(f"- **{nid}** [{etype}] (score:{score}, conf:{conf})")
                else:
                    lines.append(f"- **{nid}** (score:{score}, conf:{conf})")
                lines.append(f"  {name}")
                if typ == "Skill" and item.get("stage"):
                    lines.append(f"  stage={item['stage']} dir={item.get('dir', '')}")
                if typ == "Entity" and item.get("properties"):
                    lines.append(f"  props={item['properties']}")
        return ToolResult(call_id=call_id, name="memory_search", success=True, output="\n".join(lines))

    async def _rag_global(self, call_id: str, question: str, top_k: int) -> ToolResult:
        """Global search: aggregate entities by type and category.
        Phase 5 TODO: GDS Louvain community detection for deeper clustering."""
        query = """
            MATCH (s:Skill)-[:REFERENCES]->(e:Entity)
            WITH s.category AS theme, e.entity_type AS etype,
                 collect(DISTINCT {name: e.name, content: e.content}) AS entities,
                 count(*) AS cnt
            WHERE cnt > 1
            RETURN theme, etype, entities, cnt ORDER BY cnt DESC LIMIT $top_k
        """
        records = await self._neo4j.run(query, {"top_k": top_k})
        lines = [f"## GraphRAG Results (global, top {top_k} clusters)"]
        lines.append(f"Query: {question[:200]}\n")
        for r in records:
            lines.append(f"### {r['theme']} / {r['etype']} ({r['cnt']} entities)")
            for e in r["entities"][:5]:
                lines.append(f"- [{e['etype']}] {e['name']}: {e['content'][:120]}")
        return ToolResult(call_id=call_id, name="memory_search", success=True, output="\n".join(lines))
```

- [ ] **Step 2: Write checkpoint.py**

```python
from tools.base import BaseTool, ToolSchema, ToolCall, ToolResult
from memory.neo4j_client import Neo4jClient


class UpdateWorkingCheckpointTool(BaseTool):
    def __init__(self, neo4j: Neo4jClient):
        self._neo4j = neo4j

    def schema(self):
        return ToolSchema(
            name="update_working_checkpoint",
            description="Update working memory key_info block. Records current goal, key findings, and next steps. Auto-propagated to future rounds.",
            parameters={
                "type": "object",
                "properties": {
                    "goal": {"type": "string", "description": "Current task goal"},
                    "findings": {"type": "string", "description": "Key findings so far"},
                    "next_steps": {"type": "string", "description": "Planned next steps"},
                    "session_id": {"type": "string", "description": "Current session ID"},
                },
                "required": ["session_id"],
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        sid = call.arguments["session_id"]
        goal = call.arguments.get("goal", "")
        findings = call.arguments.get("findings", "")
        next_steps = call.arguments.get("next_steps", "")
        key_info = f"Goal: {goal}\nFindings: {findings}\nNext: {next_steps}"
        await self._neo4j.run(
            "MERGE (s:Session {session_id: $sid}) SET s.key_info = $key_info",
            {"sid": sid, "key_info": key_info},
        )
        return ToolResult(call_id=call.id, name="update_working_checkpoint", success=True, output="Checkpoint updated")
```

- [ ] **Step 3: Write long_term_update.py**

```python
from tools.base import BaseTool, ToolSchema, ToolCall, ToolResult
from memory.neo4j_client import Neo4jClient


class StartLongTermUpdateTool(BaseTool):
    def __init__(self, neo4j: Neo4jClient):
        self._neo4j = neo4j

    def schema(self):
        return ToolSchema(
            name="start_long_term_update",
            description="Signal the subconscious loop to distill current execution experience into long-term memory (L2/L3).",
            parameters={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "reason": {"type": "string", "enum": ["subgoal_completed", "fault_recovery", "reusable_pattern"]},
                    "summary": {"type": "string", "description": "What was learned"},
                },
                "required": ["session_id", "reason", "summary"],
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        sid = call.arguments["session_id"]
        reason = call.arguments["reason"]
        summary = call.arguments["summary"]
        await self._neo4j.run(
            """CREATE (r:DistillationRequest {
                session_id: $sid, reason: $reason, summary: $summary,
                status: 'pending', created_at: datetime()
            })""",
            {"sid": sid, "reason": reason, "summary": summary},
        )
        return ToolResult(call_id=call.id, name="start_long_term_update", success=True, output="Distillation request queued")
```

- [ ] **Step 4: Write skill_manage.py**

```python
from tools.base import BaseTool, ToolSchema, ToolCall, ToolResult
from memory.neo4j_client import Neo4jClient


class SkillManageTool(BaseTool):
    def __init__(self, neo4j: Neo4jClient):
        self._neo4j = neo4j

    def schema(self):
        return ToolSchema(
            name="skill_manage",
            description="Manage Skill lifecycle: register new Skill, evolve stage, deprecate, or link relationships.",
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["register", "evolve", "deprecate", "link"]},
                    "skill_id": {"type": "string"},
                    "name": {"type": "string", "description": "Skill name (register)"},
                    "category": {"type": "string", "description": "Skill category (register)"},
                    "dir": {"type": "string", "description": "Skill directory path (register)"},
                    "new_stage": {"type": "string", "description": "Target stage (evolve)"},
                    "relation": {"type": "string", "enum": ["DEPENDS_ON", "CONFLICTS_WITH", "ALTERNATIVE_TO"], "description": "Relationship type (link)"},
                    "target_skill_id": {"type": "string", "description": "Target Skill for relationship (link)"},
                },
                "required": ["action", "skill_id"],
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        action = call.arguments["action"]
        sid = call.arguments["skill_id"]
        try:
            if action == "register":
                await self._neo4j.run(
                    """CREATE (s:Skill {
                        skill_id: $sid, name: $name, category: $cat, stage: 'NL',
                        version: 1, dir: $dir, usage_count: 0, success_rate: 0.0,
                        activation: 1.0, confidence: 0.0, created_at: datetime()
                    })""",
                    {"sid": sid, "name": call.arguments["name"], "cat": call.arguments["category"], "dir": call.arguments["dir"]},
                )
                return ToolResult(call_id=call.id, name="skill_manage", success=True, output=f"Skill {sid} registered")
            elif action == "evolve":
                new_stage = call.arguments["new_stage"]
                await self._neo4j.run(
                    "MATCH (s:Skill {skill_id: $sid}) SET s.stage = $stage, s.version = s.version + 1, s.updated_at = datetime()",
                    {"sid": sid, "stage": new_stage},
                )
                return ToolResult(call_id=call.id, name="skill_manage", success=True, output=f"Skill {sid} evolved to {new_stage}")
            elif action == "deprecate":
                await self._neo4j.run("MATCH (s:Skill {skill_id: $sid}) SET s.stage = 'DEPRECATED'", {"sid": sid})
                return ToolResult(call_id=call.id, name="skill_manage", success=True, output=f"Skill {sid} deprecated")
            elif action == "link":
                rel = call.arguments["relation"]
                target = call.arguments["target_skill_id"]
                await self._neo4j.run(
                    f"MATCH (a:Skill {{skill_id: $sid}}), (b:Skill {{skill_id: $target}}) MERGE (a)-[:{rel}]->(b)",
                    {"sid": sid, "target": target},
                )
                return ToolResult(call_id=call.id, name="skill_manage", success=True, output=f"Linked {sid} -[{rel}]-> {target}")
            else:
                return ToolResult(call_id=call.id, name="skill_manage", success=False, output="", error=f"Unknown action: {action}")
        except Exception as e:
            return ToolResult(call_id=call.id, name="skill_manage", success=False, output="", error=str(e))
```

- [ ] **Step 5: Write test**

```python
# tests/test_tools/test_memory_tools.py
import pytest
from tools.memory_search import MemorySearchTool
from tools.checkpoint import UpdateWorkingCheckpointTool
from tools.long_term_update import StartLongTermUpdateTool
from tools.skill_manage import SkillManageTool
from tools.base import ToolCall
from memory.neo4j_client import Neo4jClient
from agent.config import Neo4jConfig


def test_memory_search_schema():
    neo4j = Neo4jClient(Neo4jConfig())
    tool = MemorySearchTool(neo4j)
    s = tool.schema()
    assert s.name == "memory_search"
    assert "mode" in s.parameters["required"]


def test_checkpoint_schema():
    neo4j = Neo4jClient(Neo4jConfig())
    tool = UpdateWorkingCheckpointTool(neo4j)
    assert tool.schema().name == "update_working_checkpoint"


def test_skill_manage_schema():
    neo4j = Neo4jClient(Neo4jConfig())
    tool = SkillManageTool(neo4j)
    s = tool.schema()
    assert "action" in s.parameters["required"]


@pytest.mark.asyncio
async def test_skill_manage_register_and_evolve():
    neo4j = Neo4jClient(Neo4jConfig())
    tool = SkillManageTool(neo4j)
    try:
        r1 = await tool.execute(ToolCall(id="c1", name="skill_manage", arguments={
            "action": "register", "skill_id": "test-skill-99",
            "name": "Test", "category": "test", "dir": "skills/test/test-skill-99/",
        }))
        assert r1.success
        r2 = await tool.execute(ToolCall(id="c2", name="skill_manage", arguments={
            "action": "evolve", "skill_id": "test-skill-99", "new_stage": "SOP",
        }))
        assert r2.success
    finally:
        await neo4j.run("MATCH (s:Skill {skill_id: 'test-skill-99'}) DETACH DELETE s")
        await neo4j.close()
```

- [ ] **Step 6: Run tests**

```bash
pytest tests/test_tools/test_memory_tools.py -v
```
Expected: PASS (Neo4j must be running)

- [ ] **Step 7: Commit**

```bash
git add tools/memory_search.py tools/checkpoint.py tools/long_term_update.py tools/skill_manage.py tests/test_tools/test_memory_tools.py
git commit -m "feat: add memory management tools (memory_search, checkpoint, long_term_update, skill_manage)"
```

---

### Task 9: subagent 和 ask_user 工具

**Files:**
- Create: `tools/subagent.py`
- Create: `tools/ask_user.py`
- Create: `tests/test_tools/test_subagent_ask.py`

- [ ] **Step 1: Write subagent.py**

```python
import uuid
from pathlib import Path
from tools.base import BaseTool, ToolSchema, ToolCall, ToolResult
from memory.neo4j_client import Neo4jClient


class SubagentTool(BaseTool):
    def __init__(self, neo4j: Neo4jClient, dispatcher, llm_client, config,
                 workspace_dir: str = "./workspace"):
        self._neo4j = neo4j
        self._dispatcher = dispatcher
        self._llm = llm_client
        self._config = config
        self._workspace = Path(workspace_dir)

    def schema(self):
        return ToolSchema(
            name="subagent",
            description="Spawn an independent sub-agent to handle a subtask. The subagent has its own conscious loop and isolated workspace.",
            parameters={
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Subtask description"},
                    "skill_dirs": {"type": "array", "items": {"type": "string"}, "description": "Skill directories to share"},
                    "max_rounds": {"type": "integer", "description": "Max rounds (default 20)"},
                },
                "required": ["task"],
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        task = call.arguments["task"]
        max_rounds = call.arguments.get("max_rounds", self._config.max_subagent_rounds)
        sub_session_id = f"sub_{uuid.uuid4().hex[:12]}"
        sub_workspace = self._workspace / sub_session_id
        sub_workspace.mkdir(parents=True, exist_ok=True)

        await self._neo4j.run(
            """CREATE (s:Session {
                session_id: $sid, type: 'subagent', parent_session_id: $parent,
                status: 'running', created_at: datetime()
            })""",
            {"sid": sub_session_id, "parent": call.id},
        )

        from agent.conscious import ConsciousLoop
        sub_loop = ConsciousLoop(
            llm_client=self._llm,
            dispatcher=self._dispatcher,
            neo4j=self._neo4j,
            config=self._config,
            session_id=sub_session_id,
            workspace_dir=str(sub_workspace),
        )
        result_text = await sub_loop.run(task, max_rounds=max_rounds)

        await self._neo4j.run(
            "MATCH (s:Session {session_id: $sid}) SET s.status = 'completed'",
            {"sid": sub_session_id},
        )
        return ToolResult(call_id=call.id, name="subagent", success=True, output=result_text)
```

- [ ] **Step 2: Write ask_user.py**

```python
from tools.base import BaseTool, ToolSchema, ToolCall, ToolResult


class AskUserTool(BaseTool):
    def schema(self):
        return ToolSchema(
            name="ask_user",
            description="Request human input when the agent cannot proceed autonomously.",
            parameters={
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "Question for the user"},
                    "options": {"type": "array", "items": {"type": "string"}, "description": "Optional multiple-choice options"},
                },
                "required": ["question"],
            },
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        question = call.arguments["question"]
        options = call.arguments.get("options", [])
        output = f"[ASK_USER] {question}"
        if options:
            output += "\nOptions: " + ", ".join(options)
        return ToolResult(call_id=call.id, name="ask_user", success=True, output=output)
```

- [ ] **Step 3: Write test**

```python
# tests/test_tools/test_subagent_ask.py
import asyncio
from tools.ask_user import AskUserTool
from tools.base import ToolCall


def test_ask_user_returns_question():
    tool = AskUserTool()
    result = asyncio.run(tool.execute(ToolCall(
        id="c1", name="ask_user",
        arguments={"question": "Which file should I edit?", "options": ["a.py", "b.py"]},
    )))
    assert result.success
    assert "Which file should I edit?" in result.output
    assert "a.py" in result.output
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_tools/test_subagent_ask.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/subagent.py tools/ask_user.py tests/test_tools/test_subagent_ask.py
git commit -m "feat: add subagent and ask_user tools"
```

---

### Task 10: L1 索引管理

**Files:**
- Create: `memory/index.py`
- Create: `tests/test_memory/test_index.py`

- [ ] **Step 1: Write memory/index.py**

```python
from memory.neo4j_client import Neo4jClient


class L1Index:
    """L1 memory index: manages Skill node metadata for routing."""

    def __init__(self, neo4j: Neo4jClient):
        self._neo4j = neo4j

    async def search_skills(
        self,
        category: str | None = None,
        stage: str | None = None,
        keyword: str | None = None,
        context_tags: list[str] | None = None,
        top_k: int = 5,
    ) -> list[dict]:
        query = "MATCH (s:Skill) WHERE s.stage <> 'DEPRECATED'"
        params: dict = {}
        if category:
            query += " AND s.category = $category"
            params["category"] = category
        if stage:
            query += " AND s.stage = $stage"
            params["stage"] = stage
        if keyword:
            query += " AND (s.name CONTAINS $kw OR s.skill_id CONTAINS $kw)"
            params["kw"] = keyword
        if context_tags:
            tag_conds = " OR ".join(["$tag_" + str(i) + " IN s.context_tags" for i in range(len(context_tags))])
            query += f" AND ({tag_conds})"
            for i, tag in enumerate(context_tags):
                params[f"tag_{i}"] = tag
        query += " RETURN s ORDER BY s.activation DESC, s.usage_count DESC LIMIT $top_k"
        params["top_k"] = top_k
        records = await self._neo4j.run(query, params)
        return [r["s"] for r in records]

    async def get_skill(self, skill_id: str) -> dict | None:
        records = await self._neo4j.run(
            "MATCH (s:Skill {skill_id: $sid}) RETURN s", {"sid": skill_id},
        )
        return records[0]["s"] if records else None

    async def update_activation(self, skill_id: str, delta: float):
        await self._neo4j.run(
            "MATCH (s:Skill {skill_id: $sid}) SET s.activation = s.activation + $delta",
            {"sid": skill_id, "delta": delta},
        )

    async def decay_activation(self, days_threshold: int = 7, decay_rate: float = 0.95):
        await self._neo4j.run(
            """MATCH (s:Skill)
               WHERE s.updated_at < datetime() - duration({days: $days})
               SET s.activation = s.activation * $rate""",
            {"days": days_threshold, "rate": decay_rate},
        )
```

- [ ] **Step 2: Write test**

```python
# tests/test_memory/test_index.py
import pytest
from memory.neo4j_client import Neo4jClient
from memory.index import L1Index
from agent.config import Neo4jConfig


@pytest.mark.asyncio
async def test_search_skills_by_category():
    neo4j = Neo4jClient(Neo4jConfig())
    idx = L1Index(neo4j)
    try:
        await neo4j.run("""MERGE (s:Skill {skill_id: 'idx-test'})
            SET s.name = 'IndexTest', s.category = 'test', s.stage = 'NL',
                s.version = 1, s.activation = 1.0, s.usage_count = 5,
                s.dir = 'skills/test/idx-test/'""")
        results = await idx.search_skills(category="test")
        assert any(r["skill_id"] == "idx-test" for r in results)
    finally:
        await neo4j.run("MATCH (s:Skill {skill_id: 'idx-test'}) DETACH DELETE s")
        await neo4j.close()
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_memory/test_index.py -v
```
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add memory/index.py tests/test_memory/test_index.py
git commit -m "feat: add L1 index with search, activation management, and decay"
```

---

### Task 11: 压缩管道

**Files:**
- Create: `agent/compression.py`
- Create: `tests/test_agent/test_compression.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_agent/test_compression.py
from agent.compression import CompressionPipeline, truncate_head_tail


def test_truncate_head_tail_short():
    result = truncate_head_tail("hello", max_len=100)
    assert result == "hello"


def test_truncate_head_tail_long():
    text = "a" * 5000
    result = truncate_head_tail(text, max_len=1000)
    assert len(result) <= 1000 + 100   # allowance for ellipsis marker
    assert result.startswith("a")
    assert result.endswith("a")


def test_truncate_head_tail_preserves_ends():
    text = "START" + "x" * 5000 + "END"
    result = truncate_head_tail(text, max_len=1000)
    assert "START" in result
    assert "END" in result


def test_compression_stage2_exempts_recent():
    pipeline = CompressionPipeline(context_budget_chars=90000)
    messages = [{"role": "user", "content": f"msg {i}"} for i in range(20)]
    # Only compress messages beyond the 10 most recent
    compressed = pipeline.stage2_compress_tags(messages, recent_exempt=10)
    assert len(compressed) == len(messages)
    # Recent 10 should be untouched
    for i in range(10, 20):
        assert compressed[i]["content"] == f"msg {i}"


def test_compression_stage3_evicts_oldest():
    pipeline = CompressionPipeline(context_budget_chars=500)
    messages = []
    for i in range(50):
        messages.append({"role": "user", "content": f"msg {i}"})
        messages.append({"role": "assistant", "content": f"response {i}"})
    evicted = pipeline.stage3_evict(messages)
    assert len(evicted) < len(messages)
    assert evicted[0]["role"] == "user"   # post-repair starts with user
```

- [ ] **Step 2: Run tests (expected FAIL)**

```bash
pytest tests/test_agent/test_compression.py -v
```
Expected: FAIL

- [ ] **Step 3: Write agent/compression.py**

```python
def truncate_head_tail(text: str, max_len: int = 10000) -> str:
    """Keep first max_len/2 and last max_len/2 characters."""
    if len(text) <= max_len:
        return text
    half = max_len // 2
    return text[:half] + f"\n... [{len(text) - max_len} chars truncated] ...\n" + text[-half:]


class CompressionPipeline:
    def __init__(self, context_budget_chars: int = 90000):
        self.budget = context_budget_chars

    def stage1_tool_output(self, tool_name: str, output: str) -> str:
        """Stage 1: Tool-level truncation."""
        thresholds = {
            "code_run": 10000,
            "web_execute_js": 8000,
            "web_scan": 10000,
            "file_read": 20000,
            "memory_search": 0,    # keep full - already compact
        }
        limit = thresholds.get(tool_name, 10000)
        if limit == 0 or len(output) <= limit:
            return output
        return truncate_head_tail(output, max_len=limit)

    def stage2_compress_tags(self, messages: list[dict], recent_exempt: int = 10) -> list[dict]:
        """Stage 2: Replace old working memory blocks with placeholders."""
        result = []
        for i, msg in enumerate(messages):
            is_recent = i >= len(messages) - recent_exempt
            if is_recent:
                result.append(msg)
                continue
            content = msg.get("content", "")
            if len(content) > 800:
                result.append({**msg, "content": truncate_head_tail(content, max_len=800)})
            else:
                result.append(msg)
        return result

    def stage3_evict(self, messages: list[dict]) -> list[dict]:
        """Stage 3: FIFO eviction until under 0.6 * budget. Ensures starts with user."""
        target = int(self.budget * 0.6)
        while self._char_count(messages) > target and len(messages) > 5 + 4:
            messages = messages[1:]
        # structural repair: ensure starts with user message
        while messages and messages[0].get("role") != "user":
            messages = messages[1:]
        return messages

    def _char_count(self, messages: list[dict]) -> int:
        import json
        return sum(len(json.dumps(m)) for m in messages)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_agent/test_compression.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/compression.py tests/test_agent/test_compression.py
git commit -m "feat: add 4-stage compression pipeline (truncation, tag compression, eviction)"
```

---

### Task 12: 上下文组装

**Files:**
- Create: `agent/context.py`
- Create: `tests/test_agent/test_context.py`

- [ ] **Step 1: Write agent/context.py**

```python
from llm.base import Message
from tools.dispatcher import ToolDispatcher


SYSTEM_PROMPT = """You are {agent_name}, an autonomous agent with skill self-evolution capability.

## Meta-Memory: Memory Map
Your memory is organized in 6 layers stored in Neo4j:
- L0 Episodic: execution step chains, each step = one AgentScope-style Msg
- L1 Index: Skill metadata (name, category, stage, context_tags). ALWAYS search here first.
- L2 Facts: verified, reusable facts with structured properties and provenance
- L3 SOPs: standard operating procedures with preconditions and execution steps
- L4 Meta-Patterns: abstract cross-domain strategies (shared patterns across Skills)
- L5 Archive: compressed historical logs on filesystem

## Meta-Memory: Core Rules
1. **L1 First**: Use memory_search(mode="route") to find relevant Skills before acting.
2. **No Execution, No Memory**: Only write execution-verified knowledge to L2/L3 via start_long_term_update.
3. **Cross-Task Reusability**: Don't store one-time context as permanent memory. Write only what future tasks need.
4. **Incremental Update**: Small targeted additions to memory, never full overwrites.
5. **Read What You Need**: Use file_read with range/keyword anchoring, not full-file dumps.
6. **One code_run Per Round**: Observe results before deciding the next action.
7. **Persist Findings**: Use update_working_checkpoint to record goals, key findings, and next steps.

## Memory Acquisition Workflow
When starting a task, follow this pattern:
1. memory_search(mode="route", keyword="<task keywords>") → find candidate Skills
2. file_read("{skill.dir}/SKILL.md") → load Skill documentation
3. memory_search(mode="load", skill_id="...") → load related Facts, SOPs, and dependencies
4. If no matching Skill exists, proceed with available tools and register new Skill via skill_manage

## Available Tools
{tool_descriptions}

## Working Memory
Turn: {turn_number}
Recent: {recent_summaries}
Key Info: {key_info}
"""


class ContextBuilder:
    def __init__(self, dispatcher: ToolDispatcher, agent_name: str = "infoCap"):
        self._dispatcher = dispatcher
        self._agent_name = agent_name
        self._tool_descriptions = self._build_tool_descriptions()

    def _build_tool_descriptions(self) -> str:
        lines = []
        for schema in self._dispatcher.get_schemas():
            f = schema["function"]
            lines.append(f"- **{f['name']}**: {f['description']}")
        return "\n".join(lines)

    def build_system_prompt(
        self,
        turn_number: int = 0,
        recent_summaries: str = "(none)",
        key_info: str = "(no key info yet)",
    ) -> str:
        return SYSTEM_PROMPT.format(
            agent_name=self._agent_name,
            tool_descriptions=self._tool_descriptions,
            turn_number=turn_number,
            recent_summaries=recent_summaries,
            key_info=key_info,
        )

    def build_messages(
        self,
        user_message: str,
        history: list[Message],
        turn_number: int = 0,
        recent_summaries: str = "(none)",
        key_info: str = "(no key info yet)",
    ) -> list[Message]:
        """Assemble the full message list for an LLM call.
        
        Always-on layer:
          - System prompt with meta-memory + tool descriptions
          - Working memory anchors (turn summaries + key_info)
          - Compressed conversation history
        
        On-demand layer (not auto-injected; loaded by agent via tool calls):
          - L1 index routing → memory_search
          - SKILL.md → file_read
          - L2/L3 memories → memory_search mode=load
          - Historical traces → memory_search mode=trace
        """
        system = self.build_system_prompt(turn_number, recent_summaries, key_info)
        messages = [Message(role="system", content=system)]
        messages.extend(history)
        messages.append(Message(role="user", content=user_message))
        return messages

    def wrap_tool_result(self, tool_name: str, tool_output: str, call_id: str) -> Message:
        return Message(role="tool", content=tool_output, tool_call_id=call_id, name=tool_name)

    def wrap_assistant(self, content: str | None, tool_calls) -> Message:
        if tool_calls:
            tool_call_text = "\n".join(
                f"[ToolCall: {tc.name}({tc.arguments})]" for tc in tool_calls
            )
            return Message(role="assistant", content=content or tool_call_text)
        return Message(role="assistant", content=content or "")
```

- [ ] **Step 2: Write test**

```python
# tests/test_agent/test_context.py
from agent.context import ContextBuilder
from tools.dispatcher import ToolDispatcher
from tools.ask_user import AskUserTool
from llm.base import Message


def test_context_builds_system_prompt():
    dispatcher = ToolDispatcher()
    dispatcher.register(AskUserTool())
    builder = ContextBuilder(dispatcher)
    prompt = builder.build_system_prompt(turn_number=1)
    assert "ask_user" in prompt
    assert "Meta-Memory" in prompt
    assert "Core Rules" in prompt
    assert "L1 First" in prompt


def test_build_messages_includes_always_on_layer():
    dispatcher = ToolDispatcher()
    builder = ContextBuilder(dispatcher)
    msgs = builder.build_messages(
        user_message="hello",
        history=[],
        turn_number=3,
        recent_summaries="  [1] searched files\n  [2] found config",
        key_info="Goal: read config\nFindings: port=7687",
    )
    assert msgs[0].role == "system"
    assert "Turn: 3" in msgs[0].content
    assert "searched files" in msgs[0].content
    assert "port=7687" in msgs[0].content
    assert msgs[-1].role == "user"
    assert msgs[-1].content == "hello"


def test_working_memory_defaults():
    dispatcher = ToolDispatcher()
    builder = ContextBuilder(dispatcher)
    prompt = builder.build_system_prompt()
    assert "(none)" in prompt
    assert "(no key info yet)" in prompt
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_agent/test_context.py -v
```
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add agent/context.py tests/test_agent/test_context.py
git commit -m "feat: add context builder with system prompt and message assembly"
```

---

### Task 13: 意识循环引擎

**Files:**
- Create: `agent/conscious.py`
- Create: `agent/engine.py`
- Create: `tests/test_agent/test_conscious.py`

- [ ] **Step 1: Write agent/conscious.py**

```python
import uuid
from pathlib import Path
from llm.base import LlmClient, Message, ToolCall as LlmToolCall
from tools.dispatcher import ToolDispatcher
from tools.base import ToolCall as DispatchToolCall
from memory.neo4j_client import Neo4jClient
from memory.index import L1Index
from agent.context import ContextBuilder
from agent.compression import CompressionPipeline
from agent.config import Config


class ConsciousLoop:
    def __init__(
        self,
        llm_client: LlmClient,
        dispatcher: ToolDispatcher,
        neo4j: Neo4jClient,
        config: Config,
        session_id: str | None = None,
        workspace_dir: str | None = None,
    ):
        self._llm = llm_client
        self._dispatcher = dispatcher
        self._neo4j = neo4j
        self._config = config
        self._index = L1Index(neo4j)
        self._context_builder = ContextBuilder(dispatcher)
        self._compression = CompressionPipeline(
            context_budget_chars=config.context_budget_tokens * 3
        )
        self.session_id = session_id or f"sess_{uuid.uuid4().hex[:12]}"
        self._workspace = Path(workspace_dir or config.workspace_dir)
        self._workspace.mkdir(parents=True, exist_ok=True)
        self._history: list[Message] = []
        self._turn_count = 0
        self._last_20_summaries: list[str] = []

    async def run(self, user_input: str, max_rounds: int = 30) -> str:
        """Execute the conscious loop until the task is complete or max_rounds reached."""
        await self._neo4j.run(
            """CREATE (s:Session {session_id: $sid, type: 'main', status: 'running',
               created_at: datetime(), turn_count: 0})""",
            {"sid": self.session_id},
        )

        for round_idx in range(max_rounds):
            self._turn_count = round_idx + 1

            # Stage 2 compression every 5 rounds
            if self._turn_count > 1 and self._turn_count % 5 == 0:
                self._history = self._compression.stage2_compress_tags(
                    [{"role": m.role, "content": m.content} for m in self._history]
                )
                self._history = [Message(**m) for m in self._history]

            # Build working memory anchors
            total = len(self._last_20_summaries)
            start = max(0, total - 5)
            recent_text = "\n".join(
                f"  [{total - i}] {s}"
                for i, s in enumerate(reversed(self._last_20_summaries[start:total]))
            )
            key_info = await self._get_key_info()

            # Build messages: for round 0, pass user_input directly; later rounds use "(continue)"
            # User message is recorded in history AFTER building to avoid duplication
            current_input = user_input if round_idx == 0 else "(continue)"
            messages = self._context_builder.build_messages(
                user_message=current_input,
                history=self._history,
                turn_number=self._turn_count,
                recent_summaries=recent_text or "(none)",
                key_info=key_info,
            )
            # Record user message in history for future rounds
            if round_idx == 0:
                self._history.append(Message(role="user", content=user_input))

            # LLM call
            tool_schemas = self._dispatcher.get_schemas()
            response = await self._llm.chat(messages, tool_schemas)

            # If no tool calls, task is complete
            if not response.tool_calls:
                final = response.content or "Task completed."
                self._history.append(Message(role="assistant", content=final))
                await self._finalize_session()
                return final

            # Execute tool calls
            for tc in response.tool_calls:
                result = await self._dispatcher.dispatch(
                    DispatchToolCall(id=tc.id, name=tc.name, arguments=tc.arguments)
                )

                # Stage 1: tool output truncation
                truncated_output = self._compression.stage1_tool_output(tc.name, result.output)

                # Log to L0 as AgentScope-aligned ExecutionStep (Msg with ContentBlocks)
                await self._log_execution_step(tc.name, tc.id, tc.arguments, truncated_output[:200])

                # Add to history
                self._history.append(Message(
                    role="assistant",
                    content=f"Tool: {tc.name}({tc.arguments})",
                ))
                self._history.append(Message(
                    role="tool",
                    content=truncated_output,
                    tool_call_id=tc.id,
                    name=tc.name,
                ))

            # Stage 3 eviction if over budget
            raw_msgs = [{"role": m.role, "content": m.content} for m in self._history]
            if self._compression._char_count(raw_msgs) > self._compression.budget:
                self._history = [
                    Message(**m) for m in self._compression.stage3_evict(raw_msgs)
                ]

            # Stage 4: working memory anchor (simplified)
            self._last_20_summaries.append(f"Round {self._turn_count}: {response.content or 'tool calls'}")
            if len(self._last_20_summaries) > 20:
                self._last_20_summaries = self._last_20_summaries[-20:]

            # Update session turn count
            await self._neo4j.run(
                "MATCH (s:Session {session_id: $sid}) SET s.turn_count = $tc",
                {"sid": self.session_id, "tc": self._turn_count},
            )

        await self._finalize_session()
        return "Max rounds reached."

    async def _log_execution_step(self, tool_name: str, tool_call_id: str, arguments: dict, output: str):
        """Create ExecutionStep as AgentScope-aligned Msg with ContentBlocks."""
        import shortuuid
        step_id = f"msg_{shortuuid.uuid()[:10]}"
        step_data = {
            "id": step_id,
            "name": tool_name,
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": tool_call_id, "name": tool_name, "input": arguments},
                {"type": "tool_result", "id": tool_call_id, "name": tool_name, "output": output},
            ],
            "metadata": {"session_id": self.session_id, "turn": self._turn_count},
            "invocation_id": getattr(self, "_last_invocation_id", None),
        }
        await self._neo4j.run(
            """MATCH (s:Session {session_id: $sid})
               CREATE (s)-[:HAS_STEP]->(:ExecutionStep {
                 id: $data.id, name: $data.name, role: $data.role,
                 content: $data.content, metadata: $data.metadata,
                 timestamp: datetime(), invocation_id: $data.invocation_id
               })""",
            {"sid": self.session_id, "data": step_data},
        )

    async def _get_key_info(self) -> str:
        records = await self._neo4j.run(
            "MATCH (s:Session {session_id: $sid}) RETURN s.key_info",
            {"sid": self.session_id},
        )
        if records and records[0].get("s.key_info"):
            return records[0]["s.key_info"]
        return "(no key info yet)"

    async def _finalize_session(self):
        await self._neo4j.run(
            "MATCH (s:Session {session_id: $sid}) SET s.status = 'completed'",
            {"sid": self.session_id},
        )
```

- [ ] **Step 2: Write agent/engine.py**

```python
from agent.config import Config
from llm.openai_client import OpenAIClient
from llm.deepseek_client import DeepSeekClient
from memory.neo4j_client import Neo4jClient
from tools.dispatcher import ToolDispatcher
from tools.file_ops import FileReadTool, FileWriteTool, FilePatchTool
from tools.code_run import CodeRunTool
from tools.web_interact import WebScanTool, WebExecuteJsTool
from tools.memory_search import MemorySearchTool
from tools.checkpoint import UpdateWorkingCheckpointTool
from tools.long_term_update import StartLongTermUpdateTool
from tools.skill_manage import SkillManageTool
from tools.ask_user import AskUserTool
from tools.subagent import SubagentTool
from agent.conscious import ConsciousLoop


class AgentEngine:
    def __init__(self, config: Config):
        self.config = config
        self.neo4j = Neo4jClient(config.neo4j)
        if config.llm.provider == "openai":
            self.llm = OpenAIClient(config.llm)
        elif config.llm.provider == "deepseek":
            self.llm = DeepSeekClient(config.llm)
        else:
            raise ValueError(f"Unknown LLM provider: {config.llm.provider}")
        self.dispatcher = ToolDispatcher()
        self._web_scan_tool = WebScanTool()  # Shared browser for web_scan + web_execute_js
        self._register_tools()

    def _register_tools(self):
        self.dispatcher.register(FileReadTool())
        self.dispatcher.register(FileWriteTool())
        self.dispatcher.register(FilePatchTool())
        self.dispatcher.register(CodeRunTool(self.config.workspace_dir))
        self.dispatcher.register(self._web_scan_tool)
        self.dispatcher.register(WebExecuteJsTool(self._web_scan_tool))
        self.dispatcher.register(MemorySearchTool(self.neo4j))
        self.dispatcher.register(UpdateWorkingCheckpointTool(self.neo4j))
        self.dispatcher.register(StartLongTermUpdateTool(self.neo4j))
        self.dispatcher.register(SkillManageTool(self.neo4j))
        self.dispatcher.register(AskUserTool())
        self.dispatcher.register(SubagentTool(
            self.neo4j, self.dispatcher, self.llm, self.config,
        ))

    async def init(self):
        await self.neo4j.init_schema()

    async def run(self, user_input: str, session_id: str | None = None) -> str:
        loop = ConsciousLoop(
            llm_client=self.llm,
            dispatcher=self.dispatcher,
            neo4j=self.neo4j,
            config=self.config,
            session_id=session_id,
        )
        return await loop.run(user_input)

    async def close(self):
        await self.neo4j.close()
```

- [ ] **Step 3: Write test**

```python
# tests/test_agent/test_conscious.py
import pytest
from agent.config import Config
from agent.engine import AgentEngine


def test_engine_creates_with_config():
    config = Config()
    engine = AgentEngine(config)
    assert len(engine.dispatcher.tool_names()) == 12


def test_engine_has_all_required_tools():
    config = Config()
    engine = AgentEngine(config)
    names = engine.dispatcher.tool_names()
    required = [
        "file_read", "file_patch", "file_write",
        "code_run", "web_scan", "web_execute_js",
        "memory_search", "update_working_checkpoint",
        "start_long_term_update", "skill_manage",
        "subagent", "ask_user",
    ]
    for name in required:
        assert name in names, f"Missing tool: {name}"
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_agent/test_conscious.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/conscious.py agent/engine.py tests/test_agent/test_conscious.py
git commit -m "feat: add conscious loop and agent engine wiring all 12 tools"
```

---

### Task 14: FastAPI + WebSocket 服务

**Files:**
- Create: `server/main.py`
- Create: `server/ws.py`
- Create: `server/api/__init__.py`
- Create: `server/api/chat.py`
- Create: `tests/test_server/test_api.py`

- [ ] **Step 1: Write server/ws.py**

```python
import json
from fastapi import WebSocket, WebSocketDisconnect
from agent.engine import AgentEngine


class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, WebSocket] = {}

    async def connect(self, session_id: str, ws: WebSocket):
        await ws.accept()
        self._connections[session_id] = ws

    def disconnect(self, session_id: str):
        self._connections.pop(session_id, None)

    async def send(self, session_id: str, data: dict):
        ws = self._connections.get(session_id)
        if ws:
            await ws.send_text(json.dumps(data))


class ChatHandler:
    def __init__(self, engine: AgentEngine):
        self._engine = engine
        self._manager = ConnectionManager()

    async def handle(self, ws: WebSocket):
        session_id = ws.headers.get("x-session-id", "default")
        await self._manager.connect(session_id, ws)
        try:
            while True:
                msg = await ws.receive_text()
                data = json.loads(msg)
                user_input = data.get("content", "")

                await self._manager.send(session_id, {
                    "type": "status", "status": "thinking",
                })

                # Run conscious loop
                result = await self._engine.run(user_input, session_id=session_id)

                await self._manager.send(session_id, {
                    "type": "message", "content": result,
                })
        except WebSocketDisconnect:
            self._manager.disconnect(session_id)
```

- [ ] **Step 2: Write server/main.py**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from agent.config import Config
from agent.engine import AgentEngine


_engine: AgentEngine | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _engine
    config = Config()
    _engine = AgentEngine(config)
    await _engine.init()
    yield
    await _engine.close()


app = FastAPI(title="infoCap", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.websocket("/ws/chat")
async def chat_ws(ws):
    from server.ws import ChatHandler
    handler = ChatHandler(_engine)
    await handler.handle(ws)
```

- [ ] **Step 3: Write test**

```python
# tests/test_server/test_api.py
from fastapi.testclient import TestClient
from server.main import app


def test_health_endpoint():
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
```

- [ ] **Step 4: Run server to verify**

```bash
uvicorn server.main:app --host 0.0.0.0 --port 8000 &
sleep 2
curl http://localhost:8000/api/health
kill %1
```
Expected: `{"status":"ok"}`

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_server/test_api.py -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add server/ tests/test_server/
git commit -m "feat: add FastAPI server with WebSocket chat endpoint"
```

---

### Task 15: 基本 Web UI (Next.js)

**Files:**
- Create: `webui/` (Next.js 14+ project via create-next-app)
- Modify: `webui/src/app/page.tsx`
- Create: `webui/src/app/layout.tsx`

- [ ] **Step 1: Scaffold Next.js project**

```bash
cd webui && npx create-next-app@latest . --typescript --tailwind --app --no-src-dir --import-alias "@/*" --yes
```

- [ ] **Step 2: Write webui/app/layout.tsx**

```tsx
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "infoCap",
  description: "Self-evolving Agent Platform",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="bg-zinc-950 text-zinc-100 min-h-screen">{children}</body>
    </html>
  );
}
```

- [ ] **Step 3: Write webui/app/page.tsx (Chat UI)**

```tsx
"use client";

import { useState, useRef, useEffect } from "react";

type Message = { role: "user" | "assistant" | "status"; content: string };

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ws = new WebSocket("ws://localhost:8000/ws/chat");
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.type === "status") {
        setMessages((prev) => [...prev, { role: "status", content: "Thinking..." }]);
      } else if (data.type === "message") {
        setMessages((prev) => {
          const filtered = prev.filter((m) => m.role !== "status");
          return [...filtered, { role: "assistant", content: data.content }];
        });
      }
    };
    wsRef.current = ws;
    return () => ws.close();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = () => {
    if (!input.trim() || !wsRef.current) return;
    setMessages((prev) => [...prev, { role: "user", content: input }]);
    wsRef.current.send(JSON.stringify({ content: input }));
    setInput("");
  };

  return (
    <div className="max-w-3xl mx-auto h-screen flex flex-col p-4">
      <div className="flex items-center gap-2 py-4 border-b border-zinc-800">
        <div className={`w-2 h-2 rounded-full ${connected ? "bg-green-500" : "bg-red-500"}`} />
        <h1 className="text-lg font-semibold">infoCap</h1>
        <span className="text-xs text-zinc-500">Self-evolving Agent</span>
      </div>
      <div className="flex-1 overflow-y-auto py-4 space-y-3">
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[80%] rounded-lg px-4 py-2 text-sm ${
              m.role === "user"
                ? "bg-blue-600 text-white"
                : m.role === "status"
                ? "bg-zinc-800 text-zinc-400 italic"
                : "bg-zinc-800 text-zinc-200"
            }`}>
              <pre className="whitespace-pre-wrap font-sans">{m.content}</pre>
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      <div className="flex gap-2 py-4 border-t border-zinc-800">
        <input
          className="flex-1 bg-zinc-800 rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          placeholder="Send a message..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
        />
        <button
          className="bg-blue-600 hover:bg-blue-700 rounded-lg px-6 py-2 text-sm font-medium transition-colors"
          onClick={send}
        >
          Send
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Start dev server and verify**

```bash
cd webui && npm run dev &
```
Expected: Next.js dev server at http://localhost:3000

- [ ] **Step 5: Commit**

```bash
git add webui/
git commit -m "feat: add Next.js chat UI with WebSocket streaming"
```

---

### Task 16: 集成测试 (端到端)

**Files:**
- Create: `tests/test_integration/test_e2e.py`
- Create: `.env.example`

- [ ] **Step 1: Write .env.example**

```bash
INFOCAP_LLM_PROVIDER=openai
INFOCAP_LLM_MODEL=gpt-4o
INFOCAP_LLM_API_KEY=sk-your-key-here
INFOCAP_LLM_BASE_URL=
INFOCAP_NEO4J_URI=bolt://localhost:7687
INFOCAP_NEO4J_USER=neo4j
INFOCAP_NEO4J_PASSWORD=infocap123
INFOCAP_CONTEXT_BUDGET_TOKENS=30000
```

- [ ] **Step 2: Write integration test**

```python
# tests/test_integration/test_e2e.py
import pytest
from agent.config import Config
from agent.engine import AgentEngine


@pytest.mark.asyncio
@pytest.mark.integration
async def test_engine_runs_simple_task():
    config = Config()
    engine = AgentEngine(config)
    await engine.init()
    try:
        result = await engine.run("Reply with just the word 'OK' and nothing else.")
        assert result is not None
        assert len(result) > 0
    finally:
        await engine.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_engine_file_read_tool():
    import tempfile, os
    config = Config()
    engine = AgentEngine(config)
    await engine.init()
    try:
        # Write a test file
        tmp = os.path.join(tempfile.gettempdir(), "infocap_test.txt")
        with open(tmp, "w") as f:
            f.write("hello from infocap test\n" * 5)

        result = await engine.run(
            f"Read the file at {tmp} using file_read and tell me the first line."
        )
        assert result is not None
    finally:
        await engine.close()
```

- [ ] **Step 3: Run integration tests**

```bash
INFOCAP_LLM_API_KEY=$YOUR_KEY pytest tests/test_integration/test_e2e.py -v -m integration
```
Expected: Agent responds with "OK" and correctly reads the file.

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration/ .env.example
git commit -m "test: add end-to-end integration tests"
```

---

## Phase 1 完成检查清单

- [x] Task 1: 项目骨架 (pyproject.toml, docker-compose, config)
- [x] Task 2: LLM 客户端 (OpenAI + DeepSeek)
- [x] Task 3: Neo4j 图模型 + 客户端
- [x] Task 4: 工具基类 + 调度器
- [x] Task 5: 文件操作工具 (file_read/patch/write)
- [x] Task 6: 代码执行工具 (code_run)
- [x] Task 7: Web 交互工具 (web_scan/execute_js)
- [x] Task 8: 记忆管理工具 (memory_search/checkpoint/long_term_update/skill_manage)
- [x] Task 9: subagent + ask_user 工具
- [x] Task 10: L1 索引管理
- [x] Task 11: 压缩管道
- [x] Task 12: 上下文组装
- [x] Task 13: 意识循环引擎
- [x] Task 14: FastAPI + WebSocket 服务
- [x] Task 15: Next.js 聊天界面
- [x] Task 16: 集成测试

**启动命令:**
```bash
# Terminal 1: Start Neo4j
docker compose up -d neo4j

# Terminal 2: Start backend
cp .env.example .env   # edit with your API keys
uvicorn server.main:app --host 0.0.0.0 --port 8000

# Terminal 3: Start frontend
cd webui && npm run dev

# Open http://localhost:3000
```
