"use client";

import { ChevronDown, CircleUser, LogOut } from "lucide-react";
import { useState } from "react";

import { useMe } from "@/components/me-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { signOut } from "@/lib/api/client";

export function UserMenu() {
  const me = useMe();
  const [state, setState] = useState<"idle" | "signingOut" | "failed">("idle");

  async function handleSignOut(event: Event) {
    event.preventDefault(); // keep the menu open so a failure can be shown
    setState("signingOut");
    try {
      await signOut();
      // Full page load: nothing from this session survives (SECURITY.md T6).
      window.location.assign("/login");
    } catch {
      // The session is still valid, so do not pretend the user signed out.
      setState("failed");
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="min-w-0 max-w-56 gap-1.5" aria-label={`Account: ${me.name}`}>
          {/* Phones: icon only; the name is in the menu and the label. */}
          <CircleUser aria-hidden="true" className="sm:hidden" />
          <span className="hidden truncate sm:inline">{me.name}</span>
          {me.is_admin ? <Badge variant="secondary">ADMIN</Badge> : null}
          <ChevronDown aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-56">
        <DropdownMenuLabel className="grid gap-0.5">
          <span className="text-sm font-medium text-foreground">{me.name}</span>
          <span className="text-xs font-normal text-muted-foreground">{me.email}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={handleSignOut} disabled={state === "signingOut"}>
          <LogOut aria-hidden="true" />
          {state === "signingOut" ? "Signing out…" : "Sign out"}
        </DropdownMenuItem>
        {state === "failed" ? (
          <p role="alert" className="px-2 py-1.5 text-xs text-destructive">
            Sign-out failed. You are still signed in; try again.
          </p>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
