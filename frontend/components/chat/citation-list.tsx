import { BookOpen, ExternalLink, FileText, Link2, MessageSquare, SquareKanban, type LucideIcon } from "lucide-react";

import type { Citation } from "@/lib/api/types";
import { safeHttpUrl } from "@/lib/citations";
import { formatExact, formatRelative } from "@/lib/format";

// Generic icons only, never brand logos; the text label carries the meaning.
const SOURCES: Record<string, { label: string; Icon: LucideIcon }> = {
  slack: { label: "Slack", Icon: MessageSquare },
  drive: { label: "Drive", Icon: FileText },
  jira: { label: "Jira", Icon: SquareKanban },
  confluence: { label: "Confluence", Icon: BookOpen },
};

function SourceBadge({ source }: { source: string }) {
  const { label, Icon } = SOURCES[source] ?? { label: source, Icon: Link2 };
  return (
    <span className="inline-flex shrink-0 items-center gap-1 rounded-md border bg-secondary px-1.5 py-0.5 text-xs font-medium text-secondary-foreground">
      <Icon aria-hidden="true" className="size-3" />
      {label}
    </span>
  );
}

function CitationItem({ citation }: { citation: Citation }) {
  // Source URLs are untrusted: only absolute http(s) URLs become links.
  const href = safeHttpUrl(citation.url);
  const exact = formatExact(citation.updated_at);
  return (
    <li className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm">
      <SourceBadge source={citation.source} />
      {href ? (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex min-w-0 items-center gap-1 font-medium text-primary underline-offset-4 hover:underline"
        >
          <span className="break-words">{citation.title}</span>
          <ExternalLink aria-hidden="true" className="size-3 shrink-0" />
          <span className="sr-only">(opens in a new tab)</span>
        </a>
      ) : (
        <span className="font-medium break-words">{citation.title}</span>
      )}
      <span className="text-xs text-muted-foreground">
        updated{" "}
        <time dateTime={citation.updated_at} title={exact}>
          {formatRelative(citation.updated_at)}
        </time>
        <span className="sr-only"> ({exact})</span>
      </span>
    </li>
  );
}

/** The sources an answer was built from, in the order the answer first cites them. */
export function CitationList({ citations }: { citations: Citation[] }) {
  return (
    <section aria-label="Sources" className="grid gap-2 border-t pt-3">
      <h2 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Sources</h2>
      <ul className="grid gap-2">
        {citations.map((citation) => (
          <CitationItem key={citation.id} citation={citation} />
        ))}
      </ul>
    </section>
  );
}
