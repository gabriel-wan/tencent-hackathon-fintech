# Current architecture

What is built right now, not what is planned (see [ARCHITECTURE.md](ARCHITECTURE.md)
and [DECISIONS.md](../decisions/DECISIONS.md)). Only components that exist in code
or config appear here. Any PR that adds, removes or rewires a component updates
this diagram.

```mermaid
flowchart LR
    USER["Browser"]

    subgraph COMPOSE["Docker Compose (docker-compose.yml)"]
        FE["frontend<br/>Next.js, :3000<br/>app/page.tsx"]
        BE["backend<br/>FastAPI, :8000<br/>GET /health<br/>auth: sessions, /logout<br/>connectors: /connectors, /oauth/*/callback"]
        MIG["migrate<br/>alembic upgrade head<br/>runs once, then exits"]
        DB[("db<br/>PostgreSQL 17 + pgvector<br/>users, sessions, connections<br/>(tokens encrypted)<br/>internal only")]
    end

    MIG -->|"migrations"| DB

    USER -->|"HTTP :3000"| FE
    USER -.->|"HTTP :8000 (direct)"| BE
    FE -->|"server-side fetch<br/>BACKEND_URL/health"| BE
    BE -->|"SQLAlchemy engine (app/db.py)<br/>POSTGRES_* from backend/.env"| DB

    subgraph SRC["External sources (real, not mocked)"]
        JI["Jira"]
        CF["Confluence"]
        GD["Google Drive"]
        SL["Slack"]
    end

    USER -.->|"connect: OAuth sign-in<br/>(redirects via the browser)"| SRC
    BE -->|"OAuth code exchange, token refresh;<br/>API calls as the user (/connectors/*/ping)"| SRC
    BE -.->|"admin clients: python -m app.connectors<br/>can_read (Drive, Slack) built, not yet called<br/>no sync, no documents stored yet"| SRC
```
