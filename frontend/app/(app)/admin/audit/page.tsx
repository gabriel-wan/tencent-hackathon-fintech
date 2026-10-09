import type { Metadata } from "next";

import { AuditTrail } from "@/components/admin/audit-trail";
import { PageContainer } from "@/components/page-container";
import { filtersFromParams } from "@/lib/audit";

export const metadata: Metadata = { title: "Audit trail · KnowBuddy" };

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> };

// Scenario 5: "show me everything user X accessed ... in the last 30 days".
// The filters live in the URL (/admin/audit?user=…&from=…), so a view can be bookmarked or shared.
export default async function AuditPage({ searchParams }: Props) {
  const filters = filtersFromParams(await searchParams);
  return (
    <PageContainer className="grid max-w-5xl content-start gap-6">
      <div className="grid gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Audit trail</h1>
        <p className="text-muted-foreground">
          Who asked what, which documents were allowed or denied and why, what was answered, and every admin change.
          The &quot;Ref #&quot; under each chat answer is its record number.
        </p>
      </div>
      <AuditTrail initialFilters={filters} />
    </PageContainer>
  );
}
