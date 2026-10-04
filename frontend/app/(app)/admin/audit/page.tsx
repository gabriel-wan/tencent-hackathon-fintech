import type { Metadata } from "next";

import { AuditPreview } from "@/components/admin/audit-preview";
import { DesignPreview } from "@/components/admin/design-preview";
import { NotBuiltYet } from "@/components/admin/not-built-yet";
import { PageContainer } from "@/components/page-container";
import { listDevUsers } from "@/lib/api/server";

export const metadata: Metadata = { title: "Audit trail · Internal Brain" };

// Scenario 5: "show me everything user X accessed ... in the last 30 days".
export default async function AuditPage() {
  // The design preview exists only while the backend is in development mode.
  const devMode = (await listDevUsers()) !== null;
  return (
    <PageContainer className="grid max-w-5xl content-start gap-6">
      <div className="grid gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Audit trail</h1>
        <p className="text-muted-foreground">
          Who asked what, which documents were allowed or denied and why, and what was answered.
        </p>
      </div>
      <NotBuiltYet>
        <p>
          This page waits for the audit API: <code>GET /api/admin/audit</code> (search) and{" "}
          <code>POST /api/admin/audit/verify</code> (hash chain), roadmap Task 3, 5–6 Oct.
        </p>
        <p>Every question is already recorded; the &quot;Ref #&quot; under each chat answer is its record number.</p>
      </NotBuiltYet>
      {devMode ? (
        <DesignPreview>
          <AuditPreview />
        </DesignPreview>
      ) : null}
    </PageContainer>
  );
}
