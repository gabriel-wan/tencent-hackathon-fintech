import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

// One centred column; ~760 px keeps answer text at a readable line length.
// Admin pages pass a wider max width for tables.
export function PageContainer({ children, className }: { children: ReactNode; className?: string }) {
  return <main className={cn("mx-auto w-full max-w-[760px] flex-1 px-4 py-8", className)}>{children}</main>;
}
