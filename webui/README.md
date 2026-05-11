# Noesis Web UI

Next.js 16 frontend for the Noesis agent platform.

## Pages

| Route | Description |
|-------|-------------|
| `/` | Chat interface (WebSocket + REST) |
| `/skills` | Skill management (CRUD) |
| `/skills/[id]` | Skill detail with relations |
| `/memory` | Knowledge graph visualization |

## Development

```bash
npm install
npm run dev       # http://localhost:3000
```

The frontend connects to the backend at `NEXT_PUBLIC_API_HOST:NEXT_PUBLIC_API_PORT` (configured in `../.env`).

## Build

```bash
npm run build
npm start         # Production server
```
