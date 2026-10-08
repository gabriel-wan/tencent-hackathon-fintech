import type { ReactNode } from "react";

import { AppHeader } from "@/components/app-header";
import { MockBadge } from "@/components/mock-badge";

// Pages that work without a session: /login and /status.
export default function PublicLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <AppHeader actions={<MockBadge />} />
      {children}
    </>
  );
}
