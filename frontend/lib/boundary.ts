// The admin boundary (ADR-002) as the /admin/boundary page reads it: types for
// the admin API (backend/app/connectors/admin.py) and pure helpers.
//
// The boundary is the list of channels, folders, projects and spaces KnowBuddy
// may read at all. Sync copies only these, as the admin; search re-checks it on
// every question. People still only ever see what each tool lets them read.
import type { SourceName } from "@/lib/api/types";

/**
 * GET /api/admin/scopes/{source}: what the admin can see in that tool. Slack adds `private`; Drive adds the
 * folder's `parent` (null at the top or when it isn't listed) and its `path` ("Finance / 2026").
 */
export type Scope = { id: string; title: string; private?: boolean; parent?: string | null; path?: string };

/** GET /api/admin/boundary: one allowed scope. `last_synced_at` null: never synced. */
export type BoundaryEntry = {
  source: string;
  scope_id: string;
  scope_type: string;
  title: string;
  added_at: string;
  last_synced_at: string | null;
};

export const TOOLS: { source: SourceName; label: string; scope: string; scopes: string }[] = [
  { source: "slack", label: "Slack", scope: "channel", scopes: "channels" },
  { source: "drive", label: "Google Drive", scope: "folder", scopes: "folders" },
  { source: "jira", label: "Jira", scope: "project", scopes: "projects" },
  { source: "confluence", label: "Confluence", scope: "space", scopes: "spaces" },
];

/**
 * Why a tool's scope list couldn't load. The backend answers 404 when the admin hasn't
 * connected the tool, 401 when the tool refused the stored access, and 502 when the
 * tool's API failed. Those codes are about the TOOL, so they must not be read like the
 * app's own 401 (signed out) or the proxy's 502 (our server down).
 */
export type ScopesProblem = "not-connected" | "reconnect" | "tool-failed";

/**
 * The problem a failed scope list means, or null when it's the app's own (signed out, server down…).
 * Only the tool's own messages are recognised; anything else fails safe, as an ordinary error (a 401
 * means "sign in again"), so a reworded backend message can never show "reconnect" to someone who is
 * actually signed out. The messages: backend/app/connectors/admin.py scopes(), and provider_error()
 * in connectors/api.py.
 */
export function scopesProblem(status: number, detail: string): ScopesProblem | null {
  if (status === 404 && /connect .+ first/i.test(detail)) return "not-connected"; // "connect slack first"
  if (status === 401 && /connect again/i.test(detail)) return "reconnect"; // "slack …: connect again"
  if (status === 502 && /API call failed$/i.test(detail)) return "tool-failed"; // "slack API call failed"
  return null;
}

export function scopeKey(source: string, scopeId: string): string {
  return `${source}:${scopeId}`;
}

/** One row of a tool's section: a scope the admin can pick, or one already in the boundary. */
export type ScopeRow = {
  id: string;
  title: string;
  inBoundary: boolean;
  lastSyncedAt: string | null;
  /** False: in the boundary, but no longer in the admin's own list (they left it, or it was archived). */
  visible: boolean;
  private: boolean; // a private Slack channel
  parent: string | null; // a Drive folder's parent, if listed
  path: string; // a Drive folder's path of parent names, "" at the top
};

const byTitle = (a: { title: string }, b: { title: string }) => a.title.localeCompare(b.title);

const details = (s: Scope | undefined) => ({ private: s?.private ?? false, parent: s?.parent ?? null, path: s?.path ?? "" });

/**
 * A tool's rows: what's in the boundary first, then what the admin could add. `scopes`
 * null: the list couldn't load, so only the boundary shows, and nothing is flagged unseen.
 */
export function rowsFor(source: string, scopes: Scope[] | null, boundary: BoundaryEntry[]): ScopeRow[] {
  const allowed = boundary.filter((b) => b.source === source);
  const seen = new Set((scopes ?? []).map((s) => s.id));
  const inside: ScopeRow[] = allowed
    .map((b) => {
      const listed = scopes?.find((s) => s.id === b.scope_id);
      return {
        id: b.scope_id,
        title: listed?.title || b.title || b.scope_id,
        inBoundary: true,
        lastSyncedAt: b.last_synced_at,
        visible: scopes === null || seen.has(b.scope_id),
        ...details(listed),
      };
    })
    .sort(byTitle);
  const ids = new Set(allowed.map((b) => b.scope_id));
  const outside: ScopeRow[] = (scopes ?? [])
    .filter((s) => !ids.has(s.id))
    .map((s) => ({ id: s.id, title: s.title || s.id, inBoundary: false, lastSyncedAt: null, visible: true, ...details(s) }))
    .sort(byTitle);
  return [...inside, ...outside];
}

/** Rows whose name (or Drive path) contains the typed text, any case. */
export function filterRows(rows: ScopeRow[], text: string): ScopeRow[] {
  const wanted = text.trim().toLowerCase();
  return wanted ? rows.filter((r) => `${r.path} ${r.title}`.toLowerCase().includes(wanted)) : rows;
}

/** The page's "Show" choice. */
export type ShowMode = "all" | "in" | "out";

/** Rows matching the search and the Show choice. A Drive folder included with its parent counts as "in". */
export function matchRows(rows: ScopeRow[], text: string, show: ShowMode): ScopeRow[] {
  const inside = (r: ScopeRow) => r.inBoundary || coveredBy(r, rows) !== null;
  return filterRows(rows, text).filter((r) => show === "all" || (show === "in") === inside(r));
}

/**
 * The nearest folder above this one that is in the boundary, or null. Sync includes subfolders, so a folder
 * under a ticked one is already in (the backend refuses adding it again, 409).
 */
export function coveredBy(row: ScopeRow, rows: ScopeRow[]): ScopeRow | null {
  const byId = new Map(rows.map((r) => [r.id, r]));
  const seen = new Set([row.id]);
  for (let p = row.parent; p && !seen.has(p); p = byId.get(p)?.parent ?? null) {
    seen.add(p);
    const up = byId.get(p);
    if (!up) return null;
    if (up.inBoundary) return up;
  }
  return null;
}

/** True when a folder below this one is in the boundary (adding this one would be refused, 409). */
export function containsAllowed(row: ScopeRow, rows: ScopeRow[]): boolean {
  return rows.some((r) => r.inBoundary && r.id !== row.id && isAbove(row.id, r, rows));
}

function isAbove(id: string, row: ScopeRow, rows: ScopeRow[]): boolean {
  const byId = new Map(rows.map((r) => [r.id, r]));
  const seen = new Set([row.id]);
  for (let p = row.parent; p && !seen.has(p); p = byId.get(p)?.parent ?? null) {
    if (p === id) return true;
    seen.add(p);
  }
  return false;
}

/** Drive folders as a tree, depth first, each level by name, with its depth (0 at the top). */
export function treeOrder(rows: ScopeRow[]): { row: ScopeRow; depth: number }[] {
  const ids = new Set(rows.map((r) => r.id));
  const children = new Map<string | null, ScopeRow[]>();
  for (const r of rows) {
    const key = r.parent && ids.has(r.parent) ? r.parent : null;
    children.set(key, [...(children.get(key) ?? []), r]);
  }
  const out: { row: ScopeRow; depth: number }[] = [];
  const seen = new Set<string>();
  const walk = (parent: string | null, depth: number) => {
    for (const r of (children.get(parent) ?? []).sort(byTitle)) {
      if (seen.has(r.id)) continue;
      seen.add(r.id);
      out.push({ row: r, depth });
      walk(r.id, depth + 1);
    }
  };
  walk(null, 0);
  return out;
}

/** At most this many scopes change in one bulk action (the backend's BULK_LIMIT). */
export const BULK_LIMIT = 50;

/**
 * What "Add all shown" adds: shown rows outside the boundary, leaving out Drive folders already included with
 * a parent, folders with one below them already in, and folders inside another one being added (the parent
 * covers them). What "Remove all shown" removes: the shown rows in the boundary.
 */
export function bulkRows(shown: ScopeRow[], all: ScopeRow[], mode: "add" | "remove"): ScopeRow[] {
  if (mode === "remove") return shown.filter((r) => r.inBoundary);
  const candidates = shown.filter((r) => !r.inBoundary && coveredBy(r, all) === null && !containsAllowed(r, all));
  const ids = new Set(candidates.map((r) => r.id));
  return candidates.filter((r) => !candidates.some((other) => other.id !== r.id && ids.has(other.id) && isAbove(other.id, r, all)));
}

/**
 * Sync runs every 5 minutes. A scope not synced for three runs is probably failing
 * (the backend records only successful syncs), e.g. a revoked token.
 */
export const STALE_AFTER_MS = 15 * 60 * 1000;

export type RowState = "outside" | "not-connected" | "reconnect" | "unseen" | "not-synced" | "synced" | "stale";

/** A row's status. `problem`: its tool's scope list problem; a tool that isn't (properly) connected can't sync. */
export function rowState(row: ScopeRow, now: number, problem: ScopesProblem | null = null): RowState {
  if (!row.inBoundary) return "outside";
  if (problem === "not-connected" || problem === "reconnect") return problem;
  if (!row.visible) return "unseen";
  if (row.lastSyncedAt === null) return "not-synced";
  const at = Date.parse(row.lastSyncedAt);
  return Number.isNaN(at) || now - at > STALE_AFTER_MS ? "stale" : "synced";
}

/** Why an allowed scope can't sync right now (so a "sync now" shouldn't wait for it). */
export type Blocked = "not-connected" | "reconnect" | "unseen";

/**
 * Why `entry` can't sync, judged by its tool's scope list: the list itself, the list's problem, or null
 * (still loading, or failed for another reason). The tool not answering just now ("tool-failed") may pass,
 * so it doesn't block: if the sync fails too, the scope is listed as not synced yet.
 */
export function blockedReason(entry: BoundaryEntry, list: Scope[] | ScopesProblem | null): Blocked | null {
  if (list === "not-connected" || list === "reconnect") return list;
  if (Array.isArray(list) && !list.some((s) => s.id === entry.scope_id)) return "unseen";
  return null;
}

/** Each allowed scope's last sync, to tell when a "sync now" has finished. */
export function syncSnapshot(boundary: BoundaryEntry[]): Map<string, string | null> {
  return new Map(boundary.map((b) => [scopeKey(b.source, b.scope_id), b.last_synced_at]));
}

/**
 * The scopes in `before` that a sync hasn't finished yet: their last sync is unchanged. Scopes left out
 * of the snapshot (they can't sync) are not waited for. Compared with the server's own times, so the
 * browser's clock doesn't matter.
 */
export function stillSyncing(before: Map<string, string | null>, boundary: BoundaryEntry[]): BoundaryEntry[] {
  return boundary.filter((b) => {
    const key = scopeKey(b.source, b.scope_id);
    return before.has(key) && before.get(key) === b.last_synced_at;
  });
}
