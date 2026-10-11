"use client";

import { useEffect, useState } from "react";

import { useMe } from "@/components/me-provider";
import { Button } from "@/components/ui/button";
import { firstName } from "@/lib/people";

// Shown to every user, so they must stay generic: an example naming a real
// document (say, a specific incident report) would tell people without
// access that it exists (INV-5). Restricted questions are typed by hand in
// the demo.
const EXAMPLES = [
  "What were last week's blockers?",
  "Where can I find the on-call runbook?",
  "What follow-up tickets came out of the last incident?",
];

function partOfDay(hour: number): string {
  return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
}

/** Above the question box when the chat is empty: a greeting by first name and what KnowBuddy can do. */
export function Greeting() {
  const me = useMe();
  const name = firstName(me.name);
  // The time of day is the viewer's, known only in the browser (the server's clock is in another zone),
  // so the greeting appears once mounted rather than flashing a wrong one.
  const [hello, setHello] = useState<string | null>(null);
  useEffect(() => setHello(partOfDay(new Date().getHours())), []);
  return (
    <div className="grid justify-items-center gap-3 text-center">
      <img src="/icon.svg" width={48} height={48} alt="" aria-hidden="true" />
      <h2
        className={`min-h-9 text-3xl font-semibold tracking-tight transition-opacity duration-300 ${hello ? "opacity-100" : "opacity-0"}`}
      >
        {hello ? `${hello}${name ? `, ${name}` : ""}` : null}
      </h2>
      <p className="max-w-lg leading-relaxed text-muted-foreground">
        Ask about your company&apos;s Slack, Drive, Jira and Confluence. Answers use only what you already have access
        to, and every answer shows its sources.
      </p>
    </div>
  );
}

/** Under the question box when the chat is empty. Picking one fills the box; it doesn't send. */
export function Examples({ onPick }: { onPick: (question: string) => void }) {
  return (
    <div className="grid justify-items-center gap-2">
      <p className="text-sm text-muted-foreground">Try asking</p>
      <ul className="flex flex-wrap justify-center gap-2">
        {EXAMPLES.map((example) => (
          <li key={example}>
            <Button
              variant="outline"
              className="h-auto min-h-9 rounded-full px-3.5 py-1.5 text-left whitespace-normal"
              onClick={() => onPick(example)}
            >
              {example}
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
}
