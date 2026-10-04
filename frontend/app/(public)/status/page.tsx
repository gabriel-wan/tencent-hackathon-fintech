import type { Metadata } from "next";
import { connection } from "next/server";

import { PageContainer } from "@/components/page-container";

export const metadata: Metadata = { title: "Status · Internal Brain" };

type Health = { db?: string; pgvector?: string | null };

async function getHealth(): Promise<{ reachable: boolean; status?: number; body?: Health }> {
  try {
    const res = await fetch(`${process.env.BACKEND_URL}/health`, { cache: "no-store" });
    return { reachable: true, status: res.status, body: await res.json() };
  } catch {
    return { reachable: false };
  }
}

// For developers checking the stack: the backend's /health, fetched server-side.
export default async function StatusPage() {
  await connection(); // render per request: the backend is unreachable during `next build`
  const health = await getHealth();
  const rows: [string, string][] = health.reachable
    ? [
        ["Backend", `reachable (HTTP ${health.status})`],
        ["Database", health.body?.db ?? "unknown"],
        ["pgvector", health.body?.pgvector ?? "not installed"],
      ]
    : [["Backend", "unreachable"]];

  return (
    <PageContainer>
      <h1 className="text-2xl font-semibold tracking-tight">Status</h1>
      <p className="mt-2 text-muted-foreground">Backend health, checked when this page loads.</p>
      <dl className="mt-6 divide-y rounded-lg border bg-card">
        {rows.map(([label, value]) => (
          <div key={label} className="flex justify-between gap-4 px-4 py-3 text-sm">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="font-medium tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>
    </PageContainer>
  );
}
