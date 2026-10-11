"use client";

import { useEffect, useRef } from "react";

import { stepLava, warmth, type Blob } from "@/lib/lava";
import { cn } from "@/lib/utils";

// Where each blob starts (share of the screen), its size, colour and lava cycle. The last two are left out on touch
// screens, where three are plenty.
const BLOBS = [
  { fx: 0.82, fy: 0.18, size: "size-[34rem]", colour: "bg-primary/15 dark:bg-primary/10", period: 34, phase: 0 },
  { fx: 0.1, fy: 0.5, size: "size-[30rem]", colour: "bg-brand-buddy/15 dark:bg-brand-buddy/10", period: 41, phase: 2.1 },
  { fx: 0.62, fy: 0.88, size: "size-[28rem]", colour: "bg-brand-know/10 dark:bg-brand-know/15", period: 29, phase: 4.2 },
  { fx: 0.38, fy: 0.08, size: "size-[24rem]", colour: "bg-primary/10 dark:bg-primary/10", period: 37, phase: 1.3, mouseOnly: true },
  { fx: 0.92, fy: 0.68, size: "size-[22rem]", colour: "bg-brand-buddy/10 dark:bg-brand-buddy/10", period: 26, phase: 5.2, mouseOnly: true },
];

/**
 * A lava lamp of brand-coloured light behind the sign-in page: soft, see-through blobs that rise while warm and sink
 * as they cool, wander sideways, turn back at the screen's edges, blend where they overlap, and glide away from the
 * mouse when it comes close (lib/lava.ts). A frame loop moves them with `transform` only, written straight onto
 * each blob, so React never re-renders. Decorative: hidden from screen readers, never clickable. Fixed to the
 * viewport, so it can never make the page scroll sideways. Touch screens: three blobs, nothing to push them. Reduced
 * motion: the blobs stay where they start.
 */
export function AmbientBackground() {
  const refs = useRef<(HTMLDivElement | null)[]>([]);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const mouse = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
    const used = BLOBS.map((spec, i) => ({ spec, el: refs.current[i] })).filter(
      ({ spec, el }) => el && (mouse || !spec.mouseOnly),
    );
    const blobs: Blob[] = used.map(({ spec }) => ({
      x: spec.fx * window.innerWidth,
      y: spec.fy * window.innerHeight,
      vx: 0,
      vy: 0,
      phase: spec.phase,
      period: spec.period,
    }));

    let pointer: { x: number; y: number } | null = null;
    const onMove = (event: PointerEvent) => {
      pointer = { x: event.clientX, y: event.clientY };
    };
    const onLeave = () => {
      pointer = null;
    };

    let frame = 0;
    let before = performance.now();
    const tick = (now: number) => {
      const screen = { width: window.innerWidth, height: window.innerHeight };
      stepLava(blobs, (now - before) / 1000, now / 1000, screen, pointer);
      before = now;
      blobs.forEach((blob, i) => {
        const { spec, el } = used[i];
        // Each blob is laid out centred on its starting point (left, top and Tailwind's translate); the transform
        // carries it from there.
        const dx = blob.x - spec.fx * screen.width;
        const dy = blob.y - spec.fy * screen.height;
        const swell = 1 + 0.12 * warmth(blob, now / 1000);
        el!.style.transform = `translate3d(${dx.toFixed(1)}px, ${dy.toFixed(1)}px, 0) scale(${swell.toFixed(3)})`;
      });
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    if (mouse) {
      window.addEventListener("pointermove", onMove, { passive: true });
      document.documentElement.addEventListener("mouseleave", onLeave);
    }
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", onMove);
      document.documentElement.removeEventListener("mouseleave", onLeave);
    };
  }, []);

  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      {BLOBS.map((spec, i) => (
        <div
          key={i}
          ref={(el) => {
            refs.current[i] = el;
          }}
          style={{ left: `${spec.fx * 100}%`, top: `${spec.fy * 100}%` }}
          className={cn(
            "absolute -translate-x-1/2 -translate-y-1/2 rounded-full blur-3xl will-change-transform",
            spec.size,
            spec.colour,
            spec.mouseOnly && "pointer-coarse:hidden",
          )}
        />
      ))}
    </div>
  );
}
