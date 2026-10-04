"use client";

import { useRef, useState } from "react";

import { classifyAnswer } from "@/lib/answers";
import { askQuestion } from "@/lib/api/client";
import { ApiError, BackendUnreachableError, NotSignedInError } from "@/lib/api/errors";

import { announcementFor } from "./answer-card";
import { Composer, type ComposerHandle } from "./composer";
import { ExchangeView } from "./exchange-view";
import type { Exchange, FailureKind } from "./types";

function failureOf(error: unknown): FailureKind {
  if (error instanceof BackendUnreachableError) return "unreachable";
  if (error instanceof ApiError && error.status === 422) return "badInput";
  if (error instanceof ApiError && error.status === 503) return "notConfigured";
  return "server";
}

/**
 * The chat. Each question is answered on its own: the backend receives only
 * {question}, never earlier questions or answers, so history lives only here,
 * in memory, for this page load.
 */
export function ChatPanel() {
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [sending, setSending] = useState(false);
  // Screen readers hear only the newest result, not the whole thread again.
  const [announcement, setAnnouncement] = useState("");
  const composer = useRef<ComposerHandle>(null);

  function put(next: Exchange) {
    setExchanges((all) => all.map((e) => (e.id === next.id ? next : e)));
  }

  async function ask(id: string, question: string) {
    setSending(true);
    setAnnouncement("");
    let result: Exchange;
    try {
      const response = await askQuestion(question);
      result = { id, question, status: classifyAnswer(response), response };
    } catch (error) {
      if (error instanceof NotSignedInError) {
        // Session expired: start again from sign-in. The draft is not kept,
        // since the next person to sign in on this browser could see it.
        window.location.assign("/login");
        return;
      }
      result = { id, question, status: "failed", failure: failureOf(error) };
    }
    put(result);
    setAnnouncement(announcementFor(result));
    setSending(false);
    composer.current?.focus();
  }

  function send(question: string) {
    const id = crypto.randomUUID();
    setExchanges((all) => [...all, { id, question, status: "pending" }]);
    void ask(id, question);
  }

  /** "Try again": the same question, in place. */
  function retry(exchange: Exchange) {
    if (sending) return;
    put({ id: exchange.id, question: exchange.question, status: "pending" });
    void ask(exchange.id, exchange.question);
  }

  return (
    <div className="mx-auto flex w-full max-w-[760px] flex-1 flex-col px-4">
      <ol aria-label="Conversation" className="grid flex-1 content-start gap-6 py-8">
        {exchanges.map((exchange) => (
          <ExchangeView
            key={exchange.id}
            exchange={exchange}
            onRetry={() => retry(exchange)}
            retryDisabled={sending}
          />
        ))}
      </ol>
      <div aria-live="polite" className="sr-only">
        {announcement}
      </div>
      <div className="sticky bottom-0 bg-background pt-2 pb-4">
        <Composer ref={composer} sending={sending} onSend={send} />
      </div>
    </div>
  );
}
