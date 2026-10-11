// Helpers for the untrusted parts of an answer: its text and its source links,
// plus what each source says about masking (ADR-010) and freshness (ADR-005).
import { STALE_AFTER_MS } from "@/lib/boundary";

// Matches the backend's citation labels (backend/app/llm/grounding.py LABEL_RE),
// including runs like "[S1][S2]" and the space before them.
const MARKERS = /[ \t]*(?:\[S\d+\])+/g;

/** Removes [S1]-style markers: for copying the answer as plain text. */
export function stripCitationMarkers(text: string): string {
  return text
    .replace(MARKERS, "")
    .replace(/[ \t]{2,}/g, " ")
    .trim();
}

/**
 * The URL if it is an absolute http(s) URL, otherwise null. Source URLs come
 * from source systems and could hold javascript:, data: or other schemes, so
 * only http(s) is ever rendered as a link.
 */
export function safeHttpUrl(url: string): string | null {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : null;
  } catch {
    return null; // relative or malformed
  }
}

/**
 * What the Need-to-Know Shield masked in one source for this reader (`redacted`, ADR-010): the total and
 * "card 1, phone 2", or null when nothing was. A handler sees the item unmasked, so gets null.
 */
export function maskedSummary(redacted: Record<string, number> | undefined): { total: number; text: string } | null {
  const kinds = Object.entries(redacted ?? {})
    .filter(([, n]) => n > 0)
    .sort(([a], [b]) => a.localeCompare(b));
  const total = kinds.reduce((sum, [, n]) => sum + n, 0);
  return total ? { total, text: kinds.map(([kind, n]) => `${kind} ${n}`).join(", ") } : null;
}

/**
 * How current our copy of a source is (`synced_at`: its scope's last complete sync). Null when it has never
 * synced (e.g. seeded demo data): nothing pretends it was. Stale after three missed 5-minute syncs.
 */
export function freshness(syncedAt: string | null | undefined, now: number = Date.now()): { stale: boolean } | null {
  if (!syncedAt) return null;
  const at = Date.parse(syncedAt);
  if (Number.isNaN(at)) return null;
  return { stale: now - at > STALE_AFTER_MS };
}

/**
 * The freshness chip under an answer: the oldest sync (the answer is only as fresh as its stalest source). `oldestSync` is null when no source has
 * synced (seeded data), so nothing pretends it was.
 */
export function answerSummary(
  citations: { synced_at?: string | null }[],
  now: number = Date.now(),
): { oldestSync: string | null; stale: boolean } {
  const synced = citations
    .map((c) => c.synced_at)
    .filter((s): s is string => !!s && !Number.isNaN(Date.parse(s)))
    .sort((a, b) => Date.parse(a) - Date.parse(b));
  const oldestSync = synced[0] ?? null;
  return { oldestSync, stale: freshness(oldestSync, now)?.stale ?? false };
}

export type AnswerPart = { kind: "text"; text: string } | { kind: "cite"; n: number };

/**
 * The answer split into plain text and source markers, for display. Each citation carries the label that cites
 * it (`label`, per answer), and is shown as number n = its place in the Sources list (1, 2, …), so the chips and
 * the list always agree whatever order the backend lists them in. A marker whose label no citation has is dropped
 * (the backend already removes invented ones). Text stays text: nothing here is ever HTML.
 */
export function splitAnswer(text: string, labels: string[]): AnswerPart[] {
  const number = new Map(labels.map((label, i) => [label, i + 1]));
  const parts: AnswerPart[] = [];
  const pushText = (t: string) => {
    if (!t) return;
    const last = parts[parts.length - 1];
    if (last?.kind === "text") last.text += t;
    else parts.push({ kind: "text", text: t });
  };
  let at = 0;
  for (const match of text.matchAll(MARKERS)) {
    pushText(text.slice(at, match.index));
    for (const [, label] of match[0].matchAll(/\[(S\d+)\]/g)) {
      const n = number.get(label!);
      if (n !== undefined && !parts.some((p, i) => i === parts.length - 1 && p.kind === "cite" && p.n === n)) {
        parts.push({ kind: "cite", n });
      }
    }
    at = match.index! + match[0].length;
  }
  pushText(text.slice(at));
  if (parts[0]?.kind === "text") parts[0].text = parts[0].text.trimStart();
  const end = parts[parts.length - 1];
  if (end?.kind === "text") end.text = end.text.trimEnd();
  return parts.filter((p) => p.kind === "cite" || p.text !== "");
}
