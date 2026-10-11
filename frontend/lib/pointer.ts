// Pointer position as numbers CSS can use, for the sign-in page's motion (components/login/).

/**
 * Where the pointer is over an area, from -1 (left or top edge) to 1 (right or bottom edge), 0 at the centre,
 * clamped, so a pointer outside the area never tilts anything further. A zero-sized area gives the centre.
 */
export function pointerOffset(
  clientX: number,
  clientY: number,
  rect: { left: number; top: number; width: number; height: number },
): { x: number; y: number } {
  if (rect.width <= 0 || rect.height <= 0) return { x: 0, y: 0 };
  const clamp = (n: number) => Math.max(-1, Math.min(1, n));
  return {
    x: clamp(((clientX - rect.left) / rect.width) * 2 - 1),
    y: clamp(((clientY - rect.top) / rect.height) * 2 - 1),
  };
}

/** The card's tilt for an offset: up to `max` degrees, leaning toward the pointer. */
export function tiltFor(offset: { x: number; y: number }, max = 6): { rotateX: number; rotateY: number } {
  const round = (n: number) => Math.round(n * 100) / 100 || 0; // || 0: never "-0deg"
  return { rotateX: round(-offset.y * max), rotateY: round(offset.x * max) };
}
