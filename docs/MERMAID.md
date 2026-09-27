This file shows the architecture as it is built in the repository right now, not as it is planned. Planned designs belong in ARCHITECTURE.md and DECISIONS.md. The diagram shows only what exists in code and config: running services, frontend, backend, databases, external APIs, deployment targets, and how they connect. If something is not built, it is not in the diagram. Whenever a change adds, removes, or rewires a component, update the diagram in the same PR so it always matches the code. Keep this file to this paragraph plus one Mermaid diagram.

```mermaid
flowchart LR
    USER["Browser"]

    subgraph COMPOSE["Docker Compose (docker-compose.yml)"]
        FE["frontend<br/>Next.js, :3000<br/>app/page.tsx"]
        BE["backend<br/>FastAPI, :8000<br/>GET /health"]
        DB[("db<br/>PostgreSQL 17 + pgvector<br/>internal only")]
    end

    USER -->|"HTTP :3000"| FE
    USER -.->|"HTTP :8000 (direct)"| BE
    FE -->|"server-side fetch<br/>BACKEND_URL/health"| BE
    BE -->|"psycopg<br/>POSTGRES_* from backend/.env"| DB
```
