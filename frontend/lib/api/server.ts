// Server-side API client, for server components and layouts only. It calls the
// backend directly at BACKEND_URL and forwards the incoming request's whole
// Cookie header, so it works whatever the session cookie is called.
// Never import this from a client component.
import { headers } from "next/headers";

import { ApiError, BackendUnreachableError, readResponse } from "./errors";
import type { DevUser, Me } from "./types";

async function request<T>(path: string): Promise<T> {
  if (typeof window !== "undefined") throw new Error("lib/api/server.ts is server-only");
  const base = process.env.BACKEND_URL;
  if (!base) throw new BackendUnreachableError("BACKEND_URL is not set");
  const cookie = (await headers()).get("cookie");

  let res: Response;
  try {
    res = await fetch(new URL(`/api${path}`, base), {
      headers: { accept: "application/json", ...(cookie ? { cookie } : {}) },
      cache: "no-store",
      signal: AbortSignal.timeout(5_000),
    });
  } catch {
    throw new BackendUnreachableError();
  }
  return readResponse<T>(res);
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
    if (!(error instanceof ApiError && error.status === 404)) {
      console.warn("Could not list development users:", error);
    }
    return null;
  }
}
