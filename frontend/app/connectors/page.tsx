import { cookies } from "next/headers";
import { redirect } from "next/navigation";

// Browsers share cookies across ports, so the backend's session cookie reaches this page and is forwarded.
// Server-side calls use BACKEND_SERVER_URL (Docker-internal); browser links use BACKEND_LOCAL_URL.
const localApi = process.env.BACKEND_LOCAL_URL ?? "http://localhost:8000";
// Slack's sign-in needs https, which localhost lacks: in development, Slack connects with a pasted token instead.
const dev = process.env.APP_ENV === "development";

// Only messages the backend sends: a crafted ?connected=… or ?error=… link shows nothing.
const PROVIDERS = ["google", "slack", "atlassian"];
const ERRORS = [
  "access_denied", "provider_error", "invalid_state", "account_mismatch", "disconnect_failed", "slack_token_rejected",
];

type Connector = { id: string; name: string; connected: boolean; account: { email: string } | null };

async function backend(path: string, init?: RequestInit) {
  const session = (await cookies()).get("ib_session")?.value;
  return fetch(`${process.env.BACKEND_SERVER_URL}${path}`, {
    ...init,
    cache: "no-store",
    headers: { ...init?.headers, ...(session ? { cookie: `ib_session=${session}` } : {}) },
  });
}

async function connectSlackWithToken(form: FormData) {
  "use server";
  const res = await backend("/api/dev/connectors/slack", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ token: String(form.get("token") ?? "") }),
  });
  // The backend signs you in on first connect: pass its session cookie on to the browser.
  const session = res.headers.getSetCookie().join(";").match(/ib_session=([^;]+)/)?.[1];
  if (session) {
    (await cookies()).set("ib_session", session, { httpOnly: true, sameSite: "lax", path: "/", maxAge: 12 * 3600 });
  }
  const error = res.status === 409 ? "account_mismatch" : "slack_token_rejected";
  redirect(res.ok ? "/connectors?connected=slack" : `/connectors?error=${error}`);
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
      {ERRORS.includes(error ?? "") && <p role="alert">Error: {error} (see docs/connectors/GUIDE.md)</p>}
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
            ) : dev && c.id === "slack" ? (
              <form action={connectSlackWithToken} style={{ display: "inline" }}>
                <input name="token" type="password" aria-label="Slack user token" placeholder="xoxp-…" required autoComplete="off" />{" "}
                <button>Connect with token</button>
              </form>
            ) : (
              <a href={`${localApi}/connectors/${c.id}/connect`}>Connect</a>
            )}
          </li>
        ))}
      </ul>
    </main>
  );
}
