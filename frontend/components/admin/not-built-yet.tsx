import { Construction } from "lucide-react";
import type { ReactNode } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

/** Says plainly that a page is not working yet and what it waits for (AGENTS.md §2.5). */
export function NotBuiltYet({ children }: { children: ReactNode }) {
  return (
    <Alert variant="warning">
      <Construction aria-hidden="true" />
      <AlertTitle>Not built yet</AlertTitle>
      {/* wrap-anywhere: long API routes would otherwise widen the page on phones. */}
      <AlertDescription className="grid gap-1 wrap-anywhere">{children}</AlertDescription>
    </Alert>
  );
}
