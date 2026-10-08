// The backend's fixed replies, copied exactly. If the backend wording changes,
// this is the only file to update.
// ASSUMPTION: matching on text until the backend returns a status field
// (an open request to the query pipeline; see the frontend README's open questions).
import type { QueryResponse } from "@/lib/api/types";

/** backend/app/llm/grounding.py FALLBACK_ANSWER. Same reply whether nothing exists or nothing is permitted (INV-5). */
export const NOT_FOUND_ANSWER = "I could not find this in the sources you have access to.";

/** backend/app/pipeline/query.py UNAVAILABLE_ANSWER: the LLM call failed. */
export const UNAVAILABLE_ANSWER = "The assistant is unavailable right now. Please try again shortly.";

export type AnswerKind = "answered" | "notFound" | "unavailable";

export function classifyAnswer(response: Pick<QueryResponse, "answer">): AnswerKind {
  const answer = response.answer.trim();
  if (answer === NOT_FOUND_ANSWER) return "notFound";
  if (answer === UNAVAILABLE_ANSWER) return "unavailable";
  // An answer with no citations should not happen (the backend turns it into
  // NOT_FOUND_ANSWER). If it does, it is still shown, with "No sources
  // returned", rather than hidden.
  return "answered";
}
