import { describe, expect, it } from "vitest";

import { answerSummary, freshness, maskedSummary, safeHttpUrl, splitAnswer, stripCitationMarkers } from "./citations";

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

describe("answerSummary", () => {
  const now = Date.parse("2026-10-11T12:00:00Z");
  it("counts sources and merges masked kinds", () => {
    const s = answerSummary(
      [
        { redacted: { phone: 1, email: 2 }, synced_at: null },
        { redacted: { email: 1 }, synced_at: null },
        { redacted: {}, synced_at: null },
      ],
      now,
    );
    expect(s.sources).toBe(3);
    expect(s.masked).toEqual({ total: 4, text: "email 3, phone 1" });
    expect(s.oldestSync).toBeNull();
    expect(s.stale).toBe(false);
  });
  it("uses the oldest sync, and flags it stale after the window", () => {
    const s = answerSummary(
      [
        { redacted: {}, synced_at: "2026-10-11T11:58:00Z" },
        { redacted: {}, synced_at: "2026-10-11T11:30:00Z" },
        { redacted: {}, synced_at: "not a date" },
      ],
      now,
    );
    expect(s.oldestSync).toBe("2026-10-11T11:30:00Z");
    expect(s.stale).toBe(true);
    expect(s.masked).toBeNull();
  });
  it("is empty for no citations", () => {
    expect(answerSummary([], now)).toEqual({ sources: 0, masked: null, oldestSync: null, stale: false });
  });
});

describe("splitAnswer", () => {
  it("numbers markers by the citation's place in the list, not by its label", () => {
    // The backend listed S2 first, so S2 is source 1 and S1 is source 2.
    expect(splitAnswer("Tests Friday [S1]. Blocked [S2].", ["S2", "S1"])).toEqual([
      { kind: "text", text: "Tests Friday" },
      { kind: "cite", n: 2 },
      { kind: "text", text: ". Blocked" },
      { kind: "cite", n: 1 },
      { kind: "text", text: "." },
    ]);
  });
  it("keeps a run of markers, without repeating one", () => {
    expect(splitAnswer("Blocked [S1][S3][S3].", ["S1", "S3"])).toEqual([
      { kind: "text", text: "Blocked" },
      { kind: "cite", n: 1 },
      { kind: "cite", n: 2 },
      { kind: "text", text: "." },
    ]);
  });
  it("drops markers no citation has, and leaves other brackets as text", () => {
    expect(splitAnswer("See [S9] and [card ending 1111] [S1]", ["S1"])).toEqual([
      { kind: "text", text: "See and [card ending 1111]" },
      { kind: "cite", n: 1 },
    ]);
  });
  it("keeps markup as plain text", () => {
    expect(splitAnswer("<b>x</b> [S1]", ["S1"])).toEqual([
      { kind: "text", text: "<b>x</b>" },
      { kind: "cite", n: 1 },
    ]);
  });
  it("handles an answer that starts with a marker and line breaks", () => {
    expect(splitAnswer("[S1] Failover.\n\nNext [S1].", ["S1"])).toEqual([
      { kind: "cite", n: 1 },
      { kind: "text", text: " Failover.\n\nNext" },
      { kind: "cite", n: 1 },
      { kind: "text", text: "." },
    ]);
  });
});
