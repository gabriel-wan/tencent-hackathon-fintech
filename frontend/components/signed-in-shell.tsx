import type { ReactNode } from "react";

import { AppHeader } from "@/components/app-header";
import { DevPersonaBanner } from "@/components/dev-persona-banner";
import { MainNav } from "@/components/main-nav";
import { MeProvider } from "@/components/me-provider";
import { MockBadge } from "@/components/mock-badge";
import { UserMenu } from "@/components/user-menu";
import { listDevUsers } from "@/lib/api/server";
import type { Me } from "@/lib/api/types";

/**
 * The frame every signed-in page shares: the user, the development banner
 * (development only) and the header. Used by the (app) layout and by
 * /connectors, which runs its own session check (see app/connectors/page.tsx).
 */
export async function SignedInShell({ me, children }: { me: Me; children: ReactNode }) {
  // null unless the backend runs with APP_ENV=development (lib/api/server.ts).
  const devUsers = await listDevUsers();
  return (
    <MeProvider me={me}>
      {devUsers && devUsers.length > 0 ? <DevPersonaBanner users={devUsers} /> : null}
      <AppHeader
        nav={<MainNav />}
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
