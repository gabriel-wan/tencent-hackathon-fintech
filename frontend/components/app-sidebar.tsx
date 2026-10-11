"use client";

import { Menu, PanelLeftClose, PanelLeftOpen, SquarePen } from "lucide-react";
import Link from "next/link";
import { useState, type ReactNode } from "react";

import { Wordmark } from "@/components/brand";
import { useChatSession } from "@/components/chat-session";
import { MainNav } from "@/components/main-nav";
import { UserMenu } from "@/components/user-menu";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { SIDEBAR_COOKIE } from "@/lib/sidebar";
import { cn } from "@/lib/utils";


function NewChatButton({ collapsed, onDone }: { collapsed: boolean; onDone?: () => void }) {
  const { newChat } = useChatSession();
  const button = (
    <Button
      variant="outline"
      className={cn("w-full justify-start", collapsed && "justify-center")}
      size={collapsed ? "icon-lg" : "lg"}
      aria-label={collapsed ? "New chat" : undefined}
      onClick={() => {
        newChat();
        onDone?.();
      }}
    >
      <SquarePen aria-hidden="true" />
      {collapsed ? null : "New chat"}
    </Button>
  );
  return collapsed ? (
    <Tooltip>
      <TooltipTrigger asChild>{button}</TooltipTrigger>
      <TooltipContent side="right">New chat</TooltipContent>
    </Tooltip>
  ) : (
    button
  );
}

/** What the desktop sidebar and the phone menu share: new chat, the links, the account. */
function SidebarBody({ collapsed, onNavigate }: { collapsed: boolean; onNavigate?: () => void }) {
  return (
    <>
      <div className="px-2">
        <NewChatButton collapsed={collapsed} onDone={onNavigate} />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-2">
        <MainNav collapsed={collapsed} onNavigate={onNavigate} />
      </div>
      <div className="border-t p-2">
        <UserMenu collapsed={collapsed} />
      </div>
    </>
  );
}

/**
 * The signed-in frame: a sidebar from 768 px (collapsible to icons), and below that a slim top bar whose
 * menu button opens the same contents in a sheet.
 */
export function AppSidebar({ initialCollapsed, badge }: { initialCollapsed: boolean; badge?: ReactNode }) {
  const [collapsed, setCollapsed] = useState(initialCollapsed);
  const [menuOpen, setMenuOpen] = useState(false);

  function toggle() {
    const next = !collapsed;
    setCollapsed(next);
    document.cookie = `${SIDEBAR_COOKIE}=${next ? "collapsed" : "open"}; path=/; max-age=31536000; samesite=lax`;
  }

  return (
    <TooltipProvider>
      {/* Phones and small tablets */}
      <header className="sticky top-0 z-40 flex h-14 items-center gap-2 border-b bg-background/95 px-3 backdrop-blur md:hidden">
        <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
          <SheetTrigger asChild>
            <Button variant="ghost" size="icon" aria-label="Open menu">
              <Menu aria-hidden="true" />
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="w-72 gap-3 bg-sidebar py-3">
            <SheetTitle className="px-4 pt-1">
              <Wordmark />
            </SheetTitle>
            <SheetDescription className="sr-only">Main menu</SheetDescription>
            <SidebarBody collapsed={false} onNavigate={() => setMenuOpen(false)} />
          </SheetContent>
        </Sheet>
        <Link href="/" className="rounded-md">
          <Wordmark />
        </Link>
        <div className="ml-auto">{badge}</div>
      </header>

      {/* From 768 px */}
      <aside
        aria-label="Sidebar"
        className={cn(
          "sticky top-[var(--dev-banner,0px)] hidden h-[calc(100dvh-var(--dev-banner,0px))] shrink-0 flex-col gap-3 border-r bg-sidebar py-3 transition-[width] duration-200 md:flex",
          collapsed ? "w-16" : "w-64",
        )}
      >
        <div className={cn("flex items-center gap-1 px-3", collapsed && "flex-col px-2")}>
          <Link href="/" className="min-w-0 rounded-md" aria-label={collapsed ? "KnowBuddy home" : undefined}>
            {collapsed ? <img src="/icon.svg" width={28} height={28} alt="" aria-hidden="true" /> : <Wordmark />}
          </Link>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                className={cn("text-muted-foreground", !collapsed && "ml-auto")}
                onClick={toggle}
                aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                aria-expanded={!collapsed}
              >
                {collapsed ? <PanelLeftOpen aria-hidden="true" /> : <PanelLeftClose aria-hidden="true" />}
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">{collapsed ? "Expand sidebar" : "Collapse sidebar"}</TooltipContent>
          </Tooltip>
        </div>
        {badge ? <div className={cn("px-3", collapsed && "px-2")}>{badge}</div> : null}
        <SidebarBody collapsed={collapsed} />
      </aside>
    </TooltipProvider>
  );
}
