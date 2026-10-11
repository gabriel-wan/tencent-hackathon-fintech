import { cookies } from "next/headers";
import type { ReactNode } from "react";

import { AppSidebar } from "@/components/app-sidebar";
import { ChatSessionProvider } from "@/components/chat-session";
import { DevPersonaBanner } from "@/components/dev-persona-banner";
import { MeProvider } from "@/components/me-provider";
import { MockBadge } from "@/components/mock-badge";
import { isMockEnabled } from "@/lib/api/mock";
import { listDevUsers } from "@/lib/api/server";
import { SIDEBAR_COOKIE } from "@/lib/sidebar";
import type { Me } from "@/lib/api/types";

/**
 * The frame every signed-in page shares: the user, the development banner
 * (development only, full width above everything) and the sidebar. Used by the
 * (app) layout and by /connectors, which runs its own session check (see
 * app/connectors/page.tsx).
 */
export async function SignedInShell({ me, children }: { me: Me; children: ReactNode }) {
  // null unless the backend runs with APP_ENV=development (lib/api/server.ts).
  const devUsers = await listDevUsers();
  // Read here so the first paint is already right (no flash of the open sidebar).
  const collapsed = (await cookies()).get(SIDEBAR_COOKIE)?.value === "collapsed";
  return (
    <MeProvider me={me}>
      <ChatSessionProvider>
        {devUsers && devUsers.length > 0 ? <DevPersonaBanner users={devUsers} /> : null}
        {/* --dev-banner: the strip's height (36 px + its 1 px border) on desktop, so the sticky sidebar fits below it. */}
        <div
          className={`flex flex-1 flex-col md:flex-row ${devUsers && devUsers.length > 0 ? "md:[--dev-banner:calc(2.25rem+1px)]" : ""}`}
        >
          <AppSidebar initialCollapsed={collapsed} badge={isMockEnabled() ? <MockBadge /> : undefined} />
          <div className="flex min-w-0 flex-1 flex-col">{children}</div>
        </div>
      </ChatSessionProvider>
    </MeProvider>
  );
}
