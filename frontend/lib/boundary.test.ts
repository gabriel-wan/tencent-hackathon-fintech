import { describe, expect, it } from "vitest";

import {
  type BoundaryEntry,
  STALE_AFTER_MS,
  blockedReason,
  filterRows,
  rowState,
  rowsFor,
  scopesProblem,
  stillSyncing,
  syncSnapshot,
} from "./boundary";

function entry(scope_id: string, last_synced_at: string | null, title = "", source = "slack"): BoundaryEntry {
  return { source, scope_id, scope_type: "channel", title, added_at: "2026-10-07T02:52:19Z", last_synced_at };
}

describe("scopesProblem", () => {
  it.each([
    [404, "connect slack first", "not-connected"],
    [401, "slack access expired: connect again", "reconnect"],
    [401, "slack refused the stored access: connect again", "reconnect"],
    [502, "slack API call failed", "tool-failed"],
  ])("%i %j is the tool's problem: %s", (status, detail, problem) => {
    expect(scopesProblem(status, detail)).toBe(problem);
  });

  it.each([
    [401, "Not signed in"], // the app's own session ended
    [502, "backend unreachable"], // the /api proxy: our server is down
    [504, "backend timed out"],
    [403, "Admins only"],
    [500, "Internal Server Error"],
    [401, "Session expired"], // a reworded sign-out: still "sign in again", never "reconnect"
    [404, "Not Found"], // e.g. the route renamed: an ordinary error, not "connect first"
  ])("%i %j is not, so the page handles it like any other call", (status, detail) => {
    expect(scopesProblem(status, detail)).toBeNull();
  });
});

describe("rowsFor", () => {
  const scopes = [
    { id: "C3", title: "#general" },
    { id: "C1", title: "#payments-oncall" },
    { id: "C2", title: "#payments" },
  ];

  it("lists the boundary first, then what the admin could add, each by name", () => {
    const rows = rowsFor("slack", scopes, [entry("C1", "2026-10-09T04:00:00Z", "#payments-oncall")]);
    expect(rows.map((r) => [r.title, r.inBoundary])).toEqual([
      ["#payments-oncall", true],
      ["#general", false],
      ["#payments", false],
    ]);
    expect(rows[0].lastSyncedAt).toBe("2026-10-09T04:00:00Z");
  });

  it("keeps an allowed scope the admin can no longer see, flagged", () => {
    const [row] = rowsFor("slack", scopes, [entry("C9", null, "#old-project")]);
    expect(row).toMatchObject({ id: "C9", title: "#old-project", inBoundary: true, visible: false });
  });

  it("shows only the boundary when the tool's list couldn't load, flagging nothing", () => {
    const rows = rowsFor("slack", null, [entry("C1", null, "#payments-oncall")]);
    expect(rows).toEqual([{ id: "C1", title: "#payments-oncall", inBoundary: true, lastSyncedAt: null, visible: true }]);
  });

  it("ignores other tools' entries", () => {
    expect(rowsFor("drive", [], [entry("C1", null)])).toEqual([]);
  });
});

describe("filterRows", () => {
  it("matches any part of the name, in any case", () => {
    const rows = rowsFor("slack", [{ id: "C1", title: "#Payments" }, { id: "C2", title: "#general" }], []);
    expect(filterRows(rows, " pay ").map((r) => r.id)).toEqual(["C1"]);
    expect(filterRows(rows, "")).toHaveLength(2);
  });
});

describe("rowState", () => {
  const now = Date.parse("2026-10-09T05:00:00Z");
  const row = (over: Partial<ReturnType<typeof rowsFor>[number]>) => ({
    id: "C1", title: "#x", inBoundary: true, lastSyncedAt: null, visible: true, ...over,
  });

  it.each([
    [{ inBoundary: false }, "outside"],
    [{ visible: false, lastSyncedAt: "2026-10-09T04:59:00Z" }, "unseen"],
    [{ lastSyncedAt: null }, "not-synced"],
    [{ lastSyncedAt: "2026-10-09T04:57:00Z" }, "synced"],
    [{ lastSyncedAt: new Date(now - STALE_AFTER_MS - 1000).toISOString() }, "stale"],
  ])("%j -> %s", (over, state) => {
    expect(rowState(row(over), now)).toBe(state);
  });

  it.each([["not-connected"], ["reconnect"]] as const)("a tool that is %s can't sync, whatever else", (problem) => {
    for (const over of [{ lastSyncedAt: null }, { lastSyncedAt: "2026-10-09T04:59:00Z" }, { visible: false }]) {
      expect(rowState(row(over), now, problem)).toBe(problem);
    }
    expect(rowState(row({ inBoundary: false }), now, problem)).toBe("outside");
  });

  it("a tool that didn't answer just now doesn't change the status", () => {
    expect(rowState(row({ lastSyncedAt: "2026-10-09T04:57:00Z" }), now, "tool-failed")).toBe("synced");
  });
});

describe("blockedReason", () => {
  const list = [{ id: "C1", title: "#payments-oncall" }];
  it.each([
    ["not-connected", "not-connected"],
    ["reconnect", "reconnect"],
    ["tool-failed", null],
    [null, null],
    [list, null],
    [[], "unseen"],
  ] as const)("list %j -> %j", (scopes, reason) => {
    expect(blockedReason(entry("C1", null), scopes as never)).toBe(reason);
  });
});

describe("stillSyncing", () => {
  it("is done when every allowed scope's last sync moved, whatever the clocks say", () => {
    const before = syncSnapshot([entry("C1", "2026-10-09T04:00:00Z"), entry("C2", null)]);
    const after = [entry("C1", "2026-10-09T04:00:31Z"), entry("C2", "2026-10-09T04:00:32Z")];
    expect(stillSyncing(before, after)).toEqual([]);
  });

  it("lists the scopes that haven't synced yet, including one added just before the sync", () => {
    const before = syncSnapshot([entry("C1", "2026-10-09T04:00:00Z"), entry("C2", null)]);
    const after = [entry("C1", "2026-10-09T04:00:00Z"), entry("C2", null)];
    expect(stillSyncing(before, after).map((b) => b.scope_id)).toEqual(["C1", "C2"]);
  });

  it("doesn't wait for scopes left out of the snapshot (they can't sync)", () => {
    const before = syncSnapshot([entry("C1", "2026-10-09T04:00:00Z")]);
    const after = [entry("C1", "2026-10-09T04:00:31Z"), entry("C9", null)];
    expect(stillSyncing(before, after)).toEqual([]);
  });
});
