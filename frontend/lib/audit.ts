// The audit trail (ADR-007) as the /admin/audit page reads it: types for
// GET /api/admin/audit and POST /api/admin/audit/verify, and pure helpers.
//
// The two routes declare no response model, so schema.d.ts can't describe
// them: these types are written by hand from backend/app/audit/api.py and
// audit/log.py, and from what each event writes (pipeline/query.py,
// connectors/api.py, connectors/admin.py). Keep them in step. Every payload
// field is optional: older records were written before newer fields existed
// (e.g. `redactions`, #16, and `injection`, #17).
import type { SourceName } from "@/lib/api/types";

export type AuditDecision = { document: string; allowed: boolean; reason: string };

export type QueryPayload = {
  user_email?: string;
  role?: "admin" | "user";
  question?: string; // stored masked (ADR-010)
  search_mode?: string;
  live_check_mode?: string;
  candidates?: AuditDecision[];
  restricted_matches?: { document: string; reason: string }[];
  sent_to_llm?: string[];
  llm_called?: boolean;
  llm_error?: string;
  model?: string;
  answer?: string; // stored masked (ADR-010)
  citations?: string[];
  redactions?: Record<string, { need_to_know: boolean; masked: Record<string, number> }>;
  answer_masked?: Record<string, number>;
  injection?: { question: string[]; sources: { document: string; rules: string[]; removed: number }[] };
  removed_links?: number;
  removed_citations?: string[];
  grounding_note?: string;
  timings_ms?: Record<string, number>;
};

export type AuditRecord = {
  id: number;
  ts: string;
  user_email: string | null; // null: a record with no user
  event_type: string;
  payload: Record<string, unknown>;
  prev_hash: string;
  hash: string;
};

export type AuditPage = { records: AuditRecord[]; next_before_id: number | null };

export type VerifyResult = {
  ok: boolean;
  checked: number;
  first_broken_id: number | null;
  reason: string | null;
  head: { id: number; hash: string } | null;
};

/** The event types the backend writes today, for the filter. Others still show, by their name. */
export const EVENT_TYPES: { value: string; label: string }[] = [
  { value: "query", label: "Questions" },
  { value: "boundary_added", label: "Boundary: added" },
  { value: "boundary_removed", label: "Boundary: removed" },
  { value: "connector_connected", label: "Tool connected" },
  { value: "connector_disconnected", label: "Tool disconnected" },
  { value: "sync_requested", label: "Sync requested" },
  { value: "audit_searched", label: "Audit searched" },
  { value: "audit_verified", label: "Chain verified" },
];

export const SOURCES: { value: SourceName; label: string }[] = [
  { value: "slack", label: "Slack" },
  { value: "drive", label: "Google Drive" },
  { value: "jira", label: "Jira" },
  { value: "confluence", label: "Confluence" },
];

/** The page's filters as typed, all strings ("" = not set). Dates are YYYY-MM-DD, in the viewer's time zone. */
export type AuditFilters = {
  user: string;
  from: string;
  to: string;
  event_type: string;
  source: string;
  scope_id: string;
  document: string;
};

export const NO_FILTERS: AuditFilters = {
  user: "",
  from: "",
  to: "",
  event_type: "",
  source: "",
  scope_id: "",
  document: "",
};

const DATE = /^\d{4}-\d{2}-\d{2}$/;
const EVENT_TYPE = /^[a-z_]{1,40}$/; // what the API accepts (backend/app/audit/api.py)

/** Filters from the page's URL (?user=…&from=…), ignoring anything malformed. */
export function filtersFromParams(params: Record<string, string | string[] | undefined>): AuditFilters {
  const one = (key: keyof AuditFilters) => {
    const value = params[key];
    return (Array.isArray(value) ? value[0] : value)?.trim() ?? "";
  };
  const date = (key: "from" | "to") => (DATE.test(one(key)) ? one(key) : "");
  const source = one("source");
  return {
    user: one("user"),
    from: date("from"),
    to: date("to"),
    event_type: EVENT_TYPE.test(one("event_type")) ? one("event_type") : "",
    source: SOURCES.some((s) => s.value === source) ? source : "",
    scope_id: one("scope_id"),
    document: one("document"),
  };
}

/** The page's own URL query for these filters: only the ones set, so links stay short. */
export function toPageQuery(filters: AuditFilters): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) if (value.trim()) query.set(key, value.trim());
  return query.toString();
}

/** The record open in the dialog, from the page's URL (?record=56), or null. */
export function recordFromParams(params: Record<string, string | string[] | undefined>): number | null {
  const value = params.record;
  const text = (Array.isArray(value) ? value[0] : value)?.trim() ?? "";
  return /^[1-9]\d{0,15}$/.test(text) ? Number(text) : null;
}

/** The page's own URL for these filters and, if one is open, the record in the dialog. */
export function pageUrl(filters: AuditFilters, recordId: number | null = null): string {
  const query = new URLSearchParams(toPageQuery(filters));
  if (recordId !== null) query.set("record", String(recordId));
  const text = query.toString();
  return `/admin/audit${text ? `?${text}` : ""}`;
}

/** Midnight at the start of a YYYY-MM-DD day in the viewer's time zone, as ISO, `days` later. */
function startOfDay(date: string, days = 0): string {
  const [y, m, d] = date.split("-").map(Number);
  return new Date(y, m - 1, d + days).toISOString();
}

/**
 * The query for GET /api/admin/audit. "To" includes that whole day (the API's
 * `until` is exclusive), and `scope_id` is sent only with its `source` (the
 * API refuses it alone).
 */
export function toApiQuery(filters: AuditFilters, page: { beforeId?: number; limit?: number } = {}): string {
  const query = new URLSearchParams();
  const set = (key: string, value: string) => value.trim() && query.set(key, value.trim());
  set("user", filters.user);
  set("event_type", filters.event_type);
  set("document", filters.document);
  if (DATE.test(filters.from)) query.set("since", startOfDay(filters.from));
  if (DATE.test(filters.to)) query.set("until", startOfDay(filters.to, 1));
  if (filters.source) {
    query.set("source", filters.source);
    set("scope_id", filters.scope_id);
  }
  if (page.beforeId !== undefined) query.set("before_id", String(page.beforeId));
  if (page.limit !== undefined) query.set("limit", String(page.limit));
  return query.toString();
}

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

const SOURCE_LABEL = Object.fromEntries(SOURCES.map((s) => [s.value, s.label])) as Record<string, string>;
// Connector events name the sign-in provider (connectors/oauth.py), not the tool.
const PROVIDER_LABEL: Record<string, string> = { google: "Google", slack: "Slack", atlassian: "Atlassian" };

function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

const TIMING_NAMES: [string, string][] = [
  ["embed", "embed"],
  ["search", "search"],
  ["live_check", "live check"],
  ["llm", "LLM"],
  ["total", "total"],
];

/**
 * A question's step timings on one line, in pipeline order: "embed 864 ms · search 10 ms · … · total 2,786 ms".
 * Steps the record lacks are skipped; steps this list doesn't know come after, by their own name.
 */
export function timingsLine(timings: Record<string, number> | undefined): string {
  if (!timings) return "";
  const known = new Set(TIMING_NAMES.map(([key]) => key));
  const fmt = (n: number) => `${new Intl.NumberFormat("en").format(Math.round(n))} ms`;
  return [
    ...TIMING_NAMES.filter(([key]) => typeof timings[key] === "number").map(([key, name]) => `${name} ${fmt(timings[key])}`),
    ...Object.entries(timings)
      .filter(([key, value]) => !known.has(key) && typeof value === "number")
      .map(([key, value]) => `${key.replace(/_/g, " ")} ${fmt(value)}`),
  ].join(" · ");
}

/**
 * The question was checked against the STORED permissions, not live with each tool: a seeded demo user
 * with no connections (backend/app/auth/live_check.py STUB_MODE, "stub: stored ACL, not live"). Labelled
 * wherever it shows, so it can't pass for the real check (AGENTS.md §2.5).
 */
export function isStubCheck(p: QueryPayload): boolean {
  return p.live_check_mode?.startsWith("stub") ?? false;
}

/** One line saying what a record is about, for the table. Unknown types show their name. */
export function summarise(record: AuditRecord): string {
  const p = record.payload;
  switch (record.event_type) {
    case "query": {
      const q = p as QueryPayload;
      const parts = [`Asked "${q.question ?? ""}"`];
      if (q.sent_to_llm) parts.push(`${q.sent_to_llm.length} sent to the LLM`);
      if (q.restricted_matches?.length) parts.push(`${q.restricted_matches.length} restricted`);
      if (q.llm_error) parts.push("LLM failed");
      else parts.push(q.citations?.length ? "answered" : "not found");
      if (isStubCheck(q)) parts.push("not live-checked");
      return parts.join(" · ");
    }
    case "boundary_added":
    case "boundary_removed": {
      const where = `${str(p.title) || str(p.scope_id)} (${SOURCE_LABEL[str(p.source)] ?? str(p.source)})`;
      return record.event_type === "boundary_added"
        ? `Added ${where} to the boundary`
        : `Removed ${where} from the boundary`;
    }
    case "connector_connected":
      return `Connected ${PROVIDER_LABEL[str(p.provider)] ?? str(p.provider)}${p.made_admin ? " and became admin" : ""}`;
    case "connector_disconnected":
      return `Disconnected ${PROVIDER_LABEL[str(p.provider)] ?? str(p.provider)}`;
    case "sync_requested":
      return "Asked for a sync now";
    case "audit_searched":
      return `Searched the audit trail (${plural(typeof p.results === "number" ? p.results : 0, "result")})`;
    case "audit_verified":
      return p.ok
        ? `Verified the chain: intact (${plural(typeof p.checked === "number" ? p.checked : 0, "record")})`
        : `Verified the chain: broken at #${String(p.first_broken_id)}`;
    default:
      return record.event_type;
  }
}
