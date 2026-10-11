import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * "Nothing here": says what would be here and offers the next step (one action at most). Two cases look
 * alike but read differently: nothing exists yet, and nothing matches the filters (offer "Clear filters").
 */
export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon?: LucideIcon;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("grid justify-items-center gap-2 px-4 py-10 text-center", className)}>
      {Icon ? (
        <span className="mb-1 grid size-10 place-items-center rounded-full bg-muted text-muted-foreground">
          <Icon aria-hidden="true" className="size-5" />
        </span>
      ) : null}
      <p className="font-medium">{title}</p>
      {description ? <p className="max-w-sm text-sm text-muted-foreground">{description}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
