# infoCap Agent 平台设计规格

## 概述

infoCap 是一个具有 Skill 自进化能力的通用 Agent 平台。架构参考 GenericAgent 论文（9原子工具、四层记忆、三阶段进化），在此基础上进行全面增强：Neo4j 图数据库全量记忆存储、六层记忆架构、显式意识/潜意识双循环、统一 Skill 文件夹结构、subagent 任务委派。

- **语言**: Python
- **界面**: Web UI + 聊天平台适配器
- **定位**: 通用平台级 Agent
- **记忆存储**: Neo4j 全量存储 + 文件系统 Skill 代码关联

---

## 第一部分：意识/潜意识双循环

```
┌──────────────────────────────────────────────────────────────┐
│                    infoCap Agent Platform                     │
├──────────────────────┬───────────────────────────────────────┤
│  意识循环 (Conscious) │  潜意识循环 (Subconscious)             │
│  ~200ms 响应         │  后台异步，分钟级                       │
├──────────────────────┼───────────────────────────────────────┤
│  用户输入             │  定时/空闲触发                         │
│  L1索引路由 (Neo4j)   │  经验蒸馏引擎 → 生成SOP                │
│  记忆加载 (L2/L3)     │  NL→SOP→Code 三阶段编译               │
│  上下文组装           │  自主探索课程规划                      │
│  LLM推理 → 工具调用   │  技能树维护 & 权重自适应               │
│  压缩管道 (四阶段)    │  记忆生命周期 (衰减/巩固/遗忘)          │
│  工作记忆更新         │                                       │
│  响应返回             │                                       │
└──────────────────────┴───────────────────────────────────────┘
            │                          │
            └──────────┬───────────────┘
                    Neo4j 图数据库 (共享记忆中枢)
                       │
                   文件系统 (Skill代码 / L5归档)
```

- 意识循环负责实时交互，延迟敏感
- 潜意识循环负责能力成长，不阻塞前台
- 共享 Neo4j 作为唯一记忆中枢

---

## 第二部分：六层记忆架构

### 层级定义

| 层 | 名称 | 存储 | 说明 |
|----|------|------|------|
| L0 | 情景轨迹 | Neo4j | 每次任务的消息链 (ExecutionStep=一条消息, 含多个ContentBlock) |
| L1 | 语义索引 | Neo4j | Skill元数据 + 嵌入向量 |
| L2 | 开放世界知识图谱 | Neo4j | Entity节点(模型自由定义类型) + Schema关系 + Dynamic关系(模型自主创建) + 置信度溯源 |
| L3 | 程序性知识 | Neo4j | SOP 文本 + 组合/继承/变体/冲突关系 |
| L4 | 元模式 | Neo4j | 跨域抽象策略模式，支持类比迁移 |
| L5 | 深度归档 | 文件系统 | 压缩日志 + 旧版本代码 |

### 三个横切机制

- **记忆生命周期**: 每个记忆节点有 activation 值，衰减函数（未使用→指数下降），巩固（成功使用→强化），遗忘（activation < 阈值 → 降级到 L5）
- **置信度与溯源**: 每个 L2/L3 节点带 `{confidence, source_trace}`，执行验证过的 > 推理得出的 > 推测的。信念修正：修正上游 → 图遍历标记下游受影响节点
- **预判检索**: 基于当前任务上下文 + 历史图模式 → 预测后续需要的记忆 → 预加载，减少检索轮次

### 消息模型：借鉴 AgentScope 的 Msg + ContentBlock 设计

一条 ExecutionStep 对应 AgentScope 的一条 `Msg`——一个完整的对话轮次。消息内容由多个 `ContentBlock` 组成，支持文本、思考、工具调用、工具结果和多模态内容混合承载。

```
ExecutionStep (≡ AgentScope Msg)
═══════════════════════════════════════════

{
    id: "msg_3xK2mP9q",                  // shortuuid, 与 AgentScope Msg.id 一致
    name: "infocap",                      // 发送者名称
    role: "assistant",                    // "system" | "user" | "assistant"
    content: [                            // ≡ AgentScope Msg.content: list[ContentBlock]
        {
            type: "thinking",
            thinking: "我需要先读取配置文件来了解数据库连接参数。"
        },
        {
            type: "tool_use",
            id: "call_abc123",
            name: "file_read",
            input: { "path": "config.yaml" }
        },
        {
            type: "tool_result",
            id: "call_abc123",
            name: "file_read",
            output: "db:\n  host: localhost\n  port: 7687"
        },
        {
            type: "text",
            text: "配置文件中显示 Neo4j 运行在 localhost:7687。"
        },
        {
            type: "image",
            source: {
                "type": "base64",
                "media_type": "image/png",
                "data": "iVBORw0KGgo..."
            }
        }
    ],
    metadata: {                           // 扩展元数据 (可选)
        "session_id": "sess_001",
        "turn": 3,
        "skill_used": "config_reader"
    },
    timestamp: "2026-05-08T12:00:03.000",
    invocation_id: "inv_7f2a9b"           // 关联的 LLM API 调用 ID
}
```

**ExecutionStep 字段对齐 AgentScope Msg：**

| 字段 | 类型 | 来源 | 说明 |
|------|------|------|------|
| `id` | `str` | AgentScope `Msg.id` | shortuuid 生成的消息唯一 ID |
| `name` | `str` | AgentScope `Msg.name` | 发送者名称 (Agent名/工具名) |
| `role` | `str` | AgentScope `Msg.role` | `"system"` \| `"user"` \| `"assistant"` |
| `content` | `list[ContentBlock]` | AgentScope `Msg.content` | 消息内容块列表 |
| `metadata` | `dict \| None` | AgentScope `Msg.metadata` | 扩展元数据 |
| `timestamp` | `str` | AgentScope `Msg.timestamp` | `YYYY-MM-DD HH:MM:SS.fff` |
| `invocation_id` | `str \| None` | AgentScope `Msg.invocation_id` | LLM API 调用链路追踪 |

**ContentBlock 类型定义（对齐 AgentScope）：**

| Block Type | type 值 | 关键字段 | AgentScope 对应 |
|-----------|---------|---------|----------------|
| 文本 | `"text"` | `text: str` | `TextBlock` |
| 思考 | `"thinking"` | `thinking: str` | `ThinkingBlock` |
| 工具调用 | `"tool_use"` | `id: str, name: str, input: dict` | `ToolUseBlock` |
| 工具结果 | `"tool_result"` | `id: str, name: str, output: str \| list[ContentBlock]` | `ToolResultBlock` |
| 图片 | `"image"` | `source: URLSource \| Base64Source` | `ImageBlock` |
| 音频 | `"audio"` | `source: URLSource \| Base64Source` | `AudioBlock` |
| 视频 | `"video"` | `source: URLSource \| Base64Source` | `VideoBlock` |

**Source 联合类型：**
- `URLSource`: `{"type": "url", "url": "https://..."}`
- `Base64Source`: `{"type": "base64", "media_type": "image/png", "data": "..."}`

**对话历史即 ExecutionStep 链：**

```
Session
    │
    [:HAS_STEP]
    ▼
Step_1 (name: "user", role: "user")         ← 用户输入, content=[TextBlock]
    │ [:NEXT]
    ▼
Step_2 (name: "infocap", role: "assistant")  ← LLM 回复, content=[ThinkingBlock, ToolUseBlock]
    │ [:NEXT]
    ▼
Step_3 (name: "file_read", role: "assistant") ← 工具返回, content=[ToolResultBlock]
    │ [:NEXT]
    ▼
Step_4 (name: "infocap", role: "assistant")   ← LLM 最终回复, content=[TextBlock]
```

### L2 开放世界实体

L2 层使用 `Entity` 节点替代固定 `Fact` 类型。实体类型和关系类型由潜意识循环从 L0 自动提取，持续扩展知识图谱。详细定义见[第二部分附录：Neo4j 完整图模型 —— Entity 节点](#entity-节点l2-开放世界知识图谱)。

---

## 第二部分附录：Neo4j 完整图模型

### 节点定义

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              infoCap 图模型全景                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────────┐           │
│  │   User   │    │  Agent   │    │ Session  │    │ Distillation │           │
│  │          │    │          │    │          │    │   Request    │           │
│  └────┬─────┘    └────┬─────┘    └────┬─────┘    └──────────────┘           │
│       │               │               │                                      │
│       │ BELONGS_TO    │ OWNS          │ HAS_STEP                              │
│       ▼               ▼               ▼                                      │
│  ┌──────────┐    ┌──────────┐    ┌────────────────┐                          │
│  │ Session  │    │  Skill   │    │ ExecutionStep  │                          │
│  │          │◄───│          │◄───│  (≡ AgentScope │                          │
│  │          │USED│          │REC │    Msg)        │                          │
│  └──────────┘    └────┬─────┘    └────────┬───────┘                          │
│                       │                   │                                   │
│         ┌─────────────┼───────────────────┼──────────────┐                   │
│         │             │                   │              │                   │
│         ▼             ▼                   ▼              ▼                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  ┌──────────────┐         │
│  │   Fact   │  │   SOP    │  │    Skill Tree    │  │ MetaPattern  │         │
│  │   (L2)   │  │   (L3)   │  │     Category     │  │    (L4)      │         │
│  └──────────┘  └──────────┘  └──────────────────┘  └──────────────┘         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Agent 节点

表示一个 Agent 实例。在单 Agent 场景下只有一个默认 Agent，subagent 模式下每个子 Agent 也有独立节点。

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `agent_id` | `str` | ✅ | 唯一标识，如 `"agent_alpha"` |
| `name` | `str` | ✅ | 显示名称，如 `"Alpha"` |
| `role` | `str` | ✅ | 角色类型: `"default"` \| `"developer_assistant"` \| `"ops_assistant"` \| `"data_analyst"` |
| `evolution_policy` | `str` | | 进化策略: `"conservative"` \| `"balanced"` \| `"aggressive"`，默认 `"balanced"` |
| `trust_threshold` | `float` | | 采纳其他 Agent 贡献的信任门槛，默认 `0.6` |
| `created_at` | `DateTime` | ✅ | 创建时间 |
| `updated_at` | `DateTime` | | 最后更新时间 |

#### Skill 节点

Skill 是核心资产节点，贯穿六层记忆。统一 `dir` 字段关联文件系统。

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `skill_id` | `str` | ✅ | 唯一标识，如 `"github-pr-research"` |
| `name` | `str` | ✅ | 显示名称，如 `"GitHub PR 调研"` |
| `description` | `str` | ✅ | 触发条件描述 (~500 字符，用于 L1 路由匹配) |
| `category` | `str` | ✅ | 分类，如 `"web_automation"` |
| `stage` | `str` | ✅ | 进化阶段: `"NL"` \| `"SOP"` \| `"CODE"` \| `"DEPRECATED"` |
| `version` | `int` | ✅ | 单调递增版本号 |
| `dir` | `str` | ✅ | 文件系统路径: `"skills/{category}/{skill_name}/"` |
| `usage_count` | `int` | | 总使用次数，默认 `0` |
| `success_rate` | `float` | | 成功率 0.0-1.0，默认 `0.0` |
| `activation` | `float` | | 记忆激活值 0.0-1.0，默认 `1.0` |
| `confidence` | `float` | | 置信度 0.0-1.0，默认 `0.0` |
| `context_tags` | `list[str]` | | 适用场景标签: `["env:linux", "user_role:developer"]` |
| `embeddings` | `list[float]` | | 语义嵌入向量（可选，用于向量相似度检索） |
| `created_at` | `DateTime` | ✅ | 创建时间 |
| `updated_at` | `DateTime` | | 最后更新时间 |

#### Session 节点

表示一次对话会话（main 或 subagent）。

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `session_id` | `str` | ✅ | 唯一标识，如 `"sess_abc123"` 或 `"sub_abc123_001"` |
| `type` | `str` | ✅ | `"main"` \| `"subagent"` |
| `parent_session_id` | `str` | | 子 Agent 的父会话 ID（仅 subagent） |
| `source` | `str` | | 消息来源: `"web"` \| `"discord"` \| `"wechat"` \| `"api"` |
| `status` | `str` | | `"active"` \| `"paused"` \| `"completed"` \| `"aborted"` |
| `turn_count` | `int` | | 对话轮次数，默认 `0` |
| `key_info` | `str` | | Stage 4 工作记忆锚点的 key_info 块 |
| `summary` | `str` | | 会话摘要（完成后生成） |
| `created_at` | `DateTime` | ✅ | 创建时间 |
| `completed_at` | `DateTime` | | 完成时间 |

#### ExecutionStep 节点（≡ AgentScope Msg）

一条消息 = 一个 step，是整个系统的原子信息单元。

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | `str` | ✅ | shortuuid 消息 ID，如 `"msg_3xK2mP9q"` |
| `name` | `str` | ✅ | 发送者名称 (Agent 名或工具名) |
| `role` | `str` | ✅ | `"system"` \| `"user"` \| `"assistant"` |
| `content` | `list[ContentBlock]` | ✅ | 消息内容块列表（见下方 ContentBlock 定义） |
| `metadata` | `dict` | | 扩展元数据: `{"session_id", "turn", "skill_used", ...}` |
| `timestamp` | `DateTime` | ✅ | `YYYY-MM-DD HH:MM:SS.fff` |
| `invocation_id` | `str` | | 关联的 LLM API 调用 ID，用于链路追踪 |

**ContentBlock 结构（存储在 ExecutionStep.content 中）：**

```
ContentBlock = TextBlock | ThinkingBlock | ToolUseBlock | ToolResultBlock
             | ImageBlock | AudioBlock | VideoBlock

TextBlock:          { "type": "text",       "text": "..." }
ThinkingBlock:      { "type": "thinking",   "thinking": "..." }
ToolUseBlock:       { "type": "tool_use",   "id": "call_XXX", "name": "...", "input": {...} }
ToolResultBlock:    { "type": "tool_result","id": "call_XXX", "name": "...", "output": "..." | [...] }
ImageBlock:         { "type": "image",      "source": { "type": "url"|"base64", ... } }
AudioBlock:         { "type": "audio",      "source": { "type": "url"|"base64", ... } }
VideoBlock:         { "type": "video",      "source": { "type": "url"|"base64", ... } }
```

#### User 节点

表示人类用户。多用户场景下隔离各用户的会话和偏好。

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_id` | `str` | ✅ | 唯一标识，如 `"user_001"` |
| `name` | `str` | ✅ | 显示名称 |
| `preferences` | `dict` | | 用户偏好: `{"language", "work_style", ...}` |
| `created_at` | `DateTime` | ✅ | 创建时间 |

#### Entity 节点（L2 开放世界知识图谱）

L2 层不再局限于预定义的 `Fact` 类型。潜意识循环从 L0 执行轨迹中自动提取实体和关系，构建**动态生长的知识图谱**。实体类型由模型自主定义，关系类型由模型自主创建——这是一个 Schema-light 的开放世界图。

```
L2 开放世界知识图谱 = 实体节点 + 动态关系边
══════════════════════════════════════════════════════

潜意识循环从 L0 执行步骤中自动提取:

  用户: "Alice 负责的 Neo4j 服务在 10.0.1.50 上，端口 7687，最近一次超时是周五"
      │
      ▼
  ┌─────────────────────────────────────────────────────────┐
  │  提取的实体 (Entity 节点):                                  │
  │                                                          │
  │  (:Entity {                                              │
  │    entity_id: "ent_alice",                               │
  │    entity_type: "Person",        ← 模型自主定义类型       │
  │    name: "Alice Wang",                                   │
  │    content: "后端团队高级工程师，负责 Neo4j 数据库管理",     │
  │    properties: {                                         │
  │      "email": "alice@example.com",                       │
  │      "role": "DBA"                                       │
  │    },                                                    │
  │    confidence: 0.9,                                      │
  │    source: "user_claimed",                               │
  │    source_trace: ["msg_001"]                             │
  │  })                                                      │
  │                                                          │
  │  (:Entity {                                              │
  │    entity_id: "ent_neo4j_main",                          │
  │    entity_type: "Service",                               │
  │    name: "Neo4j 主库",                                    │
  │    content: "生产环境 Neo4j 数据库实例",                   │
  │    properties: {                                         │
  │      "host": "10.0.1.50",                                │
  │      "port": 7687,                                       │
  │      "version": "5.20"                                   │
  │    },                                                    │
  │    confidence: 0.95,                                     │
  │    source: "execution_verified"                          │
  │  })                                                      │
  │                                                          │
  │  (:Entity {                                              │
  │    entity_id: "ent_timeout_20260509",                    │
  │    entity_type: "Incident",                              │
  │    name: "Neo4j 连接超时",                                 │
  │    content: "周五下午 Neo4j 连接超时，持续 15 分钟",       │
  │    properties: {                                         │
  │      "date": "2026-05-08",                               │
  │      "duration_minutes": 15                              │
  │    },                                                    │
  │    confidence: 0.85,                                     │
  │    source: "user_claimed"                                │
  │  })                                                      │
  │                                                          │
  └─────────────────────────────────────────────────────────┘
      │
      ▼
  ┌─────────────────────────────────────────────────────────┐
  │  提取的关系 (动态边):                                      │
  │                                                          │
  │  (ent_alice)-[:MANAGES]->(ent_neo4j_main)                │
  │  (ent_timeout_20260509)-[:AFFECTED]->(ent_neo4j_main)    │
  │  (ent_alice)-[:RESPONSIBLE_FOR]->(ent_timeout_20260509)  │
  │                                                          │
  │  关系类型由模型根据语义自主命名，不受预定义枚举限制         │
  └─────────────────────────────────────────────────────────┘
```

**Entity 节点属性定义：**

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `entity_id` | `str` | ✅ | 唯一标识，如 `"ent_alice"` |
| `entity_type` | `str` | ✅ | 实体类型，模型自由定义: `"Person"` `"Service"` `"Incident"` `"API"` `"Config"` `"Error"` `"Tool"` `"Document"` ... |
| `name` | `str` | ✅ | 实体名称 |
| `content` | `str` | ✅ | 人类可读描述 |
| `properties` | `dict` | | 结构化属性，类型自由 |
| `confidence` | `float` | | 置信度 0.0-1.0 |
| `source` | `str` | | `"execution_verified"` \| `"inferred"` \| `"user_claimed"` \| `"speculative"` |
| `source_trace` | `list[str]` | | 溯源 L0 消息 ID 列表 |
| `activation` | `float` | | 记忆激活值，用于衰减/巩固 |
| `created_at` | `DateTime` | ✅ | 创建时间 |
| `updated_at` | `DateTime` | | 最后更新时间 |

**保留 Fact 作为 L2 的子类型：**

`entity_type: "Fact"` 的 Entity 节点等同于原有的 Fact 节点——用于存储不需要特定类型的通用事实。已有 Skill 的 `[:REFERENCES]` 关系仍然指向 `entity_type="Fact"` 的 Entity 节点。

#### SOP 节点（L3 程序性知识层）

存储可复用的标准化操作流程。

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `sop_id` | `str` | ✅ | 唯一标识，如 `"sop_github_pr_research_v2"` |
| `content` | `str` | ✅ | SOP 完整文本（Markdown 格式） |
| `skill_id` | `str` | ✅ | 所属 Skill ID |
| `version` | `int` | | SOP 版本号，默认 `1` |
| `precondition` | `str` | | 前置条件描述 |
| `confidence` | `float` | | 置信度 0.0-1.0，默认 `0.0` |
| `context_tags` | `list[str]` | | 适用场景标签 |
| `estimated_tokens` | `int` | | 预估 token 消耗 |
| `created_at` | `DateTime` | ✅ | 创建时间 |
| `updated_at` | `DateTime` | | 最后更新时间 |

#### MetaPattern 节点（L4 元模式层）

跨域抽象策略模式，从多个已稳定的 Skill 中提取。

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `pattern_id` | `str` | ✅ | 唯一标识，如 `"pattern_search_filter_extract"` |
| `name` | `str` | ✅ | 模式名称，如 `"搜索-过滤-遍历-提取模式"` |
| `description` | `str` | ✅ | 模式描述 |
| `abstract_steps` | `list[str]` | | 抽象步骤列表 |
| `applicable_domains` | `list[str]` | | 适用领域: `["web", "data", "document"]` |
| `source_skills` | `list[str]` | | 来源 Skill ID 列表 |
| `usage_count` | `int` | | 被类比迁移使用的次数 |
| `created_at` | `DateTime` | ✅ | 创建时间 |

#### SkillCategory 节点（技能树分类）

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | `str` | ✅ | 分类名，如 `"web_automation"` |
| `description` | `str` | | 分类描述 |
| `skill_count` | `int` | | 该分类下的 Skill 数量 |
| `created_at` | `DateTime` | ✅ | 创建时间 |

#### DistillationRequest 节点（蒸馏请求队列）

潜意识循环的待处理任务队列。

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `session_id` | `str` | ✅ | 来源会话 ID |
| `reason` | `str` | ✅ | 触发原因: `"subgoal_completed"` \| `"fault_recovery"` \| `"reusable_pattern"` |
| `summary` | `str` | ✅ | 经验摘要 |
| `status` | `str` | | `"pending"` \| `"processing"` \| `"completed"` \| `"rejected"` |
| `created_at` | `DateTime` | ✅ | 创建时间 |
| `processed_at` | `DateTime` | | 处理完成时间 |

---

### 关系定义

#### Agent 相关关系

| 关系 | 方向 | 属性 | 说明 |
|------|------|------|------|
| `(Agent)-[:OWNS]->(Skill)` | Agent → Skill | — | Agent 拥有/创建了该 Skill |
| `(Agent)-[:MASTERED]->(Skill)` | Agent → Skill | `proficiency: float`, `last_used: DateTime`, `use_count: int`, `verified: bool` | Agent 对该 Skill 的掌握度 |
| `(Agent)-[:PARTICIPATES_IN]->(Session)` | Agent → Session | `joined_at: DateTime` | Agent 参与该会话 |

#### Skill 相关关系

| 关系 | 方向 | 属性 | 说明 |
|------|------|------|------|
| `(Skill)-[:BELONGS_TO]->(SkillCategory)` | Skill → Category | — | Skill 所属分类 |
| `(Skill)-[:EVOLVED_TO]->(Skill)` | 旧版本 → 新版本 | `reason: str`, `distilled_from: list[str]`, `timestamp: DateTime` | 进化谱系链 |
| `(Skill)-[:HAS_SOP]->(SOP)` | Skill → SOP | `is_active: bool` | Skill 关联的 SOP（可能多个版本） |
| `(Skill)-[:REFERENCES]->(Fact)` | Skill → Fact | `relevance: str` | Skill 引用的已知事实 |
| `(Skill)-[:INSTANTIATES]->(MetaPattern)` | Skill → MetaPattern | `confidence: float` | Skill 实例化了某个元模式 |
| `(Skill)-[:DEPENDS_ON]->(Skill)` | Skill → Skill | `required: bool`, `reason: str` | 前置依赖 |
| `(Skill)-[:COMPOSED_OF]->(Skill)` | 父 Skill → 子 Skill | — | 组合关系 |
| `(Skill)-[:CONFLICTS_WITH]->(Skill)` | Skill → Skill | `description: str` | 冲突关系 |
| `(Skill)-[:ALTERNATIVE_TO]->(Skill)` | Skill → Skill | `scenario: str` | 替代关系 |
| `(Skill)-[:VARIANT_OF]->(Skill)` | 变体 → 原版 | `difference: str` | 场景变体 |
| `(Skill)-[:SUPERSEDES]->(Skill)` | 新版 → 旧版 | — | 废弃旧版本 |
| `(Skill)-[:BRANCHED_FROM]->(Skill)` | 分支 → 共同祖先 | `agent_id: str` | 多 Agent 分支来源 |

#### Session 相关关系

| 关系 | 方向 | 属性 | 说明 |
|------|------|------|------|
| `(Session)-[:HAS_STEP]->(ExecutionStep)` | Session → Step | — | Session 包含的步骤 |
| `(Session)-[:SPAWNED]->(Session)` | 父 Session → 子 Session | `task_summary: str` | 父会话派生子会话 |
| `(Session)-[:BELONGS_TO]->(User)` | Session → User | — | 会话归属用户 |
| `(Session)-[:USED_SKILL]->(Skill)` | Session → Skill | `first_used_at: DateTime` | 会话中使用的 Skill |

#### ExecutionStep 相关关系

| 关系 | 方向 | 属性 | 说明 |
|------|------|------|------|
| `(Step)-[:NEXT]->(Step)` | 前一步 → 下一步 | — | 会话内步骤链 |
| `(Step)-[:RECORDED_IN]->(Skill)` | Step → Skill | — | 该步骤使用了某个 Skill |
| `(Step)-[:PRODUCED]->(Fact)` | Step → Fact | — | 该步骤产生了某个事实 |

#### L2 知识图谱关系（两套关系体系并存）

L2 的图结构由两套关系体系组成：**Schema 关系**（预定义，Agent 可直接使用）和 **Dynamic 关系**（模型自主创建，用于实体间语义连接）。

**1. Schema 关系（预定义，稳定使用）：**

这些关系有明确的语义约定，Agent 和 GraphRAG 可以直接理解和使用：

| 关系 | 方向 | 属性 | 说明 |
|------|------|------|------|
| `(Entity)-[:CAUSED_BY]->(Entity)` | 结果 → 原因 | `confidence: float` | 因果关系 |
| `(Entity)-[:DEPENDS_ON]->(Entity)` | 依赖方 → 被依赖方 | `description: str` | 逻辑/运行依赖 |
| `(Entity)-[:SUPPORTS]->(Entity)` | 证据 → 结论 | `strength: float` | 证据支持关系 |
| `(Entity)-[:CONTRADICTS]->(Entity)` | A → B | `resolution: str` | 矛盾关系 |
| `(Entity)-[:OBSOLETES]->(Entity)` | 新 → 旧 | `reason: str` | 废弃过时信息 |
| `(Entity)-[:TEMPORAL_AFTER]->(Entity)` | 后发事件 → 先发事件 | `gap: str` | 时序先后 |
| `(Entity)-[:RELATES_TO]->(Entity)` | Entity → Entity | `description: str` | 通用关联 |
| `(Entity)-[:PART_OF]->(Entity)` | 部分 → 整体 | — | 组合/包含关系 |
| `(Entity)-[:HAS_PROPERTY]->(Entity)` | Entity → 属性值 | `key: str` | 属性关联（如 Service→Port） |

**2. Dynamic 关系（模型自主创建）：**

潜意识循环在提取实体时，根据语义自由创建关系类型。这些关系没有预定义 Schema，由模型命名：

```
示例 Dynamic 关系（模型实时创建）:
  (ent_alice)-[:MANAGES]->(ent_neo4j_main)
  (ent_timeout)-[:AFFECTED]->(ent_neo4j_main)
  (ent_alice)-[:RESPONSIBLE_FOR]->(ent_timeout)
  (ent_api_key)-[:AUTHENTICATES]->(ent_service)
  (ent_error_502)-[:TRIGGERED_BY]->(ent_config_change)
  (ent_docker)-[:CONTAINS]->(ent_neo4j_container)
```

Dynamic 关系使 L2 图能表达任意语义，不受预定义 Schema 限制。GraphRAG 在遍历时对 Dynamic 关系一视同仁——图遍历不区分关系是预定义还是动态创建的。

**执行轨迹溯源关系：**

这是 L2 ↔ L0 的关键桥梁，支撑置信度计算和信念修正：

| 关系 | 方向 | 属性 | 说明 |
|------|------|------|------|
| `(ExecutionStep)-[:PRODUCED]->(Entity)` | Step → Entity | `extraction_method: str` | 该步骤产生了此实体 |
| `(ExecutionStep)-[:PRODUCED]->(Entity, Entity)` | Step → 关系 | `extraction_method: str` | 该步骤产生了此关系 |
| `(Entity)-[:MENTIONED_IN]->(ExecutionStep)` | Entity → Step | — | 实体在某步骤中被提及 |

**Skill ↔ L2 的引用关系保持：**

| 关系 | 方向 | 属性 | 说明 |
|------|------|------|------|
| `(Skill)-[:REFERENCES]->(Entity)` | Skill → Entity | `relevance: str` | Skill 引用 L2 实体（不限 entity_type） |

#### SOP 相关关系（L3 程序性知识）

| 关系 | 方向 | 属性 | 说明 |
|------|------|------|------|
| `(SOP)-[:DEPENDS_ON]->(SOP)` | SOP → SOP | `step_ref: str` | SOP 之间的步骤依赖 |
| `(SOP)-[:COMPOSES]->(SOP)` | 父 SOP → 子 SOP | — | SOP 组合 |
| `(SOP)-[:EXTENDS]->(SOP)` | 子 SOP → 父 SOP | `added_steps: str` | SOP 继承扩展 |
| `(SOP)-[:VARIANT_OF]->(SOP)` | 变体 → 原版 | `scenario: str` | SOP 场景变体 |
| `(SOP)-[:CONFLICTS_WITH]->(SOP)` | SOP → SOP | `conflict_point: str` | SOP 冲突点 |
| `(SOP)-[:OPTIMIZES]->(SOP)` | 新版 → 旧版 | `improvement: str` | SOP 优化关系 |

#### MetaPattern 相关关系（L4 元模式）

| 关系 | 方向 | 属性 | 说明 |
|------|------|------|------|
| `(MetaPattern)-[:INSTANTIATED_BY]->(SOP)` | Pattern → SOP | `similarity: float` | 模式被 SOP 实例化 |
| `(MetaPattern)-[:RELATED_TO]->(MetaPattern)` | Pattern → Pattern | `description: str` | 模式间关联 |

---

### 约束与索引

```cypher
-- 唯一性约束
CREATE CONSTRAINT skill_id_unique     IF NOT EXISTS FOR (s:Skill)           REQUIRE s.skill_id IS UNIQUE;
CREATE CONSTRAINT agent_id_unique     IF NOT EXISTS FOR (a:Agent)           REQUIRE a.agent_id IS UNIQUE;
CREATE CONSTRAINT session_id_unique   IF NOT EXISTS FOR (s:Session)         REQUIRE s.session_id IS UNIQUE;
CREATE CONSTRAINT step_id_unique      IF NOT EXISTS FOR (s:ExecutionStep)   REQUIRE s.id IS UNIQUE;
CREATE CONSTRAINT entity_id_unique    IF NOT EXISTS FOR (e:Entity)          REQUIRE e.entity_id IS UNIQUE;
CREATE CONSTRAINT sop_id_unique       IF NOT EXISTS FOR (s:SOP)             REQUIRE s.sop_id IS UNIQUE;
CREATE CONSTRAINT pattern_id_unique   IF NOT EXISTS FOR (p:MetaPattern)     REQUIRE p.pattern_id IS UNIQUE;
CREATE CONSTRAINT user_id_unique      IF NOT EXISTS FOR (u:User)            REQUIRE u.user_id IS UNIQUE;
CREATE CONSTRAINT category_name_unique IF NOT EXISTS FOR (c:SkillCategory)  REQUIRE c.name IS UNIQUE;

-- 查询索引
CREATE INDEX skill_category_idx   IF NOT EXISTS FOR (s:Skill)     ON (s.category);
CREATE INDEX skill_stage_idx      IF NOT EXISTS FOR (s:Skill)     ON (s.stage);
CREATE INDEX skill_activation_idx IF NOT EXISTS FOR (s:Skill)     ON (s.activation);
CREATE INDEX entity_type_idx       IF NOT EXISTS FOR (e:Entity)    ON (e.entity_type);
CREATE INDEX entity_source_idx     IF NOT EXISTS FOR (e:Entity)    ON (e.source);
CREATE INDEX entity_confidence_idx IF NOT EXISTS FOR (e:Entity)    ON (e.confidence);
CREATE INDEX session_status_idx   IF NOT EXISTS FOR (s:Session)   ON (s.status);
CREATE INDEX step_role_idx        IF NOT EXISTS FOR (s:ExecutionStep) ON (s.role);
CREATE INDEX sop_skill_idx        IF NOT EXISTS FOR (s:SOP)       ON (s.skill_id);
CREATE INDEX distillation_status_idx IF NOT EXISTS FOR (d:DistillationRequest) ON (d.status);

-- 全文索引（Keyword 搜索）
CREATE FULLTEXT INDEX skill_search IF NOT EXISTS
  FOR (s:Skill) ON EACH [s.name, s.description];
CREATE FULLTEXT INDEX entity_search IF NOT EXISTS
  FOR (e:Entity) ON EACH [e.name, e.content];
```

---

## 第二部分附录二：上下文组装与记忆获取

### 设计原则

核心思想继承自 GA：**不要把所有记忆注入上下文，而是让 Agent 通过工具调用按需获取**。只有一个小型的"始终在线层"保持可见，更深层的记忆仅在需要时由 Agent 主动检索。

```
┌──────────────────────────────────────────────────────────────────┐
│                   每轮 LLM 调用的上下文构成                          │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │ 始终在线层 (Always-On)  — 每轮自动注入，无需工具调用        │    │
│  ├──────────────────────────────────────────────────────────┤    │
│  │                                                          │    │
│  │ ① 系统提示 (System Prompt)                               │    │
│  │    ├─ Agent 身份与核心行为准则                             │    │
│  │    ├─ 12 工具 Schema (name + description)                │    │
│  │    └─ 元记忆核心规则 (Meta-Memory Rules)                  │    │
│  │       ├─ 记忆地图: L0→L1→L2→L3→L4→L5 各层是什么          │    │
│  │       ├─ 准入规则: "No Execution, No Memory"              │    │
│  │       ├─ 操作协议: 何时用 memory_search / skill_manage    │    │
│  │       └─ 排除列表: 什么不应该写入长期记忆                   │    │
│  │                                                          │    │
│  │ ② 工作记忆锚点 (Working Memory Anchors)                   │    │
│  │    ├─ 最近 20 条单行轮次摘要 (~100 字符/条)               │    │
│  │    ├─ 当前轮次编号                                        │    │
│  │    └─ key_info 块 (由 update_working_checkpoint 维护)     │    │
│  │       └─ { 当前目标, 关键发现, 下一步计划 }                │    │
│  │                                                          │    │
│  │ ③ 对话历史 (压缩后)                                       │    │
│  │    └─ 经四阶段压缩管道处理后的 ExecutionStep 链            │    │
│  │                                                          │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │ 按需加载层 (On-Demand)  — Agent 通过工具调用主动获取       │    │
│  ├──────────────────────────────────────────────────────────┤    │
│  │                                                          │    │
│  │ ④ L1 索引导航 → memory_search(mode="route")               │    │
│  │    ├─ 语义匹配: 任务关键词 → Skill.description            │    │
│  │    ├─ 标签过滤: context_tags 匹配当前场景                  │    │
│  │    └─ 图遍历: 从已知 Skill 沿 [:DEPENDS_ON] 等边扩展       │    │
│  │    → 返回: 候选 Skill 列表 (skill_id, dir, stage, ...)    │    │
│  │                                                          │    │
│  │ ⑤ Skill 正文加载 → file_read("{dir}/SKILL.md")            │    │
│  │    → 读到 SOP 操作流程 (SOP 阶段) 或代码参考 (CODE 阶段)    │    │
│  │                                                          │    │
│  │ ⑥ 关联记忆加载 → memory_search(mode="load")               │    │
│  │    → 加载 Skill 关联的 L2 事实 + L3 SOP + 依赖 Skill       │    │
│  │                                                          │    │
│  │ ⑦ 代码/脚本加载 → file_read("{dir}/scripts/main.py")      │    │
│  │    → 或直接 code_run("{dir}/scripts/main.py --args")      │    │
│  │                                                          │    │
│  │ ⑧ 历史追溯 → memory_search(mode="trace")                  │    │
│  │    → 查询被 Stage 3 驱逐的 L0 历史步骤                     │    │
│  │                                                          │    │
│  │ ⑨ 关联发现 → memory_search(mode="related")                │    │
│  │    → 查找 Skill 的替代方案、变体、冲突 Skill               │    │
│  │                                                          │    │
│  │ ⑩ 🆕 图检索增强 → memory_search(mode="rag")               │    │
│  │    → 从当前问题提取实体 → 图种子锚定 → 多跳遍历           │    │
│  │    → 构建相关子图 → 序列化为结构化上下文                   │    │
│  │                                                          │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │ 预判检索层 (Anticipatory)  — TODO Phase 5                 │    │
│  ├──────────────────────────────────────────────────────────┤    │
│  │                                                          │    │
│  │ T-1 子图匹配预测                                          │    │
│  │     └─ 当前执行路径前缀 → Neo4j 子图匹配 → 历史上相似路径   │    │
│  │ T-2 L4 元模式类比                                         │    │
│  │     └─ 任务特征 → 匹配 L4 MetaPattern → 建议适用 Skill    │    │
│  │ T-3 信念修正传播                                           │    │
│  │     └─ 上游 Fact 修正 → 图遍历 → 标记下游受影响 Fact       │    │
│  │ T-4 L5 归档挖掘                                            │    │
│  │     └─ 潜意识循环定期扫描归档 → 发现被遗忘的有价值模式      │    │
│  │                                                          │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### 记忆获取决策流

Agent 在每个推理周期中自主决定是否需要获取更多记忆。这不是硬编码的流水线，而是由 LLM 根据当前任务上下文驱动的工具调用决策。

```
任务到达
    │
    ▼
┌─────────────────────────────────────────────────────┐
│ 第 1 轮: 初始路由                                    │
│                                                     │
│ 上下文: 系统提示 + 工作记忆锚点 + 用户消息              │
│                                                     │
│ Agent 自主决策:                                      │
│ ① 任务是否已有匹配的 Skill?                           │
│    → 调用 memory_search(mode="route", keyword="...") │
│ ② 需要读取项目文件了解上下文?                          │
│    → 调用 file_read(path, start, count)             │
│ ③ 可以直接执行?                                      │
│    → 调用 code_run(code="...")                      │
│                                                     │
│ 关键: Agent 从 2,298 tokens 的极简上下文开始           │
│       只在需要时扩展，从不预加载全量记忆                │
└──────────────┬──────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────┐
│ 第 N 轮: 记忆扩展                                    │
│                                                     │
│ Agent 在推理过程中发现:                               │
│ "我需要知道历史上类似任务是怎么处理的"                   │
│    → memory_search(mode="trace", session_id="...")   │
│                                                     │
│ "这个 Skill 依赖什么?"                                │
│    → memory_search(mode="load", skill_id="...")      │
│    → 自动链式加载 [:DEPENDS_ON] Skill 的 SKILL.md    │
│                                                     │
│ "有没有更好的替代方案?"                                │
│    → memory_search(mode="related", skill_id="...")   │
│    → 发现 [:ALTERNATIVE_TO] 和 [:VARIANT_OF] 分支    │
│                                                     │
│ "我发现了可复用的知识"                                 │
│    → start_long_term_update(reason, summary)          │
│    → 写入 L2 或 L3 (先验证，再提交)                    │
└──────────────────────────────────────────────────────┘
```

### GraphRAG 图检索增强 (memory_search mode="rag")

infoCap 的 Neo4j 图模型天然支持 GraphRAG 式的知识检索。不同于传统 RAG 的向量相似度匹配，GraphRAG 利用图结构进行**多跳语义遍历**，发现直接匹配之外的相关知识。

```
┌──────────────────────────────────────────────────────────────────┐
│                 GraphRAG 检索流程 (mode="rag")                     │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  输入: 用户问题 + 当前上下文                                        │
│                                                                   │
│  Step 1: 实体提取与锚定 (Entity Extraction & Seeding)              │
│  ┌─────────────────────────────────────────────────────┐         │
│  │ 从问题中提取关键实体和概念:                            │         │
│  │   问题: "Neo4j 数据库连接超时，之前谁处理过类似问题?"     │         │
│  │   实体: ["Neo4j", "连接超时", "数据库"]                │         │
│  │                                                      │         │
│  │ 在图中锚定种子节点:                                    │         │
│  │   MATCH (n)                                           │         │
│  │   WHERE n.content CONTAINS "Neo4j"                    │         │
│  │      OR n.content CONTAINS "连接超时"                  │         │
│  │      OR n.content CONTAINS "数据库"                    │         │
│  │      OR n.name CONTAINS "Neo4j"                       │         │
│  │   RETURN n                                            │         │
│  │                                                      │         │
│  │  → 种子集合: {Entity(ent_neo4j_config),                │         │
│  │               SOP(sop_db_troubleshoot),               │         │
│  │               Skill(skill_neo4j_admin), ...}          │         │
│  └─────────────────────────────────────────────────────┘         │
│                                                                   │
│  Step 2: 多跳图遍历 (Multi-Hop Traversal)                         │
│  ┌─────────────────────────────────────────────────────┐         │
│  │ 从种子节点出发，沿关系边扩展 N 跳 (默认 2-3):          │         │
│  │                                                      │         │
│  │   MATCH (seed)-[*1..3]-(related)                     │         │
│  │   WHERE seed IN $seed_ids                            │         │
│  │   RETURN seed, related, relationships                │         │
│  │                                                      │         │
│  │ 跳数-关系类型策略:                                     │         │
│  │   Hop 1: 直接关联                                     │         │
│  │     (Skill)-[:HAS_SOP]→(SOP)                         │         │
│  │     (Fact)-[:CAUSED_BY]→(Fact)                       │         │
│  │     (ExecutionStep)-[:PRODUCED]→(Fact)               │         │
│  │                                                      │         │
│  │   Hop 2: 间接关联                                     │         │
│  │     (Skill)-[:DEPENDS_ON]→(Skill)-[:REFERENCES]→(Fact)│         │
│  │     (Fact)-[:SUPPORTS]→(Fact)-[:CAUSED_BY]→(Fact)    │         │
│  │                                                      │         │
│  │   Hop 3: 弱关联 (可选，大图时采样)                     │         │
│  │     (Session)-[:HAS_STEP]→(Step)-[:PRODUCED]→(Fact)  │         │
│  │     (Skill)-[:ALTERNATIVE_TO]→(Skill)-[:HAS_SOP]→(SOP)│         │
│  └─────────────────────────────────────────────────────┘         │
│                                                                   │
│  Step 3: 子图评分与剪枝 (Relevance Scoring & Pruning)              │
│  ┌─────────────────────────────────────────────────────┐         │
│  │ 对遍历到的每个节点计算相关度分数:                       │         │
│  │                                                      │         │
│  │   Score(n) = w_sem · Sim(n, query)                   │         │
│  │            + w_str · StructuralReach(n, seeds)        │         │
│  │            + w_frq · Frequency(n)                     │         │
│  │            + w_rec · Recency(n)                       │         │
│  │                                                      │         │
│  │ 剪枝策略:                                             │         │
│  │   - 分数 < 阈值 → 移除                                 │         │
│  │   - 同类型重复节点 (如多个相似 Fact) → 保留 top-2      │         │
│  │   - 中间节点 (仅用于连接的 Skill/SOP) → 保留摘要       │         │
│  │   - 子图总节点数 > 50 → 提高阈值重新剪枝               │         │
│  └─────────────────────────────────────────────────────┘         │
│                                                                   │
│  Step 4: 子图序列化 (Subgraph Serialization)                      │
│  ┌─────────────────────────────────────────────────────┐         │
│  │ 将检索到的子图转换为 LLM 可消费的结构化文本:             │         │
│  │                                                      │         │
│  │   ## 相关记忆子图 (GraphRAG Results)                   │         │
│  │                                                      │         │
│  │   ### Skills (L1)                                    │         │
│  │   - **neo4j_admin** (CODE, conf:0.92)                │         │
│  │     Neo4j 数据库管理, dir: skills/ops/neo4j_admin/    │         │
│  │     [:DEPENDS_ON] db_troubleshoot                     │         │
│  │                                                      │         │
│  │   ### Facts (L2)                                     │         │
│  │   - **fact_neo4j_timeout** (conf:0.95)               │         │
│  │     Neo4j 默认连接超时为 30s                           │         │
│  │     props: {default_timeout: 30, max_timeout: 300}    │         │
│  │     [:CAUSED_BY] fact_firewall_rule                   │         │
│  │                                                      │         │
│  │   ### SOPs (L3)                                      │         │
│  │   - **sop_db_troubleshoot** (v2, conf:0.88)           │         │
│  │     Step 1: 检查连接参数 → Step 2: 检查防火墙...       │         │
│  │     [:EXTENDS] sop_generic_network_debug               │         │
│  │                                                      │         │
│  │   ### Execution Traces (L0)                          │         │
│  │   - **msg_3xK2mP9q** (2026-05-08, success)           │         │
│  │     Session: sess_abc, Turn 5                         │         │
│  │     "超时问题通过增加 timeout 参数解决"                 │         │
│  │     [:PRODUCED] fact_neo4j_timeout                    │         │
│  │                                                      │         │
│  └─────────────────────────────────────────────────────┘         │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

#### 两种检索策略：本地搜索 vs 全局搜索

| 策略 | 对应 GraphRAG | 适用场景 | 实现 |
|------|-------------|---------|------|
| **本地搜索 (Local)** | GraphRAG Local Search | "Neo4j 超时怎么解决?" — 特定实体相关 | 从种子实体出发，遍历 1-2 跳邻域 |
| **全局搜索 (Global)** | GraphRAG Global Search | "整个系统有哪些安全相关配置?" — 跨主题摘要 | 社区检测 + 按主题聚类 → 摘要 |

```cypher
-- 本地搜索: 2 跳遍历
MATCH path = (seed)-[*1..2]-(related)
WHERE seed.skill_id IN $seeds OR seed.entity_id IN $seeds
RETURN nodes(path), relationships(path)
LIMIT 100

-- 全局搜索: 按类别聚合 (Phase 1 简化版)
MATCH (s:Skill)-[:REFERENCES]->(e:Entity)
WHERE s.category = $category
RETURN s.category AS theme, collect(DISTINCT f.content) AS facts

-- 全局搜索: 社区检测 (TODO Phase 5, 需 GDS 插件)
CALL gds.louvain.stream('knowledge-graph')
YIELD nodeId, communityId
```

#### Phase 1 vs 后续 TODO

| 组件 | Phase 1 | TODO Phase |
|------|---------|------------|
| 实体提取 + 种子锚定 | ✅ 关键词匹配 (全文索引) | Phase 2: LLM 实体提取 |
| 本地搜索 (1-2 hop) | ✅ 完整实现 | Phase 2: 向量相似度增强 |
| 子图评分与剪枝 | ✅ 基础评分 (频率+新近度) | Phase 2: 完整四维评分 |
| 子图序列化 | ✅ 结构化文本输出 | — |
| 全局搜索 (按类别聚合) | ✅ 基础实现 | Phase 5: GDS 社区检测 |
| 向量语义匹配 | ❌ | Phase 2 |

### 系统提示结构

```python
SYSTEM_PROMPT = """You are {agent_name}, an autonomous agent with skill self-evolution capability.

## Meta-Memory: Memory Map
Your memory is organized in 6 layers stored in Neo4j:
- L0 Episodic: execution step chains, each step = one AgentScope-style Msg
- L1 Index: Skill metadata (name, category, stage, context_tags). ALWAYS search here first.
- L2 Facts: verified, reusable facts with properties and provenance
- L3 SOPs: standard operating procedures with preconditions and steps
- L4 Meta-Patterns: abstract cross-domain strategies
- L5 Archive: compressed historical logs on filesystem

## Meta-Memory: Core Rules
1. **L1 First**: Use memory_search(mode="route") to find relevant Skills before acting.
2. **No Execution, No Memory**: Only write execution-verified knowledge to L2/L3.
3. **Cross-Task Reusability**: Don't store one-time context as permanent memory.
4. **Incremental Update**: Small additions, never full overwrites of existing memory.
5. **Read What You Need**: Use file_read with range/keyword, not full dumps.
6. **One code_run Per Round**: Observe results before next action.
7. **Persist Findings**: Use update_working_checkpoint for key discoveries.

## Available Tools
{tool_descriptions}

## Working Memory
Turn: {turn_number}
Recent: {recent_summaries}
Key Info: {key_info}
"""
```

### 工作记忆锚点的生命周期

```
┌──────────────────────────────────────────────────────────────────┐
│                   工作记忆锚点传播机制                              │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  每轮 LLM 调用后:                                                  │
│  ┌─────────────────────────────────────────────────────┐         │
│  │ 1. Agent 执行工具 → 产生 ExecutionStep                │         │
│  │ 2. 从响应中提取单行摘要 → 追加到 recent_summaries      │         │
│  │ 3. 如果 Agent 调用了 update_working_checkpoint:        │         │
│  │    → 更新 key_info 块 (Neo4j Session.key_info)       │         │
│  │ 4. 如果 Agent 未调用: 系统自动从最近轮次生成摘要        │         │
│  └─────────────────────────────────────────────────────┘         │
│                                                                   │
│  Stage 2 压缩 (~每 5 轮):                                          │
│  ┌─────────────────────────────────────────────────────┐         │
│  │ 旧轮次中的 <key_info> 和 <history> 块 → 替换为 [...]  │         │
│  │ 只有最新副本被保留——"写一次，自动传播"                   │         │
│  └─────────────────────────────────────────────────────┘         │
│                                                                   │
│  Stage 3 驱逐后:                                                   │
│  ┌─────────────────────────────────────────────────────┐         │
│  │ 被驱逐的消息 → 写入 Neo4j L0 ExecutionStep            │         │
│  │ 工作记忆锚点成为被驱逐消息的"唯一替代品"                  │         │
│  │ Agent 可通过 memory_search(mode="trace") 按需找回     │         │
│  └─────────────────────────────────────────────────────┘         │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### Phase 1 实现范围 vs 后续 TODO

| 组件 | Phase 1 | TODO Phase |
|------|---------|------------|
| 系统提示 + 工具 Schema | ✅ 完整实现 | — |
| 元记忆核心规则 (7 条) | ✅ 完整实现 | — |
| 工作记忆锚点 (摘要 + 轮次 + key_info) | ✅ 完整实现 | — |
| L1 索引导航 (memory_search route) | ✅ 完整实现 | — |
| L2 Entity 节点 Schema + 手动创建 (skill_manage) | ✅ 完整实现 | — |
| L2/L3 按需加载 (memory_search load) | ✅ 基础实现 | Phase 2: 关系图优化 |
| L2 自动实体提取 (潜意识从L0提取) | ❌ TODO | Phase 3 |
| SKILL.md 按需加载 (file_read) | ✅ 完整实现 | — |
| 对话历史注入 (压缩后) | ✅ 完整实现 | — |
| GraphRAG 本地搜索 (memory_search rag local) | ✅ 完整实现 | Phase 2: 向量增强 |
| GraphRAG 全局搜索 (memory_search rag global) | ✅ 基础实现 (分类聚合) | Phase 5: GDS 社区检测 |
| 预判检索 — 子图匹配 | ❌ TODO | Phase 5 |
| 预判检索 — L4 元模式类比 | ❌ TODO | Phase 5 |
| 信念修正 — 图遍历传播 | ❌ TODO | Phase 5 |
| L5 归档挖掘 | ❌ TODO | Phase 5 |
| 向量语义检索 (embeddings) | ❌ TODO | Phase 2 |

---

## 第三部分：Skill 系统与进化

### 统一文件夹结构（所有阶段不变）

```
skills/{category}/{skill_name}/
├── SKILL.md                    # 始终存在，内容随阶段进化
├── scripts/                    # CODE 阶段编译的可执行代码
├── references/                 # 参考文档
├── assets/                     # 模板和资源
├── checkpoints/                # 执行断点
└── archive/                    # 旧版本归档
```

### 三阶段进化路径

| 阶段 | SKILL.md 内容 | scripts/ | 触发条件 |
|------|--------------|----------|----------|
| NL | 探索性自然语言描述 + 试错记录 | 空 | usage_count > 3 且有成功路径 |
| SOP | 结构化操作流程 + 故障恢复 | 空 | 5+ 次成功且差异收敛 |
| CODE | 精简代码参考文档 | 完整可执行代码 | confidence > 0.9, 连续 5 次无重大变更 |

- 阶段过渡由潜意识循环自动完成，无需人工干预
- 每次进化在 Neo4j 中通过 `[:EVOLVED_TO]` 创建版本链
- 旧版本自动归档到 `archive/`
- L4 元模式从多个已稳定的 CODE 阶段 Skill 中提取

### Neo4j 中 Skill 通过 `dir` 字段关联文件系统

```
Skill 节点: { skill_id, name, category, stage, version, dir, usage_count, 
              success_rate, activation, confidence, embeddings, context_tags }

通过 dir = "skills/{category}/{skill_name}/" 定位所有资源:
  file_read("{dir}/SKILL.md")
  code_run("{dir}/scripts/main.py")
  file_read("{dir}/references/api_docs.md")
```

### 三级渐进加载

- Level 1: Skill 节点元数据始终在 L1 索引中 (~100 tokens/skill)
- Level 2: SKILL.md 按需加载到上下文 (< 500 行)
- Level 3: scripts/, references/, assets/ 按需通过工具调用获取

---

## 第四部分：原子工具集 (9 + 3 = 12)

| 能力类 | 工具 | 说明 |
|--------|------|------|
| 文件操作 | `file_read`, `file_patch`, `file_write` | 精度读取/唯一匹配快速失败/全量写入 |
| 代码执行 | `code_run` | 每轮一次，沙箱执行 |
| Web交互 | `web_scan`, `web_execute_js` | 语义提取/浏览器操作 |
| 记忆管理 | `memory_search` | Neo4j 图查询统一入口 (route/load/trace/related) |
| 记忆管理 | `update_working_checkpoint` | 工作记忆维护 + L0 轨迹写入 |
| 记忆管理 | `start_long_term_update` | 触发潜意识蒸馏 |
| 记忆管理 | `skill_manage` | Skill 生命周期管理 (register/evolve/deprecate/link) |
| 任务委派 | `subagent` | 派生独立子Agent执行子任务 |
| 人机交互 | `ask_user` | 人工介入请求 |

### subagent 工具

- 父Agent 传递: task + context (skill_dirs, facts, max_rounds, workspace)
- 子Agent: 独立的意识循环、L0 轨迹、工作记忆、隔离 workspace
- 子Agent 可调用其他所有工具（只读 Neo4j）
- 子Agent 不可: 修改父工作记忆、触发蒸馏、嵌套创建子Agent
- Neo4j 关系: `(:Session {type:"main"})-[:SPAWNED]->(:Session {type:"subagent"})`

---

## 第五部分：压缩管道

沿用 GA 四阶段，增强消息驱逐后的 Neo4j 可恢复性：

| 阶段 | 触发 | 策略 |
|------|------|------|
| Stage 1 | 每轮自动 | 对称头尾截断，memory_search 完整保留 |
| Stage 2 | ~每 5 轮 | 过期块占位符、旧轮次截断至 ~800 字符，最近 10 条豁免 |
| Stage 3 | CH > B | FIFO 驱逐至 0.6B，驱逐前写入 Neo4j L0 |
| Stage 4 | 每轮注入 | 20条摘要 + 轮次号 + key_info (含 Neo4j 节点引用) |

预算公式: CH ≤ α × W_tokens (α ≈ 3)

---

## 第六部分：自主探索

- **触发**: 空闲 > 5min 或定时 30min
- **课程规划**: S(t) = w_b·B(t) + w_d·D(t) + w_u·U(t) + w_i·I(t)
- **执行**: 30 轮上限，沙箱隔离
- **权重自适应**: 预测 vs 实际使用对比 → 调整维度权重 → 归一化

---

## 第七部分：运行时架构

```
Agent Engine (主进程)
├── 意识循环 (asyncio 事件循环)
│   ├── 消息入队 → L1路由 → 上下文组装 → LLM推理 → 工具调度 → 压缩 → 响应
│   └── 每步写 L0 轨迹到 Neo4j
├── 潜意识循环 (asyncio 后台任务)
│   ├── L2 实体提取器 (从 L0 自动提取 Entity + Dynamic 关系)
│   ├── 蒸馏调度器 (每5min / 空闲触发)
│   ├── 自主探索引擎 (课程规划 + 权重自适应)
│   └── 记忆生命周期维护 (衰减/巩固/遗忘)
└── 共享组件
    ├── Neo4j Driver Pool
    ├── LLM Client (OpenAI/Anthropic)
    ├── Tool Dispatcher
    ├── Compression Pipeline
    ├── Skill Registry
    └── Embedding Service

Web Server (独立进程)
├── FastAPI Backend → WebSocket → Next.js Frontend
└── Platform Adapters (Discord, Slack, 微信...)
```

### L2 实体提取器（潜意识循环核心任务）

潜意识循环定期从 L0 新产生的 ExecutionStep 中提取实体和关系，自动扩展 L2 知识图谱。这是 GraphRAG 检索质量的根基——图越丰富，检索越精准。

```
┌──────────────────────────────────────────────────────────────────┐
│              L2 实体提取流程 (每 5min 或空闲触发)                    │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Step 1: 获取未处理的 L0 消息                                      │
│  ┌─────────────────────────────────────────────────────┐         │
│  │ MATCH (s:ExecutionStep)                              │         │
│  │ WHERE NOT EXISTS { (s)-[:PRODUCED]->(:Entity) }      │         │
│  │   AND s.timestamp > datetime() - duration('PT30M')   │         │
│  │ RETURN s.id, s.content, s.role ORDER BY s.timestamp  │         │
│  │ LIMIT 50                                             │         │
│  └─────────────────────────────────────────────────────┘         │
│                                                                   │
│  Step 2: LLM 实体-关系抽取                                         │
│  ┌─────────────────────────────────────────────────────┐         │
│  │ 将 L0 消息批量发送给 LLM，要求提取:                     │         │
│  │                                                      │         │
│  │   实体列表:                                           │         │
│  │   [{ entity_type, name, content, properties }]       │         │
│  │                                                      │         │
│  │   关系列表:                                           │         │
│  │   [{ from_entity_id, relation_type, to_entity_id }]  │         │
│  │                                                      │         │
│  │ 提取 Prompt 约束:                                     │         │
│  │   - entity_type 自由命名 (Person, Service, Error...)  │         │
│  │   - relation_type 根据语义自由命名                    │         │
│  │   - 优先使用已有实体 (MATCH existing Entity)          │         │
│  │   - 低置信度信息标记为 speculative                    │         │
│  │   - 仅提取有跨任务复用价值的信息                       │         │
│  └─────────────────────────────────────────────────────┘         │
│                                                                   │
│  Step 3: 实体去重与合并                                            │
│  ┌─────────────────────────────────────────────────────┐         │
│  │ 对新提取的每个实体:                                    │         │
│  │                                                      │         │
│  │   MATCH (e:Entity)                                   │         │
│  │   WHERE e.name = $new_name                           │         │
│  │     AND e.entity_type = $new_type                    │         │
│  │                                                      │         │
│  │   找到同名同类型 → 合并: 更新 properties + 提升置信度   │         │
│  │   未找到 → 新建 Entity 节点                            │         │
│  │   找到但 properties 冲突 → 创建新版本, [CONTRADICTS]   │         │
│  └─────────────────────────────────────────────────────┘         │
│                                                                   │
│  Step 4: 写入 Neo4j + 溯源边                                       │
│  ┌─────────────────────────────────────────────────────┐         │
│  │ CREATE (step)-[:PRODUCED {                            │         │
│  │   extraction_method: "llm_entity_extraction"          │         │
│  │ }]->(entity)                                         │         │
│  │                                                      │         │
│  │ CREATE (entity_a)-[:{dynamic_relation_type} {         │         │
│  │   source: "extracted",                               │         │
│  │   confidence: 0.85,                                  │         │
│  │   source_trace: [step.id]                            │         │
│  │ }]->(entity_b)                                       │         │
│  └─────────────────────────────────────────────────────┘         │
│                                                                   │
│  Safety constraints:                                              │
│  - 不提取 PII (密码/token/key)                                     │
│  - 不提取纯临时状态 (当前光标位置、临时变量)                          │
│  - 置信度 < 0.3 的实体不写入                                       │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### 项目目录

```
infoCap/
├── agent/            # 核心引擎 (engine, conscious, subconscious, context, compression)
├── tools/            # 原子工具 (dispatcher, file_ops, code_run, web_interact, 
│                     #           memory_search, skill_manage, checkpoint, 
│                     #           long_term_update, ask_user, subagent)
├── memory/           # 记忆系统 (neo4j_client, index, entities, sop, meta_pattern,
│                     #            lifecycle, provenance, extractor, graph_models)
├── skill_system/     # Skill系统 (registry, loader, evolution, distillation, tree, scorer)
├── exploration/      # 自主探索 (curriculum, executor, reflector)
├── adapters/         # 平台适配器 (base, web, discord, wechat)
├── server/           # Web服务 (FastAPI + WebSocket)
├── webui/            # Next.js 前端
├── skills/           # Skill 文件系统 (运行时生成)
├── docs/superpowers/specs/
├── docker-compose.yml
└── pyproject.toml
```


---

## 第八部分：实现路线图

### Phase 1: 核心骨架 (1-2周)
- Neo4j Schema: Agent, Skill, Session, L0_ExecutionStep, L2_Fact, L3_SOP 节点 + 核心关系
- 12 原子工具实现
- 意识循环 (最小可用)
- 四阶段压缩管道
- 基本 Web UI (对话 + 流式输出)

### Phase 2: Skill 系统 + 记忆 (2-3周)
- Skill 统一文件夹结构 + Registry + 三级渐进加载
- L2 知识图谱 (CRUD, 关系, 置信度溯源)
- L3 SOP 层 (文本存储, 组合/继承/变体)
- L4 元模式提取 (基础版)
- 记忆生命周期

### Phase 3: 自进化 (2-3周)
- 潜意识循环 + 异步任务调度
- NL → SOP 经验蒸馏引擎
- SOP 优化迭代 + 变体检测
- SOP → Code 编译 + 自动验证
- 技能树 + 四维评分

### Phase 4: 自主探索 + Subagent (1-2周)
- 自主探索闭环 + 反射驱动权重自适应
- subagent 工具 (派生/隔离/结果收集)
- 聊天平台适配器 (至少一个)

### Phase 5: 完善 (2-3周)
- L5 归档层 + 潜意识挖掘
- 信念修正传播
- 预判检索
- 完整 Web UI
- 压力测试 + 部署文档

---

## 与 GenericAgent 的关键差异

| 维度 | GenericAgent | infoCap |
|------|-------------|---------|
| 记忆存储 | 纯文件系统 | Neo4j + 文件系统关联 |
| 记忆层级 | 4层 | 6层 + 3横切机制 |
| 记忆关系 | 无 | 丰富语义图边 |
| 记忆生命周期 | 无 | 衰减-巩固-遗忘 |
| 置信度溯源 | 无 | 完整置信度 + 信念修正传播 |
| 预判检索 | 无 | 子图匹配预测 |
| 元模式 | 无 | L4 跨域抽象策略 |
| Skill结构 | 自定义 | 统一文件夹 + 三级渐进加载 |
| 进化 | 三阶段 | 三阶段 + 完整谱系图 + 自动验证 |
| Skill关系 | 无 | 依赖/组合/冲突/替代/变体 |
| 子任务 | 无 | subagent 工具委派 |
| 双循环 | 隐含 | 显式分离 |
| 界面 | 实验性 | Web UI + 聊天平台适配器 |
