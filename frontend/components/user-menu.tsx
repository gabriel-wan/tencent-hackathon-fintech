"use client";

import { ChevronsUpDown, LogOut, Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

import { useMe } from "@/components/me-provider";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuItem,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { signOut } from "@/lib/api/client";
import { initials } from "@/lib/people";
import { cn } from "@/lib/utils";

const THEMES = [
  { value: "system", label: "System", Icon: Monitor },
  { value: "light", label: "Light", Icon: Sun },
  { value: "dark", label: "Dark", Icon: Moon },
] as const;

/** The sidebar's footer: who is signed in, the theme and sign-out. */
export function UserMenu({ collapsed = false }: { collapsed?: boolean }) {
  const me = useMe();
  const { theme, setTheme } = useTheme();
  // The stored theme is only known in the browser.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
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

  const trigger = (
    <DropdownMenuTrigger
      aria-label={`Account: ${me.name}`}
      className={cn(
        "flex w-full min-w-0 cursor-pointer items-center gap-2.5 rounded-md p-1.5 text-left text-sm outline-none hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50 active:bg-[color-mix(in_oklch,var(--accent),var(--foreground)_10%)] aria-expanded:bg-accent",
        collapsed && "justify-center",
      )}
    >
      <span
        aria-hidden="true"
        className="grid size-7 shrink-0 place-items-center rounded-full bg-primary text-xs font-semibold text-primary-foreground"
      >
        {initials(me.name)}
      </span>
      {collapsed ? null : (
        <>
          <span className="grid min-w-0 flex-1">
            <span className="truncate font-medium">{me.name}</span>
            <span className="truncate text-xs text-muted-foreground">{me.is_admin ? "Admin" : me.email}</span>
          </span>
          <ChevronsUpDown aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
        </>
      )}
    </DropdownMenuTrigger>
  );

  return (
    <DropdownMenu>
      {collapsed ? (
        <Tooltip>
          <TooltipTrigger asChild>{trigger}</TooltipTrigger>
          <TooltipContent side="right">{me.name}</TooltipContent>
        </Tooltip>
      ) : (
        trigger
      )}
      <DropdownMenuContent align="start" side={collapsed ? "right" : "top"} className="min-w-60">
        <DropdownMenuLabel className="grid gap-0.5">
          <span className="text-sm font-medium text-foreground">{me.name}</span>
          <span className="text-xs font-normal text-muted-foreground">{me.email}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">Theme</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={mounted ? (theme ?? "system") : "system"} onValueChange={setTheme}>
          {THEMES.map(({ value, label, Icon }) => (
            <DropdownMenuRadioItem key={value} value={value}>
              <Icon aria-hidden="true" />
              {label}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={handleSignOut} disabled={state === "signingOut"}>
          <LogOut aria-hidden="true" />
          {state === "signingOut" ? "Signing out…" : "Sign out"}
        </DropdownMenuItem>
        {state === "failed" ? (
          <p role="alert" className="px-2 py-1.5 text-xs text-destructive">
            Sign-out failed. Please check your network connection and try again.
          </p>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
