<div align="center">

<img src="https://img.shields.io/badge/Python-3.11+-blue?logo=python" alt="Python">
<img src="https://img.shields.io/badge/Neo4j-5.20-green?logo=neo4j" alt="Neo4j">
<img src="https://img.shields.io/badge/FastAPI-0.112-teal?logo=fastapi" alt="FastAPI">
<img src="https://img.shields.io/badge/Next.js-14-black?logo=next.js" alt="Next.js">
<img src="https://img.shields.io/badge/License-MIT-yellow" alt="License">

</div>

# Noesis

> 一个具有图原生记忆的自我进化 Agent。它从每次交互中学习，将经验提炼为可复用的工作流，并自主扩展其知识图谱。

受 [GenericAgent](https://github.com/lsdefine/GenericAgent) 启发，Noesis 继承了其极简原子工具集、分层记忆架构和三阶段技能进化——并在此基础上扩展了 Neo4j 图原生存储、显意识/潜意识双循环处理、多平台连接和自主探索能力。

---

## 亮点

- **图原生记忆** — 6 层 Neo4j 图存储，记录执行轨迹、技能、实体、SOP 和元模式，关系丰富
- **自我进化技能** — NL → SOP → Code 三阶段进化：Agent 从经验中学习，提炼工作流，编译为可执行脚本
- **显意识/潜意识双循环** — 实时 ReAct 推理处理用户任务；后台循环处理提炼、提取和自主探索
- **开放世界知识图谱** — L2 实体支持动态类型、置信度追踪、信念修正，以及从对话中自动提取
- **多平台** — Web UI + 微信 + QQ + Telegram + Discord + 飞书，共享同一会话
- **AgentScope 兼容消息** — 基于 ContentBlock 的统一消息模型，支持各平台转换器（OpenAI、DeepSeek）

---

## 核心架构

```
┌──────────────────────────────────────────────────────┐
│                  Noesis Agent 平台                    │
├───────────────────┬──────────────────────────────────┤
│   显意识循环       │   潜意识循环                     │
│   (ReAct 模式)    │   (后台运行，空闲时触发)           │
│                   │                                  │
│   用户输入 →       │   经验提炼                       │
│   L1 路由 →       │   NL → SOP → Code 进化          │
│   LLM 推理 →      │   实体自动提取                   │
│   工具执行 →       │   信念修正                       │
│   压缩 →          │   记忆生命周期                   │
│   响应            │   自主探索                       │
├───────────────────┴──────────────────────────────────┤
│              Neo4j 图数据库                           │
│     L0 轨迹 · L1 索引 · L2 实体 · L3 SOP              │
│         L4 元模式 · L5 归档                           │
├──────────────────────────────────────────────────────┤
│  Web UI │ 微信 │ QQ │ Telegram │ Discord │ 飞书       │
└──────────────────────────────────────────────────────┘
```

### 六层记忆

| 层 | 名称 | 存储 | 用途 |
|-------|------|---------|---------|
| **L0** | 情景轨迹 | Neo4j | 完整的执行路径，AgentScope 兼容消息格式 |
| **L1** | 语义索引 | Neo4j | 技能元数据及嵌入向量，始终存在于系统提示中 |
| **L2** | 知识图谱 | Neo4j | 开放世界实体，包含置信度、溯源、动态关系 |
| **L3** | SOP | Neo4j + 文件系统 | SKILL.md 文件中的标准操作流程 |
| **L4** | 元模式 | Neo4j | 跨领域抽象策略 |
| **L5** | 深度归档 | 文件系统 | 压缩日志、历史快照 |

### 三阶段技能进化

```
NL 阶段          SOP 阶段           CODE 阶段
自然语言  →  结构化 SOP   →  可执行代码
(探索)        (工作流)        (编译脚本)

Token 消耗: 100%  →  ~30%             →  ~10%
```

### 15 个原子工具

| 类别 | 工具 |
|----------|-------|
| **文件** | `file_read` · `file_patch` · `file_write` |
| **代码** | `code_run`（Python/Bash/PowerShell） |
| **网络** | `web_scan` · `web_execute_js` · `web_scraper` |
| **记忆** | `memory_search`（6 种模式） · `update_working_checkpoint` · `start_long_term_update` |
| **技能** | `skill_manage` · `entity_manage` · `meta_pattern` |
| **Agent** | `subagent` · `ask_user` |

---

## 快速开始

### 环境要求

- Python 3.11+
- Neo4j 5.x（Docker 或本地）
- Node.js 18+（Web UI）

### 1. 克隆并安装

```bash
git clone https://github.com/yourname/noesis.git
cd noesis
cp .env.example .env    # 编辑填入你的 API 密钥
uv sync
```

### 2. 启动 Neo4j

```bash
docker compose up -d neo4j
```

### 3. 启动 Noesis

```bash
# 后端（端口 8000）
uv run python main.py

# 前端（端口 3000）
cd webui && npm install && npm run dev
```

### 4. 打开

- **Web UI**: http://localhost:3000
- **API 文档**: http://localhost:8000/docs

---

## 平台适配器

所有适配器共享同一会话——在不同平台之间无缝切换。

```bash
# .env 配置
NOESIS_PLATFORM_WECHAT_ENABLED=true    # 微信（iLink API，扫码登录）
NOESIS_PLATFORM_QQ_ENABLED=true        # QQ（botpy SDK）
NOESIS_PLATFORM_TELEGRAM_ENABLED=true  # Telegram（bot token）
NOESIS_PLATFORM_DISCORD_ENABLED=true   # Discord（bot token）
NOESIS_PLATFORM_FEISHU_ENABLED=true    # 飞书/Lark（应用凭证）
```

---

## 进化实例

```
用户："研究最近的 GitHub PR 活动"
  │
第 1 轮：Agent 用自然语言探索
         → 32 次 LLM 调用，222K tokens
  │
  └─ start_long_term_update(reason="reusable_pattern")
  │
第 2 轮：从经验生成 SOP
         → 12 次 LLM 调用，66K tokens  (↓70%)
  │
  └─ start_long_term_update(reason="reusable_pattern")
  │
第 3 轮：从 SOP 编译为代码
         → 5 次 LLM 调用，23K tokens   (↓90%)
```

---

## 灵感来源

- [GenericAgent](https://github.com/lsdefine/GenericAgent) — 极简原子工具集 + 4 层记忆 + 3 阶段进化
- [AgentScope](https://github.com/agentscope-ai/agentscope) — 基于 ContentBlock 设计的消息模型

## 许可证

MIT
