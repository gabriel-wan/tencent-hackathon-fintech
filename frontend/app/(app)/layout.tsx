import { redirect, unstable_rethrow } from "next/navigation";
import { connection } from "next/server";
import type { ReactNode } from "react";

import { AppHeader } from "@/components/app-header";
import { DevPersonaBanner } from "@/components/dev-persona-banner";
import { MeProvider } from "@/components/me-provider";
import { MockBadge } from "@/components/mock-badge";
import { PageContainer } from "@/components/page-container";
import { ServerUnavailable } from "@/components/server-unavailable";
import { UserMenu } from "@/components/user-menu";
import { NotSignedInError } from "@/lib/api/errors";
import { getMe, listDevUsers } from "@/lib/api/server";
import type { Me } from "@/lib/api/types";

/**
 * Session gate for every signed-in page. Runs on the server for each request:
 * no session → /login; backend down → a "Can't reach the server" message.
 *
 * This is UX, not security: the backend checks the session on every API call
 * (SECURITY.md INV-3), so a page that slipped past this gate would still get
 * nothing. Done here rather than in Next.js middleware (renamed in Next 16).
 */
export default async function SignedInLayout({ children }: { children: ReactNode }) {
  // Per request, never prerendered: who is signed in differs for every visitor.
  await connection();
  let me: Me;
  try {
    me = await getMe();
  } catch (error) {
    unstable_rethrow(error); // let Next.js's own control-flow errors through
    if (error instanceof NotSignedInError) redirect("/login");
    console.error("Session check failed:", error);
    return (
      <>
        <AppHeader actions={<MockBadge />} />
        <PageContainer>
          <ServerUnavailable />
        </PageContainer>
      </>
    );
  }

  // null unless the backend runs with APP_ENV=development (lib/api/server.ts).
  const devUsers = await listDevUsers();

  return (
    <MeProvider me={me}>
      {devUsers && devUsers.length > 0 ? <DevPersonaBanner users={devUsers} /> : null}
      <AppHeader
        actions={
          <>
            <MockBadge />
            <UserMenu />
          </>
        }
      />
      {children}
    </MeProvider>
  );
}
