/**
 * Forwards /api/* from the browser to the backend, so the browser only ever
 * talks to this origin and the session cookie (ib_session, httpOnly) works
 * without CORS.
 *
 * A route handler, not a next.config.ts rewrite: rewrites capture BACKEND_URL
 * when the app is built, but Docker only provides it at run time.
 *
 * This file carries the session cookie but makes no authorization decision:
 * the backend decides everything (SECURITY.md INV-2, INV-3).
 */
import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

// Only these request headers reach the backend.
const FORWARDED_REQUEST_HEADERS = ["content-type", "accept", "cookie"];
// The longest backend call is POST /api/query (LLM ~7 s plus live checks up to 2 s).
const TIMEOUT_MS = 30_000;

type Context = { params: Promise<{ path: string[] }> };

function json(status: number, detail: string): Response {
  return Response.json({ detail }, { status, headers: { "cache-control": "no-store" } });
}

async function forward(request: NextRequest, { params }: Context): Promise<Response> {
  const base = process.env.BACKEND_URL;
  if (!base) return json(500, "BACKEND_URL is not set");

  // Stay inside /api: refuse segments that would walk out of it.
  const { path } = await params;
  if (path.some((segment) => segment === "." || segment === ".." || segment.includes("/"))) {
    return json(400, "invalid path");
  }
  // The host always comes from the environment, never from the request.
  const target = new URL(`/api/${path.map(encodeURIComponent).join("/")}`, base);
  target.search = request.nextUrl.search;

  const headers = new Headers();
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch (error) {
    // Never retried: a repeated POST could ask the same question twice.
    if (error instanceof DOMException && error.name === "TimeoutError") return json(504, "backend timed out");
    return json(502, "backend unreachable");
  }

  const responseHeaders = new Headers({ "cache-control": "no-store" });
  for (const name of ["content-type", "location"]) {
    const value = upstream.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  // Every Set-Cookie, so POST /api/dev/session signs this origin in.
  for (const cookie of upstream.headers.getSetCookie()) responseHeaders.append("set-cookie", cookie);

  const noBody = upstream.status === 204 || upstream.status === 304 || request.method === "HEAD";
  return new Response(noBody ? null : await upstream.arrayBuffer(), {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export { forward as GET, forward as POST, forward as PUT, forward as PATCH, forward as DELETE };
