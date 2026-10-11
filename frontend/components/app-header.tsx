import Link from "next/link";
import type { ReactNode } from "react";

import { Wordmark } from "@/components/brand";
import { ThemeToggle } from "@/components/theme-toggle";

export function AppHeader({ nav, actions }: { nav?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div className="mx-auto flex h-14 w-full max-w-5xl items-center gap-4 px-4">
        <Link href="/" className="shrink-0 rounded-md whitespace-nowrap">
          <Wordmark />
        </Link>
        {nav ? (
          <nav aria-label="Main" className="hidden items-center gap-1 sm:flex">
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
