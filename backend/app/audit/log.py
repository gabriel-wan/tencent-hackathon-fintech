"""Audit events (ADR-007): an append-only, tamper-evident log, one hash chain per company.

Three layers protect it:
1. Triggers reject UPDATE, DELETE and TRUNCATE on audit_events (migration 0002).
2. The app logs in as a database role that may only read and add records (app/db.py, migrations
   0006 and 0007). It is the app's own login, so no statement can switch it to the owner.
3. Each record stores the hash of the previous record of its company (prev_hash) and its own hash,
   computed by the database function audit_event_hash from its id, time, company, user, event type
   and payload. Changing or deleting a record breaks the chain, and verify_chain finds the first break.

Records of people who are not in a company yet (e.g. Drive connected first) form their own chain
(company_id NULL). A record's company is its user's company when it is written. Once that person
joins a company, its admin can search those earlier records (search_events), but only the
no-company chain as a whole can verify them, so no admin API does.

Limitation: someone with full database access could rewrite every record after a change and
recompute the hashes. The chain's head (verify_chain's `head`) can be noted outside the system, e.g.
in the demo or a daily report, to catch that too.
"""
import json
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, text

# Advisory lock namespace for chain writes. The (int, int) key space never overlaps the single-bigint
# locks app/sync.py takes per company.
CHAIN_LOCK = 0x41554449  # "AUDI"

SEARCH_LIMIT = 200

# A record "touches" a document if the document was a candidate (allowed or denied), was sent to the
# LLM, was cited, or was a restricted match the user tried to reach.
_TOUCHES = """(
    e.payload->'sent_to_llm' @> jsonb_build_array({key})
    OR e.payload->'citations' @> jsonb_build_array({key})
    OR e.payload->'candidates' @> jsonb_build_array(jsonb_build_object('document', {key}))
    OR e.payload->'restricted_matches' @> jsonb_build_array(jsonb_build_object('document', {key}))
)"""


def record_event(conn: Connection, user_id: int | None, event_type: str, payload: dict[str, Any]) -> int:
    """Append one record to its company's chain, inside the caller's transaction. Returns its id.

    Holds that company's chain lock until the caller's transaction ends, so make this the transaction's
    last statement and commit promptly: anything slow after it (an API call, the LLM) would stall every
    other audit write of that company."""
    company_id = None
    if user_id is not None:
        company_id = conn.execute(text("SELECT company_id FROM users WHERE id = :u"), {"u": user_id}).scalar()
    # One writer per chain until this transaction ends, so two records can't link to the same previous one.
    # Postgres lock keys are 32-bit: fold the id in, so huge ids don't fail (a shared key only means waiting).
    conn.execute(text("SELECT pg_advisory_xact_lock(:ns, CAST(:k AS int))"),
                 {"ns": CHAIN_LOCK, "k": (company_id or 0) % 2147483647})
    prev = conn.execute(
        text("SELECT hash FROM audit_events WHERE company_id IS NOT DISTINCT FROM CAST(:c AS bigint) "
             "ORDER BY id DESC LIMIT 1"),
        {"c": company_id},
    ).scalar()
    return conn.execute(
        text(
            "INSERT INTO audit_events (id, ts, company_id, user_id, event_type, payload, prev_hash, hash) "
            "SELECT n.id, n.ts, CAST(:c AS bigint), CAST(:u AS bigint), :t, n.payload, CAST(:prev AS text), "
            "       audit_event_hash(CAST(:prev AS text), n.id, n.ts, CAST(:c AS bigint), CAST(:u AS bigint), "
            "                        CAST(:t AS text), n.payload) "
            "FROM (SELECT nextval(pg_get_serial_sequence('audit_events', 'id')) AS id, clock_timestamp() AS ts, "
            "             CAST(:payload AS jsonb) AS payload) n "
            "RETURNING id"
        ),
        {"c": company_id, "u": user_id, "t": event_type, "prev": prev,
         "payload": json.dumps(payload, default=str)},
    ).scalar_one()


def verify_chain(conn: Connection, company_id: int | None) -> dict[str, Any]:
    """Recompute a company's chain. `first_broken_id` is the first record whose content changed, or whose
    link to the previous record no longer matches (that record was changed, deleted or reordered)."""
    key = {"c": company_id}
    broken = conn.execute(
        text(
            "WITH chain AS ("
            "  SELECT id, prev_hash, hash, lag(hash) OVER (ORDER BY id) AS previous, "
            "         audit_event_hash(prev_hash, id, ts, company_id, user_id, event_type, payload) AS recomputed "
            "  FROM audit_events WHERE company_id IS NOT DISTINCT FROM CAST(:c AS bigint)) "
            "SELECT id, hash IS DISTINCT FROM recomputed AS content_changed FROM chain "
            "WHERE hash IS DISTINCT FROM recomputed OR prev_hash IS DISTINCT FROM previous "
            "ORDER BY id LIMIT 1"
        ),
        key,
    ).first()
    checked, head_id, head_hash = conn.execute(
        text("SELECT count(*), max(id), (array_agg(hash ORDER BY id DESC))[1] FROM audit_events "
             "WHERE company_id IS NOT DISTINCT FROM CAST(:c AS bigint)"),
        key,
    ).one()
    reason = None
    if broken is not None:
        reason = ("this record was changed after it was written" if broken.content_changed
                  else "the record before this one was changed, deleted or reordered")
    return {
        "ok": broken is None,
        "checked": checked,
        "first_broken_id": broken.id if broken else None,
        "reason": reason,
        "head": {"id": head_id, "hash": head_hash} if head_id else None,
    }


def search_events(
    conn: Connection,
    company_id: int,
    *,
    user_email: str | None = None,
    event_type: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    document: str | None = None,
    source: str | None = None,
    scope_id: str | None = None,
    before_id: int | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """One company's records, newest first, including its members' records from before they joined it
    (the no-company chain). `document` is a document key such as "jira:10042";
    `source` (+ `scope_id`) matches records that touched any document of that tool (or channel, folder,
    project or space), and admin changes to that scope."""
    in_scope = (
        "(EXISTS (SELECT 1 FROM documents d WHERE d.company_id = e.company_id AND d.source = :source "
        "         AND (CAST(:scope AS text) IS NULL OR d.scope_id = :scope) AND "
        + _TOUCHES.format(key="CAST(d.source || ':' || d.source_id AS text)")
        + ") OR (e.payload->>'source' = :source "
        "        AND (CAST(:scope AS text) IS NULL OR e.payload->>'scope_id' = :scope)))"
    )
    rows = conn.execute(
        text(
            "SELECT e.id, e.ts, u.email AS user_email, e.event_type, e.payload, e.prev_hash, e.hash "
            "FROM audit_events e LEFT JOIN users u ON u.id = e.user_id "
            "WHERE (e.company_id = :c OR (e.company_id IS NULL AND u.company_id = :c)) "
            "  AND (CAST(:email AS text) IS NULL OR u.email = lower(:email)) "
            "  AND (CAST(:etype AS text) IS NULL OR e.event_type = :etype) "
            "  AND (CAST(:since AS timestamptz) IS NULL OR e.ts >= CAST(:since AS timestamptz)) "
            "  AND (CAST(:until AS timestamptz) IS NULL OR e.ts < CAST(:until AS timestamptz)) "
            "  AND (CAST(:before AS bigint) IS NULL OR e.id < CAST(:before AS bigint)) "
            "  AND (CAST(:doc AS text) IS NULL OR " + _TOUCHES.format(key="CAST(:doc AS text)") + ") "
            "  AND (CAST(:source AS text) IS NULL OR " + in_scope + ") "
            "ORDER BY e.id DESC LIMIT :lim"
        ),
        {"c": company_id, "email": user_email, "etype": event_type, "since": since, "until": until,
         "before": before_id, "doc": document, "source": source, "scope": scope_id,
         "lim": min(limit, SEARCH_LIMIT)},
    ).mappings()
    return [dict(r) for r in rows]
