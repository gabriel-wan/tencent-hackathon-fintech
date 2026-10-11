import type { Metadata } from "next";
import { connection } from "next/server";

import { PageContainer } from "@/components/page-container";
import { PageHeader } from "@/components/page-header";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Status · KnowBuddy" };

type Health = { db?: string; pgvector?: string | null };

async function getHealth(): Promise<{ reachable: boolean; status?: number; body?: Health }> {
  try {
    const res = await fetch(`${process.env.BACKEND_SERVER_URL}/health`, { cache: "no-store" });
    return { reachable: true, status: res.status, body: await res.json() };
  } catch {
    return { reachable: false };
  }
}

// For developers checking the stack: the backend's /health, fetched server-side.
export default async function StatusPage() {
  await connection(); // render per request: the backend is unreachable during `next build`
  const health = await getHealth();
  // [label, value, healthy?]. null: information only (the pgvector version).
  const rows: [string, string, boolean | null][] = health.reachable
    ? [
        ["Backend", `reachable (HTTP ${health.status})`, health.status === 200],
        ["Database", health.body?.db ?? "unknown", health.body?.db === "ok"],
        ["pgvector", health.body?.pgvector ?? "not installed", health.body?.pgvector ? null : false],
      ]
    : [["Backend", "unreachable", false]];

  return (
    <PageContainer className="grid content-start gap-6">
      <PageHeader title="Status" description="Backend health, checked when this page loads." />
      <dl className="divide-y rounded-lg border bg-card">
        {rows.map(([label, value, healthy]) => (
          <div key={label} className="flex justify-between gap-4 px-4 py-3 text-sm">
            <dt className="text-muted-foreground">{label}</dt>
            {/* The value stays plain text inside <dd>: the deploy's live check reads
                "Database</dt><dd …>ok</dd>" (.github/workflows/deploy.yml). The dot is CSS only. */}
            <dd
              className={cn(
                "font-medium tabular-nums",
                healthy !== null &&
                  "before:mr-2 before:inline-block before:size-2 before:rounded-full before:align-middle before:content-['']",
                healthy === true && "text-success-foreground before:bg-success-foreground",
                healthy === false && "text-destructive before:bg-destructive",
              )}
            >
              {value}
            </dd>
          </div>
        ))}
      </dl>
    </PageContainer>
  );
}
