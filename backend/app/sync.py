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
import re
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine, text

from app.connectors import store
from app.db import engine as default_engine
from app.llm.client import LLMClient
from app.redaction import for_embedding, names_in, protected_spans
from app.retrieval.search import vector_literal

log = logging.getLogger(__name__)

INTERVAL_S = 300  # ADR-005: every 5 minutes
EMBED_BATCH = 512
# ADR-012: small chunks embed one topic each; the pipeline adds the neighbouring chunks back as context.
# Set with scripts/eval_retrieval.py. Title, headings and chunk must fit in EMBEDDING_MAX_CHARS together.
CHUNK_CHARS = 800
OVERLAP_CHARS = 120  # at most this much of a chunk's end is repeated at the start of the next one
CUT_LOOKAHEAD = 200  # characters past the limit scanned, to see an identifier the limit falls inside
HEADING_LINE = re.compile(r"(#{1,6}) ")  # a Markdown heading, as the connectors write them
HEARTBEAT = Path(tempfile.gettempdir()) / "sync-heartbeat"  # touched while the loop makes progress
HEALTHY_WITHIN_S = 3 * INTERVAL_S  # the container is unhealthy when the heartbeat is older


def _cut(text: str) -> int:
    """Where the next chunk of `text` (longer than CHUNK_CHARS) ends: before a heading line (not in the first
    quarter, so sections don't leave tiny chunks), else the last line break, sentence end or space; never inside
    anything the Need-to-Know Shield detects (ADR-010); else the start of the identifier the limit falls in; else
    the limit. Half a card number, or a label without its value, in another chunk would escape masking."""
    spans = protected_spans(text[:CHUNK_CHARS + CUT_LOOKAHEAD])

    def free(i: int) -> bool:
        return not any(start < i < end for start, end in spans)

    for i in range(CHUNK_CHARS, CHUNK_CHARS // 4, -1):
        if text[i - 1] == "\n" and HEADING_LINE.match(text, i) and free(i):
            return i
    for sep in ("\n", ". ", " "):
        for i in range(CHUNK_CHARS, len(sep) - 1, -1):
            if text.endswith(sep, 0, i) and free(i):
                return i
    # No free separator: back to the start of the identifier the limit falls in, and of any identifier that start
    # falls in (spans overlap), so the cut lands inside none of them; not into the first quarter, where text that
    # is identifiers wall to wall has no safe cut anyway.
    cut = CHUNK_CHARS
    while inside := [start for start, end in spans if CHUNK_CHARS // 4 < start < cut < end]:
        cut = min(inside)
    return cut


def _overlap_start(text: str, cut: int) -> int:
    """Where the chunk after a cut at `cut` starts: at the earliest line start within OVERLAP_CHARS before the cut
    (and in the chunk's second half, so every chunk moves on), repeating those lines; at the cut itself after a
    heading (a new section) or when no line start qualifies. Never inside an identifier, which stays whole."""
    if HEADING_LINE.match(text, cut):
        return cut
    spans = protected_spans(text[:cut + CUT_LOOKAHEAD])
    for i in range(max(cut // 2, cut - OVERLAP_CHARS, 1), cut):
        if text[i - 1] == "\n" and not any(start < i < end for start, end in spans):
            return i
    return cut


def chunk(body: str) -> list[str]:
    """Non-blank lines packed into pieces of at most CHUNK_CHARS, cut where `_cut` says, each repeating the end of
    the one before where `_overlap_start` says."""
    text, chunks = "\n".join(line for line in body.splitlines() if line.strip()), []
    while len(text) > CHUNK_CHARS:
        cut = _cut(text)
        chunks.append(text[:cut].rstrip())
        text = text[_overlap_start(text, cut):]
    return [c for c in [*chunks, text] if c.strip()]


def _heading_paths(texts: list[str]) -> list[list[str]]:
    """For each of a document's chunks, in order, the headings it sits under (outermost first): those met in the
    chunks before it, less any its own first line replaces."""
    heads: dict[int, str] = {}
    paths = []
    for t in texts:
        own = HEADING_LINE.match(t)
        paths.append([heads[n] for n in sorted(heads) if not own or n < len(own[1])])
        for line in t.splitlines():
            if m := HEADING_LINE.match(line):
                heads = {n: h for n, h in heads.items() if n < len(m[1])} | {len(m[1]): line}
    return paths


def upsert(conn, company_id: int, doc: dict) -> None:
    """Write one document; its chunks are replaced only when the text changed. `text` None means
    unchanged at the source (not downloaded): only title, URL, ACL and metadata are refreshed."""
    key = {"c": company_id, "s": doc["source"], "sid": doc["source_id"]}
    old, old_title = conn.execute(text("SELECT content_hash, title FROM documents WHERE company_id = :c "
                                       "AND source = :s AND source_id = :sid"), key).first() or (None, None)
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
            # context: the title and the headings each chunk sits under, searched and embedded with it (ADR-012).
            conn.execute(text("INSERT INTO chunks (document_id, ordinal, text, context) VALUES (:d, :o, :t, :ctx)"),
                         [{"d": doc_id, "o": i, "t": t, "ctx": "\n".join([doc["title"], *path])}
                          for i, (t, path) in enumerate(zip(chunks, _heading_paths(chunks), strict=True))])
    elif old_title is not None and old_title != doc["title"]:  # renamed: its chunks are searched and embedded anew
        conn.execute(text("UPDATE chunks SET context = :t || substr(context, char_length(:old) + 1), "
                          "embedding = NULL WHERE document_id = :d"), {"t": doc["title"], "old": old_title, "d": doc_id})


def embed_missing(engine: Engine, llm) -> int:
    """Embed one batch of chunks that have no vector yet (new, or the LLM was down). Returns how many.

    Chunks marked `keyword_only` are left alone (whoever wrote them decided; today the development seed's
    filler). The partial index chunks_to_embed_idx serves this query, so skipped chunks are never read."""
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT id, document_id, text, context FROM chunks WHERE embedding IS NULL "
                                 "AND NOT keyword_only ORDER BY id LIMIT :n"), {"n": EMBED_BATCH}).all()
        store_embeddings(conn, rows, llm)
    return len(rows)


def store_embeddings(conn, rows, llm) -> None:
    """Embeds these chunks (their text masked first, ADR-010) and stores the vectors, in id order."""
    rows = sorted(rows, key=lambda r: r.id)  # one lock order for every writer: no deadlocks between them
    if rows:
        for row, vec in zip(rows, llm.embed(masked_for_embedding(conn, rows)), strict=True):
            conn.execute(text("UPDATE chunks SET embedding = CAST(:v AS vector) WHERE id = :id"),
                         {"v": vector_literal(vec), "id": row.id})


def masked_for_embedding(conn, rows) -> list[str]:
    """Each chunk as the embedding model reads it: its context (title and headings, ADR-012), then its text, all
    masked (ADR-010). Names are collected from the whole document, so a name labelled in one chunk is masked in
    every other chunk too."""
    docs = conn.execute(text("SELECT d.id, d.title, string_agg(c.text, E'\n' ORDER BY c.ordinal) "
                             "FROM documents d JOIN chunks c ON c.document_id = d.id WHERE d.id = ANY(:ids) "
                             "GROUP BY d.id, d.title"), {"ids": list({r.document_id for r in rows})}).all()
    names = {doc_id: names_in([title, body]) for doc_id, title, body in docs}
    return [for_embedding("\n\n".join(filter(None, [r.context, r.text])), names[r.document_id]) for r in rows]


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
    # A tool the admin hasn't connected fails for every one of its scopes: skip the rest of them and log it once,
    # so hundreds of scopes don't bury real failures under the same warning (review of PR #35).
    unconnected: dict[str, int] = {}
    for source, scope_id in scopes:
        HEARTBEAT.touch()
        if source in unconnected:
            unconnected[source] += 1
            continue
        try:
            with engine.connect() as db:  # what is stored, to download only new or edited items
                # No content hash: its text must be read again (migration 0009 re-chunks everything this way).
                known = dict(db.execute(text("SELECT source_id, updated_at FROM documents WHERE company_id = :c "
                                             "AND source = :s AND scope_id = :scope AND content_hash IS NOT NULL"),
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
        except store.NotConnected:
            unconnected[source] = 1
            continue
        except Exception as e:  # one scope failing (revoked, API down) never stops the others
            log.warning("company %s: %s %s not synced: %s", company_id, source, scope_id, type(e).__name__)
            continue
        log.info("company %s: %s %s synced, %d items, %d removed", company_id, source, scope_id, len(docs), gone)
    for source, count in unconnected.items():
        log.warning("company %s: %s not connected: %d scope%s not synced", company_id, source, count,
                    "" if count == 1 else "s")
    try:
        llm = llm or LLMClient.from_env()
        while embed_missing(engine, llm):
            HEARTBEAT.touch()
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
    parser.add_argument("--health", action="store_true",
                        help=f"exit 0 if the loop made progress in the last {HEALTHY_WITHIN_S} seconds")
    args = parser.parse_args(argv)
    if args.health:
        return 0 if HEARTBEAT.exists() and time.time() - HEARTBEAT.stat().st_mtime < HEALTHY_WITHIN_S else 1
    if unknown := set(args.sources) - store.SOURCES.keys():
        parser.error(f"unknown source(s): {', '.join(sorted(unknown))}")
    while True:
        HEARTBEAT.touch()
        with default_engine.connect() as db:
            companies = [args.company] if args.company else db.execute(text("SELECT id FROM companies")).scalars().all()
        for company in companies:
            try:
                sync_company(default_engine, company, args.sources or None)
            except Exception:  # e.g. the database restarting: never let one company stop the loop
                log.exception("company %s: sync failed", company)
        if not args.loop:
            return 0
        HEARTBEAT.touch()
        time.sleep(INTERVAL_S)


if __name__ == "__main__":
    setup_logging()
    sys.exit(main(sys.argv[1:]))
