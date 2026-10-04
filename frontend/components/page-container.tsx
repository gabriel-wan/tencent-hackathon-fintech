import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

// One centred column; ~760 px keeps answer text at a readable line length.
// Admin pages pass a wider max width for tables. id="main" is the target of
// the "Skip to content" link; tabIndex -1 lets it receive focus from it.
export function PageContainer({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <main
      id="main"
      tabIndex={-1}
      className={cn("mx-auto w-full max-w-[760px] flex-1 px-4 py-8 outline-none", className)}
    >
      {children}
    </main>
  );
}
