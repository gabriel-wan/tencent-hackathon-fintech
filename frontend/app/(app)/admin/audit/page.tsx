import type { Metadata } from "next";

import { PageContainer } from "@/components/page-container";

export const metadata: Metadata = { title: "Audit trail · Internal Brain" };

export default function AuditPage() {
  return (
    <PageContainer className="max-w-5xl">
      <h1 className="text-2xl font-semibold tracking-tight">Audit trail</h1>
    </PageContainer>
  );
}
