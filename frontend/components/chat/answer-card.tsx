import { CircleAlert, RotateCcw, ShieldCheck, TriangleAlert } from "lucide-react";
import Link from "next/link";

import { useMe } from "@/components/me-provider";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { isMockResponse } from "@/lib/api/mock";
import type { QueryResponse } from "@/lib/api/types";
import { stripCitationMarkers } from "@/lib/citations";

import { CitationList } from "./citation-list";
import type { Exchange, FailureKind } from "./types";

const FAILURE_MESSAGES: Record<FailureKind, string> = {
  badInput: "This question couldn't be sent. Check its length and try again.",
  notConfigured: "The assistant isn't available right now.",
  unreachable: "Couldn't reach the server.",
  server: "Something went wrong on the server.",
};

/** Plain text only: the answer is derived from untrusted retrieved content. */
function AnswerText({ text }: { text: string }) {
  return <p className="leading-relaxed whitespace-pre-wrap">{stripCitationMarkers(text)}</p>;
}

/**
 * The answer's audit record number. For admins, a link to that record (/admin/audit?record=N); others see
 * the number only (the audit trail is admin-only, and its API refuses anyone else anyway).
 */
function Reference({ response }: { response: QueryResponse }) {
  const me = useMe();
  const id = response.audit_id;
  return (
    <p className="text-right text-xs text-muted-foreground tabular-nums">
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
    </p>
  );
}

/**
 * Lines written to the AI in the sources were removed before it answered (ADR-011, `instructions_removed`).
 * Only on a real answer: a "not found" reply must look the same whatever was sent (INV-5). Not which
 * source or what text: the API deliberately doesn't say; admins see it in the audit record.
 */
function InjectionNotice({ removed }: { removed: number }) {
  if (removed <= 0) return null;
  return (
    <Alert>
      <ShieldCheck aria-hidden="true" />
      <AlertTitle>KnowBuddy ignored instructions hidden in the sources</AlertTitle>
      <AlertDescription>
        {removed === 1 ? "A line" : `${removed} lines`} written to the AI rather than to people{" "}
        {removed === 1 ? "was" : "were"} removed before the answer was written. The answer above doesn&apos;t
        follow {removed === 1 ? "it" : "them"}.
      </AlertDescription>
    </Alert>
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
  switch (exchange.status) {
    case "pending":
      // A neutral indicator only: no invented progress steps (AGENTS.md §2.5).
      return (
        <div aria-busy="true" className="grid gap-3 rounded-xl border bg-card p-4">
          <p className="text-sm text-muted-foreground">Searching your sources…</p>
          <Skeleton className="h-3 w-11/12" />
          <Skeleton className="h-3 w-8/12" />
        </div>
      );

    case "answered":
      return (
        <article aria-label="Answer" className="grid gap-4 rounded-xl border bg-card p-4">
          <AnswerText text={exchange.response.answer} />
          <InjectionNotice removed={exchange.response.instructions_removed} />
          {exchange.response.citations.length > 0 ? (
            <CitationList citations={exchange.response.citations} />
          ) : (
            <p className="text-sm text-muted-foreground">No sources returned.</p>
          )}
          <Reference response={exchange.response} />
        </article>
      );

    case "notFound":
      // Identical whether nothing exists or nothing is permitted (INV-5):
      // nothing here depends on why there was no answer.
      return (
        <article aria-label="Answer" className="grid gap-4 rounded-xl border bg-card p-4">
          <p className="leading-relaxed text-muted-foreground">{exchange.response.answer}</p>
          <Reference response={exchange.response} />
        </article>
      );

    case "unavailable":
      return (
        <div className="grid gap-3">
          <Alert variant="warning">
            <TriangleAlert aria-hidden="true" />
            <AlertDescription>{exchange.response.answer}</AlertDescription>
          </Alert>
          <RetryButton onRetry={onRetry} disabled={retryDisabled} />
        </div>
      );

    case "failed":
      return (
        <div className="grid gap-3">
          <p className="flex items-center gap-2 text-sm text-destructive">
            <CircleAlert aria-hidden="true" className="size-4 shrink-0" />
            {FAILURE_MESSAGES[exchange.failure]}
          </p>
          <RetryButton onRetry={onRetry} disabled={retryDisabled} />
        </div>
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
