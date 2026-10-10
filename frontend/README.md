# Frontend

**For:** anyone editing the website.
**You'll:** find the commands, where things are, and the styling and dependency rules.
**Not here:** how the frontend works (pages, sign-in, the `/api` proxy, the chat) →
[docs/architecture/FRONTEND.md](../docs/architecture/FRONTEND.md) · running the whole app →
[docs/RUNNING.md](../docs/RUNNING.md).

The frontend never decides who may see what: the backend filters by permission before anything reaches the LLM
([SECURITY.md](../docs/SECURITY.md), INV-2). The design decisions behind it are ADR-009 in
[DECISIONS.md](../docs/decisions/DECISIONS.md).

## Stack

| Piece | What it is for |
|---|---|
| Next.js 16 (App Router) | Pages and server-side calls to the backend |
| Tailwind CSS v4 | Styling, compiled at build time (`postcss.config.mjs`) |
| shadcn/ui (Radix base, Nova preset) | Accessible components, copied into `components/ui/` |
| next-themes | System / Light / Dark theme, no flash on load |
| lucide-react | Icons (generic icons only; tool logos come from `public/logos/`, see below) |

## Commands

Run from `frontend/`, with Node 24, the same version as the Docker image (Homebrew: `node@24`, see
[RUNNING.md](../docs/RUNNING.md) §1).

| Command | Does |
|---|---|
| `npm ci` | Installs exactly the locked dependencies (once, and after each pull) |
| `npm run dev` | Runs the website with live reloading on http://localhost:3000. If the Docker frontend already holds that port: `npm run dev -- -p 3001` |
| `npm test` | Unit tests (Vitest); tests sit next to the code as `*.test.ts` |
| `npx tsc --noEmit` | Type-checks everything |
| `npm run build` | The production build |
| `npm run gen:api-types` | Regenerates `lib/api/schema.d.ts` from the running backend's API (http://localhost:8000) |

What each check catches, and the manual and accessibility checks: [docs/TESTING.md](../docs/TESTING.md) §2 and §5.

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
components/admin/     the audit trail and the boundary editor
lib/api/              backend client (client.ts, server.ts), errors, generated types, mock mode
lib/                  answer, citation, audit, boundary and date helpers; connectors.ts (connector ids, OAuth messages); utils.ts is shadcn's cn()
components.json       shadcn CLI settings
```

## Theme and styling rules

- Colours are CSS variables in `app/globals.css` (light under `:root`, dark under `.dark`), using shadcn's names.
  Use them through Tailwind classes (`bg-card`, `text-muted-foreground`, `border-input`, `bg-warning`); never
  hard-code a colour in a component.
- **Tool logos** (`components/platform-logo.tsx`, files in `public/logos/`) only name an integration (Slack,
  Google Drive, Jira, Confluence), always next to the tool's written name, which carries the meaning. Each file comes
  from the vendor's own brand page, unaltered: Slack's media kit (the colour mark), Google's Drive branding guidelines,
  and Atlassian's logo library (the "app" icons). A missing or failing file shows nothing, or a generic icon.
- Our brand colour is `--primary`. shadcn's `--accent` is the hover background, not the brand colour.
- `--destructive` is for genuine failures only. A "not found" answer is never red.
- `--warning` is for "unavailable", development-only aids and mock data.
- Input borders use `--input`, which meets 3:1 contrast; `--border` is for decorative edges only.
- Every text/background pair meets WCAG AA. Re-check contrast when changing a value.
- Animations are switched off under `prefers-reduced-motion`.

The design principles and the full accessibility rules (WCAG 2.2 AA):
[docs/architecture/FRONTEND.md](../docs/architecture/FRONTEND.md).

## Adding a shadcn component

`npx shadcn@latest add <component>` (for example `card`). It writes `components/ui/<component>.tsx` and may add a
Radix dependency; list any new dependency in the PR. Add components only when a page needs them.

## Dependency notes

- `shadcn` and `tw-animate-css` are dev dependencies: only their CSS is used, at build time. `npm audit` reports an
  advisory in the shadcn CLI's own tree (`braces`); it does not reach the app's runtime dependencies
  (`npm audit --omit=dev` is clean).
- `cn` is shadcn's class-name merger, published by the same npm account as the `shadcn` package.
- `openapi-typescript` and `vitest` are dev dependencies (type generation, tests). `@types/node` is `^24` to match
  the Node 24 runtime (Vitest 5 needs 22 or newer).

## More

- How the frontend works: [docs/architecture/FRONTEND.md](../docs/architecture/FRONTEND.md).
- Planned UI work and open questions: [docs/PROJECT.md](../docs/PROJECT.md) ("Planned UI work" and "Open items").
- How we work (branches, commits, pull requests): [CONTRIBUTING.md](../CONTRIBUTING.md).
