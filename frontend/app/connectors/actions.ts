"use server";

// Server actions for the Connections page. They run on the frontend's server,
// call the backend as the current visitor (their cookie is forwarded), and
// decide nothing: the backend checks the session and acts only on the
// caller's own connections.
//
// Server actions are public endpoints (anyone can call one with any
// argument), so the connector id is checked against the fixed list before it
// goes anywhere near a URL.
import { unstable_rethrow } from "next/navigation";

import { BackendUnreachableError } from "@/lib/api/errors";
import { backendFetch } from "@/lib/api/server";
import { isConnectorId } from "@/lib/connectors";

export type ActionResult = { ok: true; detail?: string } | { ok: false; message: string };

const UNREACHABLE: ActionResult = { ok: false, message: "Couldn't reach the server. Try again in a moment." };
const BAD_CONNECTOR: ActionResult = { ok: false, message: "Unknown connection." };

/** GET /connectors/{id}/ping: calls the tool's own API as you, which proves the connection works. */
export async function testConnection(connector: string): Promise<ActionResult> {
  if (!isConnectorId(connector)) return BAD_CONNECTOR;
  try {
    const res = await backendFetch(`/connectors/${connector}/ping`, {}, 15_000); // calls the tool's own API
    if (res.ok) {
      const body = (await res.json()) as { as?: unknown };
      return { ok: true, detail: typeof body.as === "string" ? body.as : undefined };
    }
    if (res.status === 404) return { ok: false, message: "Not connected." };
    if (res.status === 401) return { ok: false, message: "Access expired or was revoked. Connect again." };
    return { ok: false, message: "The tool didn't answer. Try again in a moment." };
  } catch (error) {
    unstable_rethrow(error);
    return error instanceof BackendUnreachableError ? UNREACHABLE : { ok: false, message: "The test failed." };
  }
}

/**
 * DELETE /connectors/{id}. Jira and Confluence share one Atlassian sign-in,
 * so disconnecting either one disconnects both (the backend does that).
 */
export async function disconnectConnection(connector: string): Promise<ActionResult> {
  if (!isConnectorId(connector)) return BAD_CONNECTOR;
  try {
    const res = await backendFetch(`/connectors/${connector}`, { method: "DELETE" });
    return res.ok ? { ok: true } : { ok: false, message: "Couldn't disconnect. Try again." };
  } catch (error) {
    unstable_rethrow(error);
    return error instanceof BackendUnreachableError ? UNREACHABLE : { ok: false, message: "Couldn't disconnect." };
  }
}
