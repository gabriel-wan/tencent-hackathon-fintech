// Server-side API client, for server components and layouts only. It calls the
// backend directly at BACKEND_SERVER_URL and forwards the incoming request's whole
// Cookie header, so it works whatever the session cookie is called.
// Never import this from a client component.
import { headers } from "next/headers";
import { unstable_rethrow } from "next/navigation";

import { ApiError, BackendUnreachableError, readResponse } from "./errors";
import type { Connector } from "@/lib/connectors";
import type { DevUser, Me } from "./types";

/**
 * A request to the backend as the current visitor: the incoming Cookie header
 * is forwarded as-is. `path` is the backend's own path, for example
 * "/api/me" or "/connectors". Throws BackendUnreachableError when it cannot
 * be reached or does not answer within `timeoutMs`; the caller reads the Response.
 */
export async function backendFetch(path: string, init: RequestInit = {}, timeoutMs = 5_000): Promise<Response> {
  if (typeof window !== "undefined") throw new Error("lib/api/server.ts is server-only");
  const base = process.env.BACKEND_SERVER_URL;
  if (!base) throw new BackendUnreachableError("BACKEND_SERVER_URL is not set");
  const cookie = (await headers()).get("cookie");

  try {
    return await fetch(new URL(path, base), {
      ...init,
      headers: { accept: "application/json", ...init.headers, ...(cookie ? { cookie } : {}) },
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch {
    throw new BackendUnreachableError();
  }
}

async function request<T>(path: string): Promise<T> {
  return readResponse<T>(await backendFetch(`/api${path}`));
}

/** GET /api/me for the current request. Throws NotSignedInError when signed out. */
export function getMe(): Promise<Me> {
  return request<Me>("/me");
}

/**
 * GET /api/dev/users. Returns null when the routes do not exist (404: the
 * backend is not in development mode) or cannot be listed, so the UI hides
 * every development-only control. The backend is the only source of truth
 * for development mode (ui-plan.md 4.1).
 */
export async function listDevUsers(): Promise<DevUser[] | null> {
  try {
    return await request<DevUser[]>("/dev/users");
  } catch (error) {
    unstable_rethrow(error); // let Next.js's own control-flow errors through
    if (!(error instanceof ApiError && error.status === 404)) {
      console.warn("Could not list development users:", error);
    }
    return null;
  }
}

/** GET /connectors: the four tools and whether this visitor has connected each. */
export async function listConnectors(): Promise<Connector[]> {
  return readResponse<Connector[]>(await backendFetch("/connectors"));
}
