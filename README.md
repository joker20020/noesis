<div align="center">

<img src="https://img.shields.io/badge/Python-3.11+-blue?logo=python" alt="Python">
<img src="https://img.shields.io/badge/Neo4j-5.20-green?logo=neo4j" alt="Neo4j">
<img src="https://img.shields.io/badge/FastAPI-0.112-teal?logo=fastapi" alt="FastAPI">
<img src="https://img.shields.io/badge/Next.js-14-black?logo=next.js" alt="Next.js">
<img src="https://img.shields.io/badge/License-MIT-yellow" alt="License">

</div>

# Noesis

> A self-evolving Agent with graph-native memory. It learns from every interaction, distills experience into reusable workflows, and autonomously expands its knowledge graph.

Inspired by [GenericAgent](https://github.com/lsdefine/GenericAgent), Noesis inherits the minimal atomic toolset, layered memory architecture, and three-stage skill evolution — then extends them with Neo4j graph-native storage, conscious/subconscious dual-loop processing, multi-platform connectivity, and autonomous exploration.

---

## Highlights

- **Graph-Native Memory** — 6-layer Neo4j graph stores execution traces, skills, entities, SOPs, and meta-patterns with rich relationships
- **Self-Evolving Skills** — NL → SOP → Code three-stage evolution: agent learns from experience, distills workflows, compiles to executable scripts
- **Conscious/Subconscious Dual Loop** — Real-time ReAct reasoning handles user tasks; background loop handles distillation, extraction, and autonomous exploration
- **Open-World Knowledge Graph** — L2 entities with dynamic types, confidence tracking, belief revision, and automatic extraction from conversations
- **Multi-Platform** — Web UI + WeChat + QQ + Telegram + Discord + Feishu, all sharing one session
- **AgentScope-Compatible Messages** — ContentBlock-based unified message model with per-provider converters (OpenAI, DeepSeek)

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

### Prerequisites

- Python 3.11+
- Neo4j 5.x (Docker or local)
- Node.js 18+ (for Web UI)

### 1. Clone & Install

```bash
git clone https://github.com/yourname/noesis.git
cd noesis
cp .env.example .env    # Edit with your API keys
uv sync
```

### 2. Start Neo4j

```bash
docker compose up -d neo4j
```

### 3. Start Noesis

```bash
# Backend (port 8000)
uv run python main.py

# Frontend (port 3000)
cd webui && npm install && npm run dev
```

### 4. Open

- **Web UI**: http://localhost:3000
- **API Docs**: http://localhost:8000/docs

---

## Platform Adapters

All adapters share a single session — switch between platforms seamlessly.

```bash
# .env configuration
NOESIS_PLATFORM_WECHAT_ENABLED=true    # WeChat (iLink API, QR login)
NOESIS_PLATFORM_QQ_ENABLED=true        # QQ (botpy SDK)
NOESIS_PLATFORM_TELEGRAM_ENABLED=true  # Telegram (bot token)
NOESIS_PLATFORM_DISCORD_ENABLED=true   # Discord (bot token)
NOESIS_PLATFORM_FEISHU_ENABLED=true    # Feishu/Lark (app credentials)
```

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

- [GenericAgent](https://github.com/lsdefine/GenericAgent) — Minimal atomic toolset + 4-layer memory + 3-stage evolution
- [AgentScope](https://github.com/agentscope-ai/agentscope) — Message model with ContentBlock design

## License

MIT
