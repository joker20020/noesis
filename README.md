<div align="center">

<img src="https://img.shields.io/badge/Python-3.11+-blue?logo=python" alt="Python">
<img src="https://img.shields.io/badge/Neo4j-5.20-green?logo=neo4j" alt="Neo4j">
<img src="https://img.shields.io/badge/FastAPI-0.112-teal?logo=fastapi" alt="FastAPI">
<img src="https://img.shields.io/badge/Next.js-16-black?logo=next.js" alt="Next.js">
<img src="https://img.shields.io/badge/Docker-✓-2496ED?logo=docker" alt="Docker">
<img src="https://img.shields.io/badge/License-MIT-yellow" alt="License">

</div>

# Noesis

> A self-evolving Agent with graph-native memory. It learns from every interaction, distills experience into reusable workflows, and autonomously expands its knowledge graph.

Inspired by [GenericAgent](https://github.com/lsdefine/GenericAgent), Noesis inherits the minimal atomic toolset, layered memory architecture, and three-stage skill evolution — then extends them with Neo4j graph-native storage, conscious/subconscious dual-loop processing, multi-platform connectivity, and autonomous exploration.

---

## Highlights

- **Graph-Native Memory** — 6-layer Neo4j graph stores execution traces, skills, entities, SOPs, and meta-patterns with rich relationships
- **Self-Evolving Skills** — NL → SOP → Code three-stage evolution: agent learns from experience, distills workflows, compiles to executable scripts
- **Conscious/Subconscious Dual Loop** — Real-time ReAct reasoning handles user tasks; background loop handles distillation, extraction, lifecycle, and autonomous exploration
- **Open-World Knowledge Graph** — L2 entities with dynamic types, confidence tracking, belief revision, and automatic extraction from conversations
- **Multi-Platform** — Web UI + WeChat + QQ + Telegram + Discord + Feishu, all sharing one session
- **Docker Compose** — One-command deployment with Neo4j, backend, and frontend

---

## Core Architecture

```
┌──────────────────────────────────────────────────────┐
│                  Noesis Agent Platform                │
├───────────────────┬──────────────────────────────────┤
│  Conscious Loop   │  Subconscious Loop               │
│  (ReAct Pattern)  │  (Background, triggered by idle) │
│                   │                                  │
│  User Input →     │  Experience Distillation         │
│  L1 Route →       │  NL → SOP → Code Evolution      │
│  LLM Reason →     │  Entity Auto-Extraction          │
│  Tool Execute →   │  Belief Revision                 │
│  Compress →       │  Memory Lifecycle                │
│  Respond          │  Compressed Step Eviction        │
│                   │  Autonomous Exploration          │
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
| **L0** | Episodic Traces | Neo4j | Complete execution paths as ExecutionStep linked-list |
| **L1** | Semantic Index | Neo4j | Skill metadata, always-on in system prompt |
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

### 15 Atomic Tools

| Category | Tools |
|----------|-------|
| **File** | `file_read` · `file_patch` · `file_write` |
| **Code** | `code_run` (Python/Bash/PowerShell) |
| **Web** | `web_scan` · `web_execute_js` · `web_scraper` |
| **Memory** | `memory_search` (6 modes) · `update_working_checkpoint` · `start_long_term_update` |
| **Skill** | `skill_manage` · `entity_manage` · `meta_pattern` |
| **Agent** | `subagent` · `ask_user` |

---

## Quick Start

### Docker Compose (Recommended)

```bash
git clone https://github.com/yourname/noesis.git
cd noesis
cp .env.example .env          # Edit with your API keys
docker compose up -d          # Starts Neo4j + Backend + Frontend
```

| Service | URL |
|---------|-----|
| Web UI | http://localhost:3000 |
| API Docs | http://localhost:8000/docs |
| Neo4j Browser | http://localhost:7474 |

### Local Development

#### Prerequisites

- Python 3.11+
- Neo4j 5.x
- Node.js 20+
- [uv](https://docs.astral.sh/uv/)

#### 1. Install

```bash
git clone https://github.com/yourname/noesis.git
cd noesis
cp .env.example .env          # Edit with your API keys

# Python backend
uv sync
uv run playwright install chromium
uv run playwright install-deps chromium   # Linux only

# Frontend
cd webui && npm install
```

#### 2. Start Neo4j

```bash
docker compose up -d neo4j
```

#### 3. Start Services

```bash
# Backend (port 8000)
uv run python main.py

# Frontend (port 3000, separate terminal)
cd webui && npm run dev
```

---

## Configuration

All settings are in `.env` (copy from `.env.example`).

### Required

| Variable | Default | Description |
|----------|---------|-------------|
| `NOESIS_LLM_PROVIDER` | `openai` | LLM provider: `openai` or `deepseek` |
| `NOESIS_LLM_MODEL` | `gpt-4o` | Model name |
| `NOESIS_LLM_API_KEY` | — | API key |
| `NOESIS_LLM_BASE_URL` | — | Custom API base URL (optional) |

### Neo4j

| Variable | Default |
|----------|---------|
| `NOESIS_NEO4J_URI` | `bolt://localhost:7687` |
| `NOESIS_NEO4J_USER` | `neo4j` |
| `NOESIS_NEO4J_PASSWORD` | `noesis123` |

> In Docker Compose, `NOESIS_NEO4J_URI` is overridden to `bolt://neo4j:7687` (service name).

### Web Server

| Variable | Default | Description |
|----------|---------|-------------|
| `NOESIS_WEB_HOST` | `127.0.0.1` | Bind address (`0.0.0.0` in Docker) |
| `NOESIS_WEB_PORT` | `8000` | Backend port |
| `FRONTEND_PORT` | `3000` | Frontend port (Docker only) |
| `NEXT_PUBLIC_API_HOST` | `localhost` | Browser→backend address |

### Context Budget

| Variable | Default |
|----------|---------|
| `NOESIS_CONTEXT_BUDGET_TOKENS` | `30000` |
| `NOESIS_SUBCONSCIOUS_IDLE_SECONDS` | `300` |
| `NOESIS_SUBCONSCIOUS_TIMER_SECONDS` | `1800` |

---

## Platform Adapters

All adapters share a single session — switch between platforms seamlessly.

```bash
# .env — set _ENABLED=true and fill credentials
NOESIS_PLATFORM_WECHAT_ENABLED=true    # WeChat (iLink API, QR login, no credentials needed)
NOESIS_PLATFORM_QQ_ENABLED=true        # QQ (botpy SDK, app_id + app_secret)
NOESIS_PLATFORM_TELEGRAM_ENABLED=true  # Telegram (bot token)
NOESIS_PLATFORM_DISCORD_ENABLED=true   # Discord (bot token + channels)
NOESIS_PLATFORM_FEISHU_ENABLED=true    # Feishu/Lark (app_id + app_secret)
```

| Adapter | Credentials Required |
|---------|---------------------|
| WeChat | None — scan QR code to login |
| QQ | `QQ_APP_ID`, `QQ_APP_SECRET`, `QQ_ALLOWED_USERS` |
| Telegram | `TELEGRAM_TOKEN`, `TELEGRAM_ALLOWED_USERS` |
| Discord | `DISCORD_TOKEN`, `DISCORD_CHANNELS` |
| Feishu | `FEISHU_APP_ID`, `FEISHU_APP_SECRET` |

---

## Docker

```bash
# Create env from template
cp .env.example .env

# All services
docker compose up -d

# Specific service
docker compose up -d backend

# View logs
docker compose logs -f backend

# Rebuild after code changes
docker compose up -d --build
```

### Volumes

| Volume | Purpose |
|--------|---------|
| `neo4j_data` | Neo4j database files |
| `neo4j_logs` | Neo4j logs |
| `workspace_data` | Agent workspace, WeChat token, media |
| `skills_data` | Skill files (SKILL.md) |
| `archives_data` | Compressed archives |

### Dockerfile

- Python 3.11-slim + uv for dependency management
- Playwright Chromium with all system dependencies
- Multi-stage Next.js build for the frontend
- Neo4j health check before backend starts

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/history` | Session execution history |
| `GET` | `/api/skills` | List all skills |
| `POST` | `/api/skills` | Create a new skill |
| `GET` | `/api/skills/{id}` | Skill detail with SKILL.md + relations |
| `DELETE` | `/api/skills/{id}` | Delete skill |
| `GET` | `/api/memory/graph?keyword=` | Knowledge graph nodes & edges |
| `POST` | `/api/abort` | Abort current agent task |
| `DELETE` | `/api/session` | Clear session + restart |
| `WS` | `/ws/chat` | WebSocket chat |

---

## Evolution in Action

```
User: "Research recent GitHub PR activity"
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

- [GenericAgent](https://github.com/lsdefine/GenericAgent) — Minimal atomic toolset + layered memory + 3-stage skill evolution
- [AgentScope](https://github.com/agentscope-ai/agentscope) — Message model with ContentBlock design

## License

MIT
