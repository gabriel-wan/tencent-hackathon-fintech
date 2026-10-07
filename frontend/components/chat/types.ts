import type { AnswerKind } from "@/lib/answers";
import type { QueryResponse } from "@/lib/api/types";

/** Why a question got no answer at all (as opposed to a "not found" answer). */
export type FailureKind = "badInput" | "notConfigured" | "unreachable" | "server";

/**
 * One question and what came back. Kept in browser memory only: never in
 * localStorage or sessionStorage, and wiped by the full page load on
 * sign-out or user switch (SECURITY.md T6).
 */
export type Exchange =
  | { id: string; question: string; status: "pending" }
  | { id: string; question: string; status: AnswerKind; response: QueryResponse }
  | { id: string; question: string; status: "failed"; failure: FailureKind };
