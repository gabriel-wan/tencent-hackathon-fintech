/**
 * MOCK MODE (development only). Fake replies for POST /api/query, so the chat
 * states can be built without spending LLM tokens and states that cannot be
 * triggered on demand (unavailable, network error) can be seen. Everything
 * else (sign-in, /api/me, dev routes) stays real.
 *
 * On when NEXT_PUBLIC_API_MOCK=1 in frontend/.env AND this is not a
 * production build, so it can never run in Docker images or on the live site.
 * Whenever it is on, the header shows a MOCK DATA badge (AGENTS.md §2.5).
 * Content is fictional (the MerlionPay seed world).
 */
import { NOT_FOUND_ANSWER, UNAVAILABLE_ANSWER } from "@/lib/answers";

import { ApiError, BackendUnreachableError, NotSignedInError } from "./errors";
import type { Citation, QueryResponse } from "./types";

// Default arguments keep the literal process.env.NEXT_PUBLIC_API_MOCK
// reference, which Next.js inlines at build time.
export function isMockEnabled(
  flag: string | undefined = process.env.NEXT_PUBLIC_API_MOCK,
  nodeEnv: string | undefined = process.env.NODE_ENV,
): boolean {
  return flag === "1" && nodeEnv !== "production";
}

/** Mocked answers carry audit_id 0: they were never audited. */
export const MOCK_AUDIT_ID = 0;

export function isMockResponse(response: Pick<QueryResponse, "audit_id">): boolean {
  return isMockEnabled() && response.audit_id === MOCK_AUDIT_ID;
}

export const MOCK_DELAY_MS = 6_000;

const SLACK_ONCALL: Citation = {
  id: "slack:C_PAYONCALL:1727741000.000100",
  title: "#payments-oncall",
  url: "https://merlionpay.slack.example/archives/C_PAYONCALL/p1727741000000100",
  source: "slack",
  updated_at: "2026-10-02T09:14:00Z",
  synced_at: null, // like seeded data: never synced from a real tool
};
const DRIVE_RUNBOOK: Citation = {
  id: "drive:D_RUNBOOK",
  title: "Payments on-call runbook",
  url: "https://docs.google.example/document/d/D_RUNBOOK",
  source: "drive",
  updated_at: "2026-10-02T13:00:00Z",
  synced_at: null, // like seeded data: never synced from a real tool
};
const SLACK_ENG: Citation = {
  id: "slack:C_ENG:1727827400.000200",
  title: "#eng",
  url: "https://merlionpay.slack.example/archives/C_ENG/p1727827400000200",
  source: "slack",
  updated_at: "2026-10-02T13:30:00Z",
  synced_at: null, // like seeded data: never synced from a real tool
};
const JIRA_TICKET: Citation = {
  id: "jira:PAY-412",
  title: "PAY-412 Migrate to the new payment gateway",
  url: "https://merlionpay.atlassian.example/browse/PAY-412",
  source: "jira",
  updated_at: "2026-09-30T08:00:00Z",
  synced_at: null, // like seeded data: never synced from a real tool
};
const CONFLUENCE_DOC: Citation = {
  id: "confluence:98765",
  title: "Gateway migration decision record",
  url: "https://merlionpay.atlassian.example/wiki/spaces/ENG/pages/98765",
  source: "confluence",
  updated_at: "2026-09-28T10:00:00Z",
  synced_at: null, // like seeded data: never synced from a real tool
};

function reply(answer: string, citations: Citation[]): QueryResponse {
  return { answer, citations, audit_id: MOCK_AUDIT_ID };
}

type Fixture = () => QueryResponse;

const FIXTURES: Record<string, Fixture> = {
  answered: () =>
    reply(
      "The payment gateway migration (PAY-412) is blocked: the vendor has not rotated the TLS certificate " +
        "for the new gateway yet [S1]. The on-call runbook says to fail over to the secondary acquirer if the " +
        "authorisation error rate exceeds 2% for 5 minutes [S2].",
      [SLACK_ONCALL, DRIVE_RUNBOOK],
    ),
  long: () =>
    reply(
      [
        "The migration to the new payment gateway (PAY-412) is blocked on the vendor's TLS certificate " +
          "rotation, which the vendor expects on Thursday [S1][S3].",
        "After the rotation the team needs one day of sandbox testing before cutover [S1]. The decision record " +
          "explains why the new gateway was chosen and lists the rollback plan [S4].",
        "During the cutover window, on-call engineers follow runbook v12: check the payments dashboard, page " +
          "the on-call engineer, confirm the gateway status page, and fail over to the secondary acquirer if " +
          "the authorisation error rate exceeds 2% for 5 minutes [S2].",
        "The ledger database migration also runs on Saturday at 2am, so the two changes should not overlap [S5].",
      ].join("\n\n"),
      [SLACK_ONCALL, DRIVE_RUNBOOK, JIRA_TICKET, CONFLUENCE_DOC, SLACK_ENG],
    ),
  markers: () =>
    reply("Step one is the dashboard [S1]. Step two pages on-call [S1][S2].\n[S2] Failover is step four.", [
      DRIVE_RUNBOOK,
      SLACK_ONCALL,
    ]),
  "bad-url": () =>
    reply("This source's URL is not http(s), so it must be shown as plain text, not a link [S1].", [
      { ...DRIVE_RUNBOOK, title: "Source with a javascript: URL", url: "javascript:alert('mock')" },
      SLACK_ENG,
    ]),
  "no-citations": () => reply("This answer arrived without citations (should not happen).", []),
  "not-found": () => reply(NOT_FOUND_ANSWER, []),
  unavailable: () => reply(UNAVAILABLE_ANSWER, []),
};

const ERRORS: Record<string, () => Error> = {
  "401": () => new NotSignedInError(),
  "422": () => new ApiError(422, "String should have at most 2000 characters"),
  "503": () => new ApiError(503, "LLM is not configured"),
  offline: () => new BackendUnreachableError(),
};

function keywordIn(question: string): string {
  const keys = [...Object.keys(FIXTURES), ...Object.keys(ERRORS)];
  // Longest first, so "mock:no-citations" is not read as something shorter.
  const found = keys.sort((a, b) => b.length - a.length).find((key) => question.includes(`mock:${key}`));
  return found ?? "answered";
}

/** A fake POST /api/query. "mock:<state>" in the question picks the state; "mock:fast" skips the delay. */
export async function mockAnswer(question: string): Promise<QueryResponse> {
  if (!question.includes("mock:fast")) await new Promise((resolve) => setTimeout(resolve, MOCK_DELAY_MS));
  const key = keywordIn(question);
  if (key in ERRORS) throw ERRORS[key]();
  return FIXTURES[key]();
}
