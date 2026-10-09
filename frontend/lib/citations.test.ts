import { describe, expect, it } from "vitest";

import { freshness, maskedSummary, safeHttpUrl, stripCitationMarkers } from "./citations";

describe("safeHttpUrl", () => {
  it.each([
    ["javascript:alert(1)"],
    ["JavaScript:alert(1)"],
    [" javascript:alert(1)"],
    ["data:text/html,<script>alert(1)</script>"],
    ["vbscript:msgbox(1)"],
    ["file:///etc/passwd"],
    ["/relative/path"],
    ["//evil.example/x"],
    ["not a url"],
    [""],
  ])("%j is not linked", (url) => {
    expect(safeHttpUrl(url)).toBeNull();
  });

  it("https URL is linked", () => {
    expect(safeHttpUrl("https://docs.google.example/document/d/D_RUNBOOK")).toBe(
      "https://docs.google.example/document/d/D_RUNBOOK",
    );
  });

  it("http URL is linked", () => {
    expect(safeHttpUrl("http://merlionpay.slack.example/archives/C_ENG")).toBe(
      "http://merlionpay.slack.example/archives/C_ENG",
    );
  });
});

describe("stripCitationMarkers", () => {
  it("citation markers are removed without leaving double spaces", () => {
    expect(stripCitationMarkers("Blocked on the TLS cert [S1]. Fail over at 2% [S1][S2].")).toBe(
      "Blocked on the TLS cert. Fail over at 2%.",
    );
  });

  it("markers at the start and end of lines are removed and line breaks kept", () => {
    expect(stripCitationMarkers("[S2] Starts here\nnext line [S3]")).toBe("Starts here\nnext line");
  });

  it("text without markers is unchanged", () => {
    expect(stripCitationMarkers("No markers here.")).toBe("No markers here.");
  });

  it("square brackets that are not citation labels are kept", () => {
    expect(stripCitationMarkers("See ticket [PAY-412] and step [2].")).toBe("See ticket [PAY-412] and step [2].");
  });
});

describe("maskedSummary", () => {
  it("is null when nothing was masked (or the reader is a handler)", () => {
    expect(maskedSummary({})).toBeNull();
    expect(maskedSummary(undefined)).toBeNull();
    expect(maskedSummary({ card: 0 })).toBeNull();
  });

  it("totals the kinds and lists them in a stable order", () => {
    expect(maskedSummary({ phone: 2, card: 1, nric: 1 })).toEqual({ total: 4, text: "card 1, nric 1, phone 2" });
  });
});

describe("freshness", () => {
  const now = Date.parse("2026-10-09T10:00:00Z");

  it("is null for a source that never synced, e.g. seeded data", () => {
    expect(freshness(null, now)).toBeNull();
    expect(freshness(undefined, now)).toBeNull();
    expect(freshness("not a date", now)).toBeNull();
  });

  it("is fresh within 15 minutes, stale after", () => {
    expect(freshness("2026-10-09T09:57:00Z", now)).toEqual({ stale: false });
    expect(freshness("2026-10-09T09:45:00Z", now)).toEqual({ stale: false });
    expect(freshness("2026-10-09T09:44:59Z", now)).toEqual({ stale: true });
  });
});
