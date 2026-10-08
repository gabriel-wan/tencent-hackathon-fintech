"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { BackendUnreachableError, ApiError } from "@/lib/api/errors";
import { connectSlackWithToken } from "@/lib/api/client";

/**
 * DEVELOPMENT ONLY. Slack's OAuth needs an https redirect, which a laptop does
 * not have, so in development Slack is connected with a user token (xoxp-...)
 * pasted here: POST /api/dev/connectors/slack, which exists only while the
 * backend runs with APP_ENV=development. The page shows this form only when
 * the backend lists /api/dev/users. Never put a real company's token anywhere
 * but your own local .env or this local form.
 */
export function SlackTokenForm() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [state, setState] = useState<{ kind: "idle" | "sending" } | { kind: "error"; message: string }>({ kind: "idle" });

  async function submit(event: FormEvent) {
    event.preventDefault();
    setState({ kind: "sending" });
    try {
      await connectSlackWithToken(token.trim());
      setToken(""); // never keep the token in the page
      router.refresh();
      setState({ kind: "idle" });
    } catch (error) {
      setToken("");
      const message =
        error instanceof BackendUnreachableError
          ? "Couldn't reach the server."
          : error instanceof ApiError && error.status === 409
            ? "That Slack account is already linked to someone else, or a different person is signed in."
            : error instanceof ApiError && error.status === 403
              ? "That workspace belongs to a company you can't join (for example, you are a guest)."
              : error instanceof ApiError && error.status === 422
                ? "That doesn't look like a Slack user token (it starts with xoxp-)."
                : error instanceof ApiError && error.status === 503
                  ? "The backend isn't set up for connections yet: check TOKEN_ENCRYPTION_KEY in backend/.env."
                  : "Slack rejected that token.";
      setState({ kind: "error", message });
    }
  }

  return (
    <form
      onSubmit={submit}
      aria-labelledby="slack-token-heading"
      className="grid gap-3 rounded-xl border border-dashed border-warning-foreground/40 p-4"
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="warning">DEVELOPMENT ONLY</Badge>
        <h2 id="slack-token-heading" className="text-sm font-medium">
          Connect Slack with a token
        </h2>
      </div>
      <p className="text-xs text-muted-foreground">
        Slack sign-in needs https, which local development doesn&apos;t have. Paste a Slack user token (starts with{" "}
        <code>xoxp-</code>) from your own test workspace. See docs/connectors/GUIDE.md.
      </p>
      <label htmlFor="slack-token" className="sr-only">
        Slack user token
      </label>
      <div className="flex flex-wrap gap-2">
        <Input
          id="slack-token"
          type="password"
          autoComplete="off"
          placeholder="xoxp-…"
          required
          value={token}
          onChange={(event) => setToken(event.target.value)}
          className="min-w-0 flex-1"
        />
        <Button type="submit" disabled={state.kind === "sending" || token.trim() === ""}>
          {state.kind === "sending" ? "Connecting…" : "Connect with token"}
        </Button>
      </div>
      {state.kind === "error" ? (
        <p role="alert" className="text-sm text-destructive">
          {state.message}
        </p>
      ) : null}
    </form>
  );
}
