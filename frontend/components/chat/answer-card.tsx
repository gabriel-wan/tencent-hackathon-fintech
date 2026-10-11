"use client";

import { Check, CircleAlert, Clock, Copy, EyeOff, RotateCcw, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useId, useState, type ReactNode } from "react";

import { InfoTip } from "@/components/info-tip";
import { useMe } from "@/components/me-provider";
import { StatusChip } from "@/components/status-chip";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { isMockResponse } from "@/lib/api/mock";
import type { QueryResponse } from "@/lib/api/types";
import { answerSummary, splitAnswer, stripCitationMarkers } from "@/lib/citations";
import { formatExact, formatRelative } from "@/lib/format";

import { CitationList } from "./citation-list";
import type { Exchange, FailureKind } from "./types";

const FAILURE_MESSAGES: Record<FailureKind, string> = {
  badInput: "This question couldn't be sent. Check its length and try again.",
  notConfigured: "The assistant isn't available right now.",
  unreachable: "Couldn't reach the server.",
  server: "Something went wrong on the server.",
};

/** Scrolls to source n of this answer, highlights it for a moment and moves focus to its link (or the row). */
function showSource(id: string) {
  const row = document.getElementById(id);
  if (!row) return;
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  row.scrollIntoView({ block: "nearest", behavior: reduceMotion ? "auto" : "smooth" });
  (row.querySelector<HTMLElement>("a") ?? row).focus({ preventScroll: true });
  row.dataset.flash = "";
  setTimeout(() => delete row.dataset.flash, 1500);
}

/**
 * Plain text only: the answer is derived from untrusted retrieved content. Its [S<n>] markers become numbered
 * chips that show that source in the list below; everything else stays a text node.
 */
function AnswerText({ response, sourceId }: { response: QueryResponse; sourceId: (n: number) => string }) {
  const { citations } = response;
  const parts = splitAnswer(response.answer, citations.map((c) => c.label));
  return (
    <TooltipProvider>
      <p className="leading-relaxed whitespace-pre-wrap">
        {parts.map((part, i) => {
          if (part.kind === "text") return part.text;
          const citation = citations[part.n - 1]!;
          return (
            <Tooltip key={i}>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  onClick={() => showSource(sourceId(part.n))}
                  aria-label={`Source ${part.n}: ${citation.title}`}
                  className="ml-0.5 inline-flex cursor-pointer h-[1.15rem] min-w-[1.15rem] items-center justify-center rounded bg-muted px-1 align-[0.1em] text-[0.7rem] font-medium text-muted-foreground tabular-nums transition-colors outline-none hover:bg-primary hover:text-primary-foreground focus-visible:ring-2 focus-visible:ring-ring active:bg-[color-mix(in_oklch,var(--primary),var(--foreground)_28%)]"
                >
                  {part.n}
                </button>
              </TooltipTrigger>
              <TooltipContent>{citation.title}</TooltipContent>
            </Tooltip>
          );
        })}
      </p>
    </TooltipProvider>
  );
}

/** Every reply sits beside the KnowBuddy icon (FRONTEND.md design principle 2), with no card around it. */
function AnswerFrame({ children, busy = false, label }: { children: ReactNode; busy?: boolean; label?: string }) {
  return (
    <article aria-label={label} aria-busy={busy || undefined} className="flex gap-3">
      <img src="/icon.svg" width={28} height={28} alt="" aria-hidden="true" className="mt-0.5 size-7 shrink-0" />
      <div className="grid min-w-0 flex-1 gap-3">{children}</div>
    </article>
  );
}

/**
 * The answer's audit record number. For admins, a link to that record (/admin/audit?record=N); others see
 * the number only (the audit trail is admin-only, and its API refuses anyone else anyway).
 */
function Reference({ response }: { response: QueryResponse }) {
  const me = useMe();
  const id = response.audit_id;
  return (
    <span className="text-xs text-muted-foreground tabular-nums">
      {isMockResponse(response) ? (
        "Ref # — (mock)"
      ) : me.is_admin ? (
        <Link href={`/admin/audit?record=${id}`} className="text-primary underline-offset-4 hover:underline">
          Ref #{id}
          <span className="sr-only"> (open its audit record)</span>
        </Link>
      ) : (
        `Ref #${id}`
      )}
    </span>
  );
}

/** One fact about the answer: a chip, and its explanation behind an ⓘ (hover, focus, tap). */
function Fact({ tone, icon, text, label, children }: {
  tone?: "neutral" | "danger";
  icon: ReactNode;
  text: ReactNode;
  label: string;
  children: ReactNode;
}) {
  return (
    <li className="inline-flex items-center gap-0.5">
      <StatusChip tone={tone}>
        {icon}
        {text}
      </StatusChip>
      <InfoTip label={label}>{children}</InfoTip>
    </li>
  );
}

/**
 * What was masked for you and how fresh the sources are, at a glance. Only on a real answer: a "not found"
 * reply must look the same whatever happened (INV-5).
 */
function TrustLine({ response }: { response: QueryResponse }) {
  const summary = answerSummary(response.citations);
  if (!summary.masked && !summary.oldestSync) return null;
  return (
    <ul aria-label="About this answer" className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
      {summary.masked ? (
        <Fact icon={<EyeOff aria-hidden="true" />} text={`${summary.masked.total} masked for you`} label="About masking">
          The Need-to-Know Shield hid these before the AI saw them: {summary.masked.text}. Each source below says
          which it masked.
        </Fact>
      ) : null}
      {summary.oldestSync ? (
        summary.stale ? (
          <Fact tone="danger" icon={<Clock aria-hidden="true" />} text="May be out of date" label="About freshness">
            The oldest source was last synced <SyncedWhen at={summary.oldestSync} />, more than 15 minutes ago.
          </Fact>
        ) : (
          <Fact icon={<Clock aria-hidden="true" />} text={<>Synced <SyncedWhen at={summary.oldestSync} /></>} label="About freshness">
            KnowBuddy re-reads the tools every 5 minutes. This is when its oldest source was last checked.
          </Fact>
        )
      ) : null}
    </ul>
  );
}

function SyncedWhen({ at }: { at: string }) {
  return (
    <time dateTime={at} title={formatExact(at)}>
      {formatRelative(at)}
    </time>
  );
}

function CopyButton({ text }: { text: string }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  async function copy() {
    try {
      // A browser can leave the promise waiting on a permission it never asks for: give up after 1.5 s.
      const timeout = new Promise<never>((_, reject) => setTimeout(() => reject(new Error("timeout")), 1500));
      await Promise.race([navigator.clipboard.writeText(text), timeout]);
      setState("copied");
    } catch {
      setState("failed"); // no clipboard on plain http, permission refused, or no reply
    }
    setTimeout(() => setState("idle"), 2000);
  }
  return (
    <Button variant="ghost" size="sm" onClick={copy} className="-ml-2.5 text-muted-foreground">
      {state === "copied" ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
      <span aria-live="polite">{state === "copied" ? "Copied" : state === "failed" ? "Couldn't copy" : "Copy"}</span>
    </Button>
  );
}

function RetryButton({ onRetry, disabled }: { onRetry: () => void; disabled: boolean }) {
  return (
    <Button variant="outline" size="sm" onClick={onRetry} disabled={disabled} className="justify-self-start">
      <RotateCcw aria-hidden="true" />
      Try again
    </Button>
  );
}

type Props = { exchange: Exchange; onRetry: () => void; retryDisabled: boolean };

export function AnswerCard({ exchange, onRetry, retryDisabled }: Props) {
  // Ids for this answer's sources, so its chips jump to its own list (several answers are on the page).
  const base = useId();
  const sourceId = (n: number) => `${base}-source-${n}`;
  switch (exchange.status) {
    case "pending":
      // A neutral indicator only: no invented progress steps (AGENTS.md §2.5).
      return (
        <AnswerFrame busy>
          <p className="text-sm text-muted-foreground">Searching your sources…</p>
          <Skeleton className="h-3 w-11/12" />
          <Skeleton className="h-3 w-8/12" />
        </AnswerFrame>
      );

    case "answered": {
      const text = stripCitationMarkers(exchange.response.answer);
      return (
        <AnswerFrame label="Answer">
          <AnswerText response={exchange.response} sourceId={sourceId} />
          <TrustLine response={exchange.response} />
          {exchange.response.citations.length > 0 ? (
            <CitationList citations={exchange.response.citations} sourceId={sourceId} />
          ) : (
            <p className="text-sm text-muted-foreground">No sources returned.</p>
          )}
          <div className="flex items-center justify-between gap-2">
            <CopyButton text={text} />
            <Reference response={exchange.response} />
          </div>
        </AnswerFrame>
      );
    }

    case "notFound":
      // Identical whether nothing exists or nothing is permitted (INV-5):
      // nothing here depends on why there was no answer.
      return (
        <AnswerFrame label="Answer">
          <p className="leading-relaxed text-muted-foreground">{exchange.response.answer}</p>
          <div className="flex justify-end">
            <Reference response={exchange.response} />
          </div>
        </AnswerFrame>
      );

    case "unavailable":
      return (
        <AnswerFrame>
          <Alert variant="warning">
            <TriangleAlert aria-hidden="true" />
            <AlertDescription>{exchange.response.answer}</AlertDescription>
          </Alert>
          <RetryButton onRetry={onRetry} disabled={retryDisabled} />
        </AnswerFrame>
      );

    case "failed":
      return (
        <AnswerFrame>
          <p className="flex items-center gap-2 text-sm text-destructive">
            <CircleAlert aria-hidden="true" className="size-4 shrink-0" />
            {FAILURE_MESSAGES[exchange.failure]}
          </p>
          <RetryButton onRetry={onRetry} disabled={retryDisabled} />
        </AnswerFrame>
      );
  }
}

/** The screen-reader announcement when a question finishes. */
export function announcementFor(exchange: Exchange): string {
  switch (exchange.status) {
    case "pending":
      return "";
    case "answered": {
      // Short on purpose: the answer itself is in the thread, and reading it
      // here too would repeat it when someone browses the page.
      const n = exchange.response.citations.length;
      return n === 0 ? "Answer received, with no sources." : `Answer received, with ${n} source${n === 1 ? "" : "s"}.`;
    }
    case "notFound":
    case "unavailable":
      return exchange.response.answer;
    case "failed":
      return FAILURE_MESSAGES[exchange.failure];
  }
}
