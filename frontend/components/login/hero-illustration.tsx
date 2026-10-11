import { ShieldCheck } from "lucide-react";

import { PlatformLogo } from "@/components/platform-logo";

/**
 * The sign-in page's picture: a small, made-up answer (fictional company, ADR-004), drawn with the
 * app's own colours so it follows light and dark mode. Decorative only: hidden from screen readers,
 * nothing in it is clickable, and it shows no real data.
 */
export function HeroIllustration() {
  return (
    <div aria-hidden="true" className="relative mx-auto w-full max-w-md select-none">
      <div className="rounded-2xl bg-card p-5 text-sm shadow-sm ring-1 ring-foreground/10">
        <div className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-3.5 py-2 text-primary-foreground">
          What&apos;s blocking the database migration?
        </div>

        <div className="mt-4 grid gap-2 leading-relaxed">
          <p>
            The cutover waits on the replica fix in MIG-12 <Cite n={1} />. On-call saw replication lag on Tuesday{" "}
            <Cite n={2} />.
          </p>
          <div className="h-2 w-4/5 rounded-full bg-muted" />
          <div className="h-2 w-3/5 rounded-full bg-muted" />
        </div>

        <ul className="mt-4 grid gap-2 border-t pt-4 text-xs">
          <Source n={1} source="jira" title="MIG-12 Replica fix" />
          <Source n={2} source="slack" title="#eng-db" masked />
          <Source n={3} source="confluence" title="Migration runbook" />
        </ul>
      </div>

      <div className="absolute -right-3 -bottom-5 grid size-14 place-items-center rounded-2xl bg-card shadow-sm ring-1 ring-foreground/10">
        <ShieldCheck className="size-7 text-brand-buddy" strokeWidth={1.75} />
      </div>
    </div>
  );
}

function Cite({ n }: { n: number }) {
  return (
    <span className="rounded bg-muted px-1 py-0.5 text-[0.7rem] font-medium text-muted-foreground">S{n}</span>
  );
}

function Source({ n, source, title, masked = false }: { n: number; source: string; title: string; masked?: boolean }) {
  return (
    <li className="flex items-center gap-2">
      <span className="w-5 text-muted-foreground">S{n}</span>
      <PlatformLogo source={source} size={14} />
      <span className="truncate">{title}</span>
      {masked ? (
        <span className="ml-auto rounded-full border border-success-foreground/30 bg-success px-2 py-0.5 text-success-foreground">
          2 masked
        </span>
      ) : null}
    </li>
  );
}
