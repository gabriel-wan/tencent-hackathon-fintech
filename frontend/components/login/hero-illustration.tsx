"use client";

import { ShieldCheck } from "lucide-react";
import { useEffect, useState, type Ref } from "react";

import { PlatformLogo } from "@/components/platform-logo";
import { cn } from "@/lib/utils";

// The answer, in pieces: text, and the numbered source chips it cites (as in the chat).
const ANSWER: ({ text: string } | { cite: number })[] = [
  { text: "The cutover waits on the replica fix in MIG-7" },
  { cite: 1 },
  { text: ". On-call saw replication lag on Tuesday" },
  { cite: 2 },
  { text: "." },
];
const ANSWER_LENGTH = ANSWER.reduce((n, part) => n + ("text" in part ? part.text.length : 0), 0);
const TYPE_MS = 22; // per character
const START_MS = 600; // the question shows first

/**
 * The sign-in page's picture: a small, made-up answer (fictional company, ADR-004), drawn with the app's own
 * colours so it follows light and dark mode. On load it plays once: the question, the answer typing itself, the
 * sources popping in, the shield checking. It tilts toward the pointer with a soft highlight (usePointerMotion
 * writes the variables on `cardRef`). Decorative only: hidden from screen readers, nothing clickable, no real
 * data. For reduced motion it shows complete and still.
 */
export function HeroIllustration({ cardRef }: { cardRef?: Ref<HTMLDivElement> }) {
  const [typed, setTyped] = useState(0); // characters of the answer shown
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setTyped(ANSWER_LENGTH);
      return;
    }
    let shown = 0;
    let timer = window.setTimeout(function step() {
      shown += 1;
      setTyped(shown);
      if (shown < ANSWER_LENGTH) timer = window.setTimeout(step, TYPE_MS);
    }, START_MS);
    return () => window.clearTimeout(timer);
  }, []);
  const done = typed >= ANSWER_LENGTH;

  return (
    <div aria-hidden="true" className="relative mx-auto w-full max-w-md select-none [perspective:1000px]">
      <div
        ref={cardRef}
        className="group/card relative overflow-hidden rounded-2xl bg-card p-5 text-sm shadow-sm ring-1 ring-foreground/10 transition-transform duration-200 ease-out [transform:rotateX(var(--tilt-x,0deg))_rotateY(var(--tilt-y,0deg))] motion-reduce:transform-none"
      >
        {/* The highlight that follows the pointer over the card. */}
        <div className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover/card:opacity-100 [background:radial-gradient(260px_circle_at_var(--spot-x,50%)_var(--spot-y,50%),color-mix(in_oklch,var(--primary)_14%,transparent),transparent_70%)]" />

        <div className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-3.5 py-2 text-primary-foreground animate-[kb-rise_400ms_ease-out_both]">
          What&apos;s blocking the database migration?
        </div>

        <div className="mt-4 grid gap-2 leading-relaxed">
          {/* The full answer holds the space (invisible), so typing never moves the card. */}
          <p className="relative">
            <span className="invisible"><Answer upTo={ANSWER_LENGTH} /></span>
            <span className="absolute inset-0">
              <Answer upTo={typed} />
              {typed > 0 && !done ? <span className="ml-px inline-block h-3.5 w-0.5 animate-pulse bg-primary align-middle" /> : null}
            </span>
          </p>
          <div className={cn("h-2 w-4/5 rounded-full bg-muted transition-opacity duration-500", done ? "opacity-100" : "opacity-0")} />
          <div className={cn("h-2 w-3/5 rounded-full bg-muted transition-opacity duration-500 delay-100", done ? "opacity-100" : "opacity-0")} />
        </div>

        <ul className="mt-4 grid gap-2 border-t pt-4 text-xs">
          <Source n={1} source="jira" title="MIG-7 Ledger database migration" show={done} delay="delay-150" />
          <Source n={2} source="slack" title="#eng" masked show={done} delay="delay-300" />
          <Source n={3} source="confluence" title="Migration runbook" show={done} delay="delay-500" />
        </ul>
      </div>

      <div
        className={cn(
          "absolute -right-3 -bottom-5 grid size-14 place-items-center rounded-2xl bg-card shadow-sm ring-1 ring-foreground/10 transition-[opacity,transform] delay-700 duration-500 ease-out",
          done ? "scale-100 opacity-100" : "scale-75 opacity-0",
        )}
      >
        <ShieldCheck className="size-7 text-brand-buddy" strokeWidth={1.75} />
      </div>
    </div>
  );
}

/** The answer's first `upTo` characters, with each source chip once the text before it is typed. */
function Answer({ upTo }: { upTo: number }) {
  let left = upTo;
  return (
    <>
      {ANSWER.map((part, i) => {
        if ("cite" in part) return left > 0 || upTo >= ANSWER_LENGTH ? <Cite key={i} n={part.cite} /> : null;
        const shown = part.text.slice(0, Math.max(0, left));
        left -= part.text.length;
        return <span key={i}>{shown}</span>;
      })}
    </>
  );
}

function Cite({ n }: { n: number }) {
  return (
    <span className="ml-0.5 inline-flex h-[1.15rem] min-w-[1.15rem] items-center justify-center rounded bg-muted px-1 align-[0.1em] text-[0.7rem] font-medium text-muted-foreground">
      {n}
    </span>
  );
}

function Source({ n, source, title, masked = false, show, delay }: {
  n: number;
  source: string;
  title: string;
  masked?: boolean;
  show: boolean;
  delay: string;
}) {
  return (
    <li
      className={cn(
        "flex items-center gap-2 transition-[opacity,transform] duration-400 ease-out",
        delay,
        show ? "translate-y-0 opacity-100" : "translate-y-1 opacity-0",
      )}
    >
      <span className="w-4 text-muted-foreground tabular-nums">{n}</span>
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
