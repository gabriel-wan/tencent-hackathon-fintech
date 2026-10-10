// Helpers for the untrusted parts of an answer: its text and its source links,
// plus what each source says about masking (ADR-010) and freshness (ADR-005).
import { STALE_AFTER_MS } from "@/lib/boundary";

// Matches the backend's citation labels (backend/app/llm/grounding.py LABEL_RE),
// including runs like "[S1][S2]" and the space before them.
const MARKERS = /[ \t]*(?:\[S\d+\])+/g;

/**
 * Removes [S1]-style markers. Citations do not yet say which label they are
 * (an open request to the query pipeline), so markers cannot be linked to the right
 * source; the Sources list is shown below the answer instead.
 */
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
