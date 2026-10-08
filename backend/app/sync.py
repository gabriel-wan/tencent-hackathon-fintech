"""Sync (ADR-005): copy each company's boundary content, and who may read it, into documents and chunks.

For every boundary scope (channel, folder, project, space) the source is read as the company admin's
own connection (ADR-002), and each item becomes one `documents` row in the shape of
docs/architecture/CONNECTORS.md section 5. Chunks are rewritten only when the text changed; ACLs and
titles are refreshed every run, but text is downloaded only for items whose modified time changed
(each source's fetch(client, scope_id, changed) yields `text` None for the others). Items no longer in a scope are soft-deleted (`deleted_at`), but only
after that scope was read completely. Chunks without an embedding are embedded at the end, so an
LLM outage only delays semantic search.

Syncs of one company never overlap, and a scope removed mid-sync is not written back. Each scope's
last complete sync is kept in `sync_state`, shown as `synced_at` on citations.

    python -m app.sync [--company ID] [--loop] [slack drive jira confluence]
"""

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime

from sqlalchemy import Engine, text

from app.connectors import store
from app.db import engine as default_engine
from app.llm.client import EMBEDDING_MAX_CHARS, LLMClient
from app.retrieval.search import vector_literal

log = logging.getLogger(__name__)

INTERVAL_S = 300  # ADR-005: every 5 minutes
EMBED_BATCH = 512


def chunk(body: str) -> list[str]:
    """Lines packed into pieces of at most EMBEDDING_MAX_CHARS; a longer line is cut."""
    pieces = [line[i:i + EMBEDDING_MAX_CHARS] for line in body.splitlines() if line.strip()
              for i in range(0, len(line), EMBEDDING_MAX_CHARS)]
    chunks: list[str] = []
    for piece in pieces:
        if chunks and len(chunks[-1]) + 1 + len(piece) <= EMBEDDING_MAX_CHARS:
            chunks[-1] += "\n" + piece
        else:
            chunks.append(piece)
    return chunks


def upsert(conn, company_id: int, doc: dict) -> None:
    """Write one document; its chunks are replaced only when the text changed. `text` None means
    unchanged at the source (not downloaded): only title, URL, ACL and metadata are refreshed."""
    key = {"c": company_id, "s": doc["source"], "sid": doc["source_id"]}
    old = conn.execute(text("SELECT content_hash FROM documents WHERE company_id = :c AND source = :s "
                            "AND source_id = :sid"), key).scalar()
    content_hash = old if doc["text"] is None else hashlib.sha256(doc["text"].encode()).hexdigest()
    doc_id = conn.execute(
        text(
            "INSERT INTO documents (company_id, source, source_id, scope_id, title, url, updated_at, acl, "
            "metadata, content_hash) VALUES (:c, :s, :sid, :scope, :t, :url, CAST(:u AS timestamptz), "
            "CAST(:acl AS text[]), CAST(:meta AS jsonb), :h) "
            "ON CONFLICT (company_id, source, source_id) DO UPDATE SET scope_id = EXCLUDED.scope_id, "
            "title = EXCLUDED.title, url = EXCLUDED.url, updated_at = EXCLUDED.updated_at, acl = EXCLUDED.acl, "
            "metadata = EXCLUDED.metadata, content_hash = EXCLUDED.content_hash, deleted_at = NULL "
            "RETURNING id"
        ),
        {**key, "scope": doc["scope_id"], "t": doc["title"], "url": doc["url"], "u": doc["updated_at"],
         "acl": list(doc["acl"]), "meta": json.dumps(doc.get("metadata", {})), "h": content_hash},
    ).scalar_one()
    if old != content_hash:
        conn.execute(text("DELETE FROM chunks WHERE document_id = :d"), {"d": doc_id})
        if chunks := chunk(doc["text"]):
            conn.execute(text("INSERT INTO chunks (document_id, ordinal, text) VALUES (:d, :o, :t)"),
                         [{"d": doc_id, "o": i, "t": t} for i, t in enumerate(chunks)])


def embed_missing(engine: Engine, llm) -> int:
    """Embed one batch of chunks that have no vector yet (new, or the LLM was down). Returns how many."""
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT id, text FROM chunks WHERE embedding IS NULL ORDER BY id LIMIT :n"),
                            {"n": EMBED_BATCH}).all()
        if rows:
            for row, vec in zip(rows, llm.embed([r.text for r in rows]), strict=True):
                conn.execute(text("UPDATE chunks SET embedding = CAST(:v AS vector) WHERE id = :id"),
                             {"v": vector_literal(vec), "id": row.id})
    return len(rows)


def sync_company(engine: Engine, company_id: int, sources: list[str] | None = None, llm=None) -> None:
    """Read every boundary scope of the company (or only `sources`) as its admin, and write it.
    Skipped if a sync of this company is already running."""
    with engine.connect() as held:
        if not held.execute(text("SELECT pg_try_advisory_lock(:c)"), {"c": company_id}).scalar():
            log.info("company %s: a sync is already running, skipped", company_id)
            return
        held.commit()
        try:
            _sync_company(engine, company_id, sources, llm)
        finally:
            held.execute(text("SELECT pg_advisory_unlock(:c)"), {"c": company_id})
            held.commit()


def _sync_company(engine: Engine, company_id: int, sources: list[str] | None, llm) -> None:
    with engine.connect() as db:
        admin = db.execute(text("SELECT id FROM users WHERE company_id = :c AND is_admin ORDER BY id LIMIT 1"),
                           {"c": company_id}).scalar()
        scopes = db.execute(text("SELECT source, scope_id FROM boundary WHERE company_id = :c "
                                 "AND source = ANY(:s) ORDER BY source, scope_id"),
                            {"c": company_id, "s": sources or list(store.SOURCES)}).all()
    if admin is None:
        log.warning("company %s has no admin: nothing synced", company_id)
        return
    for source, scope_id in scopes:
        try:
            with engine.connect() as db:  # what is stored, to download only new or edited items
                known = dict(db.execute(text("SELECT source_id, updated_at FROM documents WHERE company_id = :c "
                                             "AND source = :s AND scope_id = :scope"),
                                        {"c": company_id, "s": source, "scope": scope_id}).all())

            def changed(source_id: str, updated_at: str, known=known) -> bool:
                return known.get(source_id) != datetime.fromisoformat(updated_at)

            docs = list(store.SOURCES[source].fetch(store.client(engine, admin, source), scope_id, changed))
            key = {"c": company_id, "s": source, "scope": scope_id}
            with engine.begin() as conn:  # the whole scope at once: a failure writes nothing
                # FOR SHARE: a concurrent removal waits for this write, so its soft-delete lands last.
                if conn.execute(text("SELECT 1 FROM boundary WHERE company_id = :c AND source = :s "
                                     "AND scope_id = :scope FOR SHARE"), key).first() is None:
                    log.info("company %s: %s %s removed during sync, not written", company_id, source, scope_id)
                    continue
                for doc in docs:
                    upsert(conn, company_id, doc)
                gone = conn.execute(
                    text("UPDATE documents SET deleted_at = now() WHERE company_id = :c AND source = :s "
                         "AND scope_id = :scope AND deleted_at IS NULL AND NOT (source_id = ANY(:seen))"),
                    {**key, "seen": [d["source_id"] for d in docs]},
                ).rowcount
                conn.execute(text("INSERT INTO sync_state (company_id, source, key, updated_at) "
                                  "VALUES (:c, :s, :scope, now()) ON CONFLICT (company_id, source, key) "
                                  "DO UPDATE SET updated_at = now()"), key)
        except Exception as e:  # one scope failing (not connected, revoked, API down) never stops the others
            log.warning("company %s: %s %s not synced: %s", company_id, source, scope_id, type(e).__name__)
            continue
        log.info("company %s: %s %s synced, %d items, %d removed", company_id, source, scope_id, len(docs), gone)
    try:
        llm = llm or LLMClient.from_env()
        while embed_missing(engine, llm):
            pass
    except Exception as e:  # keyword search still works; vectors are filled on a later run
        log.warning("embedding skipped: %s", type(e).__name__)


def setup_logging() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "info").upper(), format="%(levelname)s %(name)s: %(message)s")
    # Library logs include URLs and response bodies (messages, file text): never let them through.
    for lib in ("httpx", "httpcore", "googleapiclient", "google", "slack_sdk", "urllib3"):
        logging.getLogger(lib).setLevel(logging.WARNING)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.sync", description="Sync boundary content into the database.")
    parser.add_argument("sources", nargs="*", help=f"any of {', '.join(store.SOURCES)} (default: all)")
    parser.add_argument("--company", type=int, help="one company ID (default: all)")
    parser.add_argument("--loop", action="store_true", help=f"repeat every {INTERVAL_S} seconds")
    args = parser.parse_args(argv)
    if unknown := set(args.sources) - store.SOURCES.keys():
        parser.error(f"unknown source(s): {', '.join(sorted(unknown))}")
    while True:
        with default_engine.connect() as db:
            companies = [args.company] if args.company else db.execute(text("SELECT id FROM companies")).scalars().all()
        for company in companies:
            try:
                sync_company(default_engine, company, args.sources or None)
            except Exception:  # e.g. the database restarting: never let one company stop the loop
                log.exception("company %s: sync failed", company)
        if not args.loop:
            return 0
        time.sleep(INTERVAL_S)


if __name__ == "__main__":
    setup_logging()
    sys.exit(main(sys.argv[1:]))
