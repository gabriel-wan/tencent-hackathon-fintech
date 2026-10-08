import { CircleAlert } from "lucide-react";
import type { Metadata } from "next";
import { redirect, unstable_rethrow } from "next/navigation";
import { connection } from "next/server";

import { SlackTokenForm } from "@/components/connectors/slack-token-form";
import { DevSignInList } from "@/components/dev-sign-in-list";
import { PageContainer } from "@/components/page-container";
import { ServerUnavailable } from "@/components/server-unavailable";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { NotSignedInError } from "@/lib/api/errors";
import { getMe, listDevUsers } from "@/lib/api/server";
import { connectUrl, oauthErrorMessage } from "@/lib/connectors";

export const metadata: Metadata = { title: "Sign in · KnowBuddy" };

type Props = { searchParams: Promise<{ error?: string | string[] }> };

async function sessionState(): Promise<"signedIn" | "signedOut" | "unreachable"> {
  try {
    await getMe();
    return "signedIn";
  } catch (error) {
    unstable_rethrow(error); // let Next.js's own control-flow errors through
    return error instanceof NotSignedInError ? "signedOut" : "unreachable";
  }
}

export default async function LoginPage({ searchParams }: Props) {
  await connection(); // per request, never prerendered
  const session = await sessionState();
  if (session === "signedIn") redirect("/");

  const { error } = await searchParams;
  // Only a code the backend can send is shown (lib/connectors.ts); anything else is ignored.
  const errorMessage = oauthErrorMessage(error);
  // null unless the backend runs with APP_ENV=development (lib/api/server.ts).
  const devUsers = session === "signedOut" ? await listDevUsers() : null;

  return (
    <PageContainer className="max-w-md">
      <div className="grid gap-6">
        {session === "unreachable" ? <ServerUnavailable /> : null}

        <Card>
          <CardHeader>
            <CardTitle>
              <h1 className="text-xl font-semibold tracking-tight">Sign in to KnowBuddy</h1>
            </CardTitle>
            <CardDescription>
              Answers from your company&apos;s Slack, Drive, Jira and Confluence, limited to what you can already see.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3">
            {errorMessage ? (
              <Alert variant="destructive">
                <CircleAlert aria-hidden="true" />
                <AlertDescription>{errorMessage}</AlertDescription>
              </Alert>
            ) : null}
            {/* Plain links: the sign-in redirect has to start and end on the backend. Signing in
                connects that tool to your account; there is no separate password. */}
            <Button asChild size="lg" className="w-full">
              <a href={connectUrl("drive")}>Sign in with Google</a>
            </Button>
            <div className="grid grid-cols-2 gap-3">
              <Button asChild variant="outline" size="lg">
                <a href={connectUrl("slack")}>Slack</a>
              </Button>
              <Button asChild variant="outline" size="lg">
                <a href={connectUrl("jira")}>Atlassian</a>
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Signing in connects that tool, and only what you can already see there is used. Your company comes from
              your Slack workspace, so connect Slack too. Jira and Confluence join it once your admin has added them.
            </p>
          </CardContent>
        </Card>

        {devUsers && devUsers.length > 0 ? (
          <section
            aria-labelledby="dev-sign-in-heading"
            className="grid gap-3 rounded-xl border border-dashed border-warning-foreground/40 p-4"
          >
            <div className="flex items-center gap-2">
              <Badge variant="warning">DEVELOPMENT ONLY</Badge>
              <h2 id="dev-sign-in-heading" className="text-sm font-medium">
                Sign in as a seeded user
              </h2>
            </div>
            <p className="text-xs text-muted-foreground">
              Identity is not verified here. These sign-ins exist only while the backend runs with{" "}
              <code>APP_ENV=development</code>.
            </p>
            <DevSignInList users={devUsers} />
          </section>
        ) : null}

        {/* Development only (devUsers is null otherwise). Slack's sign-in needs https, so locally Slack is
            connected with a pasted token, and connecting it is also how a new person signs in and how a
            company starts. Signed-out visitors can't reach /connectors, so the form must be here too. */}
        {devUsers !== null ? <SlackTokenForm /> : null}
      </div>
    </PageContainer>
  );
}
