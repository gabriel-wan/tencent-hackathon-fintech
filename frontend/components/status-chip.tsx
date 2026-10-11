import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

/**
 * The one small status label for the whole app (answers, Connections, audit, boundary), so a state looks the
 * same everywhere. Colour carries meaning only:
 * - neutral: information (a source's tool, "2 masked" is the system working, so it is not green);
 * - success: a good outcome (allowed, connected, chain intact);
 * - danger: a real failure (denied, failed, out of date). Never for "not found";
 * - warning: development-only aids and mock data, nothing else (FRONTEND.md design principle 4).
 * Put an icon first (aria-hidden); the words always carry the meaning.
 */
const statusChipVariants = cva(
  "inline-flex w-fit shrink-0 items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs font-medium whitespace-nowrap [&>svg]:size-3 [&>svg]:shrink-0",
  {
    variants: {
      tone: {
        neutral: "border-border bg-secondary text-secondary-foreground",
        success: "border-success-foreground/30 bg-success text-success-foreground",
        danger: "border-destructive/30 bg-destructive/10 text-destructive",
        warning: "border-warning-foreground/30 bg-warning text-warning-foreground",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export function StatusChip({
  tone,
  className,
  ...props
}: ComponentProps<"span"> & VariantProps<typeof statusChipVariants>) {
  return <span data-slot="status-chip" className={cn(statusChipVariants({ tone }), className)} {...props} />;
}
