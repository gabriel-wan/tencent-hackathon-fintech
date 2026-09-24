# Submission checklist

> ## Deadline: **16 October 2026, 23:59 (Singapore)**
> Submission form: <https://tinyurl.com/TCHackathonSGProjectSubmission>
> Finalists announced 23 Oct 2026. Demo Day 3 Nov 2026 (TBC).

Requirements source: [requirements.md](requirements.md). Tick items only when
they are actually done and checked by a second team member.

## Required submission items

- [ ] **Project title** decided (working name: Internal Brain; final name TBD)
- [ ] **Short blurb** – under 10 words, counted
- [ ] **Project description** written, covering:
  - [ ] Target users / scenarios
  - [ ] Real-world pain points and core problems solved
  - [ ] Business value – quantifiable metrics or clearly defined impact
  - [ ] Technical architecture (business + technical, how prompts drive the AI)
- [ ] **Working prototype** that demonstrates the five challenge scenarios
- [ ] **GitHub repository** – complete source code, README accurate, no secrets in history
- [ ] **CodeBuddy / WorkBuddy proof** – minimum 3 screenshots or a screen
      recording of development chat logs (see [tool-usage.md](tool-usage.md))
- [ ] **16:9 cover image** (recommended 380×216 px)

## Optional items

- [ ] **Demo video** (5–8 min): overview, core features, reflection on build
      approach and CodeBuddy/WorkBuddy tips
- [ ] **Live demo link** (earns bonus points) – only if it is stable and does
      not expose real credentials or data

## Track-specific deliverables (FinTech – Aspire)

- [ ] **Worked example** for each of the five scenarios, in the submission:
  - [ ] 1. Unified natural-language query with citations
  - [ ] 2. Data freshness within the bounded window
  - [ ] 3. Negative permission case with no existence leak
  - [ ] 4. Live permission change handling
  - [ ] 5. Audit inquiry by a compliance officer
- [ ] **Architecture diagram** including a **trust-boundary diagram** and key
      design trade-offs
- [ ] Chosen case study stated at the start of the presentation

## Quality gates before submitting

- [ ] **Final testing** – end-to-end run of the demo script on a clean machine
- [ ] **Security testing** – every invariant in SECURITY.md has a passing test
      or a documented exception; negative cases verified by hand as well
- [ ] Secrets scan of the repository and its git history
- [ ] Mocked integrations are labelled as mocked in code, docs and the demo
- [ ] README, ARCHITECTURE.md and DECISIONS.md match what was actually built
- [ ] **Demo script** written and rehearsed, with fallbacks if a live service fails
- [ ] **Final presentation** prepared (for preliminary judging and, if selected, Demo Day)
- [ ] Submission form filled in and confirmed by all three team members
