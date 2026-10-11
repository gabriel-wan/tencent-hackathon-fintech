import { describe, expect, it } from "vitest";

import { firstName, initials } from "./people";

describe("initials", () => {
  it("takes the first and last name, ignoring the bracketed role", () => {
    expect(initials("Alice Tan (payments engineer)")).toBe("AT");
    expect(initials("Priya Nair (admin and compliance)")).toBe("PN");
    expect(initials("Mary Anne de Souza")).toBe("MS");
  });
  it("handles one word and empty names", () => {
    expect(initials("dana")).toBe("D");
    expect(initials("  ")).toBe("?");
    expect(initials("(role only)")).toBe("?");
  });
});

describe("firstName", () => {
  it("returns the first word without the role", () => {
    expect(firstName("Alice Tan (payments engineer)")).toBe("Alice");
  });
  it("uses the local part of an email-only name", () => {
    expect(firstName("knowbuddy.priya@gmail.com")).toBe("knowbuddy.priya");
  });
  it("returns an empty string for nothing", () => {
    expect(firstName("")).toBe("");
  });
});
