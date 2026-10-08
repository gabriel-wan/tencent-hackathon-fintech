"use client";

import { Eye, EyeOff } from "lucide-react";
import { useState, type ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

/**
 * DEVELOPMENT ONLY: a layout preview filled with fixture data, so a page can
 * be reviewed before its API exists. Hidden until asked for, framed and
 * labelled MOCK DATA, and its controls do nothing, so it cannot be mistaken
 * for a working feature (AGENTS.md §2.5). Pages render it only when the
 * backend is in development mode.
 */
export function DesignPreview({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <section aria-label="Design preview" className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
          {open ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
          {open ? "Hide design preview" : "Show design preview"}
        </Button>
        <span className="text-xs text-muted-foreground">Development only. Fixture data; nothing on it works.</span>
      </div>
      {open ? (
        <div className="grid gap-4 rounded-xl border-2 border-dashed border-warning-foreground/40 p-4">
          <Badge variant="warning" className="justify-self-start">
            MOCK DATA: design preview
          </Badge>
          {children}
        </div>
      ) : null}
    </section>
  );
}
