import type { Metadata } from "next";

import { BoundaryEditor } from "@/components/admin/boundary-editor";
import { PageContainer } from "@/components/page-container";
import { PageHeader } from "@/components/page-header";

export const metadata: Metadata = { title: "Boundary · KnowBuddy" };

// ADR-002: the admin chooses which channels, folders, projects and spaces
// KnowBuddy may read at all. Also where "Sync now" lives for the freshness demo
// (scenario 2).
export default function BoundaryPage() {
  return (
    <PageContainer className="grid max-w-5xl content-start gap-6">
      <PageHeader
        title="Boundary"
        description="Which channels, folders, projects and spaces KnowBuddy may read. Content outside the boundary is never used, even for people who can see it in the tool."
      />
      <BoundaryEditor />
    </PageContainer>
  );
}
