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
        FE["frontend<br/>Next.js + Tailwind + shadcn/ui, :3000<br/>/login, / (signed in, placeholder), /connectors,<br/>/status, /healthz<br/>session gate (app/(app)/layout.tsx)<br/>/api/* proxy (app/api/[...path])"]
        subgraph BE["backend: FastAPI, :8000"]
            API["app/api<br/>/api/query, /api/me, /api/session<br/>/api/dev/* (development only)"]
            PIPE["app/pipeline/query.py"]
            AUTH["app/auth<br/>session, principals,<br/>live check runner"]
            SEARCH["app/retrieval/search.py<br/>company + ACL + boundary filter,<br/>keyword + vector"]
            LLMC["app/llm<br/>client, grounding"]
            AUD["app/audit/log.py"]
            CONN["app/connectors<br/>/connectors, /oauth/*/callback, /api/admin/*<br/>sign-in, tokens, fetch, live checks"]
        end
        SYNC["sync<br/>python -m app.sync --loop<br/>every company, every 5 min"]
        MIG["migrate<br/>alembic upgrade head<br/>runs once, then exits"]
        DB[("db<br/>PostgreSQL 17 + pgvector<br/>companies, users, sessions, user_principals,<br/>boundary, documents, chunks, audit_events,<br/>connections (tokens encrypted)")]
    end

    MIG -->|"migrations 0001 to 0005"| DB
    USER -->|"HTTP :3000"| FE
    USER -.->|"HTTP :8000 (direct)"| BE
    FE -->|"/api/* proxy and server-side fetches,<br/>session cookie forwarded<br/>BACKEND_SERVER_URL: /api/*, /connectors, /health"| BE
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
    CONN -->|"OAuth code exchange, token refresh;<br/>live checks as the asking user"| SRC
    AUTH -->|"can_read per source"| CONN
    SYNC -->|"fetch boundary scopes<br/>as the company admin"| SRC
    SYNC -->|"documents, chunks"| DB
    SYNC -->|"embeddings"| TH
```

Details and contracts: [QUERY_PIPELINE.md](QUERY_PIPELINE.md). Many companies share
one deployment; every query is limited to the user's own company. Documents come
from sync, or from the development seed (`app/seed.py`).
