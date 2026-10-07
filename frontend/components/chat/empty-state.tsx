import { Button } from "@/components/ui/button";

// Shown to every user, so they must stay generic: an example naming a real
// document (say, a specific incident report) would tell people without
// access that it exists (INV-5). Restricted questions are typed by hand in
// the demo.
const EXAMPLES = [
  "What were last week's blockers?",
  "Where can I find the on-call runbook?",
  "What follow-up tickets came out of the last incident?",
];

export function EmptyState({ onPick }: { onPick: (question: string) => void }) {
  return (
    <div className="grid gap-6 py-10">
      <div className="grid gap-2">
        <h2 className="text-2xl font-semibold tracking-tight">What do you need to know?</h2>
        <p className="leading-relaxed text-muted-foreground">
          Ask about your company&apos;s Slack, Drive, Jira and Confluence. Answers use only what you already have access to,
          and every answer shows its sources.
        </p>
      </div>
      <div className="grid gap-2">
        <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Try asking</p>
        <ul className="flex flex-wrap gap-2">
          {EXAMPLES.map((example) => (
            <li key={example}>
              <Button
                variant="outline"
                className="h-auto min-h-11 px-3 py-2 text-left whitespace-normal"
                onClick={() => onPick(example)}
              >
                {example}
              </Button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
