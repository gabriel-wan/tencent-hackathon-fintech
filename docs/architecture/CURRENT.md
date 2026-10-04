# Current architecture

What is built right now, not what is planned (see [ARCHITECTURE.md](ARCHITECTURE.md)
and [DECISIONS.md](../decisions/DECISIONS.md)). Only components that exist in code
or config appear here. Any PR that adds, removes or rewires a component updates
this diagram.

```mermaid
flowchart LR
    USER["Browser"]
    TH["Tencent Cloud TokenHub<br/>hy3 chat + kinfra embeddings"]

    subgraph COMPOSE["Docker Compose (docker-compose.yml)"]
        FE["frontend<br/>Next.js, :3000<br/>app/page.tsx<br/>app/connectors/page.tsx (test page)"]
        subgraph BE["backend: FastAPI, :8000"]
            API["app/api<br/>/api/query, /api/me, /api/session<br/>/api/dev/* (development only)"]
            PIPE["app/pipeline/query.py"]
            AUTH["app/auth<br/>session, principals,<br/>live check (STUB)"]
            SEARCH["app/retrieval/search.py<br/>ACL + boundary filter,<br/>keyword + vector"]
            LLMC["app/llm<br/>client, grounding"]
            AUD["app/audit/log.py"]
            CONN["app/connectors<br/>/connectors, /oauth/*/callback<br/>sign-in, tokens, API clients"]
        end
        MIG["migrate<br/>alembic upgrade head<br/>runs once, then exits"]
        DB[("db<br/>PostgreSQL 17 + pgvector<br/>users, sessions, user_principals, boundary,<br/>documents, chunks, audit_events,<br/>connections (tokens encrypted)")]
    end

    MIG -->|"migrations 0001 to 0004"| DB
    USER -->|"HTTP :3000"| FE
    USER -.->|"HTTP :8000 (direct)"| BE
    FE -->|"server-side fetch, forwards the session cookie<br/>BACKEND_SERVER_URL/health, /connectors"| BE
    API --> PIPE
    PIPE --> AUTH
    PIPE --> SEARCH
    PIPE -->|"allowed sources only"| LLMC
    PIPE --> AUD
    SEARCH --> DB
    AUTH --> DB
    AUD --> DB
    LLMC --> TH
    CONN -->|"connections, sessions,<br/>user_principals"| DB

    subgraph SRC["External sources (real, not mocked)"]
        JI["Jira"]
        CF["Confluence"]
        GD["Google Drive"]
        SL["Slack"]
    end

    USER -.->|"connect: OAuth sign-in<br/>(redirects via the browser)"| SRC
    CONN -->|"OAuth code exchange, token refresh;<br/>API calls as the user (/connectors/*/ping)"| SRC
    CONN -.->|"admin clients: python -m app.connectors<br/>can_read (Drive, Slack) built, not yet wired<br/>into the live check; no sync yet"| SRC
```

Details and contracts: [QUERY_PIPELINE.md](QUERY_PIPELINE.md). Connectors sign
users in and record their principals, but do not sync yet; documents come from
the development seed (`app/seed.py`).
