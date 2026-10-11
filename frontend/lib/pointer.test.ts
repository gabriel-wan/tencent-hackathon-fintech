import { describe, expect, it } from "vitest";

import { easeToward, pointerOffset, tiltFor } from "./pointer";

const rect = { left: 100, top: 50, width: 200, height: 100 };

describe("pointerOffset", () => {
  it("is 0 at the centre and ±1 at the edges", () => {
    expect(pointerOffset(200, 100, rect)).toEqual({ x: 0, y: 0 });
    expect(pointerOffset(100, 50, rect)).toEqual({ x: -1, y: -1 });
    expect(pointerOffset(300, 150, rect)).toEqual({ x: 1, y: 1 });
  });
  it("clamps a pointer outside the area, and survives a zero-sized one", () => {
    expect(pointerOffset(900, -400, rect)).toEqual({ x: 1, y: -1 });
    expect(pointerOffset(5, 5, { left: 0, top: 0, width: 0, height: 0 })).toEqual({ x: 0, y: 0 });
  });
});

describe("tiltFor", () => {
  it("leans toward the pointer, at most 6 degrees", () => {
    expect(tiltFor({ x: 1, y: -1 })).toEqual({ rotateX: 6, rotateY: 6 }); // top right: top edge back, right edge back
    expect(tiltFor({ x: -0.5, y: 0.5 })).toEqual({ rotateX: -3, rotateY: -3 });
    expect(tiltFor({ x: 0, y: 0 })).toEqual({ rotateX: 0, rotateY: 0 });
  });
});

describe("easeToward", () => {
  it("moves part of the way each frame, then lands exactly", () => {
    expect(easeToward(0, 1, 0.1)).toBeCloseTo(0.1);
    expect(easeToward(-1, 1, 0.5)).toBe(0);
    expect(easeToward(0.9995, 1)).toBe(1);
    let x = 0;
    for (let i = 0; i < 200 && x !== 1; i++) x = easeToward(x, 1);
    expect(x).toBe(1);
  });
});
