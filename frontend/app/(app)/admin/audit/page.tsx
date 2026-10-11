import type { Metadata } from "next";

import { AuditTrail } from "@/components/admin/audit-trail";
import { PageContainer } from "@/components/page-container";
import { PageHeader } from "@/components/page-header";
import { filtersFromParams, recordFromParams } from "@/lib/audit";

export const metadata: Metadata = { title: "Audit trail · KnowBuddy" };

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> };

// Scenario 5: "show me everything user X accessed ... in the last 30 days".
// The filters and the open record live in the URL (/admin/audit?user=…&record=56), so a view or a
// record can be bookmarked or shared.
export default async function AuditPage({ searchParams }: Props) {
  const params = await searchParams;
  return (
    <PageContainer className="grid max-w-5xl content-start gap-6">
      <PageHeader
        title="Audit trail"
        description={
          <>
            Who asked what, which documents were allowed or denied and why, what was answered, and every admin
            change. The &quot;Ref #&quot; under each chat answer is its record number.
          </>
        }
      />
      <AuditTrail initialFilters={filtersFromParams(params)} initialRecordId={recordFromParams(params)} />
    </PageContainer>
  );
}
