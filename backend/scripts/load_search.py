"""Load-test retrieval (issue #31): seed N synthetic chunks into a throwaway database, then time
hybrid_search and the audit-only restricted_matches per persona and print p50/p95 and plan checks.

Drops and recreates POSTGRES_DB, which must end in "_loadtest", so it can never touch real data. From the
repository root, with the database service running (`docker compose up -d db`):

    docker compose run --rm --build -e POSTGRES_DB=brain_loadtest -v ./backend/scripts:/app/scripts \\
        backend python -m scripts.load_search --chunks 100000

Synthetic data: random unit vectors (so semantic results are noise; this measures time, not quality),
words drawn from a Zipf distribution so some question words match many chunks and some few, and ACLs
in the shape the connectors store (team user lists, workspace-wide, a security team, a little public).
Set PLANS=1 to print each persona's EXPLAIN ANALYZE. Results are recorded in docs/TESTING.md section 9.
"""
import argparse
import os
import random
import statistics
import time

import psycopg
from psycopg import sql
from sqlalchemy import text

DB_NAME = os.environ.get("POSTGRES_DB", "")
if not DB_NAME.endswith("_loadtest"):
    raise SystemExit(f"Refusing to run against database {DB_NAME!r}: POSTGRES_DB must end with '_loadtest'.")

from app.db import owner_engine  # noqa: E402  (after the safety check)
from app.retrieval.search import SEARCH_SQL, hybrid_search, restricted_matches, vector_literal  # noqa: E402

# Question words, from common to rare: placed every 40th rank of the Zipf vocabulary.
WORDS = ("status payment service incident team customer data report access deployment release policy "
         "account review gateway latency outage database error card transfer settlement refund ledger "
         "forecast budget quarterly revenue singapore owner runbook fraud detection credentials rotate "
         "escalation compliance audit vulnerabilities security handover oncall spike rollback migration "
         "reconciliation chargeback kyc onboarding sanction merchant invoice treasury liquidity").split()
QUESTIONS = [
    "What is the status of the payment gateway incident?",
    "Who owns the fraud detection runbook?",
    "List all security vulnerabilities in the card service",
    "How do I rotate the database credentials?",
    "Quarterly revenue forecast for Singapore",
    "Latency spike after the last deployment rollback",
    "Customer refund escalation policy",
    "Oncall handover notes for reconciliation",
]
TEAMS, TEAM_SIZE, SCOPES, OUTSIDE_SCOPES = 10, 30, 50, 10
PERSONAS = {  # name -> principals held (as app/auth/principals.py returns them)
    "employee": ["public", "slack:members", "google:domain:corp.com", "atlassian:user:emp"],
    "security": ["public", "slack:members", "google:domain:corp.com", "atlassian:user:sec"],
    "contractor": ["public", "atlassian:user:ctr"],
}


def vocabulary(size: int = 5000) -> list[str]:
    syllables = ["ka", "lo", "mi", "ne", "ru", "ta", "vo", "ze", "pi", "do", "sa", "fe"]
    rng = random.Random(1)
    words = list(dict.fromkeys("".join(rng.choices(syllables, k=4)) for _ in range(size * 2)))[:size]
    for i, word in enumerate(WORDS):
        words[(i + 1) * 40] = word
    return words


def acl(rng: random.Random) -> list[str]:
    roll = rng.random()
    if roll < 0.30:  # workspace- or domain-wide
        return [rng.choice(["slack:members", "google:domain:corp.com"])]
    if roll < 0.85:  # one team's users (Jira project browsers, a private channel's members)
        team = rng.randrange(TEAMS)
        people = [f"atlassian:user:t{team}u{i}" for i in range(TEAM_SIZE)]
        people += ["atlassian:user:emp"] * (team in (0, 1)) + ["atlassian:user:sec"] * (team == 2)
        return people + ["atlassian:user:ctr"] * (rng.random() < 0.01)
    if roll < 0.99:  # the security team
        return [f"atlassian:user:sec{i}" for i in range(5)] + ["atlassian:user:sec"]
    return ["public"]  # overshared


def reset_database() -> None:
    owner = dict(host=os.environ["POSTGRES_HOST"], user=os.environ["POSTGRES_USER"],
                 password=os.environ["POSTGRES_PASSWORD"])
    with psycopg.connect(**owner, dbname="postgres", autocommit=True) as admin:
        admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(DB_NAME)))
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DB_NAME)))
    from alembic import command
    from alembic.config import Config
    command.upgrade(Config("alembic.ini"), "head")


def seed(chunks: int) -> int:
    """Returns the company id."""
    rng, words = random.Random(42), vocabulary()
    weights = [1 / rank for rank in range(1, len(words) + 1)]
    raw = owner_engine().raw_connection()
    try:
        cur = raw.cursor()
        company = cur.execute("INSERT INTO companies (name) VALUES ('Load test') RETURNING id").fetchone()[0]
        for s in range(SCOPES):
            cur.execute("INSERT INTO boundary (company_id, source, scope_id, scope_type) "
                        "VALUES (%s, 'jira', %s, 'project')", (company, f"S{s}"))
        cur.execute("DROP INDEX chunks_embedding_hnsw_idx")  # bulk load first, build the index once
        documents, texts, made = [], [], 0
        while made < chunks:
            doc = len(documents) + 1
            documents.append((doc, company, "jira", str(doc), f"S{rng.randrange(SCOPES + OUTSIDE_SCOPES)}",
                              f"Doc {doc}", "2026-10-01T00:00:00Z", acl(rng)))
            for ordinal in range(min(rng.randint(1, 7), chunks - made)):
                texts.append((doc, ordinal, " ".join(rng.choices(words, weights, k=120))))
                made += 1
        with cur.copy("COPY documents (id, company_id, source, source_id, scope_id, title, updated_at, acl) "
                      "FROM STDIN") as copy:
            for row in documents:
                copy.write_row(row)
        with cur.copy("COPY chunks (document_id, ordinal, text) FROM STDIN") as copy:
            for row in texts:
                copy.write_row(row)
        cur.execute("SELECT setval(pg_get_serial_sequence('documents', 'id'), %s)", (len(documents),))
        # Random unit vectors, made in the database (sending 1,024 floats per chunk is the slow part).
        # (The WHERE on c.id makes the subquery run once per chunk, not once for all.)
        cur.execute("UPDATE chunks c SET embedding = (SELECT l2_normalize(array_agg(random() - 0.5)::vector) "
                    "FROM generate_series(1, 1024) WHERE c.id IS NOT NULL)")
        # One process: parallel builds use shared memory, and Docker's default /dev/shm is only 64 MB.
        cur.execute("SET maintenance_work_mem = '1GB'; SET max_parallel_maintenance_workers = 0")
        cur.execute("CREATE INDEX chunks_embedding_hnsw_idx ON chunks USING hnsw (embedding vector_cosine_ops)")
        cur.execute("ANALYZE")
        raw.commit()
        return company
    finally:
        raw.close()


def timed(fn) -> float:
    start = time.perf_counter()
    fn()
    return (time.perf_counter() - start) * 1000


def pct(values: list[float], p: int) -> float:
    return statistics.quantiles(values, n=100, method="inclusive")[p - 1]


def measure(company: int, runs: int) -> None:
    rng = random.Random(7)
    engine = owner_engine()
    print(f"\n{'persona':<11} {'visible':>8} {'search p50':>11} {'p95':>7} {'audit p50':>10} {'p95':>7} "
          f"{'docs':>5} {'vec rows':>9} {'HNSW':>5}")
    for name, principals in PERSONAS.items():
        search, audit, found = [], [], []
        for question in QUESTIONS:
            qvec = [rng.gauss(0, 1) for _ in range(1024)]
            for i in range(runs + 1):  # the first run warms the cache and is not counted
                with engine.begin() as conn:
                    t = timed(lambda: found.append(len(hybrid_search(conn, company, principals, question, qvec))))
                with engine.begin() as conn:
                    a = timed(lambda: restricted_matches(conn, company, principals, question))
                if i:
                    search.append(t)
                    audit.append(a)
        with engine.begin() as conn:
            visible = conn.execute(text(
                "SELECT round(100.0 * count(*) FILTER (WHERE d.acl && CAST(:p AS text[])) / count(*), 1) "
                "FROM chunks c JOIN documents d ON d.id = c.document_id"), {"p": principals}).scalar()
            # Vector rows alone (a question with no words): does a narrow ACL still fill chunk_limit (50)?
            conn.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
            params = {"company_id": company, "principals": principals, "question": "", "use_vec": True,
                      "qvec": vector_literal(qvec), "chunk_limit": 50, "rrf_k": 60}
            vec_rows = len(conn.execute(SEARCH_SQL, params).all())
            plan = "\n".join(r[0] for r in conn.execute(text("EXPLAIN (ANALYZE, BUFFERS) " + SEARCH_SQL.text),
                                                        params | {"question": QUESTIONS[0]}))
        if os.environ.get("PLANS"):
            print(f"\n--- {name}: {QUESTIONS[0]}\n{plan}\n")
        print(f"{name:<11} {visible:>7}% {pct(search, 50):>9.0f}ms {pct(search, 95):>5.0f}ms "
              f"{pct(audit, 50):>8.0f}ms {pct(audit, 95):>5.0f}ms {statistics.mean(found):>5.1f} {vec_rows:>9} "
              f"{'yes' if 'chunks_embedding_hnsw_idx' in plan else 'NO':>5}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--chunks", type=int, default=10_000)
    parser.add_argument("--runs", type=int, default=5, help="timed runs per question and persona")
    parser.add_argument("--measure-only", action="store_true", help="reuse the database the last run seeded")
    args = parser.parse_args()
    if args.measure_only:
        with owner_engine().connect() as conn:
            company = conn.execute(text("SELECT id FROM companies WHERE name = 'Load test'")).scalar_one()
    else:
        reset_database()
        start = time.perf_counter()
        company = seed(args.chunks)
        print(f"seeded {args.chunks} chunks in {time.perf_counter() - start:.0f}s")
    measure(company, args.runs)


if __name__ == "__main__":
    main()
