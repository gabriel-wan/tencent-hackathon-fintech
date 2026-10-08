# frontend/

Next.js app (see DECISIONS.md, ADR-001). Status: sign-in (Google, Slack and
Atlassian through the backend's OAuth, plus the development persona switcher),
the chat, the Connections page and the signed-in shell work; the admin pages
are honest stubs (the audit and boundary APIs both exist; wiring the pages to
them is next).

The frontend never makes authorization decisions; the backend filters by
permission before anything reaches the LLM (SECURITY.md, INV-2). Frontend tests
live in this folder.

## Stack

| Piece | What it is for |
|---|---|
| Next.js 16 (App Router) | Pages and server-side calls to the backend |
| Tailwind CSS v4 | Styling, compiled at build time (`postcss.config.mjs`) |
| shadcn/ui (Radix base, Nova preset) | Accessible components, copied into `components/ui/` |
| next-themes | System / Light / Dark theme, no flash on load |
| lucide-react | Icons (generic icons only, no brand logos) |

## How it works

Every page, sign-in and the session gate, the Connections page, the chat's states, the admin pages, the `/api`
proxy, server actions, API types, how answers and links are rendered, and mock mode:
[docs/architecture/FRONTEND.md](../docs/architecture/FRONTEND.md).

## Tests

From `frontend/`: `npm test` (Vitest); tests sit next to the code (`*.test.ts`). What they cover and the other
checks to run: [docs/TESTING.md](../docs/TESTING.md) section 2.

## Folders

```
app/(app)/            signed-in pages; layout.tsx is the session gate
app/connectors/       Connections page and its server actions
app/(public)/         /login and /status, no session needed
app/api/[...path]/    the /api proxy to the backend
app/                  root layout.tsx (theme), globals.css, healthz/
components/ui/        shadcn-generated components: edit freely, keep them generic
components/           our own components, built from components/ui
components/connectors/  connection cards and the development-only Slack token form
components/admin/     admin stubs: NotBuiltYet, DesignPreview, audit and boundary previews
lib/mock/             DEVELOPMENT ONLY fixtures for the admin design previews
lib/api/              backend client (client.ts, server.ts), errors, generated types, mock mode
lib/                  answer, citation and date helpers; connectors.ts (connector ids, OAuth messages); utils.ts is shadcn's cn()
components.json       shadcn CLI settings
```

## Running

- With everything else: `docker compose up --build` from the repo root, then
  http://localhost:3000.
- Hot reload while editing: install Node 24 (same as the Docker image), then in
  `frontend/`: `npm ci` once and `npm run dev`. Use `npm run dev -- -p 3001`
  if the Docker frontend already holds port 3000.

## Theme and styling rules

- Colours are CSS variables in `app/globals.css` (light under `:root`, dark
  under `.dark`), using shadcn's names. Use them through Tailwind classes
  (`bg-card`, `text-muted-foreground`, `border-input`, `bg-warning`); never
  hard-code a colour in a component.
- Our brand colour is `--primary`. shadcn's `--accent` is the hover
  background, not the brand colour.
- `--destructive` is for genuine failures only. A "not found" answer is never
  red.
- `--warning` is for "unavailable", development-only aids and mock data.
- Input borders use `--input`, which meets 3:1 contrast; `--border` is for
  decorative edges only.
- Every text/background pair meets WCAG AA. Re-check contrast when changing a
  value.
- Animations are switched off under `prefers-reduced-motion`.

## Design principles and accessibility

The design principles and the accessibility rules (WCAG 2.2 AA):
[docs/architecture/FRONTEND.md](../docs/architecture/FRONTEND.md). How to check them:
[docs/TESTING.md](../docs/TESTING.md) section 5.

## Planned next (not built)

| Waiting on | UI work |
|---|---|
| Nothing (the API exists) | Real `/admin/boundary` on the boundary API: list scopes per tool, add and remove them, "Sync now" |
| Nothing | Show which sources are connected in the chat |
| Return target after the OAuth callback | Show sign-in errors on `/login` rather than `/connectors`. The target must come from a fixed allowlist, never an arbitrary URL (open redirect) |
| `label` on each citation | Turn `[S1]` markers into chips linked to the right source (today they are stripped: an answer citing `[S1]` and `[S3]` came back with two citations, so mapping by position would be wrong) |
| `status` on query responses | Classify answers by status instead of matching the fixed sentences |
| Nothing (the API exists) | Real `/admin/audit` (search, verify chain); make "Ref #" a link for admins |
| Something to poll after `POST /api/admin/sync` (`synced_at` on citations and `last_synced_at` on the boundary already exist) | "Synced N minutes ago" under answers and after "Sync now", for the freshness demo (scenario 2) |
| A company field on `GET /api/me` | Tell "you have no company yet" apart from "nothing found" (today `/connectors` only infers it from the connections) |
| Redaction and injection flags (7–8 Oct) | Redaction chip on citations; blocked-injection notice on answers |

Each replaces a stub or a reserved slot; remove the matching "Not built yet"
panel and design preview in the same PR.

**Deployment (ADR-008).** Outside `APP_ENV=development` the backend marks the
session cookie `Secure`, which browsers only send over HTTPS. The live site
must be served over HTTPS, or sign-in silently fails.

## Open questions

Raised while building the UI; answers belong in DECISIONS.md or the code.

| For | Question |
|---|---|
| Whole team | May the audit page show titles of documents the admin cannot read? (ARCHITECTURE §3.12 vs ADR-007.) Until decided, documents are shown by key |
| Whole team | Who sets up HTTPS on the Lighthouse server? |
| Whole team | Demo accounts: which Google accounts are OAuth test users (Testing-mode tokens expire after 7 days)? A Google-only contractor no longer works (Google names no company), and Slack guests need a paid plan: how does the demo show the contractor? |
| Whole team | Linter/formatter is still open (ADR-001) |
| Query pipeline | Add `label` and `status` to the query response; should a 503 "LLM is not configured" become the fixed "unavailable" reply? |
| Query pipeline | Without an LLM configured, `/api/query` returns 503 before the pipeline runs, so the question is not audited. Should it be? |
| Connectors | A fixed-allowlist return target after sign-in, so a successful sign-in can land in the chat; what happens when someone disconnects their last connection; can personal Gmail users get `google:domain:gmail.com` as a principal? |
| Connectors | `GET /api/me` has no company field, and `POST /api/admin/sync` gives nothing to poll (only each scope's `last_synced_at`): can both be added? |

## Adding a shadcn component

From `frontend/`: `npx shadcn@latest add <component>` (for example `card`).
It writes `components/ui/<component>.tsx` and may add a Radix dependency; list
any new dependency in the PR. Add components only when a page needs them.

## Dependency notes

- `shadcn` and `tw-animate-css` are dev dependencies: only their CSS is used,
  at build time. `npm audit` reports an advisory in the shadcn CLI's own tree
  (`braces`); it does not reach the app's runtime dependencies
  (`npm audit --omit=dev` is clean).
- `cn` is shadcn's class-name merger, published by the same npm account as the
  `shadcn` package.
- `openapi-typescript` and `vitest` are dev dependencies (type generation,
  tests). `@types/node` is `^24` to match the Node 24 runtime (Vitest 5 needs
  22 or newer).
