import { CircleAlert } from "lucide-react";
import type { Metadata } from "next";
import { redirect, unstable_rethrow } from "next/navigation";
import { connection } from "next/server";

import { Wordmark } from "@/components/brand";
import { SlackTokenForm } from "@/components/connectors/slack-token-form";
import { DevSignInList } from "@/components/dev-sign-in-list";
import { Disclosure } from "@/components/disclosure";
import { LoginHero } from "@/components/login/login-hero";
import { PageContainer } from "@/components/page-container";
import { PlatformLogo } from "@/components/platform-logo";
import { ServerUnavailable } from "@/components/server-unavailable";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { NotSignedInError } from "@/lib/api/errors";
import { getMe, listDevUsers } from "@/lib/api/server";
import { connectUrl, oauthErrorMessage, type ConnectorId } from "@/lib/connectors";

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
    <PageContainer className="max-w-5xl">
      <div className="grid gap-10">
        {session === "unreachable" ? <ServerUnavailable /> : null}

        <LoginHero>
          <div className="grid gap-6">
            <Wordmark size="lg" tagline />
            <h1 className="text-4xl font-semibold tracking-tight text-balance sm:text-5xl">
              <span className="block">Know what you need.</span>{" "}
              <span className="block">No-buddy sees what they shouldn&apos;t.</span>
            </h1>
            <p className="max-w-prose text-lg text-muted-foreground">
              Answers from your company&apos;s Slack, Drive, Jira and Confluence, limited to what you can already see.
            </p>

            {errorMessage ? (
              <Alert variant="destructive" className="max-w-prose">
                <CircleAlert aria-hidden="true" />
                <AlertDescription>{errorMessage}</AlertDescription>
              </Alert>
            ) : null}

            {/* Plain links: the sign-in redirect has to start and end on the backend. Signing in
                connects that tool to your account; there is no separate password. Slack first: it is
                the only sign-in that can start a company (backend/app/connectors/oauth.py account()). */}
            <div className="grid gap-4">
              <Button asChild variant="outline" size="xl" className="w-full sm:w-fit">
                <a href={connectUrl("slack")}>
                  <PlatformLogo source="slack" size={20} />
                  Sign in with Slack
                </a>
              </Button>
              <div className="flex items-center gap-3 text-sm text-muted-foreground">
                <span>Alternatively, sign in with</span>
                <TooltipProvider>
                  <LogoSignIn connector="drive" logo="google" name="Google" />
                  <LogoSignIn connector="jira" logo="atlassian" name="Atlassian" />
                </TooltipProvider>
              </div>
            </div>

            <Disclosure summary="How accounts work" className="max-w-prose">
              <ul className="grid list-disc gap-2 pl-4.5 text-muted-foreground">
                <li>Signing in connects that tool. Only what you can already see there is used, and there&apos;s no separate password.</li>
                <li>Your company comes from your Slack workspace, so sign in with Slack first, or connect it later.</li>
                <li>Jira and Confluence join once your admin has added your company&apos;s Atlassian site.</li>
              </ul>
            </Disclosure>
          </div>

        </LoginHero>

        <div className="grid max-w-md gap-6">
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
      </div>
    </PageContainer>
  );
}

/** A logo-only sign-in link: the name is its accessible label and its tooltip (hover and keyboard focus). */
function LogoSignIn({ connector, logo, name }: { connector: ConnectorId; logo: string; name: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button asChild variant="outline" size="icon-xl" className="rounded-full">
          <a href={connectUrl(connector)} aria-label={`Sign in with ${name}`}>
            <PlatformLogo source={logo} size={22} />
          </a>
        </Button>
      </TooltipTrigger>
      <TooltipContent>Sign in with {name}</TooltipContent>
    </Tooltip>
  );
}
