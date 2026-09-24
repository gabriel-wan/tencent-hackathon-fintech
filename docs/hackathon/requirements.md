# Hackathon requirements (FinTech track)

Extracted from the official handbook ([handbook.pdf](handbook.pdf)) and the
contest page (<https://tch.tencentcloud.com/contest/44>), checked on
2026-09-24. If these two ever disagree, ask the organisers; do not guess.

## 1. Mandatory project requirements (all tracks)

| Requirement | Detail | Source |
|---|---|---|
| Original project | Must be original and must not infringe third-party rights | Handbook §8, §13 |
| Built on CodeBuddy or WorkBuddy | "Built on at least one of the products CodeBuddy or WorkBuddy" | Handbook §8 |
| Proof of tool usage | **Mandatory.** Chat screenshots, API call logs, or a written development-process description. Without proof the project does not proceed to scoring. | Handbook §8 |
| Conversation history | Minimum of **3 screenshots or a screen recording** of CodeBuddy/WorkBuddy chat logs from development | Handbook §8 |
| Source code | Complete source code submitted through a GitHub repository | Handbook §4, §8 |
| Project title | Name of the project | Handbook §8 |
| Short blurb | Summary of the value delivered. **Hard limit: under 10 words** | Handbook §8 |
| Project description | Overview (target scenarios, users, value proposition); real-world scenario insights (pain points, audience, core problems solved); solution design (business and technical architecture, how prompts drive the AI); business value (quantifiable metrics or clearly defined impact) | Handbook §8 |
| Cover image | 16:9, used for the online showcase; recommended 380×216 px | Handbook §8 |
| Demo video | **Optional.** 5–8 minutes: overview, core agent features and usage, short reflection on the build approach and tool tips referencing CodeBuddy/WorkBuddy | Handbook §8 |
| Project link | **Optional.** Live URL or demo link; "earns bonus points" | Handbook §8 |
| Track-specific items | Check the challenge statement (see below) | Handbook §8 |

Team and eligibility (Handbook §10): 1–3 members per team, all based in
Singapore, one registration per team.

## 2. FinTech challenge requirements

Full detail and worked examples are in [challenge.md](challenge.md). Summary of
what must be demonstrably solved, each with a worked example in the submission:

1. **Unified natural-language query** – determine relevant platforms, retrieve
   permission-filtered context, return a single grounded answer with citations.
2. **Permission-aware retrieval** – know the asker's identity and permissions at
   query time; filter *before* the LLM; never flatten platform permission models.
3. **Data freshness** – new or updated content available within a bounded,
   predictable window, "on the order of minutes to ~1 hour"; never silently
   serve stale content as current.
4. **Negative permission cases** – refuse or filter without revealing that
   restricted content exists (no metadata side-channel).
5. **Live permission changes** – revocations are reflected in subsequent
   queries; no stale-permitted content.
6. **Audit inquiry** – tamper-evident, complete, queryable audit trail that a
   compliance officer can use to reconstruct who asked what, what was
   retrieved, what was answered, with timestamps and per-document decisions.
7. **LLM leakage mitigation** – reduce the risk of hallucinated or confabulated
   content the model was not given.

Required deliverables for this track: live demo walkthrough; architecture
diagram including a **trust-boundary diagram** and key trade-offs; complete
source code on GitHub.

## 3. Timeline

| Milestone | Date | Notes |
|---|---|---|
| Challenge kick-off | 16 Sep 2026 | Submissions open |
| Training | 16 Sep – 16 Oct 2026 | Online and offline workshops |
| **Project submission** | **16 Oct 2026** | Contest page shows the window as 09.16–10.16, 00:00–23:59 |
| Finalist announcement | 23 Oct 2026 | Top 2 teams per track go to Demo Day |
| Demo Day and awards | 3 Nov 2026 (TBC in the handbook; the contest page lists it without TBC) | Singapore, offline |

Submission link: <https://tinyurl.com/TCHackathonSGProjectSubmission>

## 4. Judging

Preliminary technical judging is by the challenge contributor (Aspire) and
Tencent Cloud experts. The handbook says detailed track criteria are shared
after registration. **If the team has received them, add them here.**

Demo Day evaluation dimensions (10 points each, Handbook §11):

| Dimension | Key review focus |
|---|---|
| Impact & Relevance | Addresses a real problem, creates meaningful value |
| Human-Centered Design | Designed for real users |
| AI Interaction | Quality and depth of AI usage |
| Technical Execution | Technical quality and completeness |
| Feasibility | Realistic and scalable beyond the hackathon |
| Demo & Storytelling | How effectively the project is presented |
| Innovation & Creativity | Originality and uniqueness |
| User Experience & Accessibility | Usability and accessibility |
| Responsible AI & Ethics | Responsible and trustworthy AI practices |
| Overall Quality & Judge's Impression | Overall assessment |

For this challenge, "Responsible AI", "Technical Execution" and "Feasibility"
map most directly onto the permission and audit requirements.

## 5. Hackathon-provided credits (not architecture requirements)

| Tool | Allocation |
|---|---|
| CodeBuddy / WorkBuddy | 1,000 credits per person |
| Miora | 1,000 credits per person |

These are registration benefits to support development. They do **not** oblige
the team to build any of these tools into the product architecture. The only
hard tool requirement is that the project is *built using* CodeBuddy or
WorkBuddy with proof (section 1).

## 6. Prizes (for context)

First SGD 10,000; second SGD 5,000; third SGD 2,000; five track winners
receive 5,000 CodeBuddy/WorkBuddy credits. Additional benefits listed in the
handbook: Tencent CSIG internship fast track, incubation opportunities, and an
official Tencent Cloud certificate for teams that submit.

## 7. Intellectual property

IP stays with the team. The organiser receives a non-exclusive, royalty-free
licence to use the project name, description, screenshots/screencasts and
team information for non-commercial promotion (Handbook §13).
