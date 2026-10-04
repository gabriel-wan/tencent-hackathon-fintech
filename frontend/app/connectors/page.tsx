import { cookies } from "next/headers";
import { redirect } from "next/navigation";

// Browsers share cookies across ports, so the backend's session cookie reaches this page and is forwarded.
// Server-side calls use BACKEND_SERVER_URL (Docker-internal); browser links use BACKEND_LOCAL_URL.
const localApi = process.env.BACKEND_LOCAL_URL ?? "http://localhost:8000";

// Only messages the backend sends: a crafted ?connected=… or ?error=… link shows nothing.
const PROVIDERS = ["google", "slack", "atlassian"];
const ERRORS = ["access_denied", "provider_error", "invalid_state", "account_mismatch", "disconnect_failed"];

type Connector = { id: string; name: string; connected: boolean; account: { email: string } | null };

async function backend(path: string, init?: RequestInit) {
  const session = (await cookies()).get("ib_session")?.value;
  return fetch(`${process.env.BACKEND_SERVER_URL}${path}`, {
    ...init,
    cache: "no-store",
    headers: session ? { cookie: `ib_session=${session}` } : {},
  });
}

async function disconnect(id: string) {
  "use server";
  const res = await backend(`/connectors/${encodeURIComponent(id)}`, { method: "DELETE" });
  redirect(res.ok ? "/connectors" : "/connectors?error=disconnect_failed");
}

export default async function ConnectorsPage({
  searchParams,
}: {
  searchParams: Promise<{ connected?: string; error?: string }>;
}) {
  const { connected, error } = await searchParams; // set by the backend's OAuth callback
  const connectors: Connector[] = await (await backend("/connectors")).json();
  return (
    <main>
      <h1>Connectors</h1>
      {PROVIDERS.includes(connected ?? "") && <p>Connected to {connected}.</p>}
      {ERRORS.includes(error ?? "") && <p role="alert">Error: {error} (see docs/connectors/GUIDE.md, Troubleshooting)</p>}
      <ul>
        {connectors.map((c) => (
          <li key={c.id}>
            <strong>{c.name}</strong>{" "}
            {c.connected ? (
              <>
                {c.account?.email} <a href={`${localApi}/connectors/${c.id}/ping`} target="_blank">Test</a>{" "}
                <form action={disconnect.bind(null, c.id)} style={{ display: "inline" }}>
                  <button>Disconnect</button>
                </form>
              </>
            ) : (
              <a href={`${localApi}/connectors/${c.id}/connect`}>Connect</a>
            )}
          </li>
        ))}
      </ul>
    </main>
  );
}
