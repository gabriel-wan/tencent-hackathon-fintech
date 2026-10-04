import { CircleAlert } from "lucide-react";
import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { DevSignInList } from "@/components/dev-sign-in-list";
import { PageContainer } from "@/components/page-container";
import { ServerUnavailable } from "@/components/server-unavailable";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { NotSignedInError } from "@/lib/api/errors";
import { getMe, listDevUsers } from "@/lib/api/server";

export const metadata: Metadata = { title: "Sign in · Internal Brain" };

// Errors the backend's OAuth callback can send (?error=..., connectors branch,
// backend/app/connectors/api.py). Only these are shown; any other value is
// ignored, so a crafted link cannot put its own text on this page.
const SIGN_IN_ERRORS = new Map<string, string>([
  ["access_denied", "Sign-in was cancelled."],
  ["provider_error", "This account can't sign in here. Use your company account."],
  ["invalid_state", "Sign-in expired. Please try again."],
  ["account_mismatch", "This account is linked to someone else. Sign out and try again."],
]);

type Props = { searchParams: Promise<{ error?: string | string[] }> };

export default async function LoginPage({ searchParams }: Props) {
  const session = await getMe().then(
    () => "signedIn" as const,
    (error) => (error instanceof NotSignedInError ? ("signedOut" as const) : ("unreachable" as const)),
  );
  if (session === "signedIn") redirect("/");

  const { error } = await searchParams;
  const errorMessage = typeof error === "string" ? SIGN_IN_ERRORS.get(error) : undefined;
  // null unless the backend runs with APP_ENV=development (lib/api/server.ts).
  const devUsers = session === "signedOut" ? await listDevUsers() : null;

  return (
    <PageContainer className="max-w-md">
      <div className="grid gap-6">
        {session === "unreachable" ? <ServerUnavailable /> : null}

        <Card>
          <CardHeader>
            <CardTitle>
              <h1 className="text-xl font-semibold tracking-tight">Sign in to Internal Brain</h1>
            </CardTitle>
            <CardDescription>
              Answers from your company&apos;s Slack and Drive, limited to what you can already see.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3">
            {errorMessage ? (
              <Alert variant="destructive">
                <CircleAlert aria-hidden="true" />
                <AlertDescription>{errorMessage}</AlertDescription>
              </Alert>
            ) : null}
            {/* Phase 7 turns this into a plain link to the backend's
                /connectors/drive/connect once the connectors branch merges. */}
            <Button size="lg" className="w-full" disabled aria-describedby="google-sign-in-note">
              Sign in with Google
            </Button>
            <p id="google-sign-in-note" className="text-xs text-muted-foreground">
              Google sign-in arrives with the connectors merge.
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
      </div>
    </PageContainer>
  );
}
