import { Construction } from "lucide-react";
import type { ReactNode } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

/** Says plainly that a page is not working yet and what it waits for (AGENTS.md §2.5). */
export function NotBuiltYet({ children }: { children: ReactNode }) {
  return (
    <Alert variant="warning">
      <Construction aria-hidden="true" />
      <AlertTitle>Not built yet</AlertTitle>
      <AlertDescription className="grid gap-1">{children}</AlertDescription>
    </Alert>
  );
}
