"use client";

import { Info, RefreshCw, ShieldAlert } from "lucide-react";
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
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { addScope, listBoundary, listScopes, removeScope, syncNow } from "@/lib/api/client";
import { ApiError, BackendUnreachableError, NotSignedInError } from "@/lib/api/errors";
import type { SourceName } from "@/lib/api/types";
import {
  type BoundaryEntry,
  type Scope,
  type ScopeRow,
  type ScopesProblem,
  TOOLS,
  filterRows,
  rowState,
  rowsFor,
  scopeKey,
  stillSyncing,
  syncSnapshot,
} from "@/lib/boundary";
import { formatRelative } from "@/lib/format";

// /admin/boundary (ADR-002): the admin chooses which channels, folders,
// projects and spaces KnowBuddy may read at all. Ticking one adds it and syncs
// straight away; unticking removes it (its content leaves answers at once).
// Admins only: the admin layout hides the page from others, and every route
// returns 403 to them anyway. Every change and sync is recorded in the audit trail.

const POLL_EVERY_MS = 3_000;
const POLL_FOR_MS = 60_000;
const FILTER_FROM = 10; // show a filter box above this many rows

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
  if (error instanceof ApiError) return `Something went wrong (HTTP ${error.status}).`;
  return "Something went wrong.";
}

function HowItWorks() {
  return (
    <details className="rounded-lg border bg-card px-4 py-3 text-sm">
      <summary className="cursor-pointer font-medium">How the boundary works</summary>
      <div className="mt-3 grid gap-2 text-muted-foreground">
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
            Every change is recorded in the{" "}
            <Link href="/admin/audit?event_type=boundary_added" className="text-primary underline underline-offset-4">
              audit trail
            </Link>
            .
          </li>
        </ul>
      </div>
    </details>
  );
}

function SyncStatus({ state }: { state: SyncState }) {
  return (
    <div aria-live="polite" className="text-sm">
      {state.status === "syncing" ? <p className="text-muted-foreground">Syncing… this can take a minute.</p> : null}
      {state.status === "done" ? <p className="text-muted-foreground">Synced just now.</p> : null}
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

function RowStatusLine({ row, tool, now, syncing }: { row: ScopeRow; tool: Tool; now: number; syncing: boolean }) {
  const state = rowState(row, now);
  if (state === "outside") return null;
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

function ToolSection({
  tool,
  scopes,
  boundary,
  now,
  syncing,
  pending,
  rowErrors,
  onToggle,
  onRetry,
}: {
  tool: Tool;
  scopes: ScopesState;
  boundary: BoundaryEntry[];
  now: number;
  syncing: boolean;
  pending: Set<string>;
  rowErrors: Record<string, string>;
  onToggle: (tool: Tool, row: ScopeRow) => void;
  onRetry: (tool: Tool) => void;
}) {
  const [filter, setFilter] = useState("");
  const rows = rowsFor(tool.source, scopes.status === "ready" ? scopes.scopes : null, boundary);
  const shown = filterRows(rows, filter);
  const allowed = rows.filter((r) => r.inBoundary).length;
  const headingId = `tool-${tool.source}`;
  return (
    <section aria-labelledby={headingId} className="grid gap-3 rounded-lg border bg-card p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id={headingId} className="font-medium">
          {tool.label}
        </h2>
        <p className="text-xs text-muted-foreground">
          {scopes.status === "ready"
            ? `${allowed} of ${rows.length} ${tool.scopes} in the boundary`
            : `${allowed} in the boundary`}
        </p>
      </div>
      {scopes.status === "loading" ? (
        <div className="grid gap-2">
          <Skeleton className="h-5 w-2/3" />
          <Skeleton className="h-5 w-1/2" />
        </div>
      ) : null}
      {scopes.status === "problem" ? (
        <ProblemNotice tool={tool} problem={scopes.problem} onRetry={() => onRetry(tool)} />
      ) : null}
      {scopes.status === "failed" ? (
        <p role="alert" className="text-sm text-destructive">
          {scopes.message}
        </p>
      ) : null}
      {rows.length > FILTER_FROM ? (
        <Input
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          placeholder={`Filter ${tool.scopes}`}
          aria-label={`Filter ${tool.label} ${tool.scopes}`}
          className="max-w-xs"
        />
      ) : null}
      {scopes.status === "ready" && rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          You can&apos;t see any {tool.scopes} in {tool.label}.
        </p>
      ) : null}
      {shown.length ? (
        <ul className="grid gap-1">
          {shown.map((row) => {
            const key = scopeKey(tool.source, row.id);
            const id = `scope-${tool.source}-${row.id}`;
            return (
              <li key={row.id} className="flex min-h-11 items-start gap-3 py-1">
                <Checkbox
                  id={id}
                  className="mt-0.5"
                  checked={row.inBoundary}
                  disabled={pending.has(key)}
                  aria-describedby={rowErrors[key] ? `${id}-error` : undefined}
                  onCheckedChange={() => onToggle(tool, row)}
                />
                <div className="grid flex-1 gap-0.5">
                  <label htmlFor={id} className="text-sm font-medium">
                    {row.title}
                  </label>
                  <RowStatusLine row={row} tool={tool} now={now} syncing={syncing} />
                  {rowErrors[key] ? (
                    <span id={`${id}-error`} role="alert" className="text-xs text-destructive">
                      {rowErrors[key]}
                    </span>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      ) : null}
      {rows.length > 0 && shown.length === 0 ? (
        <p className="text-sm text-muted-foreground">No {tool.scopes} match &quot;{filter}&quot;.</p>
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
  const [now, setNow] = useState(() => Date.now());
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

  /** Sync the company now, then follow it until every allowed scope's last sync has moved (or a minute passes). */
  async function startSync() {
    if (syncingRef.current) {
      againRef.current = true; // the running sync may have started before the latest change
      return;
    }
    syncingRef.current = true;
    setSync({ status: "syncing" });
    try {
      const before = syncSnapshot(await listBoundary());
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
  return (
    <div className="grid gap-4">
      <HowItWorks />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SyncStatus state={sync} />
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
            now={now}
            syncing={syncing}
            pending={pending}
            rowErrors={rowErrors}
            onToggle={toggle}
            onRetry={loadScopes}
          />
        ))
      )}

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
