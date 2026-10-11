import { describe, expect, it } from "vitest";

import { firstMaskedValue, hasMaskedValues } from "./masking";

describe("hasMaskedValues", () => {
  it.each([
    "[secret]",
    "card [card ending 1111]",
    "to [account ending 6789]",
    "[IBAN ending 4321]",
    "NRIC [NRIC *****567D]",
    "call [phone 1]",
    "[email 2]",
    "customer [name 1]",
    "[passport 1]",
    "[date of birth]",
    "[address]",
  ])("%j has a masked value", (text) => {
    expect(hasMaskedValues(text)).toBe(true);
  });

  it.each(["Blocked [S1][S2].", "see [draft] notes", "[link removed]", "", undefined])("%j has none", (text) => {
    expect(hasMaskedValues(text)).toBe(false);
  });
});

describe("firstMaskedValue", () => {
  it("finds the first masked value across texts, as written", () => {
    expect(firstMaskedValue("Paid [S1].", "Refund to [card ending 1111] and [name 1]")).toBe("[card ending 1111]");
    expect(firstMaskedValue("Call [phone 2] [S1]", "[secret]")).toBe("[phone 2]");
  });

  it("is null when nothing was masked", () => {
    expect(firstMaskedValue("Blocked [S1].", "[link removed]", undefined)).toBeNull();
    expect(firstMaskedValue()).toBeNull();
  });
});
