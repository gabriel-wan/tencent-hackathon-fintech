import { describe, expect, it } from "vitest";

import { NOT_FOUND_ANSWER, UNAVAILABLE_ANSWER } from "@/lib/answers";

import { ApiError, BackendUnreachableError, NotSignedInError } from "./errors";
import { isMockEnabled, mockAnswer, mockAudit, MOCK_AUDIT_ID } from "./mock";

describe("isMockEnabled", () => {
  it("is false in production even when the variable is set", () => {
    expect(isMockEnabled("1", "production")).toBe(false);
  });

  it("is true in development when the variable is 1", () => {
    expect(isMockEnabled("1", "development")).toBe(true);
  });

  it.each([[undefined], [""], ["0"], ["true"]])("is false in development when the variable is %j", (flag) => {
    expect(isMockEnabled(flag, "development")).toBe(false);
  });
});

describe("mockAnswer", () => {
  it("question without a keyword returns the answered fixture", async () => {
    const reply = await mockAnswer("what is blocking the migration? mock:fast");
    expect(reply.citations.length).toBeGreaterThan(0);
    expect(reply.audit_id).toBe(MOCK_AUDIT_ID);
  });

  it("mock:not-found returns the backend's exact not-found sentence", async () => {
    expect((await mockAnswer("mock:not-found mock:fast")).answer).toBe(NOT_FOUND_ANSWER);
  });

  it("mock:unavailable returns the backend's exact unavailable sentence", async () => {
    expect((await mockAnswer("mock:unavailable mock:fast")).answer).toBe(UNAVAILABLE_ANSWER);
  });

  it("mock:shield has a source with masked identifiers, recently synced", async () => {
    const [source] = (await mockAnswer("mock:shield mock:fast")).citations;
    expect(source.redacted).toEqual({ card: 1, name: 1, phone: 2 });
    expect(source.synced_at).not.toBeNull();
  });

  it("mock:injection reports a removed instruction, on a real answer", async () => {
    const reply = await mockAnswer("mock:injection mock:fast");
    expect(reply.instructions_removed).toBe(1);
    expect(reply.citations.length).toBeGreaterThan(0);
    expect(reply.audit_id).toBe(MOCK_AUDIT_ID); // still marked as mock
  });

  it("mock:no-citations is not read as a shorter keyword", async () => {
    expect((await mockAnswer("mock:no-citations mock:fast")).citations).toEqual([]);
  });

  it.each([
    ["mock:401", NotSignedInError],
    ["mock:422", ApiError],
    ["mock:503", ApiError],
    ["mock:offline", BackendUnreachableError],
  ])("%s throws the matching error", async (keyword, ErrorType) => {
    await expect(mockAnswer(`${keyword} mock:fast`)).rejects.toBeInstanceOf(ErrorType);
  });
});

describe("mockAudit", () => {
  it("answers with citations to records, never audited", async () => {
    const reply = await mockAudit("what did ben do? mock:fast");
    expect(reply.status).toBe("answered");
    expect(reply.audit_id).toBe(MOCK_AUDIT_ID);
    for (const c of reply.citations) expect(reply.answer).toContain(`[${c.label}]`);
    expect(reply.facts?.matches).toBe(3);
  });

  it("covers every state", async () => {
    expect((await mockAudit("mock:clarify mock:fast")).choices).toHaveLength(2);
    expect((await mockAudit("mock:no-records mock:fast")).status).toBe("no_records");
    expect((await mockAudit("mock:unavailable mock:fast")).facts).toBeNull();
    await expect(mockAudit("mock:offline mock:fast")).rejects.toThrow();
  });
});
