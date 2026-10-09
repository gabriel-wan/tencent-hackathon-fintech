import { describe, expect, it } from "vitest";

import {
  type AuditRecord,
  NO_FILTERS,
  filtersFromParams,
  isStubCheck,
  pageUrl,
  recordFromParams,
  summarise,
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
