"use client";

import { useEffect, type RefObject } from "react";

import { easeToward, pointerOffset, tiltFor } from "@/lib/pointer";

/**
 * Feeds the pointer's position anywhere on the page to CSS, for the sign-in page's motion. On `area` (inherited
 * by the background inside it): `--px` and `--py` (-1 to 1 across the window), `--mx` and `--my` (the pointer in
 * pixels) and `--glow` (1 while the pointer is on the page), eased a little each frame so the background glides
 * after the mouse rather than jumping. On `card`: `--tilt-x` and `--tilt-y` (degrees) and `--spot-x` and `--spot-y`
 * (the highlight, as %). CSS variables are written straight onto the elements, so React never re-renders on mouse
 * moves, and the frame loop stops once everything has caught up. Does nothing for people who ask for reduced
 * motion, or on touch screens (no hover); the background then only drifts on its own (or, reduced, stays still).
 */
export function usePointerMotion(area: RefObject<HTMLElement | null>, card: RefObject<HTMLElement | null>) {
  useEffect(() => {
    const el = area.current;
    if (!el) return;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)");
    const mouse = window.matchMedia("(hover: hover) and (pointer: fine)");
    if (still.matches || !mouse.matches) return;

    const target = { x: 0, y: 0, mx: window.innerWidth / 2, my: window.innerHeight / 2 };
    const now = { ...target };
    let frame = 0;
    let last: PointerEvent | null = null;

    const tick = () => {
      frame = 0;
      now.x = easeToward(now.x, target.x);
      now.y = easeToward(now.y, target.y);
      now.mx = easeToward(now.mx, target.mx, 0.12, 0.5);
      now.my = easeToward(now.my, target.my, 0.12, 0.5);
      el.style.setProperty("--px", now.x.toFixed(3));
      el.style.setProperty("--py", now.y.toFixed(3));
      el.style.setProperty("--mx", `${now.mx.toFixed(1)}px`);
      el.style.setProperty("--my", `${now.my.toFixed(1)}px`);
      const box = card.current;
      if (box && last) {
        const over = pointerOffset(last.clientX, last.clientY, box.getBoundingClientRect());
        const tilt = tiltFor(over);
        box.style.setProperty("--tilt-x", `${tilt.rotateX}deg`);
        box.style.setProperty("--tilt-y", `${tilt.rotateY}deg`);
        box.style.setProperty("--spot-x", `${Math.round((over.x + 1) * 50)}%`);
        box.style.setProperty("--spot-y", `${Math.round((over.y + 1) * 50)}%`);
      }
      const settled = now.x === target.x && now.y === target.y && now.mx === target.mx && now.my === target.my;
      if (!settled) frame = requestAnimationFrame(tick);
    };
    const wake = () => {
      if (!frame) frame = requestAnimationFrame(tick);
    };
    const onMove = (event: PointerEvent) => {
      last = event;
      const page = pointerOffset(event.clientX, event.clientY, {
        left: 0,
        top: 0,
        width: window.innerWidth,
        height: window.innerHeight,
      });
      target.x = page.x;
      target.y = page.y;
      target.mx = event.clientX;
      target.my = event.clientY;
      el.style.setProperty("--glow", "1");
      wake();
    };
    const onLeave = () => {
      last = null;
      target.x = 0;
      target.y = 0;
      el.style.setProperty("--glow", "0");
      for (const name of ["--tilt-x", "--tilt-y", "--spot-x", "--spot-y"]) card.current?.style.removeProperty(name);
      wake();
    };
    const root = document.documentElement;
    window.addEventListener("pointermove", onMove, { passive: true });
    root.addEventListener("mouseleave", onLeave);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", onMove);
      root.removeEventListener("mouseleave", onLeave);
    };
  }, [area, card]);
}
