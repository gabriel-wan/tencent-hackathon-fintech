"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useMe } from "@/components/me-provider";
import { cn } from "@/lib/utils";

export type NavItem = { href: string; label: string };

/**
 * Admin links are shown only to admins, but hiding a link is cosmetic: the
 * admin pages redirect non-admins and the backend must refuse them too.
 * Connectors joins once the connectors branch merges (ui-plan.md Phase 7).
 */
export function useNavItems(): NavItem[] {
  const me = useMe();
  return [
    { href: "/", label: "Chat" },
    ...(me.is_admin
      ? [
          { href: "/admin/audit", label: "Audit" },
          { href: "/admin/boundary", label: "Boundary" },
        ]
      : []),
  ];
}

export function isCurrent(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

/** Header links from 640 px up; below that they live in the user menu. */
export function MainNav() {
  const items = useNavItems();
  const pathname = usePathname();
  return (
    <>
      {items.map((item) => {
        const current = isCurrent(pathname, item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={current ? "page" : undefined}
            className={cn(
              "rounded-md px-2.5 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground",
              current && "bg-accent font-medium text-foreground",
            )}
          >
            {item.label}
          </Link>
        );
      })}
    </>
  );
}
