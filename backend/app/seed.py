"""DEVELOPMENT SEED DATA. Fictional company, people and content. Not connector data.

Gives Task 2 and Task 3 rows to work against before the connectors land.
Each document exercises one permission case:

  #payments-oncall   private Slack channel: Alice and Priya only
  #eng               public Slack channel: every full member, not guests
  #security-incidents private Slack channel: Priya only
  Payments runbook   Drive, shared with the whole company domain
  Q3 incident report Drive, shared with Priya only
  Contractor guide   Drive, shared with the domain and with Charlie
  Salary bands       Drive, company-wide BUT in a folder outside the admin boundary
  Dispute log        Drive, company-wide; its customer data is unmasked for Priya only (ADR-010)
  Card in Slack      #payments-oncall thread: card and phone masked for everyone (Slack names no handler)

A second company, Kopi Labs, shares the database. Its #general thread is open to
every Slack member, which Alice also is in her own company: she must never see it
(company isolation).

Run:  docker compose run --rm backend python -m app.seed [--embed]
--embed also computes embeddings through TokenHub (needs LLM_* settings and an
API key allowed to use the embedding model).
"""
import hashlib
import json
import os
import sys

from sqlalchemy import text

from app.db import engine

DOMAIN = "merlionpay.example"

USERS = [
    # email, name, is_admin, principals
    ("alice@merlionpay.example", "Alice Tan (payments engineer)", False,
     ["slack:user:U001", "slack:members", "google:user:alice@merlionpay.example", f"google:domain:{DOMAIN}"]),
    ("ben@merlionpay.example", "Ben Lim (backend engineer)", False,
     ["slack:user:U002", "slack:members", "google:user:ben@merlionpay.example", f"google:domain:{DOMAIN}"]),
    ("charlie@contractor.example", "Charlie Ng (external contractor)", False,
     ["slack:user:U003", "google:user:charlie@contractor.example"]),  # Slack guest: no slack:members
    ("priya@merlionpay.example", "Priya Nair (admin and compliance)", True,
     ["slack:user:U004", "slack:members", "google:user:priya@merlionpay.example", f"google:domain:{DOMAIN}"]),
]

BOUNDARY = [
    # source, scope_id, scope_type, title
    ("slack", "C_PAYONCALL", "channel", "#payments-oncall"),
    ("slack", "C_ENG", "channel", "#eng"),
    ("slack", "C_SECURITY", "channel", "#security-incidents"),
    ("drive", "F_ENG", "folder", "Engineering"),
    ("drive", "F_SEC", "folder", "Security"),
    # F_HR deliberately NOT in the boundary.
]

DOCUMENTS = [
    # source, source_id, scope_id, title, url, updated_at, acl, text
    ("slack", "C_PAYONCALL:1727741000.000100", "C_PAYONCALL", "#payments-oncall",
     "https://merlionpay.slack.example/archives/C_PAYONCALL/p1727741000000100", "2026-10-02T09:14:00Z",
     ["slack:user:U001", "slack:user:U004"],
     "Alice: The payment gateway migration (PAY-412) is blocked. The vendor has not rotated the TLS "
     "certificate for the new gateway yet.\nPriya: Vendor says the certificate rotation lands Thursday. "
     "After that we need one day of sandbox testing before cutover."),
    ("slack", "C_ENG:1727827400.000200", "C_ENG", "#eng",
     "https://merlionpay.slack.example/archives/C_ENG/p1727827400000200", "2026-10-02T13:30:00Z",
     ["slack:members"],
     "Ben: Reminder, the ledger database migration runs Saturday at 2am.\nAlice: The payments on-call "
     "runbook now includes the failover step for the secondary acquirer."),
    ("slack", "C_SECURITY:1727913800.000300", "C_SECURITY", "#security-incidents",
     "https://merlionpay.slack.example/archives/C_SECURITY/p1727913800000300", "2026-10-03T08:00:00Z",
     ["slack:user:U004"],
     "Priya: Q3 incident post-review is done. Root cause was credential stuffing against the merchant "
     "portal; 312 merchant accounts were reset. Full report is in the Security folder."),
    ("drive", "D_RUNBOOK", "F_ENG", "Payments on-call runbook",
     "https://docs.google.example/document/d/D_RUNBOOK", "2026-10-02T13:00:00Z",
     [f"google:domain:{DOMAIN}"],
     "Payments on-call runbook v12.\nStep 1: check the payments dashboard.\nStep 2: page the on-call "
     "engineer.\nStep 3: confirm the gateway status page.\nStep 4: if the authorisation error rate exceeds "
     "2% for 5 minutes, fail over to the secondary acquirer."),
    ("drive", "D_Q3_INCIDENT", "F_SEC", "Q3 security incident report",
     "https://docs.google.example/document/d/D_Q3_INCIDENT", "2026-10-03T07:00:00Z",
     ["google:user:priya@merlionpay.example"],
     "Q3 security incident report. Credential stuffing attack against the merchant portal between 14 and "
     "16 August. 312 merchant accounts reset. Remediation: rate limiting and mandatory 2FA for merchants."),
    ("drive", "D_CONTRACTOR_GUIDE", "F_ENG", "Contractor onboarding guide",
     "https://docs.google.example/document/d/D_CONTRACTOR_GUIDE", "2026-09-20T10:00:00Z",
     [f"google:domain:{DOMAIN}", "google:user:charlie@contractor.example"],
     "Contractor onboarding guide. Contractors get access to the Engineering Drive folder and the "
     "#contractors Slack channel only. Raise access requests with Priya."),
    ("slack", "C_PAYONCALL:1727845000.000400", "C_PAYONCALL", "#payments-oncall",
     "https://merlionpay.slack.example/archives/C_PAYONCALL/p1727845000000400", "2026-10-02T15:10:00Z",
     ["slack:user:U001", "slack:user:U004"],
     "Alice: Customer called about a failed top-up on card 5555 5555 5555 4444, wants a callback on "
     "8123 4567.\nPriya: Raise it in the dispute log, I will handle the refund."),
    ("drive", "D_DISPUTES", "F_ENG", "Customer dispute log",
     "https://docs.google.example/document/d/D_DISPUTES", "2026-10-03T09:30:00Z",
     [f"google:domain:{DOMAIN}"],
     "Customer dispute log, owned by Priya.\nDispute 118, customer: Jane Lee (jane.lee@example.com, +65 9123 4567, "
     "NRIC S1234567D) was double-charged S$42.50 on card 4111 1111 1111 1111 for a top-up. "
     "Refund approved to account no. 123-45678-9."),
    ("drive", "D_SALARY", "F_HR", "Salary bands 2026",
     "https://docs.google.example/document/d/D_SALARY", "2026-09-01T10:00:00Z",
     [f"google:domain:{DOMAIN}"],
     "Salary bands 2026 for all engineering levels. This folder is outside the admin boundary, so it must "
     "never appear in an answer."),
]

NEED_TO_KNOW = {"D_DISPUTES": ["google:user:priya@merlionpay.example"]}

KOPI = "kopilabs.example"

KOPI_USERS = [
    ("dana@kopilabs.example", "Dana Koh (Kopi Labs engineer)", False,
     ["slack:user:U101", "slack:members", "google:user:dana@kopilabs.example", f"google:domain:{KOPI}"]),
]

KOPI_BOUNDARY = [("slack", "C_GENERAL", "channel", "#general")]

KOPI_DOCUMENTS = [
    ("slack", "C_GENERAL:1727999000.000100", "C_GENERAL", "#general",
     "https://kopilabs.slack.example/archives/C_GENERAL/p1727999000000100", "2026-10-03T10:00:00Z",
     ["slack:members"],
     "Dana: Our payment gateway migration finished last week with no blockers."),
]

COMPANIES = [
    # Slack team ID (the seed's key for the company), name, users, boundary, documents
    ("T_MERLION", "MerlionPay", USERS, BOUNDARY, DOCUMENTS),
    ("T_KOPI", "Kopi Labs", KOPI_USERS, KOPI_BOUNDARY, KOPI_DOCUMENTS),
]


def seed_company(conn, team, company_name, users, boundary, documents) -> None:
    company = conn.execute(
        text(
            "INSERT INTO companies (name, slack_team_id) VALUES (:n, :t) "
            "ON CONFLICT (slack_team_id) DO UPDATE SET name = EXCLUDED.name RETURNING id"
        ),
        {"n": company_name, "t": team},
    ).scalar_one()

    for email, name, is_admin, principals in users:
        user_id = conn.execute(
            text(
                "INSERT INTO users (email, name, is_admin, company_id) VALUES (:e, :n, :a, :c) "
                "ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name, is_admin = EXCLUDED.is_admin, "
                "company_id = EXCLUDED.company_id "
                "RETURNING id"
            ),
            {"e": email, "n": name, "a": is_admin, "c": company},
        ).scalar_one()
        conn.execute(text("DELETE FROM user_principals WHERE user_id = :u"), {"u": user_id})
        for p in principals:
            conn.execute(text("INSERT INTO user_principals VALUES (:u, :p)"), {"u": user_id, "p": p})

    for source, scope_id, scope_type, title in boundary:
        conn.execute(
            text(
                "INSERT INTO boundary (company_id, source, scope_id, scope_type, title) "
                "VALUES (:c, :s, :i, :t, :ti) "
                "ON CONFLICT (company_id, source, scope_id) DO UPDATE SET title = EXCLUDED.title"
            ),
            {"c": company, "s": source, "i": scope_id, "t": scope_type, "ti": title},
        )

    for source, source_id, scope_id, title, url, updated_at, acl, body in documents:
        doc_id = conn.execute(
            text(
                "INSERT INTO documents (company_id, source, source_id, scope_id, title, url, updated_at, acl, "
                "metadata, content_hash) VALUES (:c, :s, :sid, :scope, :t, :url, CAST(:u AS timestamptz), "
                "CAST(:acl AS text[]), "
                "CAST(:meta AS jsonb), :h) "
                "ON CONFLICT (company_id, source, source_id) DO UPDATE SET scope_id = EXCLUDED.scope_id, "
                "title = EXCLUDED.title, url = EXCLUDED.url, updated_at = EXCLUDED.updated_at, "
                "acl = EXCLUDED.acl, metadata = EXCLUDED.metadata, content_hash = EXCLUDED.content_hash, "
                "deleted_at = NULL "
                "RETURNING id"
            ),
            {"c": company, "s": source, "sid": source_id, "scope": scope_id, "t": title, "url": url,
             "u": updated_at, "acl": acl,
             "meta": json.dumps({"seed": True, "need_to_know": NEED_TO_KNOW.get(source_id, [])}),
             "h": hashlib.sha256(body.encode()).hexdigest()},
        ).scalar_one()
        conn.execute(text("DELETE FROM chunks WHERE document_id = :d"), {"d": doc_id})
        conn.execute(
            text("INSERT INTO chunks (document_id, ordinal, text, text_hash) VALUES (:d, 0, :t, :h)"),
            {"d": doc_id, "t": body, "h": hashlib.sha256(body.encode()).hexdigest()},
        )


def main() -> None:
    if os.environ.get("APP_ENV") != "development":
        sys.exit("Refusing to seed: APP_ENV is not 'development'.")
    embed = "--embed" in sys.argv

    with engine.begin() as conn:
        for team, company_name, users, boundary, documents in COMPANIES:
            seed_company(conn, team, company_name, users, boundary, documents)

        if embed:
            from app.llm.client import LLMClient
            from app.retrieval.search import vector_literal
            from app.sync import masked_for_embedding

            rows = conn.execute(text("SELECT id, document_id, text FROM chunks ORDER BY id")).all()
            vectors = LLMClient.from_env().embed(masked_for_embedding(conn, rows))  # masked (ADR-010)
            for row, vec in zip(rows, vectors):
                conn.execute(
                    text("UPDATE chunks SET embedding = CAST(:v AS vector) WHERE id = :id"),
                    {"v": vector_literal(vec), "id": row.id},
                )

    print(f"Seeded {len(COMPANIES)} companies"
          f"{' with embeddings' if embed else ' (no embeddings: keyword search only)'}.")


if __name__ == "__main__":
    main()
