"use client";

import { ArrowUp, ListFilter, MessageSquareText, RotateCcw } from "lucide-react";
import { useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { Disclosure } from "@/components/disclosure";
import { InfoTip } from "@/components/info-tip";
import { StatusChip } from "@/components/status-chip";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { askAudit } from "@/lib/api/client";
import { isMockResponse } from "@/lib/api/mock";
import type { AskFacts, AskResponse } from "@/lib/api/types";
import { type AuditFilters, askFiltersToPage, browserTimeZone, coverageNote, eventLabel, filterChips } from "@/lib/audit";
import { splitAnswer } from "@/lib/citations";
import { cn } from "@/lib/utils";

// The audit assistant (ADR-013): the admin asks the trail in plain language. The backend turns the question into a
// search, counts the matches itself and has the LLM summarise the newest records, citing each one. This panel
// shows that answer, the counts, the search it ran (to open in the table below) and each cited record. Every
// question is itself recorded in the trail (audit_asked).

/** The backend's limit (backend/app/audit/api.py MAX_ASK_CHARS). */
const MAX_ASK_CHARS = 2000;

const EXAMPLES = [
  "Who was denied a document in the last 7 days?",
  "What changed in the boundary this month?",
  "Which questions had an instruction to the AI removed?",
];

type Exchange =
  | { id: number; question: string; status: "pending" }
  | { id: number; question: string; status: "done"; response: AskResponse }
  | { id: number; question: string; status: "failed"; message: string };

/** The answer text, its [S<n>] markers as chips that open the record they cite. Plain text only: never HTML. */
function AnswerText({ response, onOpenRecord }: { response: AskResponse; onOpenRecord: (id: number) => void }) {
  const parts = splitAnswer(response.answer, response.citations.map((c) => c.label));
  return (
    <TooltipProvider>
      <p className="leading-relaxed break-words whitespace-pre-wrap">
        {parts.map((part, i) => {
          if (part.kind === "text") return part.text;
          const id = response.citations[part.n - 1]!.record_id;
          return (
            <Tooltip key={i}>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  onClick={() => onOpenRecord(id)}
                  aria-label={`Open audit record #${id}`}
                  className="ml-0.5 inline-flex h-[1.15rem] min-w-[1.15rem] cursor-pointer items-center justify-center rounded bg-muted px-1 align-[0.1em] text-[0.7rem] font-medium text-muted-foreground tabular-nums transition-colors outline-none hover:bg-primary hover:text-primary-foreground focus-visible:ring-2 focus-visible:ring-ring"
                >
                  #{id}
                </button>
              </TooltipTrigger>
              <TooltipContent>Open audit record #{id}</TooltipContent>
            </Tooltip>
          );
        })}
      </p>
    </TooltipProvider>
  );
}

function count(n: number, one: string, many = `${one}s`): string {
  return `${n.toLocaleString()} ${n === 1 ? one : many}`;
}

/** The counts, computed by the backend over every match (never by the model). */
function FactsView({ facts }: { facts: AskFacts }) {
  const note = coverageNote(facts);
  const people = Object.entries(facts.by_user);
  const events = Object.entries(facts.by_event_type);
  return (
    <div className="grid gap-2 text-sm">
      <p className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-muted-foreground">
        <span className="font-medium text-foreground">{count(facts.matches, "matching record")}</span>
        {people.length ? <span>· {count(people.length, "person", "people")}</span> : null}
        {facts.documents_total ? <span>· {count(facts.documents_total, "document")}</span> : null}
        <InfoTip label="About these counts">
          Counted by KnowBuddy over every matching record, not by the AI. The summary above is written from the newest
          records and cites each one.
        </InfoTip>
      </p>
      {note ? <p className="text-xs text-muted-foreground">{note}</p> : null}
      {facts.matches ? (
        <Disclosure summary="Counts in detail">
          <div className="grid gap-3">
            <dl className="grid gap-1 text-sm sm:grid-cols-[auto_1fr] sm:gap-x-4">
              <dt className="text-muted-foreground">By person</dt>
              <dd>{people.map(([who, n]) => `${who} (${n})`).join(", ")}</dd>
              <dt className="text-muted-foreground">By event</dt>
              <dd>{events.map(([type, n]) => `${eventLabel(type)} (${n})`).join(", ")}</dd>
            </dl>
            {facts.documents.length ? (
              <div className="overflow-x-auto rounded-lg ring-1 ring-foreground/10">
                <Table className="min-w-[32rem]">
                  <TableHeader>
                    <TableRow>
                      <TableHead>Document</TableHead>
                      <TableHead className="text-right">Allowed</TableHead>
                      <TableHead className="text-right">Denied</TableHead>
                      <TableHead className="text-right">Restricted</TableHead>
                      <TableHead className="text-right">Sent</TableHead>
                      <TableHead className="text-right">Cited</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {facts.documents.map((d) => (
                      <TableRow key={d.document}>
                        <TableCell className="font-mono text-xs break-all">{d.document}</TableCell>
                        {[d.allowed, d.denied, d.restricted, d.sent, d.cited].map((n, i) => (
                          <TableCell key={i} className={cn("text-right tabular-nums", !n && "text-muted-foreground")}>
                            {n}
                          </TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            ) : null}
            {facts.documents_total > facts.documents.length ? (
              <p className="text-xs text-muted-foreground">
                The {facts.documents.length} documents in the most decisions, of {facts.documents_total}.
              </p>
            ) : null}
          </div>
        </Disclosure>
      ) : null}
    </div>
  );
}

function Reply({
  exchange,
  onOpenRecord,
  onOpenInTrail,
  onChoose,
  onRetry,
  busy,
}: {
  exchange: Exchange;
  onOpenRecord: (id: number) => void;
  onOpenInTrail: (filters: AuditFilters) => void;
  onChoose: (value: string, label: string) => void;
  onRetry: () => void;
  busy: boolean;
}) {
  if (exchange.status === "pending") {
    return (
      <div aria-busy="true" className="grid gap-2">
        <p className="text-sm text-muted-foreground">Searching the audit trail…</p>
        <Skeleton className="h-4 w-11/12" />
        <Skeleton className="h-4 w-2/3" />
      </div>
    );
  }
  if (exchange.status === "failed") {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <p role="alert" className="text-sm text-destructive">
          {exchange.message}
        </p>
        <Button variant="outline" size="sm" onClick={onRetry} disabled={busy}>
          <RotateCcw aria-hidden="true" />
          Try again
        </Button>
      </div>
    );
  }
  const { response } = exchange;
  const filters = askFiltersToPage(response.filters);
  const chips = filterChips(filters);
  return (
    <div className="grid min-w-0 gap-3">
      {response.status === "answered" ? (
        <AnswerText response={response} onOpenRecord={onOpenRecord} />
      ) : (
        <p className={cn("leading-relaxed", response.status === "unavailable" && "text-destructive")}>{response.answer}</p>
      )}
      {response.choices.length ? (
        <ul aria-label="Did you mean" className="flex flex-wrap gap-2">
          {response.choices.map((c) => (
            <li key={`${c.kind}:${c.source ?? ""}:${c.value}`}>
              <Button
                variant="outline"
                size="sm"
                disabled={busy}
                onClick={() => onChoose(c.value, c.label)}
                className="h-auto min-h-8 py-1.5 text-left whitespace-normal"
              >
                {c.label}
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
      {response.facts ? <FactsView facts={response.facts} /> : null}
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        {response.status !== "clarify" ? (
          <>
            <span className="inline-flex items-center gap-1">
              <ListFilter aria-hidden="true" className="size-3.5" />
              Searched:
            </span>
            {chips.length ? (
              chips.map((chip) => <StatusChip key={chip.key}>{chip.label}</StatusChip>)
            ) : (
              <span>the whole trail</span>
            )}
            <Button variant="outline" size="sm" className="ml-auto" onClick={() => onOpenInTrail(filters)}>
              Open in audit trail
            </Button>
          </>
        ) : null}
        <span className="tabular-nums">
          {isMockResponse(response) ? (
            "Ref # — (mock)"
          ) : (
            <button
              type="button"
              onClick={() => onOpenRecord(response.audit_id)}
              className="cursor-pointer text-primary underline-offset-4 hover:underline"
            >
              Ref #{response.audit_id}
              <span className="sr-only"> (open the record of this question)</span>
            </button>
          )}
        </span>
      </div>
    </div>
  );
}

export function AuditAsk({
  onOpenRecord,
  onOpenInTrail,
  describeError,
}: {
  onOpenRecord: (id: number) => void;
  onOpenInTrail: (filters: AuditFilters) => void;
  describeError: (error: unknown) => string;
}) {
  const [text, setText] = useState("");
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const nextId = useRef(1);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const busy = exchanges.some((e) => e.status === "pending");
  const trimmed = text.trim();
  const tooLong = trimmed.length > MAX_ASK_CHARS;

  async function ask(question: string, replaceId?: number) {
    const id = replaceId ?? nextId.current++;
    const pending: Exchange = { id, question, status: "pending" };
    setExchanges((list) => (replaceId ? list.map((e) => (e.id === id ? pending : e)) : [...list, pending]));
    let done: Exchange;
    try {
      done = { id, question, status: "done", response: await askAudit(question, browserTimeZone()) };
    } catch (error) {
      done = { id, question, status: "failed", message: describeError(error) };
    }
    setExchanges((list) => list.map((e) => (e.id === id ? done : e)));
  }

  function submit(event?: FormEvent) {
    event?.preventDefault();
    if (busy || !trimmed || tooLong) return;
    void ask(trimmed);
    setText("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter sends, Shift+Enter is a new line; Enter while an input method is composing confirms its characters.
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <section aria-labelledby="ask-heading" className="grid min-w-0 gap-4 rounded-xl bg-card p-4 ring-1 ring-foreground/10">
      <div className="flex items-center gap-3">
        <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-muted text-muted-foreground">
          <MessageSquareText aria-hidden="true" className="size-5" />
        </span>
        <div className="grid min-w-0 gap-0.5">
          <h2 id="ask-heading" className="flex items-center gap-1 text-sm font-semibold">
            Ask the audit trail
            <InfoTip label="About the audit assistant">
              The AI turns your question into a search. KnowBuddy runs the search in your company&apos;s trail and does
              the counting; the AI then summarises the newest matching records and cites each one. It never decides
              what you can see. Each question is recorded in the trail too.
            </InfoTip>
          </h2>
          <p className="text-sm text-muted-foreground">Ask who accessed what, when, and what was denied.</p>
        </div>
      </div>

      {exchanges.length ? (
        <ol aria-label="Questions to the audit assistant" aria-live="polite" className="grid gap-5">
          {exchanges.map((exchange) => (
            <li key={exchange.id} className="grid min-w-0 gap-3">
              <div className="ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-secondary px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap">
                <span className="sr-only">You asked: </span>
                {exchange.question}
              </div>
              <Reply
                exchange={exchange}
                busy={busy}
                onOpenRecord={onOpenRecord}
                onOpenInTrail={onOpenInTrail}
                onChoose={(value) => void ask(`${exchange.question} (I mean ${value})`)}
                onRetry={() => void ask(exchange.question, exchange.id)}
              />
            </li>
          ))}
        </ol>
      ) : (
        <ul aria-label="Example questions" className="flex flex-wrap gap-2">
          {EXAMPLES.map((example) => (
            <li key={example}>
              <Button
                variant="outline"
                size="sm"
                className="h-auto min-h-8 py-1.5 text-left whitespace-normal"
                onClick={() => {
                  setText(example);
                  textarea.current?.focus();
                }}
              >
                {example}
              </Button>
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={submit} className="grid gap-1.5">
        <label htmlFor="audit-question" className="sr-only">
          Ask the audit trail
        </label>
        <div className="flex items-end gap-2 rounded-2xl border border-input bg-background p-2 focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50">
          <Textarea
            id="audit-question"
            ref={textarea}
            value={text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={onKeyDown}
            placeholder="e.g. Show me everything ben@company.com accessed in the payment-gateway space in the last 30 days"
            rows={1}
            aria-invalid={tooLong || undefined}
            aria-describedby="audit-question-hint"
            className="max-h-40 min-h-10 resize-none border-0 bg-transparent px-2 shadow-none focus-visible:ring-0 dark:bg-transparent"
          />
          <Button
            type="submit"
            size="icon"
            disabled={busy || !trimmed || tooLong}
            aria-label="Ask"
            className="rounded-xl"
          >
            <ArrowUp aria-hidden="true" />
          </Button>
        </div>
        <p id="audit-question-hint" className="flex justify-between gap-4 px-1 text-xs text-muted-foreground">
          <span>{busy ? "Waiting for the current answer…" : "Enter to ask, Shift+Enter for a new line"}</span>
          {tooLong ? (
            <span className="font-medium text-destructive">
              {trimmed.length.toLocaleString()} / {MAX_ASK_CHARS.toLocaleString()}
            </span>
          ) : null}
        </p>
      </form>
    </section>
  );
}
