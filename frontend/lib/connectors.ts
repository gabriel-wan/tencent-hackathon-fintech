// Shared by /login and /connectors: what the backend's OAuth callback can send
// back (backend/app/connectors/api.py), and the four connectors.

/** The connector ids the backend knows (backend/app/connectors/api.py CONNECTORS). */
export const CONNECTOR_IDS = ["drive", "slack", "jira", "confluence"] as const;
export type ConnectorId = (typeof CONNECTOR_IDS)[number];

export function isConnectorId(value: unknown): value is ConnectorId {
  return typeof value === "string" && (CONNECTOR_IDS as readonly string[]).includes(value);
}

/** What GET /connectors returns for each tool (the backend does not publish a schema for it). */
export type Connector = {
  id: ConnectorId;
  name: string;
  connected: boolean;
  account: { email: string } | null;
};

export const CONNECTOR_BLURBS: Record<ConnectorId, string> = {
  drive: "Files shared with you in Google Drive.",
  slack: "Channels you are a member of.",
  jira: "Issues in the projects you can browse.",
  confluence: "Pages in the spaces you can read.",
};

/**
 * ?error= values the OAuth callback redirects back with. Only these are ever
 * shown: any other value (a crafted link) shows nothing, so nobody can put
 * their own text on our pages.
 */
const ERROR_MESSAGES = new Map<string, string>([
  ["access_denied", "Sign-in was cancelled."],
  ["provider_error", "That sign-in didn't work. Check you used the right account, then try again."],
  ["invalid_state", "The sign-in expired or was started in another browser. Please try again."],
  [
    "account_mismatch",
    "That account is already linked to someone else, or a different person is signed in. Sign out and try again.",
  ],
  [
    "no_company",
    "That Slack workspace or Atlassian site belongs to a company you can't join. For example, you may be a Slack " +
      "guest, or you granted several Atlassian sites: grant only your company's.",
  ],
  [
    "missing_permission",
    "Google Drive access wasn't granted. Connect again and tick \"See and download all your Google Drive files\" " +
      "on Google's permission screen.",
  ],
]);

export function oauthErrorMessage(code: string | string[] | undefined): string | undefined {
  return typeof code === "string" ? ERROR_MESSAGES.get(code) : undefined;
}

/** ?connected= values: the OAuth provider, not the connector (Jira and Confluence share one sign-in). */
const CONNECTED_LABELS = new Map<string, string>([
  ["google", "Google Drive"],
  ["slack", "Slack"],
  ["atlassian", "Jira and Confluence"],
]);

export function connectedLabel(provider: string | string[] | undefined): string | undefined {
  return typeof provider === "string" ? CONNECTED_LABELS.get(provider) : undefined;
}

/**
 * Where the browser goes to start a sign-in. A full-page navigation straight
 * to the backend, never a fetch: the OAuth redirect has to start and end on
 * the backend. The address comes from BACKEND_LOCAL_URL (server environment).
 */
export function connectUrl(connector: ConnectorId): string {
  const base = (process.env.BACKEND_LOCAL_URL ?? "http://localhost:8000").replace(/\/$/, "");
  return `${base}/connectors/${connector}/connect`;
}
