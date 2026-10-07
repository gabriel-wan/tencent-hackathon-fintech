"use client";

import { ArrowUp } from "lucide-react";
import { forwardRef, useImperativeHandle, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

/** The backend's limit (backend/app/api/routes.py MAX_QUESTION_CHARS). */
export const MAX_QUESTION_CHARS = 2000;
const SHOW_COUNTER_FROM = 1800;

export type ComposerHandle = { focus: () => void; fill: (text: string) => void };

type Props = { sending: boolean; onSend: (question: string) => void };

/**
 * The question box. It stays editable while an answer is pending (so the
 * next question can be typed), but nothing is sent until the current one
 * finishes: one question at a time.
 */
export const Composer = forwardRef<ComposerHandle, Props>(function Composer({ sending, onSend }, ref) {
  const [text, setText] = useState("");
  const textarea = useRef<HTMLTextAreaElement>(null);

  useImperativeHandle(ref, () => ({
    focus: () => textarea.current?.focus(),
    fill: (value: string) => {
      setText(value);
      textarea.current?.focus();
    },
  }));

  const trimmed = text.trim();
  const tooLong = trimmed.length > MAX_QUESTION_CHARS;
  const canSend = !sending && trimmed.length > 0 && !tooLong;

  function submit(event?: FormEvent) {
    event?.preventDefault();
    if (!canSend) return;
    onSend(trimmed);
    setText("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter sends, Shift+Enter is a new line. While an input method editor is
    // composing (Chinese, Japanese, ...), Enter confirms the characters instead.
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-1.5">
      <label htmlFor="question" className="sr-only">
        Ask a question
      </label>
      <div className="flex items-end gap-2 rounded-xl border border-input bg-card p-2 focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50">
        <Textarea
          id="question"
          ref={textarea}
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask about your company's Slack and Drive…"
          rows={1}
          aria-invalid={tooLong || undefined}
          aria-describedby="question-hint"
          className="max-h-48 min-h-10 resize-none border-0 bg-transparent px-1.5 shadow-none focus-visible:ring-0 dark:bg-transparent"
        />
        <Button type="submit" size="icon" disabled={!canSend} aria-label="Send question">
          <ArrowUp aria-hidden="true" />
        </Button>
      </div>
      <p id="question-hint" className="flex justify-between gap-4 px-1 text-xs text-muted-foreground">
        <span>{sending ? "Waiting for the current answer…" : "Enter to send, Shift+Enter for a new line"}</span>
        {trimmed.length >= SHOW_COUNTER_FROM ? (
          <span className={tooLong ? "font-medium text-destructive" : undefined}>
            {trimmed.length.toLocaleString()} / {MAX_QUESTION_CHARS.toLocaleString()}
          </span>
        ) : null}
      </p>
    </form>
  );
});
