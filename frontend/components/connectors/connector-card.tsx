"use client";

import { CheckCircle2, Plug, Unplug } from "lucide-react";
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
import { Button } from "@/components/ui/button";
import { PlatformLogo } from "@/components/platform-logo";
import { StatusChip } from "@/components/status-chip";
import { CONNECTOR_BLURBS, type Connector } from "@/lib/connectors";

type Props = {
  connector: Connector;
  /** Where the browser goes to connect: a full-page navigation to the backend (lib/connectors.ts connectUrl). */
  connectHref: string;
};

/** One tool, as a row: its status, and Connect, or Test and Disconnect. */
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
    // One row of the Connections list: the tool, what KnowBuddy reads there, its status, and its actions.
    <div className="flex flex-wrap items-center gap-x-4 gap-y-3 p-4">
      <PlatformLogo source={connector.id} size={28} className="self-start" />
      <div className="grid min-w-0 flex-1 basis-64 gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="font-semibold">{connector.name}</h2>
          {connector.connected ? (
            <StatusChip tone="success">
              <CheckCircle2 aria-hidden="true" />
              Connected
            </StatusChip>
          ) : (
            <StatusChip>Not connected</StatusChip>
          )}
        </div>
        <p className="text-sm text-muted-foreground">{CONNECTOR_BLURBS[connector.id]}</p>
        {connector.connected ? (
          <p className="text-sm text-muted-foreground">
            As <span className="font-medium text-foreground">{connector.account?.email ?? "your account"}</span>
          </p>
        ) : null}
        {result ? (
          <p role="status" className={result.ok ? "text-sm text-muted-foreground" : "text-sm text-destructive"}>
            {result.ok ? (result.detail ? `Works. The tool sees you as ${result.detail}.` : "Works.") : result.message}
          </p>
        ) : null}
      </div>
      <div className="flex flex-wrap gap-2">
        {connector.connected ? (
          <>
            <Button variant="outline" size="sm" onClick={() => run("test")} disabled={pending}>
              {busy === "test" ? "Testing…" : "Test"}
            </Button>
            <Button variant="outline" size="sm" onClick={() => setConfirming(true)} disabled={pending}>
              <Unplug aria-hidden="true" />
              Disconnect
            </Button>
          </>
        ) : (
          <Button asChild size="sm">
            {/* A plain link: the sign-in redirect has to start and end on the backend. */}
            <a href={connectHref}>
              <Plug aria-hidden="true" />
              Connect
            </a>
          </Button>
        )}
      </div>

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
    </div>
  );
}
