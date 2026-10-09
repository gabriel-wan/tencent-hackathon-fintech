"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

import { cn } from "@/lib/utils";

// Each tool's official logo, only to name the integration (frontend/README.md "Icons"). Files in
// public/logos/, from the vendors' own brand pages, unaltered: Slack's media kit, Google's Drive
// branding guidelines, Atlassian's logo library (the app icons).
const LOGOS: Record<string, string> = {
  slack: "/logos/slack.svg",
  drive: "/logos/google-drive.png",
  jira: "/logos/jira.svg",
  confluence: "/logos/confluence.svg",
};

/**
 * A tool's logo, decorative: the tool's name is always written next to it, so screen readers skip the
 * image (alt=""). Unknown tool, or a file that fails to load: `fallback` (or nothing), never a broken image.
 */
export function PlatformLogo({
  source,
  size = 16,
  className,
  fallback = null,
}: {
  source: string;
  size?: number;
  className?: string;
  fallback?: ReactNode;
}) {
  const [failed, setFailed] = useState(false);
  const img = useRef<HTMLImageElement>(null);
  // A server-rendered image can fail before React is listening (onError missed): check once on mount.
  useEffect(() => {
    if (img.current?.complete && img.current.naturalWidth === 0) setFailed(true);
  }, []);
  const src = LOGOS[source];
  if (!src || failed) return <>{fallback}</>;
  return (
    // A plain <img>: tiny static files at a fixed size, so next/image would add nothing.
    <img
      ref={img}
      src={src}
      width={size}
      height={size}
      alt=""
      aria-hidden="true"
      className={cn("shrink-0 object-contain", className)}
      onError={() => setFailed(true)}
    />
  );
}
