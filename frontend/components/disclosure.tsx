import { ChevronRight } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * A collapsed-by-default section with an arrow that turns when it opens. A native <details>, so keyboard,
 * screen readers and no-JavaScript all work, and it renders on the server.
 */
export function Disclosure({
  summary,
  children,
  className,
}: {
  summary: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <details className={cn("group text-sm", className)}>
      <summary className="flex w-fit cursor-pointer list-none items-center gap-1.5 rounded-md font-medium text-muted-foreground hover:text-foreground [&::-webkit-details-marker]:hidden">
        <ChevronRight aria-hidden="true" className="size-4 shrink-0 transition-transform group-open:rotate-90" />
        {summary}
      </summary>
      <div className="mt-3 pl-5.5">{children}</div>
    </details>
  );
}
