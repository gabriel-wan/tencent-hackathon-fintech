import Link from "next/link";
import type { ReactNode } from "react";

import { ThemeToggle } from "@/components/theme-toggle";

// The product name is still TBD (docs/PROJECT.md); plain-text wordmark until then.
export function AppHeader({ nav, actions }: { nav?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div className="mx-auto flex h-14 w-full max-w-5xl items-center gap-4 px-4">
        <Link href="/" className="shrink-0 rounded-md text-base font-semibold tracking-tight whitespace-nowrap">
          Internal Brain
        </Link>
        {nav ? (
          <nav aria-label="Main" className="flex items-center gap-1">
            {nav}
          </nav>
        ) : null}
        <div className="ml-auto flex min-w-0 items-center gap-1">
          {actions}
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
