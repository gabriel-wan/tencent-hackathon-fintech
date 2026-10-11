"use client";

import { useEffect, type RefObject } from "react";

import { pointerOffset, tiltFor } from "@/lib/pointer";

/**
 * Feeds the pointer's position over `area` to CSS, for the sign-in page's motion: on `area`, `--px` and `--py`
 * (-1 to 1, for the drifting shapes); on `card`, `--tilt-x` and `--tilt-y` (degrees) and `--spot-x` and
 * `--spot-y` (the highlight, as %). Writes CSS variables straight onto the elements, at most once a frame, so
 * React never re-renders on mouse moves. Does nothing for people who ask for reduced motion, or on touch screens
 * (no hover); everything then stays still.
 */
export function usePointerMotion(area: RefObject<HTMLElement | null>, card: RefObject<HTMLElement | null>) {
  useEffect(() => {
    const el = area.current;
    if (!el) return;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)");
    const mouse = window.matchMedia("(hover: hover) and (pointer: fine)");
    if (still.matches || !mouse.matches) return;

    let frame = 0;
    let last: PointerEvent | null = null;
    const apply = () => {
      frame = 0;
      if (!last) return;
      const page = pointerOffset(last.clientX, last.clientY, el.getBoundingClientRect());
      el.style.setProperty("--px", page.x.toFixed(3));
      el.style.setProperty("--py", page.y.toFixed(3));
      const target = card.current;
      if (target) {
        const box = target.getBoundingClientRect();
        const over = pointerOffset(last.clientX, last.clientY, box);
        const tilt = tiltFor(over);
        target.style.setProperty("--tilt-x", `${tilt.rotateX}deg`);
        target.style.setProperty("--tilt-y", `${tilt.rotateY}deg`);
        target.style.setProperty("--spot-x", `${Math.round((over.x + 1) * 50)}%`);
        target.style.setProperty("--spot-y", `${Math.round((over.y + 1) * 50)}%`);
      }
    };
    const onMove = (event: PointerEvent) => {
      last = event;
      if (!frame) frame = requestAnimationFrame(apply);
    };
    const onLeave = () => {
      last = null;
      for (const name of ["--px", "--py"]) el.style.removeProperty(name);
      for (const name of ["--tilt-x", "--tilt-y", "--spot-x", "--spot-y"]) card.current?.style.removeProperty(name);
    };
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerleave", onLeave);
    return () => {
      cancelAnimationFrame(frame);
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerleave", onLeave);
    };
  }, [area, card]);
}
