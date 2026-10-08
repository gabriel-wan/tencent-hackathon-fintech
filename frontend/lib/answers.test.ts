import { describe, expect, it } from "vitest";

import { classifyAnswer, NOT_FOUND_ANSWER, UNAVAILABLE_ANSWER } from "./answers";

describe("classifyAnswer", () => {
  it("fixed not-found sentence is classified as not found", () => {
    expect(classifyAnswer({ answer: NOT_FOUND_ANSWER })).toBe("notFound");
  });

  it("fixed not-found sentence with surrounding whitespace is still not found", () => {
    expect(classifyAnswer({ answer: `  ${NOT_FOUND_ANSWER}\n` })).toBe("notFound");
  });

  it("fixed unavailable sentence is classified as unavailable", () => {
    expect(classifyAnswer({ answer: UNAVAILABLE_ANSWER })).toBe("unavailable");
  });

  it("ordinary answer is classified as answered", () => {
    expect(classifyAnswer({ answer: "The migration is blocked on the TLS certificate [S1]." })).toBe("answered");
  });

  it("an answer that only mentions the not-found wording is not mistaken for it", () => {
    expect(classifyAnswer({ answer: `Note: ${NOT_FOUND_ANSWER} was the earlier reply [S1].` })).toBe("answered");
  });

  it("fixed sentences match the backend wording exactly", () => {
    // backend/app/llm/grounding.py and backend/app/pipeline/query.py
    expect(NOT_FOUND_ANSWER).toBe("I could not find this in the sources you have access to.");
    expect(UNAVAILABLE_ANSWER).toBe("The assistant is unavailable right now. Please try again shortly.");
  });
});
