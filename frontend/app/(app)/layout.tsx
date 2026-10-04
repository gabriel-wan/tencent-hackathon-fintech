import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { AppHeader } from "@/components/app-header";
import { MeProvider } from "@/components/me-provider";
import { MockBadge } from "@/components/mock-badge";
import { PageContainer } from "@/components/page-container";
import { ServerUnavailable } from "@/components/server-unavailable";
import { NotSignedInError } from "@/lib/api/errors";
import { getMe } from "@/lib/api/server";
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
  let me: Me;
  try {
    me = await getMe();
  } catch (error) {
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

  return (
    <MeProvider me={me}>
      <AppHeader actions={<MockBadge />} />
      {children}
    </MeProvider>
  );
}
