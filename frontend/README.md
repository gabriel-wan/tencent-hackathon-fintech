# frontend/

Next.js app (see DECISIONS.md, ADR-001). Currently a skeleton:
- `/` shows the backend's `/health` result, fetched server-side from `BACKEND_SERVER_URL`.
- `/connectors` (`app/connectors/page.tsx`) is a basic test page: connect, test and disconnect each tool.

The frontend never makes authorization decisions; the backend filters by
permission before anything reaches the LLM (SECURITY.md, INV-2). Frontend tests
live in this folder.
