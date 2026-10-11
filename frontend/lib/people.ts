// Display helpers for a person's name. Seeded names carry a role in brackets ("Alice Tan (payments engineer)");
// real names come from the tools and have none.

function words(name: string): string[] {
  return name.replace(/\(.*?\)/g, " ").trim().split(/\s+/).filter(Boolean);
}

/** "Alice Tan (payments engineer)" → "AT"; one word → its first letter; nothing → "?". */
export function initials(name: string): string {
  const w = words(name);
  const picked = w.length > 1 ? [w[0], w[w.length - 1]] : w;
  return picked.map((part) => part[0]!.toUpperCase()).join("") || "?";
}

/** "Alice Tan (payments engineer)" → "Alice"; an email-only name → the part before "@"; nothing → "". */
export function firstName(name: string): string {
  const first = words(name)[0] ?? "";
  return first.includes("@") ? first.split("@")[0]! : first;
}
