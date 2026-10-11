import { BookOpen, ExternalLink, FileText, Link2, MessageSquare, SquareKanban, type LucideIcon } from "lucide-react";

import { PlatformLogo } from "@/components/platform-logo";
import { StatusChip } from "@/components/status-chip";
import type { Citation } from "@/lib/api/types";
import { freshness, safeHttpUrl } from "@/lib/citations";
import { formatExact, formatRelative } from "@/lib/format";

// Each tool's logo, with a generic icon if it can't load; the text label always carries the meaning.
const SOURCES: Record<string, { label: string; Icon: LucideIcon }> = {
  slack: { label: "Slack", Icon: MessageSquare },
  drive: { label: "Drive", Icon: FileText },
  jira: { label: "Jira", Icon: SquareKanban },
  confluence: { label: "Confluence", Icon: BookOpen },
};

function SourceBadge({ source }: { source: string }) {
  const { label, Icon } = SOURCES[source] ?? { label: source, Icon: Link2 };
  return (
    <StatusChip>
      <PlatformLogo source={source} size={12} fallback={<Icon aria-hidden="true" className="size-3" />} />
      {label}
    </StatusChip>
  );
}

/** " · synced 3 minutes ago": when our copy was last checked against the tool. Nothing for never-synced data. */
function Synced({ syncedAt }: { syncedAt: string | null }) {
  const fresh = freshness(syncedAt);
  if (!fresh || !syncedAt) return null;
  const when = (
    <time dateTime={syncedAt} title={formatExact(syncedAt)}>
      {formatRelative(syncedAt)}
    </time>
  );
  return fresh.stale ? (
    <span className="text-destructive">
      {" "}
      · synced {when}, may be out of date
    </span>
  ) : (
    <span> · synced {when}</span>
  );
}

function CitationItem({ citation, n, id }: { citation: Citation; n: number; id: string }) {
  // Source URLs are untrusted: only absolute http(s) URLs become links.
  const href = safeHttpUrl(citation.url);
  const exact = formatExact(citation.updated_at);
  return (
    // data-flash: set for a moment when its chip in the answer is pressed (answer-card.tsx showSource).
    <li
      id={id}
      tabIndex={-1}
      className="-mx-2 flex scroll-mt-24 scroll-mb-40 flex-wrap items-baseline gap-x-2 gap-y-1 rounded-md px-2 py-1 text-sm outline-none transition-colors duration-500 data-flash:bg-primary/15"
    >
      <span aria-hidden="true" className="w-4 shrink-0 text-xs font-medium text-muted-foreground tabular-nums">
        {n}
      </span>
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
        {/* title: exact time on hover; assistive tech also reads it as the name. */}
        <time dateTime={citation.updated_at} title={exact}>
          {formatRelative(citation.updated_at)}
        </time>
        <Synced syncedAt={citation.synced_at} />
      </span>
    </li>
  );
}

/** The sources an answer was built from, in the order the answer first cites them. */
export function CitationList({ citations, sourceId }: { citations: Citation[]; sourceId: (n: number) => string }) {
  return (
    // A plain group, not a landmark: every answer has one, and a page of
    // identical "Sources" landmarks is noise. The heading still lets screen
    // reader users jump between them.
    <div className="grid gap-2 border-t pt-3">
      <h2 className="text-sm font-medium text-muted-foreground">Sources</h2>
      <ol className="grid gap-1">
        {citations.map((citation, i) => (
          <CitationItem key={citation.id} citation={citation} n={i + 1} id={sourceId(i + 1)} />
        ))}
      </ol>
    </div>
  );
}
