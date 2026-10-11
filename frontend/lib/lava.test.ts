import { describe, expect, it } from "vitest";

import { LAVA, stepLava, warmth, type Blob } from "./lava";

const screen = { width: 1200, height: 800 };
const blob = (over: Partial<Blob> = {}): Blob => ({ x: 600, y: 400, vx: 0, vy: 0, phase: 0, period: 30, ...over });

/** Runs `seconds` of the simulation at 60 frames a second. */
function run(blobs: Blob[], seconds: number, pointer: { x: number; y: number } | null = null, from = 0) {
  for (let frame = 0; frame < seconds * 60; frame++) stepLava(blobs, 1 / 60, from + frame / 60, screen, pointer);
}

describe("stepLava", () => {
  it("pushes a blob near the pointer away from it", () => {
    const near = blob();
    const start = Math.hypot(near.x - 520, near.y - 400);
    run([near], 0.5, { x: 520, y: 400 });
    expect(near.x).toBeGreaterThan(600);
    expect(Math.hypot(near.x - 520, near.y - 400)).toBeGreaterThan(start + 20);
  });

  it("leaves a blob out of the pointer's reach to roam as it would", () => {
    const [alone, withPointer] = [blob(), blob()];
    run([alone], 1);
    run([withPointer], 1, { x: 600 + LAVA.reach + 200, y: 400 });
    expect(withPointer).toEqual(alone);
  });

  it("never goes faster than the cap, even right under the pointer", () => {
    const b = blob();
    for (let frame = 0; frame < 120; frame++) {
      stepLava([b], 1 / 60, frame / 60, screen, { x: b.x + 1, y: b.y });
      expect(Math.hypot(b.vx, b.vy)).toBeLessThanOrEqual(LAVA.maxSpeed + 1e-9);
    }
  });

  it("stays around the screen over a long run, and survives a huge frame gap", () => {
    const blobs = [blob({ x: 10, y: 10, phase: 1 }), blob({ x: 1190, y: 790, phase: 4, period: 22 }), blob()];
    run(blobs, 300);
    stepLava(blobs, 30, 300, screen, null); // a tab hidden for 30 s
    for (const b of blobs) {
      expect(b.x).toBeGreaterThan(-150);
      expect(b.x).toBeLessThan(screen.width + 150);
      expect(b.y).toBeGreaterThan(-150);
      expect(b.y).toBeLessThan(screen.height + 150);
    }
  });

  it("rises while warm, then sinks once it cools", () => {
    const b = blob({ phase: 0, period: 40 }); // warm for the first 20 s
    run([b], 10);
    expect(b.y).toBeLessThan(400);
    const top = b.y;
    run([b], 18, null, 22); // cool from 20 s to 40 s
    expect(b.y).toBeGreaterThan(top);
  });
});

describe("warmth", () => {
  it("cycles between warm and cool", () => {
    expect(warmth({ phase: 0, period: 40 }, 10)).toBeCloseTo(1);
    expect(warmth({ phase: 0, period: 40 }, 30)).toBeCloseTo(-1);
  });
});
