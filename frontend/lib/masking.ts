// The tags the Need-to-Know Shield (ADR-010) writes in place of a sensitive value (backend/app/redaction.py
// Shield._tag): "[card ending 1111]", "[name 1]", "[secret]"… Never "[S1]", "[draft]" or "[link removed]".
const MASK_TAG =
  /\[(?:secret|date of birth|address|(?:card|account|IBAN) ending [A-Za-z0-9]{1,4}|NRIC \*+[A-Za-z0-9]{1,4}|(?:phone|email|name|passport) \d+)\]/;

/** Whether text has values the Shield masked. */
export function hasMaskedValues(text: string | undefined): boolean {
  return !!text && MASK_TAG.test(text);
}

/** The first masked value in any of the texts, as written ("[card ending 1111]"), or null: the example the
 * chat's note points at. */
export function firstMaskedValue(...texts: (string | undefined)[]): string | null {
  for (const text of texts) {
    const found = text ? MASK_TAG.exec(text) : null;
    if (found) return found[0];
  }
  return null;
}
