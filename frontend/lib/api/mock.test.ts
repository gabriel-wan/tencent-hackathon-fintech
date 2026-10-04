import { describe, expect, it } from "vitest";

import { NOT_FOUND_ANSWER, UNAVAILABLE_ANSWER } from "@/lib/answers";

import { ApiError, BackendUnreachableError, NotSignedInError } from "./errors";
import { isMockEnabled, mockAnswer, MOCK_AUDIT_ID } from "./mock";

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
