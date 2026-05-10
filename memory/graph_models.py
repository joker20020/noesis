from dataclasses import dataclass, field
from typing import Any


@dataclass
class Base64Source:
    type: str = "base64"
    media_type: str = ""
    data: str = ""


@dataclass
class URLSource:
    type: str = "url"
    url: str = ""


@dataclass
class ContentBlock:
    """Aligned with AgentScope ContentBlock types."""
    type: str  # "text"|"thinking"|"tool_use"|"tool_result"|"image"|"audio"|"video"
    text: str | None = None
    thinking: str | None = None
    id: str | None = None
    name: str | None = None
    input: dict[str, Any] | None = None
    output: Any = None
    source: Base64Source | URLSource | None = None


@dataclass
class Skill:
    skill_id: str
    name: str
    description: str = ""
    category: str = ""
    stage: str = "NL"
    version: int = 1
    dir: str = ""
    usage_count: int = 0
    success_rate: float = 0.0
    activation: float = 1.0
    confidence: float = 0.0
    context_tags: list[str] = field(default_factory=list)
    embeddings: list[float] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


@dataclass
class EntityNode:
    """L2 open-world knowledge graph node."""
    entity_id: str
    entity_type: str
    name: str
    content: str
    properties: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    source: str = ""
    source_trace: list[str] = field(default_factory=list)
    activation: float = 1.0
    created_at: str = ""
    updated_at: str = ""


@dataclass
class ExecutionStep:
    """Aligned with AgentScope Msg."""
    id: str
    name: str
    role: str
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
    reason: str
    summary: str
    status: str = "pending"
    created_at: str = ""
    processed_at: str = ""
