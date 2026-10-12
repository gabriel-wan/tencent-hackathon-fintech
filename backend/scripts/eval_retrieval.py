"""Retrieval evaluation: does the right source reach the LLM, is it the latest version, and does nothing leak?

Loads scripts/eval_corpus.py into a throwaway database through the real write path (sync.upsert: the connectors'
text, the chunker; sync.embed_missing: masking and TokenHub embeddings), next to the Company A-sized filler
(app/seed_scale.py, ~21,000 documents on overlapping topics, 1,000 of them embedded) so the right source has
to beat realistic competition, then asks every question as the
full-access persona and reports, per kind of question (specific, broad, fresh, offtopic):

- hit@1, hit@5, MRR: rank of the first gold document among the search results;
- context: a gold snippet is inside the text the LLM would receive for a gold document (query.py's _fit);
- off-topic questions that still get sources; stale text left in the index; leaks: documents returned to the
  restricted persona that it may not read. Exits 1 on any stale text or leak.

With --answers it also runs the whole pipeline (answer_question, real LLM, stored-ACL live check) and reports
how often an answerable question got "not found", how often an answer cites a gold source, and why (the audit
record's grounding note). Recreates POSTGRES_DB, which must end in "_eval". From the repository root:

    docker compose run --rm --build -e POSTGRES_DB=brain_eval -v ./backend/scripts:/app/scripts \\
        backend python -m scripts.eval_retrieval [--answers]

Results are recorded in docs/TESTING.md section 10.
"""
import argparse
import json
import os
from collections import defaultdict

import psycopg
from psycopg import sql
from sqlalchemy import text

DB_NAME = os.environ.get("POSTGRES_DB", "")
if not DB_NAME.endswith("_eval"):
    raise SystemExit(f"Refusing to run against database {DB_NAME!r}: POSTGRES_DB must end with '_eval'.")

from app import sync  # noqa: E402  (after the safety check)
from app.auth.principals import principals_for  # noqa: E402
from app.auth.session import User  # noqa: E402
from app.db import engine  # noqa: E402
from app.llm.client import LLMClient  # noqa: E402
from app.llm.grounding import FALLBACK_ANSWER  # noqa: E402
from app.pipeline.query import _fit, answer_question, source_text  # noqa: E402
from app.retrieval.search import add_neighbours, hybrid_search  # noqa: E402
from app.seed import choose_filler_sample, seed_company, seed_scale  # noqa: E402
from scripts import eval_corpus as corpus  # noqa: E402

KINDS = ("specific", "broad", "fresh", "offtopic")


def reset_database() -> None:
    owner = dict(host=os.environ["POSTGRES_HOST"], user=os.environ["POSTGRES_USER"],
                 password=os.environ["POSTGRES_PASSWORD"])
    with psycopg.connect(**owner, dbname="postgres", autocommit=True) as admin:
        admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(DB_NAME)))
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DB_NAME)))
    from alembic import command
    from alembic.config import Config
    command.upgrade(Config("alembic.ini"), "head")


def load(llm, filler_sample: int) -> int:
    """Writes the corpus as a sync would (first DOCUMENTS, then their UPDATES) next to the Company A-sized filler
    as distractors (keyword-only but for a fixed sample), embeds it; returns the company."""
    with engine.begin() as conn:
        seed_company(conn, "T_EVAL", "Lumen Pay", corpus.USERS, corpus.BOUNDARY, [])
        company = conn.execute(text("SELECT id FROM companies WHERE slack_team_id = 'T_EVAL'")).scalar_one()
        seed_scale(conn, "T_EVAL")
        choose_filler_sample(conn, filler_sample)
        for doc in [*corpus.DOCUMENTS, *corpus.UPDATES]:
            sync.upsert(conn, company, doc)
    while sync.embed_missing(engine, llm):
        pass
    return company


def user(conn, email: str) -> User:
    row = conn.execute(text("SELECT id, email, name, is_admin, company_id FROM users WHERE email = :e"),
                       {"e": email}).one()
    return User(*row)


def contains(haystack: str, snippets: list[str]) -> bool:
    return any(s.lower() in haystack.lower() for s in snippets)


def retrieval(company: int, vectors: dict[str, list[float]]) -> tuple[dict, list[str], int, int]:
    scores: dict[str, dict] = {k: defaultdict(float) for k in KINDS}
    misses, leaks = [], 0
    with engine.begin() as conn:
        eve, rex = user(conn, f"eve@{corpus.DOMAIN}"), user(conn, f"rex@{corpus.DOMAIN}")
        eve_p, rex_p = principals_for(conn, eve.id), principals_for(conn, rex.id)
        stale = sum(conn.execute(text("SELECT count(*) FROM chunks WHERE strpos(text, :s) > 0"), {"s": s}).scalar_one()
                    for s in corpus.STALE)
        for kind, question, gold, snippets in corpus.QUESTIONS:
            found = hybrid_search(conn, company, eve_p, question, vectors[question])
            add_neighbours(conn, found)
            keys = [c.key for c in found]
            s = scores[kind]
            s["n"] += 1
            if kind == "offtopic":
                s["with sources"] += bool(found)
            else:
                rank = next((i for i, k in enumerate(keys, 1) if k in gold), None)
                sent = {c.key: source_text(chunks) for c, chunks in _fit(found)}
                in_context = any(contains(body, snippets) for key, body in sent.items() if key in gold)
                s["hit@1"] += rank == 1
                s["hit@5"] += rank is not None and rank <= 5
                s["MRR"] += 1 / rank if rank else 0
                s["context"] += in_context
                if not in_context:
                    misses.append(f"  [{kind}] {question}  -> gold rank {rank}, top: {keys[:3]}")
            for c in hybrid_search(conn, company, rex_p, question, vectors[question]):
                leaks += not (set(c.acl) & set(rex_p))
    return scores, misses, stale, leaks


def answers(llm) -> dict:
    """The whole pipeline as the full-access persona: not-found rate, gold citations, grounding notes."""
    scores: dict[str, dict] = {k: defaultdict(float) for k in KINDS}
    for kind, question, gold, snippets in corpus.QUESTIONS:
        with engine.begin() as conn:
            eve = user(conn, f"eve@{corpus.DOMAIN}")
        result = answer_question(engine.begin, eve, question, llm)
        with engine.begin() as conn:
            payload = conn.execute(text("SELECT payload FROM audit_events WHERE id = :i"),
                                   {"i": result.audit_id}).scalar_one()
        s = scores[kind]
        s["n"] += 1
        not_found = result.answer == FALLBACK_ANSWER
        s["not found"] += not_found
        s["cites gold"] += any(c.id in gold for c in result.citations)
        if kind == "fresh":
            s["latest value"] += contains(result.answer, snippets)
        s[f"note: {payload.get('grounding_note') or ('llm not called' if not payload['llm_called'] else 'ok')}"] += 1
        if not_found and kind != "offtopic":
            print(f"  [{kind}] not found: {question}  ({payload.get('grounding_note') or 'no sources'})")
    return scores


def table(title: str, scores: dict) -> None:
    print(f"\n{title}")
    for kind, s in scores.items():
        n = s.pop("n", 0)
        if n:
            cells = ", ".join(f"{k} {v / n:.2f}" if k in ("MRR",) else f"{k} {int(v)}/{n}" for k, v in s.items())
            print(f"  {kind:<9} {cells}")
            s["n"] = n


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.eval_retrieval")
    parser.add_argument("--answers", action="store_true", help="also run the whole pipeline with the real LLM")
    parser.add_argument("--filler-sample", type=int, default=1000, metavar="N",
                        help="filler chunks to embed as semantic distractors (default 1000, always the same ones)")
    args = parser.parse_args()
    llm = LLMClient.from_env()
    reset_database()
    company = load(llm, args.filler_sample)
    questions = [q for _, q, _, _ in corpus.QUESTIONS]
    vectors = dict(zip(questions, llm.embed(questions), strict=True))
    scores, misses, stale, leaks = retrieval(company, vectors)
    table("Retrieval (full-access persona)", scores)
    print(f"  stale text in index: {stale}   leaks to restricted persona: {leaks}")
    if misses:
        print("\nGold snippet not in the context sent to the LLM:\n" + "\n".join(misses))
    summary = {"retrieval": scores, "stale": stale, "leaks": leaks}
    if args.answers:
        summary["answers"] = answers(llm)
        table("Answers (whole pipeline, real LLM)", summary["answers"])
    print("\n" + json.dumps(summary))
    return 1 if stale or leaks else 0


if __name__ == "__main__":
    raise SystemExit(main())
