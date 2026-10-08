/**
 * MOCK DATA for the audit page's design preview (development only).
 *
 * The real audit API now exists (GET /api/admin/audit and POST
 * /api/admin/audit/verify, backend/app/audit/api.py); these fixtures stay only
 * until /admin/audit is wired to it. The payload keys copy what
 * backend/app/pipeline/query.py writes, so wiring the real API should mostly be
 * a swap. Documents are shown by key only: whether the page may show titles of
 * restricted documents is an open team decision.
 */

export type AuditDecision = { document: string; allowed: boolean; reason: string };

export type MockAuditRecord = {
  id: number;
  ts: string;
  event_type: "query";
  payload: {
    user_email: string;
    role: "admin" | "user";
    question: string;
    search_mode: string;
    live_check_mode: string;
    candidates: AuditDecision[];
    restricted_matches: { document: string; reason: string }[];
    sent_to_llm: string[];
    llm_called: boolean;
    model?: string;
    answer: string;
    citations: string[];
  };
};

const NOT_FOUND = "I could not find this in the sources you have access to.";
const STUB = "stub: stored ACL, not live";

export const MOCK_AUDIT_RECORDS: MockAuditRecord[] = [
  {
    id: 10,
    ts: "2026-10-04T10:21:40Z",
    event_type: "query",
    payload: {
      user_email: "charlie@contractor.example",
      role: "user",
      question: "What happened in the Q3 security incident?",
      search_mode: "hybrid",
      live_check_mode: STUB,
      candidates: [],
      restricted_matches: [
        { document: "slack:C_SECURITY:1727913800.000300", reason: "user not in document ACL" },
        { document: "drive:D_Q3_INCIDENT", reason: "user not in document ACL" },
      ],
      sent_to_llm: [],
      llm_called: false,
      answer: NOT_FOUND,
      citations: [],
    },
  },
  {
    id: 9,
    ts: "2026-10-04T10:21:10Z",
    event_type: "query",
    payload: {
      user_email: "priya@merlionpay.example",
      role: "admin",
      question: "What happened in the Q3 security incident?",
      search_mode: "hybrid",
      live_check_mode: STUB,
      candidates: [
        { document: "slack:C_SECURITY:1727913800.000300", allowed: true, reason: "allowed by slack check" },
        { document: "drive:D_Q3_INCIDENT", allowed: true, reason: "allowed by drive check" },
      ],
      restricted_matches: [],
      sent_to_llm: ["slack:C_SECURITY:1727913800.000300", "drive:D_Q3_INCIDENT"],
      llm_called: true,
      model: "hy3",
      answer:
        "A credential stuffing attack targeted the merchant portal between August 14 and 16 [S2]. 312 merchant accounts were reset [S1][S2].",
      citations: ["slack:C_SECURITY:1727913800.000300", "drive:D_Q3_INCIDENT"],
    },
  },
  {
    id: 7,
    ts: "2026-10-04T10:12:05Z",
    event_type: "query",
    payload: {
      user_email: "alice@merlionpay.example",
      role: "user",
      question: "What are the salary bands?",
      search_mode: "hybrid",
      live_check_mode: STUB,
      candidates: [],
      restricted_matches: [{ document: "drive:D_SALARY", reason: "outside admin boundary" }],
      sent_to_llm: [],
      llm_called: false,
      answer: NOT_FOUND,
      citations: [],
    },
  },
  {
    id: 4,
    ts: "2026-10-04T10:11:30Z",
    event_type: "query",
    payload: {
      user_email: "ben@merlionpay.example",
      role: "user",
      question: "What's blocking the payment gateway migration?",
      search_mode: "hybrid",
      live_check_mode: STUB,
      candidates: [
        { document: "slack:C_ENG:1727827400.000200", allowed: true, reason: "allowed by slack check" },
        { document: "drive:D_RUNBOOK", allowed: true, reason: "allowed by drive check" },
      ],
      restricted_matches: [{ document: "slack:C_PAYONCALL:1727741000.000100", reason: "user not in document ACL" }],
      sent_to_llm: ["slack:C_ENG:1727827400.000200", "drive:D_RUNBOOK"],
      llm_called: true,
      model: "hy3",
      answer: NOT_FOUND,
      citations: [],
    },
  },
];
