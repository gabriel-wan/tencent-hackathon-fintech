import { cn } from "@/lib/utils";

export const TAGLINE = "Permission-aware knowledge assistant";

/**
 * The KnowBuddy logo: the app icon (app/icon.svg, which Next.js also serves as the favicon) and the
 * name as real text, so it stays sharp and follows dark mode. Decorative icon: the name is the label.
 */
export function Wordmark({ size = "sm", tagline = false, className }: {
  size?: "sm" | "lg";
  tagline?: boolean;
  className?: string;
}) {
  const large = size === "lg";
  return (
    <span className={cn("inline-flex items-center", large ? "gap-3" : "gap-2", className)}>
      {/* A plain <img>: one small static file, so next/image would add nothing. */}
      <img src="/icon.svg" width={large ? 48 : 24} height={large ? 48 : 24} alt="" aria-hidden="true" className="shrink-0" />
      <span className="grid">
        <span className={cn("font-bold tracking-tight", large ? "text-3xl leading-none" : "text-base")}>
          <span className="text-brand-know">Know</span>
          <span className="text-brand-buddy">Buddy</span>
        </span>
        {tagline ? <span className="mt-1 text-sm text-muted-foreground">{TAGLINE}</span> : null}
      </span>
    </span>
  );
}
