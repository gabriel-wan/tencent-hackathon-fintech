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
        FE["frontend<br/>Next.js + Tailwind + shadcn/ui, :3000<br/>/ (placeholder), /status, /healthz<br/>/api/* proxy (app/api/[...path])"]
        subgraph BE["backend: FastAPI, :8000"]
            API["app/api<br/>/api/query, /api/me, /api/session<br/>/api/dev/* (development only)"]
            PIPE["app/pipeline/query.py"]
            AUTH["app/auth<br/>session, principals,<br/>live check (STUB)"]
            SEARCH["app/retrieval/search.py<br/>ACL + boundary filter,<br/>keyword + vector"]
            LLMC["app/llm<br/>client, grounding"]
            AUD["app/audit/log.py"]
        end
        MIG["migrate<br/>alembic upgrade head<br/>runs once, then exits"]
        DB[("db<br/>PostgreSQL 17 + pgvector<br/>users, sessions, boundary,<br/>documents, chunks, audit_events")]
    end

    MIG -->|"migrations 0001 to 0003"| DB
    USER -->|"HTTP :3000"| FE
    USER -.->|"HTTP :8000 (direct)"| BE
    FE -->|"/api/* proxy (cookie forwarded)<br/>/status: BACKEND_URL/health"| BE
    API --> PIPE
    PIPE --> AUTH
    PIPE --> SEARCH
    PIPE -->|"allowed sources only"| LLMC
    PIPE --> AUD
    SEARCH --> DB
    AUTH --> DB
    AUD --> DB
    LLMC --> TH
```

Details and contracts: [QUERY_PIPELINE.md](QUERY_PIPELINE.md). Connectors are
not built yet; documents come from the development seed (`app/seed.py`).
