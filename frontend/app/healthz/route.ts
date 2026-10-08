// Container health check (frontend/Dockerfile). Deliberately does not call the
// backend: the frontend is healthy if it can serve a request.
export const dynamic = "force-dynamic";

export function GET() {
  return new Response("ok", { headers: { "content-type": "text/plain", "cache-control": "no-store" } });
}
