<div align="center">

<img src="https://img.shields.io/badge/Python-3.11+-blue?logo=python" alt="Python">
<img src="https://img.shields.io/badge/Neo4j-5.20-green?logo=neo4j" alt="Neo4j">
<img src="https://img.shields.io/badge/FastAPI-0.112-teal?logo=fastapi" alt="FastAPI">
<img src="https://img.shields.io/badge/Next.js-14-black?logo=next.js" alt="Next.js">
<img src="https://img.shields.io/badge/License-MIT-yellow" alt="License">

</div>

# infoCap

> A self-evolving Agent with graph-native memory. Capabilities grow with use — from natural language to SOPs to executable code.

**infoCap** is a generic AI agent platform featuring **6-layer graph memory** (Neo4j), **conscious/subconscious dual-loop** architecture, **multi-platform connectivity** (WeChat, QQ, Telegram, Discord, Feishu + Web UI), and **autonomous skill self-evolution**. It learns from every interaction, distills experience into reusable workflows, and continuously expands its knowledge graph.

Inspired by [GenericAgent](https://github.com/lsdefine/GenericAgent) — inheriting its minimal atomic toolset, layered memory, and three-stage evolution design — then significantly enhanced with graph-native storage, multi-platform chat, and autonomous exploration.

<video src="https://github.com/user-attachments/assets/demo.mp4" width="800"></video>

---

## Why infoCap?

| | GenericAgent | infoCap |
|---|-------------|---------|
| **Memory** | Filesystem-only (Markdown) | Neo4j Graph DB + Filesystem |
| **Memory layers** | 4 layers | 6 layers + 3 cross-cutting mechanisms |
| **Knowledge graph** | None | Open-world Entity graph with dynamic relationships |
| **Skill evolution** | NL → SOP → Code | NL → SOP → Optimize → Code + variant detection |
| **Belief revision** | None | Confidence + provenance + contradiction resolution |
| **Multi-platform** | Experimental adapters | 6 platforms unified + single session |
| **UI** | None | Web UI with markdown, skill management, memory visualization |
| **Autonomous exploration** | — | Curriculum planning via 4D scoring |

---

## Core Architecture

```
┌──────────────────────────────────────────────────────┐
│                  infoCap Agent Platform               │
├───────────────────┬──────────────────────────────────┤
│  Conscious Loop   │  Subconscious Loop               │
│  (Real-time)      │  (Background)                    │
│                   │                                  │
│  User Input →     │  Experience Distillation         │
│  L1 Route →       │  NL → SOP → Code Evolution      │
│  LLM Reason →     │  Entity Auto-Extraction          │
│  Tool Execute →   │  Belief Revision                 │
│  Compress →       │  Memory Lifecycle                │
│  Respond          │  Autonomous Exploration          │
├───────────────────┴──────────────────────────────────┤
│              Neo4j Graph Database                     │
│     L0 Traces · L1 Index · L2 Entities · L3 SOPs      │
│         L4 Meta-Patterns · L5 Archives                │
├──────────────────────────────────────────────────────┤
│  Web UI │ WeChat │ QQ │ Telegram │ Discord │ Feishu   │
└──────────────────────────────────────────────────────┘
```

### Six-Layer Memory

| Layer | Name | Storage | Purpose |
|-------|------|---------|---------|
| **L0** | Episodic Traces | Neo4j | Complete execution paths as AgentScope-compatible Messages |
| **L1** | Semantic Index | Neo4j | Skill metadata with embeddings, always-on in system prompt |
| **L2** | Knowledge Graph | Neo4j | Open-world Entities with confidence, provenance, dynamic relationships |
| **L3** | SOPs | Neo4j + Filesystem | Standard Operating Procedures in SKILL.md files |
| **L4** | Meta-Patterns | Neo4j | Cross-domain abstract strategies |
| **L5** | Deep Archives | Filesystem | Compressed logs, historical snapshots |

### Three-Stage Skill Evolution

```
NL Stage          SOP Stage           CODE Stage
Natural Language  →  Structured SOP   →  Executable Code
(exploration)        (workflow)          (compiled script)

Token cost: 100%  →  ~30%             →  ~10%
```

### 14 Atomic Tools

| Category | Tools |
|----------|-------|
| **File** | `file_read` · `file_patch` · `file_write` |
| **Code** | `code_run` (Python/Bash/PowerShell) |
| **Web** | `web_scan` · `web_execute_js` · `web_scraper` |
| **Memory** | `memory_search` (6 modes: route/rag/sop/pattern/load/trace) · `update_working_checkpoint` · `start_long_term_update` |
| **Skill** | `skill_manage` · `entity_manage` · `meta_pattern` |
| **Agent** | `subagent` · `ask_user` |

---

## Quick Start

### Prerequisites

- Python 3.11+
- Neo4j 5.x (Docker or local)
- Node.js 18+ (for Web UI)

### 1. Clone & Install

```bash
git clone https://github.com/yourname/infocap.git
cd infocap
cp .env.example .env    # Edit with your API keys
uv sync
```

### 2. Start Neo4j

```bash
docker compose up -d neo4j
```

### 3. Start infoCap

```bash
# Backend (port 8000)
uv run python main.py

# Frontend (port 3000)
cd webui && npm install && npm run dev
```

### 4. Open

- **Web UI**: http://localhost:3000
- **API Docs**: http://localhost:8000/docs
- **Health**: http://localhost:8000/api/health

---

## Platform Adapters

All adapters share a single session — switch between platforms seamlessly.

```bash
# .env configuration
INFOCAP_PLATFORM_WECHAT_ENABLED=true    # WeChat (iLink API, QR login)
INFOCAP_PLATFORM_QQ_ENABLED=true        # QQ (botpy SDK)
INFOCAP_PLATFORM_TELEGRAM_ENABLED=true  # Telegram (bot token)
INFOCAP_PLATFORM_DISCORD_ENABLED=true   # Discord (bot token)
INFOCAP_PLATFORM_FEISHU_ENABLED=true    # Feishu/Lark (app credentials)
```

Common commands across all platforms: `/restart` (clear history), `/stop` (abort).

---

## Project Structure

```
infoCap/
├── agent/             # Core engine (conscious, subconscious, context, compression)
├── llm/               # LLM clients (OpenAI, DeepSeek) + provider converters
├── tools/             # 14 atomic tools
├── memory/            # Neo4j graph models, entities, index, lifecycle, belief
├── skill_system/      # Skill registry, distillation, optimizer, compiler, scorer
├── exploration/       # Autonomous exploration (planner, executor, reflector)
├── adapters/          # Platform adapters (wechat, qq, telegram, discord, feishu)
├── server/            # FastAPI + WebSocket
├── webui/             # Next.js frontend
├── skills/            # Runtime-generated skill directories
└── docs/              # Design specs, plans, agent guide
```

---

## Evolution in Action

```
User: "帮我查一下最近的 GitHub PR 动态"
  │
Round 1: Agent explores with natural language
         → 32 LLM calls, 222K tokens
  │
  └─ start_long_term_update(reason="reusable_pattern")
  │
Round 2: SOP generated from experience
         → 12 LLM calls, 66K tokens  (↓70%)
  │
  └─ start_long_term_update(reason="reusable_pattern")
  │
Round 3: Code compiled from SOP
         → 5 LLM calls, 23K tokens   (↓90%)
```

---

## Inspired By

- [GenericAgent](https://github.com/lsdefine/GenericAgent) — Minimal atomic toolset + 4-layer memory + 3-stage evolution
- [AgentScope](https://github.com/agentscope-ai/agentscope) — Message model with ContentBlock design
- [OpenClaw](https://docs.openclaw.ai) — Gateway protocol and multi-channel adapter pattern

## License

MIT
