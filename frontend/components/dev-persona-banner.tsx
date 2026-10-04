"use client";

import { ChevronDown } from "lucide-react";
import { useState } from "react";

import { useMe } from "@/components/me-provider";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { devSignIn } from "@/lib/api/client";
import type { DevUser } from "@/lib/api/types";

/**
 * DEVELOPMENT ONLY. Rendered by the (app) layout only when the backend lists
 * /api/dev/users, i.e. runs with APP_ENV=development. Loud on purpose, so it
 * is never mistaken for a product feature in screenshots or the demo.
 * Switching does a full page load, which wipes the previous person's chat
 * history from memory (SECURITY.md T6).
 */
export function DevPersonaBanner({ users }: { users: DevUser[] }) {
  const me = useMe();
  const [switching, setSwitching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const current = users.find((u) => u.email === me.email);

  async function switchTo(id: string) {
    const user = users.find((u) => String(u.id) === id);
    if (!user || user.email === me.email) return;
    setSwitching(true);
    setError(null);
    try {
      await devSignIn(user.id);
      window.location.assign("/");
    } catch {
      setError("Switch failed");
      setSwitching(false);
    }
  }

  return (
    <div
      role="region"
      aria-label="Development tools"
      className="border-b border-warning-foreground/30 bg-warning text-warning-foreground"
    >
      <div className="mx-auto flex min-h-9 w-full max-w-5xl flex-wrap items-center gap-x-3 gap-y-1 px-4 py-1 text-xs">
        <span className="font-semibold tracking-wide">DEVELOPMENT ONLY</span>
        <span className="min-w-0 truncate">
          Signed in as <span className="font-medium">{me.name}</span> (identity not verified)
        </span>
        <div className="ml-auto flex items-center gap-2">
          {error ? <span role="alert">{error}</span> : null}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                disabled={switching}
                className="border-warning-foreground/40 bg-transparent text-warning-foreground hover:bg-warning-foreground/10 hover:text-warning-foreground"
              >
                {switching ? "Switching…" : "Switch user"}
                <ChevronDown aria-hidden="true" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel>Sign in as (development only)</DropdownMenuLabel>
              <DropdownMenuRadioGroup value={current ? String(current.id) : ""} onValueChange={switchTo}>
                {users.map((user) => (
                  <DropdownMenuRadioItem key={user.id} value={String(user.id)}>
                    {user.name}
                    {user.is_admin ? <span className="ml-auto pl-3 text-xs text-muted-foreground">admin</span> : null}
                  </DropdownMenuRadioItem>
                ))}
              </DropdownMenuRadioGroup>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </div>
  );
}
