import { CheckCircle2, CircleAlert, Info } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { redirect, unstable_rethrow } from "next/navigation";
import { connection } from "next/server";

import { ConnectorCard } from "@/components/connectors/connector-card";
import { SlackTokenForm } from "@/components/connectors/slack-token-form";
import { PageContainer } from "@/components/page-container";
import { ServerUnavailable } from "@/components/server-unavailable";
import { SignedInShell } from "@/components/signed-in-shell";
import { AppHeader } from "@/components/app-header";
import { MockBadge } from "@/components/mock-badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { NotSignedInError } from "@/lib/api/errors";
import { getMe, listConnectors, listDevUsers } from "@/lib/api/server";
import type { Me } from "@/lib/api/types";
import { connectedLabel, connectUrl, oauthErrorMessage, type Connector } from "@/lib/connectors";

export const metadata: Metadata = { title: "Connections · KnowBuddy" };

type Props = { searchParams: Promise<{ connected?: string | string[]; error?: string | string[] }> };

/**
 * Connect, test and disconnect your tools.
 *
 * This is also where the backend's OAuth callback lands: it redirects the
 * browser to /connectors?connected=<provider> or ?error=<code> (the target is
 * fixed in the backend). It therefore does its own session check instead of
 * living under the (app) layout: a failed sign-in has no session, and the
 * (app) layout would send it to /login and lose the error. Here, the error is
 * carried to /login, where the person is trying to sign in.
 */
export default async function ConnectionsPage({ searchParams }: Props) {
  await connection(); // per request, never prerendered
  const { connected, error } = await searchParams;
  const errorMessage = oauthErrorMessage(error);

  let me: Me;
  try {
    me = await getMe();
  } catch (failure) {
    unstable_rethrow(failure);
    if (failure instanceof NotSignedInError) {
      // Only a known code is carried over; anything else is dropped.
      redirect(errorMessage && typeof error === "string" ? `/login?error=${encodeURIComponent(error)}` : "/login");
    }
    console.error("Session check failed:", failure);
    return (
      <>
        <AppHeader actions={<MockBadge />} />
        <PageContainer>
          <ServerUnavailable />
        </PageContainer>
      </>
    );
  }

  let connectors: Connector[] | null = null;
  try {
    connectors = await listConnectors();
  } catch (failure) {
    unstable_rethrow(failure);
    console.error("Could not list connections:", failure);
  }
  // null unless the backend runs with APP_ENV=development (lib/api/server.ts).
  const devMode = (await listDevUsers()) !== null;

  const justConnected = connectedLabel(connected);
  const slackConnected = connectors?.find((c) => c.id === "slack")?.connected ?? false;
  const atlassianConnected = connectors?.some((c) => (c.id === "jira" || c.id === "confluence") && c.connected) ?? false;
  const anyConnected = connectors?.some((c) => c.connected) ?? false;
  // A company comes from a Slack workspace; an Atlassian sign-in only joins one, and Google never names one
  // (ADR-002 amendments, 5 and 7 Oct). So any Slack, Jira or Confluence connection means a company.
  const needsCompany = anyConnected && !slackConnected && !atlassianConnected;

  return (
    <SignedInShell me={me}>
      <PageContainer className="grid content-start gap-6">
        <div className="grid gap-1">
          <h1 className="text-2xl font-semibold tracking-tight">Connections</h1>
          <p className="text-muted-foreground">
            Connect the tools you use. Answers only include what you can already see in them.
          </p>
        </div>

        {justConnected ? (
          <Alert>
            <CheckCircle2 aria-hidden="true" />
            <AlertDescription className="flex flex-wrap items-center gap-x-3">
              <span>Connected {justConnected}.</span>
              <Link href="/" className="inline-flex items-center font-medium text-primary underline-offset-4 hover:underline pointer-coarse:min-h-11">
                Ask a question
              </Link>
            </AlertDescription>
          </Alert>
        ) : null}

        {errorMessage ? (
          <Alert variant="destructive">
            <CircleAlert aria-hidden="true" />
            <AlertDescription>{errorMessage}</AlertDescription>
          </Alert>
        ) : null}

        {needsCompany ? (
          <Alert>
            <Info aria-hidden="true" />
            <AlertDescription>
              Your company comes from your Slack workspace. Connect Slack to join it (Jira and Confluence join it too,
              once your admin has added your company&apos;s Atlassian site); until then, answers can&apos;t include your
              company&apos;s content.
            </AlertDescription>
          </Alert>
        ) : null}

        {connectors ? (
          <ul className="grid gap-4 sm:grid-cols-2">
            {connectors.map((connector) => (
              <li key={connector.id} className="grid">
                <ConnectorCard connector={connector} connectHref={connectUrl(connector.id)} />
              </li>
            ))}
          </ul>
        ) : (
          <ServerUnavailable />
        )}

        {devMode && !slackConnected ? <SlackTokenForm /> : null}
      </PageContainer>
    </SignedInShell>
  );
}
