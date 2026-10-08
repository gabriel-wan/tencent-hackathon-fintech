# CodeBuddy / WorkBuddy usage log

The hackathon requires the project to be **built using at least one of
CodeBuddy or WorkBuddy**, and proof of usage is **mandatory**: without it the
project is not scored. Minimum proof is 3 screenshots or a screen recording of
development chat logs ([requirements.md](requirements.md)).

Evidence is captured **during** development, as it happens, and stored in
[evidence/](evidence/). Nothing is fabricated or staged after the fact.

## Setup checklist

- [ ] CodeBuddy account configured (each member; credits claimed)
- [ ] WorkBuddy account configured (each member; credits claimed)
- [ ] Miora account configured (optional; only if the team uses it for visual assets)
- [ ] Team agreed on which tool(s) are the primary development assistants

## Evidence checklist

- [x] First development conversation captured (8 Oct, session 1 below)
- [x] Architecture assistance captured (8 Oct, sessions 2 and 3 below)
- [ ] Code implementation assistance captured
- [x] At least 3 screenshots or a screen recording saved in `evidence/` (3 sessions, 6 screenshots)
- [x] Evidence reviewed for secrets or personal data and redacted if needed (no keys, tokens or passwords
      visible; `.env` appears only as a file name; one Windows user name in a file path)
- [ ] Evidence incorporated into the final submission

## Evidence log

Add one row per file as it is captured.

| Date | Tool | File | What it shows | Captured by |
|---|---|---|---|---|
| 2026-10-08 | CodeBuddy IDE (Ask mode) | [evidence/2026-10-08-codebuddy-1-prompt-injection-review-a-prompt.png](evidence/2026-10-08-codebuddy-1-prompt-injection-review-a-prompt.png), [b-summary](evidence/2026-10-08-codebuddy-1-prompt-injection-review-b-summary.png) | Session 1: the prompt, CodeBuddy reading `grounding.py`, `query.py`, `SECURITY.md`, the grounding tests and `search.py`, then a table of prompt-injection attacks, the layer that stops each, and the gaps. Used as the starting list for the prompt-injection task (roadmap, 7–8 Oct) | Gabriel |
| 2026-10-08 | CodeBuddy IDE (Ask mode) | [evidence/2026-10-08-codebuddy-2-audit-log-tamper-review-a-prompt.png](evidence/2026-10-08-codebuddy-2-audit-log-tamper-review-a-prompt.png), [b-findings](evidence/2026-10-08-codebuddy-2-audit-log-tamper-review-b-findings.png) | Session 2: the prompt, CodeBuddy reading `audit/log.py`, migrations 0002, 0006 and 0007, `db.py` and `test_audit.py`, then which attackers could change a record without `verify_chain` noticing. It confirms ADR-007's design, including its one limit (a full rewrite by the database owner, caught by noting the chain's head) | Gabriel |
| 2026-10-08 | CodeBuddy IDE (Plan mode) | [evidence/2026-10-08-codebuddy-3-trust-boundary-diagram-a-prompt.png](evidence/2026-10-08-codebuddy-3-trust-boundary-diagram-a-prompt.png), [b-diagram](evidence/2026-10-08-codebuddy-3-trust-boundary-diagram-b-diagram.png) | Session 3: the prompt, CodeBuddy reading `CURRENT.md`, `SECURITY.md` and `QUERY_PIPELINE.md`, then a Mermaid trust-boundary diagram (identity, retrieval with the stored ACL filter and live check, context assembly, LLM, audit). The draft for the submission's required trust-boundary diagram; its claims were checked against the code | Gabriel |

In all three sessions CodeBuddy only read the code and answered in chat; it changed no files.

## Other Tencent tools available to the team

Listed for awareness. None is a requirement, and none should be adopted unless
it genuinely fits the architecture (recorded in DECISIONS.md).

| Tool | What the handbook says it is | Possible relevance |
|---|---|---|
| CodeBuddy | AI coding assistant in the IDE: completion, review, debugging, multi-file editing | Primary development tool (required proof) |
| WorkBuddy | AI-native workspace to build, deploy and manage agents with LLMs, MCP connectors, skills and scheduling | Alternative primary tool; possibly for agent prototyping |
| Miora | AI creative studio for images, video, 3D and UI from natural language | Cover image, demo visuals |
| Tencent Cloud Agent Development Platform (ADP) | Model orchestration, sandboxed runtime, tool calling, RAG, guardrails, human-in-the-loop | Not used: retrieval, permission checks and grounding are built in-house (ADR-003 to ADR-006) |
| Tencent Cloud Agent Runtime | Secure sandbox execution environment for agents | Not used: the live demo runs on one Lighthouse server (ADR-008) |
| Tencent Cloud services | Compute, database, storage, network, etc. | Used: TokenHub for the LLM (hy3) and embeddings (ADR-006); Lighthouse for hosting (ADR-008, not deployed yet) |
| Tencent Cloud TRTC ASR / TTS | Speech-to-text and text-to-speech | Not obviously relevant to this challenge |
