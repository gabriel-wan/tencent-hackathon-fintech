"use client";

import { ChevronRight, Info, ListMinus, ListPlus, Lock, RefreshCw, Search, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Disclosure } from "@/components/disclosure";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { PlatformLogo } from "@/components/platform-logo";
import { addScope, bulkScopes, listBoundary, listScopes, removeScope, syncNow } from "@/lib/api/client";
import { ApiError, BackendUnreachableError, NotSignedInError } from "@/lib/api/errors";
import type { SourceName } from "@/lib/api/types";
import {
  BULK_LIMIT,
  type BoundaryEntry,
  type Scope,
  type ScopeRow,
  type ScopesProblem,
  type ShowMode,
  TOOLS,
  blockedReason,
  bulkRows,
  coveredBy,
  matchRows,
  rowState,
  rowsFor,
  scopeKey,
  stillSyncing,
  syncSnapshot,
  treeOrder,
} from "@/lib/boundary";
import { formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";

// /admin/boundary (ADR-002): the admin chooses which channels, folders,
// projects and spaces KnowBuddy may read at all. Ticking one adds it and syncs
// straight away; unticking removes it (its content leaves answers at once).
// Admins only: the admin layout hides the page from others, and every route
// returns 403 to them anyway. Every change and sync is recorded in the audit trail.

const POLL_EVERY_MS = 3_000;
const POLL_FOR_MS = 60_000;

type Tool = (typeof TOOLS)[number];

type ScopesState =
  | { status: "loading" }
  | { status: "ready"; scopes: Scope[] }
  | { status: "problem"; problem: ScopesProblem }
  | { status: "failed"; message: string };

type SyncState =
  | { status: "idle" }
  | { status: "syncing" }
  | { status: "done" }
  | { status: "nothing" } // no allowed scope can sync: its tools aren't (properly) connected
  | { status: "partial"; pending: BoundaryEntry[] }
  | { status: "failed"; message: string };

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** What to tell the admin when a call fails. Signed out: back to /login, like the chat. */
function failureOf(error: unknown): string {
  if (error instanceof NotSignedInError) {
    window.location.assign("/login");
    return "Your session has ended.";
  }
  if (error instanceof BackendUnreachableError) return "Can't reach the server. Please try again in a moment.";
  if (error instanceof ApiError && error.status === 403) return "Only admins can change the boundary.";
  if (error instanceof ApiError && error.status === 409) return `${error.detail}.`; // overlapping Drive folders
  if (error instanceof ApiError) return `Something went wrong (HTTP ${error.status}).`;
  return "Something went wrong.";
}

function HowItWorks() {
  return (
    <Disclosure summary="How the boundary works">
      <div className="grid max-w-prose gap-2 text-muted-foreground">
        <p>
          A document can appear in an answer only if <strong className="text-foreground">both</strong> say yes: the
          tool (the person asking may read it there) and this boundary (the company lets KnowBuddy use it).
        </p>
        <ul className="grid list-disc gap-1 pl-5">
          <li>
            KnowBuddy copies only what&apos;s ticked here, every 5 minutes, using <em>your</em> connection to each
            tool. So you can only add what you can see yourself.
          </li>
          <li>Ticking a box adds it and syncs straight away. Unticking removes its content from answers at once.</li>
          <li>
            Everything outside the boundary is never copied, never sent to the AI, and never answered from, even
            for people who can open it in the tool.
          </li>
          <li>
            Every change is recorded in the audit trail:{" "}
            <Link href="/admin/audit?event_type=boundary_added" className="text-primary underline underline-offset-4">
              additions
            </Link>{" "}
            and{" "}
            <Link href="/admin/audit?event_type=boundary_removed" className="text-primary underline underline-offset-4">
              removals
            </Link>
            .
          </li>
        </ul>
      </div>
    </Disclosure>
  );
}

function SyncStatus({ state }: { state: SyncState }) {
  return (
    <div aria-live="polite" className="text-sm">
      {state.status === "syncing" ? <p className="text-muted-foreground">Syncing… this can take a minute.</p> : null}
      {state.status === "done" ? <p className="text-muted-foreground">Synced just now.</p> : null}
      {state.status === "nothing" ? (
        <p className="text-muted-foreground">
          Nothing here can sync until a tool is connected. See the note under each tool.
        </p>
      ) : null}
      {state.status === "partial" ? (
        <Alert>
          <Info aria-hidden="true" />
          <AlertTitle>Not synced yet: {state.pending.map((b) => b.title || b.scope_id).join(", ")}</AlertTitle>
          <AlertDescription>
            They sync within 5 minutes. If they stay like this, check that tool on{" "}
            <Link href="/connectors" className="underline underline-offset-4">
              Connections
            </Link>
            .
          </AlertDescription>
        </Alert>
      ) : null}
      {state.status === "failed" ? (
        <p role="alert" className="text-destructive">
          Couldn&apos;t start a sync: {state.message}
        </p>
      ) : null}
    </div>
  );
}

function RowStatusLine({
  row,
  tool,
  now,
  syncing,
  problem,
}: {
  row: ScopeRow;
  tool: Tool;
  now: number;
  syncing: boolean;
  problem: ScopesProblem | null; // the tool's scope list problem, explained by the section's notice
}) {
  const state = rowState(row, now, problem);
  if (state === "outside") return null;
  if (state === "not-connected" || state === "reconnect") {
    return (
      <span className="text-xs text-muted-foreground">
        Can&apos;t sync until {tool.label} is connected{state === "reconnect" ? " again" : ""}
      </span>
    );
  }
  if (state === "unseen") {
    return (
      <span className="text-xs text-destructive">
        You can no longer see this {tool.scope} in {tool.label}, so it can&apos;t sync.
      </span>
    );
  }
  if (state === "not-synced") {
    return <span className="text-xs text-muted-foreground">{syncing ? "Syncing…" : "Not synced yet"}</span>;
  }
  const when = formatRelative(row.lastSyncedAt!, now);
  return state === "stale" ? (
    <span className="text-xs text-destructive">Last synced {when}: it may be failing. Check {tool.label} on Connections.</span>
  ) : (
    <span className="text-xs text-muted-foreground">Synced {when}</span>
  );
}

function ProblemNotice({ tool, problem, onRetry }: { tool: Tool; problem: ScopesProblem; onRetry: () => void }) {
  const text = {
    "not-connected": `Connect ${tool.label} to choose ${tool.scopes}.`,
    reconnect: `${tool.label} refused KnowBuddy's stored access. Connect it again to choose ${tool.scopes}.`,
    "tool-failed": `${tool.label} didn't answer. Its ${tool.scopes} can't be listed right now.`,
  }[problem];
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-muted/50 px-3 py-2 text-sm">
      <p className="text-muted-foreground">{text}</p>
      {problem === "tool-failed" ? (
        <Button variant="outline" size="sm" onClick={onRetry}>
          Try again
        </Button>
      ) : (
        <Button variant="outline" size="sm" asChild>
          <Link href="/connectors">Go to Connections</Link>
        </Button>
      )}
    </div>
  );
}

/** The search text in a title, highlighted. Plain text otherwise. */
function Highlight({ text, query }: { text: string; query: string }) {
  const q = query.trim().toLowerCase();
  const at = q ? text.toLowerCase().indexOf(q) : -1;
  if (at < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, at)}
      <mark className="rounded-sm bg-primary/15 text-foreground">{text.slice(at, at + q.length)}</mark>
      {text.slice(at + q.length)}
    </>
  );
}

const PAGE = 50; // rows shown per tool before "Show more"

function ScopeItem({
  tool,
  row,
  depth,
  covered,
  query,
  now,
  syncing,
  problem,
  pending,
  error,
  onToggle,
}: {
  tool: Tool;
  row: ScopeRow;
  depth: number;
  covered: ScopeRow | null;
  query: string;
  now: number;
  syncing: boolean;
  problem: ScopesProblem | null;
  pending: boolean;
  error: string | undefined;
  onToggle: () => void;
}) {
  const id = `scope-${tool.source}-${row.id}`;
  return (
    <li className="flex min-h-11 items-start gap-3 py-1" style={depth ? { paddingLeft: `${depth * 1.25}rem` } : undefined}>
      <Checkbox
        id={id}
        className="mt-0.5"
        checked={row.inBoundary || covered !== null}
        disabled={pending || covered !== null}
        aria-describedby={error ? `${id}-error` : undefined}
        onCheckedChange={onToggle}
      />
      <div className="grid min-w-0 flex-1 gap-0.5">
        <label htmlFor={id} className="flex min-w-0 items-center gap-1.5 text-sm font-medium">
          {row.private ? <Lock aria-label="Private" className="size-3.5 shrink-0 text-muted-foreground" /> : null}
          <span className="truncate">
            <Highlight text={row.title} query={query} />
          </span>
          {tool.source === "jira" ? (
            <span className="shrink-0 font-mono text-xs font-normal text-muted-foreground">{row.id}</span>
          ) : null}
        </label>
        {tool.source === "drive" && row.path && (query || depth === 0) ? (
          <span className="truncate text-xs text-muted-foreground">
            <Highlight text={row.path} query={query} />
          </span>
        ) : null}
        {covered ? (
          <span className="text-xs text-muted-foreground">Included with {covered.title}</span>
        ) : (
          <RowStatusLine row={row} tool={tool} now={now} syncing={syncing} problem={problem} />
        )}
        {error ? (
          <span id={`${id}-error`} role="alert" className="text-xs text-destructive">
            {error}
          </span>
        ) : null}
      </div>
    </li>
  );
}

function ToolSection({
  tool,
  scopes,
  boundary,
  query,
  show,
  now,
  syncing,
  pending,
  rowErrors,
  sectionError,
  onToggle,
  onRetry,
  onBulk,
}: {
  tool: Tool;
  scopes: ScopesState;
  boundary: BoundaryEntry[];
  query: string;
  show: ShowMode;
  now: number;
  syncing: boolean;
  pending: Set<string>;
  rowErrors: Record<string, string>;
  sectionError: string | undefined;
  onToggle: (tool: Tool, row: ScopeRow) => void;
  onRetry: (tool: Tool) => void;
  onBulk: (tool: Tool, mode: "add" | "remove", rows: ScopeRow[]) => void;
}) {
  const [open, setOpen] = useState(true);
  const [limit, setLimit] = useState(PAGE);
  const rows = rowsFor(tool.source, scopes.status === "ready" ? scopes.scopes : null, boundary);
  const shown = matchRows(rows, query, show);
  const filtering = query.trim() !== "" || show !== "all";
  const allowed = rows.filter((r) => r.inBoundary).length;
  const headingId = `tool-${tool.source}`;
  const problem = scopes.status === "problem" ? scopes.problem : null;
  // Drive without a search: a tree. Otherwise flat (search results show each folder's path instead).
  const ordered = tool.source === "drive" && !query.trim()
    ? treeOrder(rows).filter(({ row }) => shown.includes(row))
    : shown.map((row) => ({ row, depth: 0 }));
  const visible = ordered.slice(0, limit);
  const toAdd = bulkRows(shown, rows, "add");
  const toRemove = bulkRows(shown, rows, "remove");

  const item = ({ row, depth }: { row: ScopeRow; depth: number }) => {
    const key = scopeKey(tool.source, row.id);
    return (
      <ScopeItem
        key={row.id}
        tool={tool}
        row={row}
        depth={depth}
        covered={tool.source === "drive" && !row.inBoundary ? coveredBy(row, rows) : null}
        query={query}
        now={now}
        syncing={syncing}
        problem={problem}
        pending={pending.has(key)}
        error={rowErrors[key]}
        onToggle={() => onToggle(tool, row)}
      />
    );
  };
  // Slack: public channels, then private ones, when there are both.
  const groups =
    tool.source === "slack" && visible.some(({ row }) => row.private) && visible.some(({ row }) => !row.private)
      ? [
          { label: "Public channels", items: visible.filter(({ row }) => !row.private) },
          { label: "Private channels", items: visible.filter(({ row }) => row.private) },
        ]
      : [{ label: null, items: visible }];

  return (
    <section aria-labelledby={headingId} className="grid gap-3 rounded-xl bg-card p-4 ring-1 ring-foreground/10">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id={headingId} className="min-w-0">
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            aria-expanded={open}
            className="flex cursor-pointer items-center gap-2 rounded-md font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <ChevronRight aria-hidden="true" className={cn("size-4 shrink-0 transition-transform", open && "rotate-90")} />
            <PlatformLogo source={tool.source} size={18} />
            {tool.label}
          </button>
        </h2>
        <p className="text-xs text-muted-foreground tabular-nums">
          {scopes.status === "ready"
            ? `${allowed} of ${rows.length} ${tool.scopes} in the boundary`
            : `${allowed} in the boundary`}
          {filtering && scopes.status === "ready" ? ` · ${shown.length} shown` : ""}
        </p>
      </div>
      {open ? (
        <>
          {scopes.status === "loading" ? (
            <div className="grid gap-2">
              <Skeleton className="h-5 w-2/3" />
              <Skeleton className="h-5 w-1/2" />
            </div>
          ) : null}
          {problem ? <ProblemNotice tool={tool} problem={problem} onRetry={() => onRetry(tool)} /> : null}
          {scopes.status === "failed" ? (
            <p role="alert" className="text-sm text-destructive">
              {scopes.message}
            </p>
          ) : null}
          {scopes.status === "ready" && rows.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              You can&apos;t see any {tool.scopes} in {tool.label}.
            </p>
          ) : null}
          {toAdd.length > 1 || toRemove.length > 1 ? (
            <div className="flex flex-wrap items-center gap-2">
              {toAdd.length > 1 ? (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={toAdd.length > BULK_LIMIT}
                  onClick={() => onBulk(tool, "add", toAdd)}
                >
                  <ListPlus aria-hidden="true" />
                  Add all {toAdd.length} shown
                </Button>
              ) : null}
              {toRemove.length > 1 ? (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={toRemove.length > BULK_LIMIT}
                  onClick={() => onBulk(tool, "remove", toRemove)}
                >
                  <ListMinus aria-hidden="true" />
                  Remove all {toRemove.length} shown
                </Button>
              ) : null}
              {toAdd.length > BULK_LIMIT || toRemove.length > BULK_LIMIT ? (
                <span className="text-xs text-muted-foreground">
                  Search to narrow it to {BULK_LIMIT} or fewer to change them all at once.
                </span>
              ) : null}
            </div>
          ) : null}
          {sectionError ? (
            <p role="alert" className="text-sm text-destructive">
              {sectionError}
            </p>
          ) : null}
          {groups.map((group) =>
            group.items.length ? (
              <div key={group.label ?? "all"} className="grid gap-1">
                {group.label ? <h3 className="text-xs font-medium text-muted-foreground">{group.label}</h3> : null}
                <ul className="grid gap-1">{group.items.map(item)}</ul>
              </div>
            ) : null,
          )}
          {ordered.length > visible.length ? (
            <Button variant="ghost" size="sm" className="justify-self-start" onClick={() => setLimit((n) => n + 100)}>
              Show {Math.min(100, ordered.length - visible.length)} more of {ordered.length - visible.length}
            </Button>
          ) : null}
          {rows.length > 0 && shown.length === 0 ? (
            <p className="text-sm text-muted-foreground">No {tool.scopes} match.</p>
          ) : null}
        </>
      ) : null}
    </section>
  );
}

export function BoundaryEditor() {
  const [boundary, setBoundary] = useState<BoundaryEntry[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [scopes, setScopes] = useState<Record<SourceName, ScopesState>>(
    () => Object.fromEntries(TOOLS.map((t) => [t.source, { status: "loading" }])) as Record<SourceName, ScopesState>,
  );
  const [sync, setSync] = useState<SyncState>({ status: "idle" });
  const [pending, setPending] = useState<Set<string>>(new Set());
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});
  const [removing, setRemoving] = useState<{ tool: Tool; row: ScopeRow } | null>(null);
  const [query, setQuery] = useState("");
  const [show, setShow] = useState<ShowMode>("all");
  const [bulk, setBulk] = useState<{ tool: Tool; mode: "add" | "remove"; rows: ScopeRow[] } | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [sectionErrors, setSectionErrors] = useState<Partial<Record<SourceName, string>>>({});
  const [now, setNow] = useState(() => Date.now());
  // The latest scope lists, for startSync (called from add() and the button) to judge what can sync.
  const scopesRef = useRef(scopes);
  scopesRef.current = scopes;
  const syncingRef = useRef(false); // a sync is being followed
  const againRef = useRef(false); // something was added meanwhile: sync once more afterwards
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    const tick = setInterval(() => setNow(Date.now()), 30_000); // keep "synced 3 minutes ago" current
    return () => {
      alive.current = false;
      clearInterval(tick);
    };
  }, []);

  const loadScopes = useCallback((tool: Tool) => {
    setScopes((s) => ({ ...s, [tool.source]: { status: "loading" } }));
    listScopes(tool.source).then(
      (result) =>
        alive.current &&
        setScopes((s) => ({
          ...s,
          [tool.source]: "scopes" in result ? { status: "ready", scopes: result.scopes } : { status: "problem", problem: result.problem },
        })),
      (error) => alive.current && setScopes((s) => ({ ...s, [tool.source]: { status: "failed", message: failureOf(error) } })),
    );
  }, []);

  useEffect(() => {
    listBoundary().then(
      (entries) => alive.current && setBoundary(entries),
      (error) => alive.current && setLoadError(failureOf(error)),
    );
    TOOLS.forEach(loadScopes);
  }, [loadScopes]);

  const setRowError = (key: string, message: string | null) =>
    setRowErrors(({ [key]: _old, ...rest }) => (message ? { ...rest, [key]: message } : rest));
  const setRowPending = (key: string, on: boolean) =>
    setPending((p) => {
      const next = new Set(p);
      if (on) next.add(key);
      else next.delete(key);
      return next;
    });

  /** A tool's scope list, its problem, or null (loading or failed), for blockedReason. */
  function listOf(source: string): Scope[] | ScopesProblem | null {
    const state = scopesRef.current[source as SourceName];
    if (state?.status === "ready") return state.scopes;
    return state?.status === "problem" ? state.problem : null;
  }

  /**
   * Sync the company now, then follow it until every allowed scope that CAN sync has a new last sync (or a
   * minute passes). Scopes whose tool isn't connected, or that the admin can no longer see, never update,
   * so they're not waited for (their rows say why).
   */
  async function startSync() {
    if (syncingRef.current) {
      againRef.current = true; // the running sync may have started before the latest change
      return;
    }
    syncingRef.current = true;
    setSync({ status: "syncing" });
    try {
      const fresh = await listBoundary();
      const before = syncSnapshot(fresh.filter((entry) => blockedReason(entry, listOf(entry.source)) === null));
      if (before.size === 0) {
        setSync({ status: "nothing" }); // don't ask the backend, and don't wait, for a sync that can't happen
        return;
      }
      await syncNow();
      const until = Date.now() + POLL_FOR_MS;
      let latest: BoundaryEntry[] = [];
      while (Date.now() < until && alive.current) {
        await sleep(POLL_EVERY_MS);
        latest = await listBoundary();
        if (!alive.current) return;
        setBoundary(latest);
        setNow(Date.now());
        if (stillSyncing(before, latest).length === 0) break;
      }
      const notYet = stillSyncing(before, latest);
      setSync(notYet.length ? { status: "partial", pending: notYet } : { status: "done" });
    } catch (error) {
      setSync({ status: "failed", message: failureOf(error) });
    } finally {
      syncingRef.current = false;
      if (againRef.current && alive.current) {
        againRef.current = false;
        void startSync();
      }
    }
  }

  async function add(tool: Tool, row: ScopeRow) {
    const key = scopeKey(tool.source, row.id);
    setRowPending(key, true);
    setRowError(key, null);
    try {
      await addScope(tool.source, row.id, row.title);
      setBoundary(await listBoundary());
      void startSync(); // ticking means "use this now": copy it straight away
    } catch (error) {
      setRowError(key, `Couldn't add ${row.title}: ${failureOf(error)}`);
    } finally {
      setRowPending(key, false);
    }
  }

  async function remove(tool: Tool, row: ScopeRow) {
    const key = scopeKey(tool.source, row.id);
    setRowPending(key, true);
    setRowError(key, null);
    try {
      await removeScope(tool.source, row.id);
      setBoundary(await listBoundary());
    } catch (error) {
      setRowError(key, `Couldn't remove ${row.title}: ${failureOf(error)}`);
    } finally {
      setRowPending(key, false);
    }
  }

  /** "Add / Remove all N shown", after the confirmation: one request, all or nothing. */
  async function runBulk(tool: Tool, mode: "add" | "remove", rows: ScopeRow[]) {
    setBulkBusy(true);
    setSectionErrors(({ [tool.source]: _old, ...rest }) => rest);
    try {
      await bulkScopes(
        tool.source,
        mode === "add" ? { add: rows.map((r) => ({ scope_id: r.id, title: r.title })) } : { remove: rows.map((r) => r.id) },
      );
      setBoundary(await listBoundary());
      if (mode === "add") void startSync(); // as with one tick: copy them straight away
    } catch (error) {
      setSectionErrors((e) => ({ ...e, [tool.source]: `Nothing changed: ${failureOf(error)}` }));
    } finally {
      setBulkBusy(false);
      setBulk(null);
    }
  }

  function toggle(tool: Tool, row: ScopeRow) {
    if (row.inBoundary) setRemoving({ tool, row }); // removing asks first
    else void add(tool, row);
  }

  if (loadError) {
    return (
      <Alert variant="destructive">
        <ShieldAlert aria-hidden="true" />
        <AlertTitle>Couldn&apos;t load the boundary</AlertTitle>
        <AlertDescription>{loadError}</AlertDescription>
      </Alert>
    );
  }

  const syncing = sync.status === "syncing";
  const privateCount = bulk?.mode === "add" ? bulk.rows.filter((r) => r.private).length : 0;
  return (
    <div className="grid gap-4">
      <HowItWorks />
      {/* Sticky from 768 px: stays in view while scrolling long lists, below the development strip. On a phone it
          would take a fifth of the screen, so there it scrolls away. */}
      <div className="z-20 -mx-4 grid gap-3 border-b bg-background/95 px-4 py-3 backdrop-blur md:sticky md:top-[var(--dev-banner,0px)]">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-56 flex-1">
            <Search aria-hidden="true" className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Find a channel, folder, project or space"
              aria-label="Find a channel, folder, project or space"
              className="pl-8"
            />
          </div>
          <div role="group" aria-label="Show" className="inline-flex rounded-lg border p-0.5">
            {(
              [
                ["all", "All"],
                ["in", "In the boundary"],
                ["out", "Not in it"],
              ] as const
            ).map(([value, label]) => (
              <Button
                key={value}
                variant={show === value ? "secondary" : "ghost"}
                size="sm"
                aria-pressed={show === value}
                onClick={() => setShow(value)}
              >
                {label}
              </Button>
            ))}
          </div>
          <Button
            variant="outline"
            onClick={() => void startSync()}
            disabled={syncing || boundary === null || boundary.length === 0}
            aria-busy={syncing}
            className="ml-auto"
          >
            <RefreshCw aria-hidden="true" className={syncing ? "animate-spin" : undefined} />
            {syncing ? "Syncing…" : "Sync now"}
          </Button>
        </div>
        <SyncStatus state={sync} />
      </div>
      {boundary === null ? (
        <div className="grid gap-2">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : (
        TOOLS.map((tool) => (
          <ToolSection
            key={tool.source}
            tool={tool}
            scopes={scopes[tool.source]}
            boundary={boundary}
            query={query}
            show={show}
            now={now}
            syncing={syncing}
            pending={pending}
            rowErrors={rowErrors}
            sectionError={sectionErrors[tool.source]}
            onToggle={toggle}
            onRetry={loadScopes}
            onBulk={(tool, mode, rows) => setBulk({ tool, mode, rows })}
          />
        ))
      )}

      <AlertDialog open={bulk !== null} onOpenChange={(open) => !open && !bulkBusy && setBulk(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {bulk?.mode === "add" ? "Add" : "Remove"} {bulk?.rows.length} {bulk?.tool.label} {bulk?.tool.scopes}{" "}
              {bulk?.mode === "add" ? "to" : "from"} the boundary?
            </AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="grid gap-2">
                <p>
                  {bulk?.rows.slice(0, 5).map((r) => r.title).join(", ")}
                  {bulk && bulk.rows.length > 5 ? ` and ${bulk.rows.length - 5} more` : ""}.
                </p>
                {bulk?.mode === "add" ? (
                  <p>
                    KnowBuddy will copy them and answer from them, for people who can see them in {bulk.tool.label}.
                    {privateCount
                      ? ` ${privateCount} ${privateCount === 1 ? "is a private channel" : "are private channels"}.`
                      : ""}
                  </p>
                ) : (
                  <p>Their content stops appearing in answers immediately, for everyone.</p>
                )}
                <p>Each change is recorded in the audit trail.</p>
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={bulkBusy}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant={bulk?.mode === "remove" ? "destructive" : "default"}
              disabled={bulkBusy}
              onClick={(event) => {
                event.preventDefault(); // stay open until the request finishes
                if (bulk) void runBulk(bulk.tool, bulk.mode, bulk.rows);
              }}
            >
              {bulkBusy ? "Working…" : bulk?.mode === "add" ? `Add ${bulk?.rows.length}` : `Remove ${bulk?.rows.length}`}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={removing !== null} onOpenChange={(open) => !open && setRemoving(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove {removing?.row.title} from the boundary?</AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="grid gap-2">
                <p>
                  Its content stops appearing in answers immediately, for everyone. The change is recorded in the
                  audit trail.
                </p>
                {removing && removing.row.lastSyncedAt === null ? (
                  <p>
                    It has never synced from {removing.tool.label}. If its content came from the demo seed, only
                    re-seeding brings it back.
                  </p>
                ) : (
                  <p>Adding it back copies it again at the next sync.</p>
                )}
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => {
                if (removing) void remove(removing.tool, removing.row);
              }}
            >
              Remove
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
