// Browser-side API client: the only place client components call the backend.
// Requests go to this origin's /api/* proxy (app/api/[...path]/route.ts), so
// the httpOnly session cookie is sent automatically.
//
// No function takes a user ID: who is asking comes only from the session
// cookie (SECURITY.md INV-3).
import { BackendUnreachableError, readResponse } from "./errors";
import type { DevUser, Me, QueryRequest, QueryResponse } from "./types";

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

/** POST /api/query. Sends exactly {question}: the backend rejects any other field. */
export function askQuestion(question: string): Promise<QueryResponse> {
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

/** GET /api/dev/users. DEVELOPMENT ONLY: the route exists only when the backend runs with APP_ENV=development. */
export function listDevUsers(): Promise<DevUser[]> {
  return request<DevUser[]>("/dev/users");
}

/** POST /api/dev/session. DEVELOPMENT ONLY: signs in as a seeded user, with no identity check. */
export function devSignIn(userId: number): Promise<Me> {
  return request<Me>("/dev/session", { method: "POST", body: { user_id: userId } });
}
