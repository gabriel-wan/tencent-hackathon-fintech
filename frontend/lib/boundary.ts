// The admin boundary (ADR-002) as the /admin/boundary page reads it: types for
// the admin API (backend/app/connectors/admin.py) and pure helpers.
//
// The boundary is the list of channels, folders, projects and spaces KnowBuddy
// may read at all. Sync copies only these, as the admin; search re-checks it on
// every question. People still only ever see what each tool lets them read.
import type { SourceName } from "@/lib/api/types";

/** GET /api/admin/scopes/{source}: what the admin can see in that tool. */
export type Scope = { id: string; title: string };

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

/** The problem a failed scope list means, or null when it's the app's own (signed out, server down…). */
export function scopesProblem(status: number, detail: string): ScopesProblem | null {
  if (status === 404) return "not-connected"; // "connect slack first"
  if (status === 401 && detail !== "Not signed in") return "reconnect"; // "… connect again"
  if (status === 502 && detail.endsWith("API call failed")) return "tool-failed";
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
};

const byTitle = (a: { title: string }, b: { title: string }) => a.title.localeCompare(b.title);

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
      };
    })
    .sort(byTitle);
  const ids = new Set(allowed.map((b) => b.scope_id));
  const outside: ScopeRow[] = (scopes ?? [])
    .filter((s) => !ids.has(s.id))
    .map((s) => ({ id: s.id, title: s.title || s.id, inBoundary: false, lastSyncedAt: null, visible: true }))
    .sort(byTitle);
  return [...inside, ...outside];
}

/** Rows whose name contains the typed text (any case). */
export function filterRows(rows: ScopeRow[], text: string): ScopeRow[] {
  const wanted = text.trim().toLowerCase();
  return wanted ? rows.filter((r) => r.title.toLowerCase().includes(wanted)) : rows;
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
