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

Run:  docker compose run --rm backend python -m app.seed [--embed]
--embed also computes embeddings through TokenHub (needs LLM_* settings and an
API key allowed to use the embedding model).
"""
import hashlib
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
    ("drive", "D_SALARY", "F_HR", "Salary bands 2026",
     "https://docs.google.example/document/d/D_SALARY", "2026-09-01T10:00:00Z",
     [f"google:domain:{DOMAIN}"],
     "Salary bands 2026 for all engineering levels. This folder is outside the admin boundary, so it must "
     "never appear in an answer."),
]


def main() -> None:
    if os.environ.get("APP_ENV") != "development":
        sys.exit("Refusing to seed: APP_ENV is not 'development'.")
    embed = "--embed" in sys.argv

    with engine.begin() as conn:
        for email, name, is_admin, principals in USERS:
            user_id = conn.execute(
                text(
                    "INSERT INTO users (email, name, is_admin) VALUES (:e, :n, :a) "
                    "ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name, is_admin = EXCLUDED.is_admin "
                    "RETURNING id"
                ),
                {"e": email, "n": name, "a": is_admin},
            ).scalar_one()
            conn.execute(text("DELETE FROM user_principals WHERE user_id = :u"), {"u": user_id})
            for p in principals:
                conn.execute(text("INSERT INTO user_principals VALUES (:u, :p)"), {"u": user_id, "p": p})

        for source, scope_id, scope_type, title in BOUNDARY:
            conn.execute(
                text(
                    "INSERT INTO boundary (source, scope_id, scope_type, title) VALUES (:s, :i, :t, :ti) "
                    "ON CONFLICT (source, scope_id) DO UPDATE SET title = EXCLUDED.title"
                ),
                {"s": source, "i": scope_id, "t": scope_type, "ti": title},
            )

        for source, source_id, scope_id, title, url, updated_at, acl, body in DOCUMENTS:
            doc_id = conn.execute(
                text(
                    "INSERT INTO documents (source, source_id, scope_id, title, url, updated_at, acl, "
                    "metadata, content_hash) VALUES (:s, :sid, :scope, :t, :url, CAST(:u AS timestamptz), "
                    "CAST(:acl AS text[]), "
                    "CAST(:meta AS jsonb), :h) "
                    "ON CONFLICT (source, source_id) DO UPDATE SET scope_id = EXCLUDED.scope_id, "
                    "title = EXCLUDED.title, url = EXCLUDED.url, updated_at = EXCLUDED.updated_at, "
                    "acl = EXCLUDED.acl, content_hash = EXCLUDED.content_hash, deleted_at = NULL "
                    "RETURNING id"
                ),
                {"s": source, "sid": source_id, "scope": scope_id, "t": title, "url": url, "u": updated_at,
                 "acl": acl, "meta": '{"seed": true}', "h": hashlib.sha256(body.encode()).hexdigest()},
            ).scalar_one()
            conn.execute(text("DELETE FROM chunks WHERE document_id = :d"), {"d": doc_id})
            conn.execute(
                text("INSERT INTO chunks (document_id, ordinal, text, text_hash) VALUES (:d, 0, :t, :h)"),
                {"d": doc_id, "t": body, "h": hashlib.sha256(body.encode()).hexdigest()},
            )

        if embed:
            from app.llm.client import LLMClient
            from app.retrieval.search import vector_literal

            rows = conn.execute(text("SELECT id, text FROM chunks ORDER BY id")).all()
            vectors = LLMClient.from_env().embed([r.text for r in rows])
            for row, vec in zip(rows, vectors):
                conn.execute(
                    text("UPDATE chunks SET embedding = CAST(:v AS vector) WHERE id = :id"),
                    {"v": vector_literal(vec), "id": row.id},
                )

    print(f"Seeded {len(USERS)} users, {len(BOUNDARY)} boundary scopes, {len(DOCUMENTS)} documents"
          f"{' with embeddings' if embed else ' (no embeddings: keyword search only)'}.")


if __name__ == "__main__":
    main()
