"use client";

import { Plug, Unplug } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { disconnectConnection, testConnection, type ActionResult } from "@/app/connectors/actions";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { CONNECTOR_BLURBS, type Connector } from "@/lib/connectors";

type Props = {
  connector: Connector;
  /** Where the browser goes to connect: a full-page navigation to the backend (lib/connectors.ts connectUrl). */
  connectHref: string;
};

/** One tool: its status, and Connect, or Test and Disconnect. */
export function ConnectorCard({ connector, connectHref }: Props) {
  const router = useRouter();
  const [result, setResult] = useState<ActionResult | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [pending, startTransition] = useTransition();
  const [busy, setBusy] = useState<"test" | "disconnect" | null>(null);

  // Jira and Confluence share one Atlassian sign-in: the backend removes both.
  const sharesSignIn = connector.id === "jira" || connector.id === "confluence";

  function run(kind: "test" | "disconnect") {
    setBusy(kind);
    setResult(null);
    startTransition(async () => {
      const outcome = kind === "test" ? await testConnection(connector.id) : await disconnectConnection(connector.id);
      setBusy(null);
      if (kind === "disconnect" && outcome.ok) {
        setResult(null); // the card itself changes to "Not connected"
        router.refresh();
      } else {
        setResult(outcome);
      }
    });
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>
            <h2 className="text-base font-semibold">{connector.name}</h2>
          </CardTitle>
          {connector.connected ? <Badge variant="secondary">Connected</Badge> : <Badge variant="outline">Not connected</Badge>}
        </div>
        <CardDescription>{CONNECTOR_BLURBS[connector.id]}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        {connector.connected ? (
          <>
            <p className="text-sm text-muted-foreground">
              Connected as <span className="font-medium text-foreground">{connector.account?.email ?? "your account"}</span>
            </p>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={() => run("test")} disabled={pending}>
                {busy === "test" ? "Testing…" : "Test"}
              </Button>
              <Button variant="outline" size="sm" onClick={() => setConfirming(true)} disabled={pending}>
                <Unplug aria-hidden="true" />
                Disconnect
              </Button>
            </div>
          </>
        ) : (
          <div>
            <Button asChild size="sm">
              {/* A plain link: the sign-in redirect has to start and end on the backend. */}
              <a href={connectHref}>
                <Plug aria-hidden="true" />
                Connect
              </a>
            </Button>
          </div>
        )}

        {result ? (
          <p role="status" className={result.ok ? "text-sm text-muted-foreground" : "text-sm text-destructive"}>
            {result.ok ? (result.detail ? `Works. The tool sees you as ${result.detail}.` : "Works.") : result.message}
          </p>
        ) : null}
      </CardContent>

      <AlertDialog open={confirming} onOpenChange={setConfirming}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Disconnect {sharesSignIn ? "Jira and Confluence" : connector.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              {sharesSignIn
                ? "Jira and Confluence share one Atlassian sign-in, so both are disconnected. "
                : ""}
              Answers will stop including what you could see there. You can connect again at any time.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => run("disconnect")}>Disconnect</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
