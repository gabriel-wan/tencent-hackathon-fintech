import type { Metadata } from "next";
import { connection } from "next/server";

import { BoundaryPreview } from "@/components/admin/boundary-preview";
import { DesignPreview } from "@/components/admin/design-preview";
import { NotBuiltYet } from "@/components/admin/not-built-yet";
import { PageContainer } from "@/components/page-container";
import { listDevUsers } from "@/lib/api/server";

export const metadata: Metadata = { title: "Boundary · KnowBuddy" };

// ADR-002: the admin chooses which channels and folders the assistant may use
// at all. Also where "Sync now" lives for the freshness demo (scenario 2).
export default async function BoundaryPage() {
  await connection(); // per request: it asks the backend, which is unreachable during `next build`
  // The design preview exists only while the backend is in development mode.
  const devMode = (await listDevUsers()) !== null;
  return (
    <PageContainer className="grid max-w-5xl content-start gap-6">
      <div className="grid gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Boundary</h1>
        <p className="text-muted-foreground">
          Which Slack channels and Drive folders the assistant may use. Content outside the boundary is never
          used, even for people who can see it in the source tool.
        </p>
      </div>
      <NotBuiltYet>
        <p>
          The boundary and sync API now exists (<code>GET /api/admin/scopes/{"{source}"}</code>,{" "}
          <code>GET /api/admin/boundary</code>, <code>PUT</code> and{" "}
          <code>DELETE /api/admin/boundary/{"{source}/{scope_id}"}</code>, <code>POST /api/admin/sync</code>);
          this page is being built on it.
        </p>
        <p>Until then, an admin sets the boundary through the backend&apos;s API docs (docs/connectors/GUIDE.md, section 7.5).</p>
      </NotBuiltYet>
      {devMode ? (
        <DesignPreview>
          <BoundaryPreview />
        </DesignPreview>
      ) : null}
    </PageContainer>
  );
}
