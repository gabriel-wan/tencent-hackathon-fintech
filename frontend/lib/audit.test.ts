import { describe, expect, it } from "vitest";

import {
  type AuditRecord,
  NO_FILTERS,
  documentRows,
  eventLabel,
  filtersFromParams,
  formatMs,
  hasMaskedValues,
  isStubCheck,
  liveCheckLabel,
  pageUrl,
  recordFromParams,
  searchLabel,
  summarise,
  timingRows,
  toApiQuery,
  toPageQuery,
} from "./audit";

function record(event_type: string, payload: Record<string, unknown>): AuditRecord {
  return { id: 7, ts: "2026-10-09T02:00:00Z", user_email: "priya@co.example", event_type, payload, prev_hash: "", hash: "" };
}

describe("summarise", () => {
  it("a question that was answered", () => {
    const r = record("query", {
      question: "What is blocking the migration?",
      sent_to_llm: ["slack:C1:1", "drive:D1"],
      restricted_matches: [{ document: "drive:D2", reason: "user not in document ACL" }],
      citations: ["slack:C1:1"],
    });
    expect(summarise(r)).toBe('Asked "What is blocking the migration?" · 2 sent to the LLM · 1 restricted · answered');
  });

  it("a question with nothing allowed", () => {
    const r = record("query", { question: "Salary bands?", sent_to_llm: [], restricted_matches: [], citations: [] });
    expect(summarise(r)).toBe('Asked "Salary bands?" · 0 sent to the LLM · not found');
  });

  it("a question whose LLM call failed", () => {
    const r = record("query", { question: "Hi", sent_to_llm: ["drive:D1"], llm_error: "TimeoutError", citations: [] });
    expect(summarise(r)).toBe('Asked "Hi" · 1 sent to the LLM · LLM failed');
  });

  it("a question checked against stored permissions says so", () => {
    const r = record("query", { question: "Hi", sent_to_llm: [], citations: [], live_check_mode: "stub: stored ACL, not live" });
    expect(summarise(r)).toBe('Asked "Hi" · 0 sent to the LLM · not found · not live-checked');
  });

  it("an older question record without the newer fields", () => {
    expect(summarise(record("query", { question: "Hi" }))).toBe('Asked "Hi" · not found');
  });

  it.each([
    ["boundary_added", { source: "slack", scope_id: "C1", title: "#eng" }, "Added #eng (Slack) to the boundary"],
    ["boundary_removed", { source: "drive", scope_id: "F1" }, "Removed F1 (Google Drive) from the boundary"],
    ["connector_connected", { provider: "slack", made_admin: true }, "Connected Slack and became admin"],
    ["connector_connected", { provider: "google", made_admin: false }, "Connected Google"],
    ["connector_disconnected", { provider: "atlassian" }, "Disconnected Atlassian"],
    ["sync_requested", { company_id: 2 }, "Asked for a sync now"],
    ["audit_searched", { filters: {}, results: 1 }, "Searched the audit trail (1 result)"],
    ["audit_verified", { ok: true, checked: 214 }, "Verified the chain: intact (214 records)"],
    ["audit_verified", { ok: false, checked: 214, first_broken_id: 90 }, "Verified the chain: broken at #90"],
    ["something_new", {}, "something_new"],
  ])("%s", (type, payload, line) => {
    expect(summarise(record(type, payload))).toBe(line);
  });
});

describe("timingRows", () => {
  it("lists the steps in pipeline order, total last", () => {
    expect(timingRows({ total: 2786, llm: 1633, embed: 864, search: 10, live_check: 280 })).toEqual([
      { step: "Embed", ms: 864, total: false },
      { step: "Search", ms: 10, total: false },
      { step: "Live check", ms: 280, total: false },
      { step: "LLM", ms: 1633, total: false },
      { step: "Total", ms: 2786, total: true },
    ]);
  });

  it("skips missing steps and puts unknown ones before the total, by name", () => {
    expect(timingRows({ total: 12, search: 4, rerank_step: 3 }).map((r) => r.step)).toEqual(["Search", "Rerank step", "Total"]);
  });

  it("is empty for an older record without timings", () => {
    expect(timingRows(undefined)).toEqual([]);
  });

  it("formats with a thousands separator", () => {
    expect(formatMs(1633.4)).toBe("1,633 ms");
  });
});

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

describe("plain-word labels", () => {
  it.each([
    ["live: each source, as the user", "Live, with each tool", "live"],
    ["stub: stored ACL, not live", "Stored permissions (development only)", "stub"],
    ["connector checks", "connector checks", "other"],
  ])("live check %j", (mode, text, kind) => {
    expect(liveCheckLabel(mode)).toEqual({ text, kind });
  });

  it("search and event names", () => {
    expect([searchLabel("hybrid"), searchLabel("keyword_only"), searchLabel("odd")]).toEqual([
      "Keyword + meaning",
      "Keyword only",
      "odd",
    ]);
    expect([eventLabel("query"), eventLabel("boundary_removed"), eventLabel("something_new")]).toEqual([
      "Question",
      "Boundary: removed",
      "something_new",
    ]);
  });
});

describe("documentRows", () => {
  const p = {
    candidates: [
      { document: "drive:D_GUIDE", allowed: true, reason: "allowed by drive check" },
      { document: "slack:C_ENG:1", allowed: true, reason: "allowed by slack check" },
      { document: "drive:D_DISPUTES", allowed: true, reason: "allowed by drive check" },
      { document: "slack:C_OLD:1", allowed: false, reason: "denied by slack check" },
    ],
    restricted_matches: [{ document: "slack:C_PAYONCALL:1", reason: "user not in document ACL" }],
    sent_to_llm: ["slack:C_ENG:1", "drive:D_DISPUTES"],
    citations: ["drive:D_DISPUTES"],
    redactions: {
      "drive:D_DISPUTES": { need_to_know: false, masked: { card: 1, name: 1 } },
      "slack:C_ENG:1": { need_to_know: true, masked: {} },
    },
    injection: { question: [], sources: [{ document: "slack:C_ENG:1", rules: ["override"], removed: 1 }] },
  };

  it("orders sent (by label), allowed but not sent, denied, then restricted matches", () => {
    expect(documentRows(p).map((r) => [r.document, r.allowed, r.sentAs])).toEqual([
      ["slack:C_ENG:1", true, 1],
      ["drive:D_DISPUTES", true, 2],
      ["drive:D_GUIDE", true, null],
      ["slack:C_OLD:1", false, null],
      ["slack:C_PAYONCALL:1", false, null],
    ]);
  });

  it("puts each note on its own document", () => {
    const [eng, disputes, guide, , restricted] = documentRows(p);
    expect(eng).toMatchObject({ cited: false, handler: true, masked: null, injection: { removed: 1, rules: ["override"] } });
    expect(disputes).toMatchObject({ cited: true, handler: false, masked: { card: 1, name: 1 }, injection: null });
    expect(guide).toMatchObject({ masked: null, handler: false, injection: null });
    expect(restricted.reason).toBe("user not in document ACL");
  });

  it("lists a document once even if two lists name it, and reads an older record", () => {
    expect(documentRows({ candidates: [{ document: "a", allowed: false, reason: "x" }], restricted_matches: [{ document: "a", reason: "y" }] })).toHaveLength(1);
    expect(documentRows({})).toEqual([]);
  });
});

describe("isStubCheck", () => {
  it.each([
    ["stub: stored ACL, not live", true],
    ["live: each source, as the user", false],
    ["connector checks", false],
    [undefined, false],
  ])("%j -> %j", (mode, stub) => {
    expect(isStubCheck({ live_check_mode: mode })).toBe(stub);
  });
});

describe("filtersFromParams", () => {
  it("reads the page's URL and drops malformed values", () => {
    expect(
      filtersFromParams({ user: " alice@co.example ", from: "2026-10-01", to: "yesterday", source: "dropbox", event_type: ["query", "x"] }),
    ).toEqual({ ...NO_FILTERS, user: "alice@co.example", from: "2026-10-01", event_type: "query" });
  });
});

describe("filtersFromParams, event types", () => {
  it("keeps a type the backend doesn't list yet, but drops one the API would refuse", () => {
    expect(filtersFromParams({ event_type: "something_new" }).event_type).toBe("something_new");
    expect(filtersFromParams({ event_type: "Not-A-Type" }).event_type).toBe("");
  });
});

describe("toPageQuery", () => {
  it("keeps only the filters that are set", () => {
    expect(toPageQuery({ ...NO_FILTERS, user: "alice@co.example", source: "jira" })).toBe("user=alice%40co.example&source=jira");
  });
});

describe("the open record in the URL", () => {
  it.each([
    [{ record: "56" }, 56],
    [{ record: ["7", "8"] }, 7],
    [{ record: "0" }, null],
    [{ record: "-3" }, null],
    [{ record: "12abc" }, null],
    [{}, null],
  ])("%j -> %j", (params, id) => {
    expect(recordFromParams(params)).toBe(id);
  });

  it("builds the page URL with the filters and the open record", () => {
    expect(pageUrl(NO_FILTERS)).toBe("/admin/audit");
    expect(pageUrl({ ...NO_FILTERS, user: "alice@co.example" }, 56)).toBe("/admin/audit?user=alice%40co.example&record=56");
  });
});

describe("toApiQuery", () => {
  it("sends nothing for no filters", () => {
    expect(toApiQuery(NO_FILTERS)).toBe("");
  });

  it("turns days into a range that includes the whole 'to' day", () => {
    const query = new URLSearchParams(toApiQuery({ ...NO_FILTERS, from: "2026-10-01", to: "2026-10-08" }));
    expect(query.get("since")).toBe(new Date(2026, 9, 1).toISOString());
    expect(query.get("until")).toBe(new Date(2026, 9, 9).toISOString());
  });

  it("sends scope_id only with its source", () => {
    expect(toApiQuery({ ...NO_FILTERS, scope_id: "C1" })).toBe("");
    expect(toApiQuery({ ...NO_FILTERS, source: "slack", scope_id: "C1" })).toBe("source=slack&scope_id=C1");
  });

  it("adds the page cursor and size", () => {
    expect(toApiQuery({ ...NO_FILTERS, event_type: "query" }, { beforeId: 41, limit: 1 })).toBe(
      "event_type=query&before_id=41&limit=1",
    );
  });
});
