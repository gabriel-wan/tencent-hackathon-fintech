// Helpers for the untrusted parts of an answer: its text and its source links.

// Matches the backend's citation labels (backend/app/llm/grounding.py LABEL_RE),
// including runs like "[S1][S2]" and the space before them.
const MARKERS = /[ \t]*(?:\[S\d+\])+/g;

/**
 * Removes [S1]-style markers. Citations do not yet say which label they are
 * (ui-plan.md question log, Q1), so markers cannot be linked to the right
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
