import { describe, expect, it } from "vitest";

import { pointerOffset, tiltFor } from "./pointer";

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
