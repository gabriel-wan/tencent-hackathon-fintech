"use client";

import { Info } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";

import { Popover, PopoverAnchor, PopoverContent } from "@/components/ui/popover";

/**
 * A small ⓘ that explains something in a sentence or two. Opens when the mouse moves over it, on
 * keyboard focus (Tab), and on tap or click (phones); closes on leaving, blur, Escape or a tap elsewhere.
 *
 * Screen readers get the explanation as the button's description, so they hear it without opening
 * anything: "About the timings, button, Embed: …". The description's text is `hidden`: a description
 * may point at hidden text, and hidden text isn't read again as page content (e.g. inside a heading).
 */
export function InfoTip({ label, children }: { label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const mouse = (event: React.PointerEvent) => event.pointerType === "mouse";
  // When the ⓘ appears under a resting mouse (e.g. a dialog opening where the pointer is), the browser
  // reports the pointer as entering it. Hover only counts once the mouse moves over it, and not in the
  // first moment after it appears.
  const shownAt = useRef(0);
  useEffect(() => {
    shownAt.current = performance.now();
  }, []);
  const hoverOpens = (event: React.PointerEvent) => mouse(event) && performance.now() - shownAt.current > 400;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverAnchor asChild>
        <button
          type="button"
          aria-label={label}
          aria-describedby={id}
          aria-expanded={open}
          className="inline-flex size-5 shrink-0 items-center justify-center rounded-full align-middle text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
          onPointerMove={(event) => !open && hoverOpens(event) && setOpen(true)}
          onPointerLeave={(event) => mouse(event) && setOpen(false)}
          // Only keyboard focus (Tab) opens it: focus moved by code, e.g. a dialog opening, must not.
          onFocus={(event) => event.currentTarget.matches(":focus-visible") && setOpen(true)}
          onBlur={() => setOpen(false)}
          onClick={() => setOpen(true)} // a tap opens it; Escape or a tap elsewhere closes it
        >
          <Info aria-hidden="true" className="size-3.5" />
        </button>
      </PopoverAnchor>
      <span id={id} hidden>
        {children}
      </span>
      <PopoverContent
        side="top"
        aria-hidden="true" // read through the button's description instead, so it isn't read twice
        className="w-auto max-w-72 text-xs leading-relaxed font-normal tracking-normal normal-case"
        // Keep focus on the ⓘ: moving it into the popover would blur the button and close it again.
        onOpenAutoFocus={(event) => event.preventDefault()}
        onCloseAutoFocus={(event) => event.preventDefault()}
      >
        {children}
      </PopoverContent>
    </Popover>
  );
}
