"use client";

import { MessageSquare, Plug, ScrollText, ShieldCheck, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useMe } from "@/components/me-provider";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export type NavItem = { href: string; label: string; Icon: LucideIcon };
export type NavGroup = { label?: string; items: NavItem[] };

/**
 * Admin links are shown only to admins, but hiding a link is cosmetic: the
 * admin pages redirect non-admins and the backend refuses them too.
 */
export function useNavGroups(): NavGroup[] {
  const me = useMe();
  return [
    {
      items: [
        { href: "/", label: "Ask", Icon: MessageSquare },
        { href: "/connectors", label: "Connections", Icon: Plug },
      ],
    },
    ...(me.is_admin
      ? [
          {
            label: "Admin",
            items: [
              { href: "/admin/audit", label: "Audit trail", Icon: ScrollText },
              { href: "/admin/boundary", label: "Boundary", Icon: ShieldCheck },
            ],
          },
        ]
      : []),
  ];
}

export function isCurrent(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

/** The sidebar's links. Collapsed: icons only, each with its name as label and tooltip. */
export function MainNav({ collapsed = false, onNavigate }: { collapsed?: boolean; onNavigate?: () => void }) {
  const groups = useNavGroups();
  const pathname = usePathname();
  return (
    <nav aria-label="Main" className="grid gap-4">
      {groups.map((group, i) => (
        <div key={group.label ?? i} className="grid gap-0.5">
          {group.label ? (
            collapsed ? (
              <div aria-hidden="true" className="mx-2 my-1 border-t" />
            ) : (
              <p className="px-2 pb-1 text-xs font-medium text-muted-foreground">{group.label}</p>
            )
          ) : null}
          {group.items.map(({ href, label, Icon }) => {
            const current = isCurrent(pathname, href);
            const link = (
              <Link
                href={href}
                onClick={onNavigate}
                aria-current={current ? "page" : undefined}
                aria-label={collapsed ? label : undefined}
                className={cn(
                  "flex h-9 items-center gap-2.5 rounded-md px-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground active:bg-[color-mix(in_oklch,var(--accent),var(--foreground)_10%)]",
                  collapsed && "justify-center px-0",
                  current && "bg-accent font-medium text-foreground",
                )}
              >
                <Icon aria-hidden="true" className={cn("size-4 shrink-0", current && "text-primary")} />
                {collapsed ? null : <span className="truncate">{label}</span>}
              </Link>
            );
            return collapsed ? (
              <Tooltip key={href}>
                <TooltipTrigger asChild>{link}</TooltipTrigger>
                <TooltipContent side="right">{label}</TooltipContent>
              </Tooltip>
            ) : (
              <div key={href}>{link}</div>
            );
          })}
        </div>
      ))}
    </nav>
  );
}
