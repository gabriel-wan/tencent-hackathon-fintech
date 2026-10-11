// The sign-in page's lava-lamp background (components/login/ambient-background.tsx): soft blobs that rise and sink,
// wander, turn back at the screen's edges and glide away from the pointer. Plain numbers in, plain numbers out, so
// the behaviour can be tested without a browser. Distances in CSS pixels, time in seconds.

export type Blob = {
  x: number; // centre
  y: number;
  vx: number; // speed, px per second
  vy: number;
  phase: number; // where it starts in its warm-cool cycle (radians)
  period: number; // seconds for one rise and sink
};

export const LAVA = {
  lift: 22, // how hard warmth lifts (and cooling sinks) a blob, px/s²
  wander: 8, // sideways drift, px/s²
  drag: 0.5, // share of speed lost per second, so blobs settle to a slow glide
  reach: 260, // the pointer pushes blobs closer than this
  push: 900, // push at the pointer itself, px/s², fading to 0 at `reach`
  edge: 1.5, // how firmly a blob past the screen's edge is turned back, per second²
  maxSpeed: 160, // px/s, so a pushed blob glides rather than shoots off
  maxStep: 0.05, // longest step simulated at once (a hidden tab resuming), seconds
};

/** How warm a blob is at time `t`: from -1 (cool, sinking) to 1 (warm, rising). */
export function warmth(blob: Pick<Blob, "phase" | "period">, t: number): number {
  return Math.sin((2 * Math.PI * t) / blob.period + blob.phase);
}

/**
 * Moves every blob on by `dt` seconds at time `t`, inside a `width` × `height` screen, pushed away from `pointer`
 * if there is one. Changes the blobs in place (it runs every frame; no garbage).
 */
export function stepLava(
  blobs: Blob[],
  dt: number,
  t: number,
  screen: { width: number; height: number },
  pointer: { x: number; y: number } | null,
): void {
  const step = Math.min(Math.max(dt, 0), LAVA.maxStep);
  for (const blob of blobs) {
    let ax = Math.sin(t * 0.3 + blob.phase * 2) * LAVA.wander;
    let ay = -warmth(blob, t) * LAVA.lift;
    if (pointer) {
      const dx = blob.x - pointer.x;
      const dy = blob.y - pointer.y;
      const distance = Math.hypot(dx, dy);
      if (distance < LAVA.reach) {
        const strength = LAVA.push * (1 - distance / LAVA.reach) ** 2;
        // Exactly on the pointer: push it up, any way out is fine.
        const [ux, uy] = distance > 0.01 ? [dx / distance, dy / distance] : [0, -1];
        ax += ux * strength;
        ay += uy * strength;
      }
    }
    if (blob.x < 0) ax += -blob.x * LAVA.edge;
    if (blob.x > screen.width) ax -= (blob.x - screen.width) * LAVA.edge;
    if (blob.y < 0) ay += -blob.y * LAVA.edge;
    if (blob.y > screen.height) ay -= (blob.y - screen.height) * LAVA.edge;

    blob.vx = (blob.vx + ax * step) * (1 - LAVA.drag * step);
    blob.vy = (blob.vy + ay * step) * (1 - LAVA.drag * step);
    const speed = Math.hypot(blob.vx, blob.vy);
    if (speed > LAVA.maxSpeed) {
      blob.vx *= LAVA.maxSpeed / speed;
      blob.vy *= LAVA.maxSpeed / speed;
    }
    blob.x += blob.vx * step;
    blob.y += blob.vy * step;
  }
}
