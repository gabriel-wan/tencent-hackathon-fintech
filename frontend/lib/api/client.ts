// Browser-side API client: the only place client components call the backend.
// Requests go to this origin's /api/* proxy (app/api/[...path]/route.ts), so
// the httpOnly session cookie is sent automatically.
//
// No function takes a user ID: who is asking comes only from the session
// cookie (SECURITY.md INV-3).
import { ApiError, BackendUnreachableError, NotSignedInError, readResponse } from "./errors";
import { isMockEnabled, mockAnswer } from "./mock";
import type { DevUser, Me, QueryRequest, QueryResponse, SourceName } from "./types";
import type { AuditPage, VerifyResult } from "@/lib/audit";
import { type BoundaryEntry, type Scope, type ScopesProblem, scopesProblem } from "@/lib/boundary";

async function request<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      method: init.method ?? "GET",
      headers: {
        accept: "application/json",
        ...(init.body !== undefined ? { "content-type": "application/json" } : {}),
      },
      body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
      credentials: "same-origin",
      cache: "no-store",
    });
  } catch {
    throw new BackendUnreachableError();
  }
  return readResponse<T>(res);
}

/**
 * POST /api/query. Sends exactly {question}: the backend rejects any other field.
 * In mock mode (development only, lib/api/mock.ts) the reply is a labelled fixture.
 */
export function askQuestion(question: string): Promise<QueryResponse> {
  if (isMockEnabled()) return mockAnswer(question);
  const body: QueryRequest = { question };
  return request<QueryResponse>("/query", { method: "POST", body });
}

/** GET /api/me. Throws NotSignedInError when there is no session. */
export function getMe(): Promise<Me> {
  return request<Me>("/me");
}

/** DELETE /api/session. */
export async function signOut(): Promise<void> {
  await request<null>("/session", { method: "DELETE" });
}

/**
 * GET /api/admin/audit. Admins only (the backend returns 403 to anyone else).
 * `query` comes from toApiQuery in lib/audit.ts. The search is itself audited.
 */
export function searchAudit(query: string): Promise<AuditPage> {
  return request<AuditPage>(`/admin/audit${query ? `?${query}` : ""}`);
}

/** POST /api/admin/audit/verify: recompute the company's hash chain. Admins only; itself audited. */
export function verifyAuditChain(): Promise<VerifyResult> {
  return request<VerifyResult>("/admin/audit/verify", { method: "POST" });
}

/**
 * GET /api/admin/scopes/{source}: the channels, folders, projects or spaces the admin
 * can see in that tool, read with the admin's own connection. Admins only.
 *
 * Not through readResponse: the backend's 401 ("connect again") and 502 ("API call
 * failed") here are about the tool, not our session or server (scopesProblem).
 */
export async function listScopes(
  source: SourceName,
): Promise<{ scopes: Scope[] } | { problem: ScopesProblem }> {
  let res: Response;
  try {
    res = await fetch(`/api/admin/scopes/${source}`, {
      headers: { accept: "application/json" },
      credentials: "same-origin",
      cache: "no-store",
    });
  } catch {
    throw new BackendUnreachableError();
  }
  if (res.ok) return { scopes: (await res.json()) as Scope[] };
  const detail = await res
    .json()
    .then((body: { detail?: unknown }) => (typeof body?.detail === "string" ? body.detail : ""))
    .catch(() => "");
  const problem = scopesProblem(res.status, detail);
  if (problem) return { problem };
  if (res.status === 401) throw new NotSignedInError();
  if (res.status === 502 || res.status === 504) throw new BackendUnreachableError(detail || undefined);
  throw new ApiError(res.status, detail || res.statusText);
}

/** GET /api/admin/boundary: the company's allowed scopes, each with its last sync. Admins only. */
export function listBoundary(): Promise<BoundaryEntry[]> {
  return request<BoundaryEntry[]>("/admin/boundary");
}

/** PUT /api/admin/boundary/{source}/{scope_id}: allow a scope. Copies nothing until a sync. Audited. */
export async function addScope(source: SourceName, scopeId: string, title: string): Promise<void> {
  await request<null>(`/admin/boundary/${source}/${encodeURIComponent(scopeId)}`, { method: "PUT", body: { title } });
}

/** DELETE /api/admin/boundary/{source}/{scope_id}: its content leaves answers at once, for everyone. Audited. */
export async function removeScope(source: SourceName, scopeId: string): Promise<void> {
  await request<null>(`/admin/boundary/${source}/${encodeURIComponent(scopeId)}`, { method: "DELETE" });
}

/** POST /api/admin/sync: sync the whole company now, in the background (nothing to wait on). Audited. */
export async function syncNow(): Promise<void> {
  await request<unknown>("/admin/sync", { method: "POST" });
}

/** GET /api/dev/users. DEVELOPMENT ONLY: the route exists only when the backend runs with APP_ENV=development. */
export function listDevUsers(): Promise<DevUser[]> {
  return request<DevUser[]>("/dev/users");
}

/** POST /api/dev/session. DEVELOPMENT ONLY: signs in as a seeded user, with no identity check. */
export function devSignIn(userId: number): Promise<Me> {
  return request<Me>("/dev/session", { method: "POST", body: { user_id: userId } });
}

/**
 * POST /api/dev/connectors/slack. DEVELOPMENT ONLY: connects Slack with a
 * pasted user token, because Slack's OAuth needs https. The route exists only
 * while the backend runs with APP_ENV=development.
 */
export function connectSlackWithToken(token: string): Promise<unknown> {
  return request<unknown>("/dev/connectors/slack", { method: "POST", body: { token } });
}
