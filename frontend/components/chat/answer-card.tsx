import { CircleAlert, RotateCcw, TriangleAlert } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { isMockResponse } from "@/lib/api/mock";
import type { QueryResponse } from "@/lib/api/types";
import { stripCitationMarkers } from "@/lib/citations";

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

function Reference({ response }: { response: QueryResponse }) {
  return (
    <p className="text-right text-xs text-muted-foreground tabular-nums">
      {isMockResponse(response) ? "Ref # — (mock)" : `Ref #${response.audit_id}`}
    </p>
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
          {exchange.response.citations.length === 0 ? (
            <p className="text-sm text-muted-foreground">No sources returned.</p>
          ) : null}
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

/** Short text for the screen-reader announcement when an answer arrives. */
export function announcementFor(exchange: Exchange): string {
  switch (exchange.status) {
    case "pending":
      return "";
    case "answered":
      return `Answer: ${stripCitationMarkers(exchange.response.answer)}`;
    case "notFound":
    case "unavailable":
      return exchange.response.answer;
    case "failed":
      return FAILURE_MESSAGES[exchange.failure];
  }
}
