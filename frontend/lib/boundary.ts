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
export type Scope = {
  id: string;
  title: string;
  private?: boolean;
  parent?: string | null;
  path?: string;
  drive_id?: string; // Drive: a shared drive's ID, "my-drive" or "shared-with-me"
  drive?: string; // Drive: that drive's name, for the headings
};

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
  driveId: string | null; // a Drive folder's drive (null when not in the admin's list)
  drive: string; // that drive's name
};

const byTitle = (a: { title: string }, b: { title: string }) => a.title.localeCompare(b.title);

const details = (s: Scope | undefined) => ({
  private: s?.private ?? false,
  parent: s?.parent ?? null,
  path: s?.path ?? "",
  driveId: s?.drive_id ?? null,
  drive: s?.drive ?? "",
});

/**
 * A tool's rows: what's in the boundary first, then what the admin could add. `scopes`
 * null: the list couldn't load, so only the boundary shows, and nothing is flagged unseen.
 */
export function rowsFor(source: string, scopes: Scope[] | null, boundary: BoundaryEntry[]): ScopeRow[] {
  const allowed = boundary.filter((b) => b.source === source);
  const listedById = new Map((scopes ?? []).map((s) => [s.id, s]));
  const seen = new Set(listedById.keys());
  const inside: ScopeRow[] = allowed
    .map((b) => {
      const listed = listedById.get(b.scope_id);
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

/**
 * The folder tree, worked out once per change of the rows (the Boundary page memoises it): every lookup below is
 * then a Map read, so thousands of Drive folders stay fast (review of the UI revamp PR: rebuilding this per call
 * froze the page at 2,000 folders).
 * - `covered`: a folder's nearest ancestor in the boundary (sync includes subfolders, so it is already in);
 * - `contains`: for a folder with a folder below it in the boundary, one such folder (adding it would overlap).
 */
export type RowIndex = { byId: Map<string, ScopeRow>; covered: Map<string, ScopeRow>; contains: Map<string, ScopeRow> };

export function indexRows(rows: ScopeRow[]): RowIndex {
  const byId = new Map(rows.map((r) => [r.id, r]));
  const covered = new Map<string, ScopeRow>();
  const contains = new Map<string, ScopeRow>();
  for (const row of rows) {
    for (const up of ancestorsOf(row, byId)) {
      if (row.inBoundary && !contains.has(up.id)) contains.set(up.id, row);
      if (up.inBoundary && !covered.has(row.id)) covered.set(row.id, up);
    }
  }
  return { byId, covered, contains };
}

/** The listed folders above this one, nearest first (a loop in odd data ends the walk). */
function ancestorsOf(row: ScopeRow, byId: Map<string, ScopeRow>): ScopeRow[] {
  const out: ScopeRow[] = [];
  const seen = new Set([row.id]);
  for (let p = row.parent; p && !seen.has(p); ) {
    const up = byId.get(p);
    if (!up) break;
    seen.add(p);
    out.push(up);
    p = up.parent;
  }
  return out;
}

/** Rows matching the search and the Show choice. A Drive folder included with its parent counts as "in". */
export function matchRows(rows: ScopeRow[], text: string, show: ShowMode, index: RowIndex = indexRows(rows)): ScopeRow[] {
  const inside = (r: ScopeRow) => r.inBoundary || index.covered.has(r.id);
  return filterRows(rows, text).filter((r) => show === "all" || (show === "in") === inside(r));
}

/** The nearest folder above this one that is in the boundary, or null. */
export function coveredBy(row: ScopeRow, index: RowIndex): ScopeRow | null {
  return index.covered.get(row.id) ?? null;
}

/** A folder below this one that is in the boundary (adding this one would be refused, 409), or null. */
export function containsAllowed(row: ScopeRow, index: RowIndex): ScopeRow | null {
  return index.contains.get(row.id) ?? null;
}

export type TreeEntry = { row: ScopeRow; depth: number; hasChildren: boolean };

/** Drive folders as a tree, depth first, each level by name, with its depth (0 at the top). */
export function treeOrder(rows: ScopeRow[]): TreeEntry[] {
  const ids = new Set(rows.map((r) => r.id));
  const children = new Map<string | null, ScopeRow[]>();
  for (const r of rows) {
    const key = r.parent && ids.has(r.parent) ? r.parent : null;
    const siblings = children.get(key);
    if (siblings) siblings.push(r);
    else children.set(key, [r]);
  }
  const out: TreeEntry[] = [];
  const seen = new Set<string>();
  const walk = (parent: string | null, depth: number) => {
    for (const r of (children.get(parent) ?? []).sort(byTitle)) {
      if (seen.has(r.id)) continue;
      seen.add(r.id);
      out.push({ row: r, depth, hasChildren: (children.get(r.id)?.length ?? 0) > 0 });
      walk(r.id, depth + 1);
    }
  };
  walk(null, 0);
  return out;
}

/**
 * A tree with folded folders: everything below a folder not in `expanded` is left out. Folders start folded, so
 * a big Drive shows its top level first.
 */
export function foldTree(entries: TreeEntry[], expanded: Set<string>): TreeEntry[] {
  const out: TreeEntry[] = [];
  let hideBelow: number | null = null; // depth of the folded folder whose subtree is being skipped
  for (const entry of entries) {
    if (hideBelow !== null && entry.depth > hideBelow) continue;
    hideBelow = entry.hasChildren && !expanded.has(entry.row.id) ? entry.depth : null;
    out.push(entry);
  }
  return out;
}

const DRIVE_ORDER = (id: string) => (id === "my-drive" ? 0 : id === "shared-with-me" ? 2 : 1);

/**
 * Drive folders grouped by drive, for the headings: My Drive first, then each shared drive by name, then
 * "Shared with me". Folders the list doesn't place (e.g. in the boundary but no longer visible) go last, under
 * "Other". One group means no headings are needed.
 */
export function driveGroups(rows: ScopeRow[]): { id: string; label: string; rows: ScopeRow[] }[] {
  const groups = new Map<string, { id: string; label: string; rows: ScopeRow[] }>();
  for (const row of rows) {
    const id = row.driveId ?? "other";
    const group = groups.get(id) ?? { id, label: row.driveId ? row.drive : "Other", rows: [] };
    group.rows.push(row);
    groups.set(id, group);
  }
  const rank = (id: string) => (id === "other" ? 3 : DRIVE_ORDER(id));
  return [...groups.values()].sort((a, b) => rank(a.id) - rank(b.id) || a.label.localeCompare(b.label));
}

/** At most this many scopes change in one bulk action (the backend's BULK_LIMIT). */
export const BULK_LIMIT = 50;

/**
 * What "Add all shown" adds: shown rows outside the boundary, leaving out Drive folders already included with
 * a parent, folders with one below them already in, and folders inside another one being added (the parent
 * covers them). What "Remove all shown" removes: the shown rows in the boundary. Each candidate's parents are
 * walked once, against a Set: about rows × depth, not rows².
 */
export function bulkRows(shown: ScopeRow[], index: RowIndex, mode: "add" | "remove"): ScopeRow[] {
  if (mode === "remove") return shown.filter((r) => r.inBoundary);
  const candidates = shown.filter((r) => !r.inBoundary && !index.covered.has(r.id) && !index.contains.has(r.id));
  const ids = new Set(candidates.map((r) => r.id));
  return candidates.filter((r) => !ancestorsOf(r, index.byId).some((up) => ids.has(up.id)));
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
