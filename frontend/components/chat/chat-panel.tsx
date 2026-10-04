"use client";

import { useEffect, useRef, useState } from "react";

import { classifyAnswer } from "@/lib/answers";
import { askQuestion } from "@/lib/api/client";
import { ApiError, BackendUnreachableError, NotSignedInError } from "@/lib/api/errors";

import { announcementFor } from "./answer-card";
import { Composer, type ComposerHandle } from "./composer";
import { EmptyState } from "./empty-state";
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

  // Follow new answers unless the reader has scrolled up to an older one.
  const bottom = useRef<HTMLDivElement>(null);
  const followNewest = useRef(true);
  useEffect(() => {
    const onScroll = () => {
      const distanceFromEnd = document.documentElement.scrollHeight - (window.scrollY + window.innerHeight);
      followNewest.current = distanceFromEnd < 160;
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  useEffect(() => {
    if (!followNewest.current || exchanges.length === 0) return;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    bottom.current?.scrollIntoView({ block: "end", behavior: reduceMotion ? "auto" : "smooth" });
  }, [exchanges]);

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
    followNewest.current = true; // sending always brings the new question into view
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
      {exchanges.length === 0 ? (
        // Fills the composer; does not send, so the question can be edited first.
        <div className="flex-1">
          <EmptyState onPick={(question) => composer.current?.fill(question)} />
        </div>
      ) : (
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
      )}
      {/* Scroll target; the margin keeps the newest answer clear of the sticky composer. */}
      <div ref={bottom} aria-hidden="true" className="scroll-mb-40" />
      <div aria-live="polite" className="sr-only">
        {announcement}
      </div>
      <div className="sticky bottom-0 bg-background pt-2 pb-4">
        <Composer ref={composer} sending={sending} onSend={send} />
      </div>
    </div>
  );
}
