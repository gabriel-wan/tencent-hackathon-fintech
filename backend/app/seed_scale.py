"""DEVELOPMENT SEED DATA: Company A-sized filler for MerlionPay. Fictional, templated text.

The handbook's Company A (docs/hackathon/challenge.md): 50+ Confluence spaces and 12,000+ pages, 30+ Jira
projects with issue-level security, 200+ Slack channels, nested Drive folders with mixed sharing. This module
generates roughly that, the same every run (a fixed random seed), so search, the permission filter and the
audit trail can be tried at that size. It is filler: the story documents in app/seed.py are what the demo
questions are about.

Everything here is marked so it can be removed: scope IDs start with SCOPE_PREFIX, and documents carry
{"seed": "scale"} in their metadata. Used by `python -m app.seed --scale` / `--remove-scale`.
"""
import random

SCOPE_PREFIX = "SC_"
MARK = "scale"

# The size of Company A (handbook), per tool.
CONFLUENCE_SPACES, PAGES_PER_SPACE = 50, 240  # 12,000 pages
JIRA_PROJECTS, ISSUES_PER_PROJECT = 30, 100  # 3,000 issues
SLACK_CHANNELS, THREADS_PER_CHANNEL = 200, 20  # 4,000 threads
DRIVE_TOP, DRIVE_FANOUT, FILES_PER_LEAF = 10, 3, 22  # 10 + 30 + 90 folders, ~2,000 files
OUTSIDE_BOUNDARY = 0.1  # share of filler scopes the admin hasn't added: never searched

DOMAIN = "merlionpay.example"
SEEDED = {  # the four seeded people, so filler is spread over who can see what
    "slack": ["slack:user:U001", "slack:user:U002", "slack:user:U003", "slack:user:U004"],
    "atlassian": ["atlassian:user:A001", "atlassian:user:A002", "atlassian:user:A003", "atlassian:user:A004"],
    "google": [f"google:user:{n}@{DOMAIN}" for n in ("alice", "ben", "priya")],
}

TEAMS = ["Payments", "Risk", "Ledger", "Merchant success", "Platform", "Data", "Mobile", "Compliance", "Treasury",
         "Fraud", "Identity", "Growth", "Support", "Billing", "Infrastructure", "Partnerships"]
SYSTEMS = ["settlement service", "card vault", "merchant portal", "payout scheduler", "KYC pipeline",
           "notification service", "reporting warehouse", "FX rates feed", "dispute workflow", "API gateway",
           "mobile wallet", "reconciliation job", "rate limiter", "audit exporter", "loyalty engine"]
TOPICS = ["capacity planning", "on-call handover", "quarterly roadmap", "latency budget", "incident review",
          "release notes", "access review", "cost report", "vendor evaluation", "test plan", "runbook update",
          "migration plan", "design review", "retrospective", "SLA report"]
VERBS = ["reduced", "increased", "reviewed", "paused", "rolled out", "deprecated", "documented", "benchmarked",
         "audited", "migrated", "scaled", "split", "merged", "monitored", "patched"]
STATUSES = ["To do", "In progress", "In review", "Blocked", "Done"]


def _text(rng: random.Random, team: str) -> str:
    system, topic = rng.choice(SYSTEMS), rng.choice(TOPICS)
    lines = [f"{team} {topic} for the {system}."]
    for _ in range(rng.randint(2, 4)):
        lines.append(f"We {rng.choice(VERBS)} the {rng.choice(SYSTEMS)} by {rng.randint(2, 60)}% "
                     f"in week {rng.randint(1, 52)}; owner: the {rng.choice(TEAMS)} team.")
    return "\n".join(lines)


def _some(rng: random.Random, pool: list[str], fake: str, k: int) -> list[str]:
    """A few named people: some seeded (so the personas see a realistic share), the rest fictional."""
    people = rng.sample(pool, rng.randint(0, 2)) + [f"{fake}{rng.randint(300, 999)}" for _ in range(k)]
    return sorted(set(people))


def generate() -> tuple[list[tuple], list[tuple]]:
    """(boundary, documents) in app.seed's tuple shapes, for MerlionPay. Same output every run."""
    rng = random.Random(2026)
    boundary: list[tuple] = []
    documents: list[tuple] = []

    def scope(source: str, scope_id: str, scope_type: str, title: str) -> None:
        if rng.random() >= OUTSIDE_BOUNDARY:
            boundary.append((source, scope_id, scope_type, title))

    # Confluence: spaces, ~10% team-restricted; within open spaces ~2% of pages restricted to named people.
    for s in range(1, CONFLUENCE_SPACES + 1):
        team = TEAMS[s % len(TEAMS)]
        space = f"{SCOPE_PREFIX}CONF{s:02d}"
        scope("confluence", space, "space", f"{team} space {s}")
        restricted = rng.random() < 0.1
        members = _some(rng, SEEDED["atlassian"], "atlassian:user:A", 6) if restricted else \
            [*SEEDED["atlassian"][:2], SEEDED["atlassian"][3], "atlassian:group:all-staff"]
        for p in range(1, PAGES_PER_SPACE + 1):
            acl = _some(rng, SEEDED["atlassian"], "atlassian:user:A", 2) if rng.random() < 0.02 else members
            page = f"{s:02d}{p:04d}"
            documents.append(("confluence", page, space, f"{team}: {rng.choice(TOPICS)} {p}",
                              f"https://merlionpay.atlassian.example/wiki/spaces/{space}/pages/{page}",
                              f"2026-{rng.randint(1, 10):02d}-{rng.randint(1, 28):02d}T08:00:00Z", acl,
                              _text(rng, team)))

    # Jira: projects with role-based access; ~3% of issues have a security level (security team only).
    for j in range(1, JIRA_PROJECTS + 1):
        team = TEAMS[j % len(TEAMS)]
        project = f"{SCOPE_PREFIX}J{j:02d}"
        scope("jira", project, "project", f"{team} project {j}")
        members = [*SEEDED["atlassian"][:2], SEEDED["atlassian"][3]] + [f"atlassian:user:A{400 + j}"]
        for i in range(1, ISSUES_PER_PROJECT + 1):
            acl = ["atlassian:user:A004", "atlassian:user:A399"] if rng.random() < 0.03 else members
            key = f"J{j:02d}-{i}"
            documents.append(("jira", f"8{j:02d}{i:04d}", project,
                              f"{key} {rng.choice(VERBS).capitalize()} the {rng.choice(SYSTEMS)}",
                              f"https://merlionpay.atlassian.example/browse/{key}",
                              f"2026-{rng.randint(1, 10):02d}-{rng.randint(1, 28):02d}T09:00:00Z", acl,
                              f"{key}. Status: {rng.choice(STATUSES)}.\n{_text(rng, team)}"))

    # Slack: ~15% private channels with named members; public ones open to every full member.
    for c in range(1, SLACK_CHANNELS + 1):
        team = TEAMS[c % len(TEAMS)]
        channel = f"{SCOPE_PREFIX}C{c:03d}"
        name = f"#{team.lower().replace(' ', '-')}-{c:03d}"
        scope("slack", channel, "channel", name)
        acl = _some(rng, SEEDED["slack"], "slack:user:U", 8) if rng.random() < 0.15 else ["slack:members"]
        for t in range(1, THREADS_PER_CHANNEL + 1):
            ts = f"17{c:03d}{t:05d}.000100"
            documents.append(("slack", f"{channel}:{ts}", channel, name,
                              f"https://merlionpay.slack.example/archives/{channel}/p{ts.replace('.', '')}",
                              f"2026-{rng.randint(1, 10):02d}-{rng.randint(1, 28):02d}T10:00:00Z", acl,
                              _text(rng, team)))

    # Drive: three levels of folders. Files belong to their top folder's scope (sync includes subfolders).
    # Sharing per file: the whole domain, named people, or "anyone with the link" in one external folder.
    for top in range(1, DRIVE_TOP + 1):
        team = TEAMS[top % len(TEAMS)]
        root = f"{SCOPE_PREFIX}F{top:02d}"
        scope("drive", root, "folder", f"{team} (shared)")
        external = top == DRIVE_TOP  # one folder shared outside the company
        for mid in range(1, DRIVE_FANOUT + 1):
            for leaf in range(1, DRIVE_FANOUT + 1):
                for f in range(1, FILES_PER_LEAF + 1):
                    roll = rng.random()
                    acl = ["public"] if external and roll < 0.5 else \
                        [f"google:domain:{DOMAIN}"] if roll < 0.7 else \
                        _some(rng, SEEDED["google"], "google:user:p", 2)
                    file_id = f"{root}_{mid}{leaf}_{f:02d}"
                    documents.append(("drive", file_id, root, f"{team} {rng.choice(TOPICS)} {mid}.{leaf}.{f}",
                                      f"https://docs.google.example/document/d/{file_id}",
                                      f"2026-{rng.randint(1, 10):02d}-{rng.randint(1, 28):02d}T11:00:00Z", acl,
                                      _text(rng, team)))
    return boundary, documents
