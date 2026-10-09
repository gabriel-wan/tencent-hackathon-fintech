# What KnowBuddy does, and how

**For:** judges, and anyone who wants to see each feature working and know how it works underneath.
**You'll:** walk through the challenge's five scenarios as worked examples, then the other features, then the
demo order.
**Not here:** setting it up → [RUNNING.md](RUNNING.md) · the parts and diagrams → [ARCHITECTURE.md](ARCHITECTURE.md) ·
the security rules → [SECURITY.md](SECURITY.md).

**Contents:** Part 1: the five scenarios · Part 2: other features · Part 3: running the demo

Every "You'll see" below is real output, recorded on 8 Oct 2026 with the demo personas ([RUNNING.md](RUNNING.md) §4)
and the real LLM. Answers come from an LLM, so the wording varies between runs; the sources and the outcome don't.
The data is fictional: MerlionPay, a payments company, and Kopi Labs, a second company that must never see
MerlionPay's content.

## Part 1: the five scenarios

### Scenario 1: one answer from several tools, with citations

**The challenge asks:** answer a natural-language question from several platforms at once, with citations, using
only what the asker may see.

**Try it:** sign in as **Alice** (payments engineer) and ask *"What is blocking the payment gateway migration, and
what does the runbook say to do if authorisations start failing?"*

**You'll see:**
> The payment gateway migration (PAY-412) is blocked because the vendor has not rotated the TLS certificate for the
> new gateway yet. The runbook says that if the authorisation error rate exceeds 2% for 5 minutes, fail over to the
> secondary acquirer.
>
> **Sources:** `#payments-oncall` (Slack) · Payments on-call runbook (Google Drive)

One answer, built from a Slack thread and a Drive document, each cited.

**What happened underneath:**
1. Alice's session gives her principals in each tool (her Slack user, `slack:members`, her Google user and domain).
2. One search over every tool returns only MerlionPay documents whose ACL includes one of those principals and
   whose channel or folder is inside the admin's boundary.
3. Each candidate is re-checked as Alice before anything reaches the LLM.
4. The LLM gets the allowed sources as labelled, untrusted blocks, and must cite them. Citations to anything it wasn't
   given are removed.

**Tested by:** `test_answer_cites_documents_and_is_audited`, `test_invented_citation_is_removed_before_answering`
(`test_query_pipeline.py`); `test_private_channel_member_sees_thread_and_non_member_does_not` (`test_search.py`).

**Limits:** each question is answered on its own, without earlier questions in the conversation.

### Scenario 2: fresh within a stated window

**The challenge asks:** new or changed content must be available within a bounded, predictable window, and stale
content must never be presented as current.

**How it works:** the `sync` service copies each company's chosen channels, folders, projects and spaces every
**5 minutes**, and an admin can run **"sync now"** (`POST /api/admin/sync`). Only changed text is re-processed. Each
scope records when it was last completely synced, and every source in an answer carries that time (`synced_at`) and
when the item itself was last updated.

**Try it** (with your own tools, [RUNNING.md](RUNNING.md) §5): add a step to a runbook in Google Drive, press **Sync
now** on the Boundary page, then ask about that step.

**You'll see:** the answer uses the new step, and its source shows the new "updated" time.

**Tested by:** `test_upsert_rewrites_chunks_only_when_the_text_changes`,
`test_each_scope_records_its_last_successful_sync`, `test_a_failed_fetch_deletes_nothing` (`test_sync.py`);
`test_results_carry_when_their_scope_last_synced` (`test_search.py`).

**Limits:** not yet recorded by hand against a real Drive. The Sources list shows when each item was last updated;
showing "synced N minutes ago" (the API already returns it) is planned.

### Scenario 3: a restricted document stays invisible

**The challenge asks:** a person must get nothing from a document they may not see, and the answer must not reveal
that it exists.

**Try it:** sign in as **Charlie** (external contractor) and ask *"What happened in the Q3 security incident?"* Then
ask the same as **Priya** (admin and compliance).

**You'll see:**
- Charlie: *"I could not find this in the sources you have access to."*
- Priya: *"The Q3 security incident was a credential stuffing attack against the merchant portal that occurred
  between 14 and 16 August… 312 merchant accounts were reset… Remediation included rate limiting and mandatory 2FA
  for merchants."* Sources: `#security-incidents` (Slack) · Q3 security incident report (Drive).

Charlie's reply is word for word the reply for a question about something that doesn't exist at all, so it confirms
nothing.

**What happened underneath:** the incident report and the security channel aren't in Charlie's ACLs, so the search
never returns them; they can't even affect the ranking. The only document he may see (the contractor guide) didn't
answer the question, so the fixed reply is returned. The audit log records what he tried to reach (Scenario 5).

**Tested by:** `test_content_the_user_cannot_see_never_reaches_the_llm`, `test_nothing_allowed_means_llm_is_not_called`,
`test_restricted_matches_are_audited_without_changing_what_the_user_or_llm_sees` (`test_query_pipeline.py`).

**Also:** company isolation. **Dana** (Kopi Labs) asks *"How did the payment gateway migration go?"* and gets only
her own company's answer: *"The payment gateway migration finished last week with no blockers."* (source: Kopi
Labs' `#general`). MerlionPay's blocked migration never appears. Tested by
`test_another_companys_documents_are_never_returned` (`test_search.py`).

### Scenario 4: a revoked permission applies at once

**The challenge asks:** when someone loses access in a tool (removed from a Slack channel, a page restricted), later
answers must stop using that content.

**How it works:** stored permissions are only the first filter. Before anything reaches the LLM, KnowBuddy asks each
tool, **as the person asking**, whether they can still read each candidate: in parallel, with a 2-second timeout. A
"no", an error or a timeout drops the item. So a revocation applies on the **very next question**, without waiting
for a sync.

**Try it** (with your own tools, [RUNNING.md](RUNNING.md) §5): after a sync, remove a teammate from a private Slack
channel in the boundary, then ask about it as them.

**You'll see:** the answer no longer uses that channel, straight away.

**Seen for real (8 Oct):** a test account's Slack token had been revoked. On its next question the live check
refused every one of its Slack documents (`token_revoked`; the audit record says "denied by slack check" for each),
and the reply was the fixed "not found". Nothing from the stored copy was used.

**Tested by:** `test_live_check_denial_drops_a_document_the_stored_acl_allowed` (`test_query_pipeline.py`);
`test_checker_error_denies`, `test_timeout_denies_without_waiting_for_the_checker`,
`test_one_failing_source_does_not_affect_another` (`test_live_check.py`);
`test_live_check_asks_the_source_as_the_asking_user` (`test_sync.py`).

**Limits:** Slack's check is per channel, so a *deleted* Slack message drops at the next sync (within 5 minutes);
Drive, Jira and Confluence deletions drop at once. The demo personas have no real connections, so their questions are
checked against stored permissions instead.

### Scenario 5: what did this person access?

**The challenge asks:** a compliance officer can reconstruct what a user asked, what was retrieved, the decision for
each document, and what was answered, from a tamper-evident log.

**Try it:** sign in as **Priya** (admin) and open **Audit** in the header. Filter **User**
`charlie@contractor.example`, **Tool** Google Drive, **Channel, folder, project or space ID** `F_SEC` (the Security folder), and press **Search**
(or open http://localhost:3000/admin/audit?user=charlie%40contractor.example&source=drive&scope_id=F_SEC). Open the
newest row, then press **Verify chain**. The same data comes from the API: `GET /api/admin/audit` with those
filters, and `POST /api/admin/audit/verify`.

**You'll see** Charlie's question from Scenario 3, as the row *Asked "What happened in the Q3 security incident?"
· 1 sent to the LLM · 2 restricted · not found*. Opening it shows:

| Field | Value |
|---|---|
| Question | What happened in the Q3 security incident? |
| Candidates | `drive:D_CONTRACTOR_GUIDE`: allowed by drive check |
| Restricted matches | `drive:D_Q3_INCIDENT` and `slack:C_SECURITY:…`: "user not in document ACL" |
| Sent to the LLM | `drive:D_CONTRACTOR_GUIDE` only |
| Answer | I could not find this in the sources you have access to. |
| Chain | this record's hash and the previous record's hash |

Verify chain shows **Chain intact** with the number of records checked, and the latest record's hash with a **Copy
hash** button. Alice (not an admin) who opens the page is sent back to the chat, and the API gives her `403 Admins
only`. Each search and verification is itself written to the log, so it appears in the list too.

**What happened underneath:** every question writes one record with the user, time, question, every candidate with
its decision and reason, what the question matched but the user may not see ("restricted matches", recorded only
here, never shown to them), what was sent, the answer and timings. Each record holds the hash of the previous one in
its company's chain, so changing or deleting any record breaks the chain, and the app's database login can only add
records.

**Tested by:** `test_the_challenges_audit_inquiry`, `test_a_changed_record_is_detected`, `test_a_deleted_record_is_detected`,
`test_the_app_can_never_switch_to_a_more_powerful_role`, `test_only_admins_can_search_or_verify` (`test_audit.py`).

**Limits:** documents appear by key, not title, until the team decides
whether an admin may see titles of documents they can't read. Someone with full database access could rewrite and
re-hash the chain; noting the chain's `head` outside the system catches that.

## Part 2: other features

### Signing in by connecting your tools

There is no password. Signing in with Google, Slack or Atlassian proves who you are and connects that tool in one
step. The first full member of a new Slack workspace starts its company and becomes its admin; later sign-ins from
that workspace join it. Atlassian only joins a company whose admin has added the site, because Atlassian can't tell a
contractor from an employee. Tokens are stored encrypted, and sessions last 12 hours.
How: [ARCHITECTURE.md](ARCHITECTURE.md) §5. Tested by `test_connections_api.py`.
Limits: whoever signs in first becomes admin, and there is no way yet to hand the role over.

### The admin's boundary

The admin chooses which channels, folders, projects and spaces KnowBuddy may read at all. Content outside the
boundary is never synced or searched, even for people who can see it in the tool. In the demo, the "Salary bands"
file is outside the boundary, so nobody gets it. Every change is audited.
**Try it:** as the admin of a company with Slack connected, open **Boundary** and tick a channel that isn't in it yet.
**You'll see** it sync within about a minute ("Synced just now"), and questions about it start being answered;
untick it and they stop at once. The scope lists come from the admin's own connection, so an admin can only add what
they can see themselves. (The seeded demo company has no connections, so its sections say "Connect Slack to choose
channels".)
Tested by `test_document_outside_admin_boundary_is_excluded` (`test_search.py`), `test_admin.py`.

### Grounded answers, and retrieved text kept in its place

The LLM only sees allowed sources, wrapped as untrusted data, and must cite them. An answer citing nothing it was
given becomes the fixed "not found" reply. The model has no tools to call, and the website shows answers as plain
text, with only http(s) links clickable.

Prompt injection (ADR-011): a source can't fake the end of its block, in any spelling or with hidden characters. A
line written to the AI ("ignore your previous instructions", "note to AI assistants:", "SYSTEM: new rule", in
English or Chinese) becomes `[instruction removed]` before the LLM sees it, and the answer reports how many lines were
removed.
Links the model wasn't shown are removed from answers. The audit record names the source and the rule, never the
text.
Try it: re-seed ([RUNNING.md](RUNNING.md) §7), sign in as Alice and ask "What is the status of the payment gateway
migration?". `#eng` has a planted ops-bot message telling the AI to say the migration was cancelled and to send
people to a "re-verify" link. You'll see the real status (blocked on the TLS certificate, sandbox tests Friday), with
no "cancelled" and no link; at http://localhost:8000/docs the same question returns `instructions_removed: 1`.
How: [QUERY_PIPELINE.md](architecture/QUERY_PIPELINE.md) §3, steps 6 to 8. Tested by `test_grounding.py` and
`test_injection.py` (with a fake model that obeys the attacker), and live against `hy3` with 10 attacks
([TESTING.md](TESTING.md) §4).
Limits: an attack reworded without any of the scanner's phrases is left to the model's rules; the website doesn't
show the notice yet.

### Need-to-Know Shield: personal data only for the people handling it

Being allowed to open a document is not the same as needing the customer's card number in it. Before any text
leaves for the LLM, the Shield masks sensitive identifiers: cards, NRIC/FIN, bank accounts, IBANs, passports, dates
of birth, phones, emails of people outside the company, names (labelled; a person's name in every mention) and Singapore addresses. Only the people the
source names as handling that item (Jira assignee and reporter, Drive owners and editors, Confluence owner and
author) see them in full. Credentials are masked for everyone, admins included. The masking is a fixed set of
checked patterns (Luhn for cards, mod-97 for IBANs), so the same text always gives the same result.

**Try it:** ask *"What happened in dispute 118?"* as **Alice**, then as **Priya** (the dispute log's owner).

**You'll see:** Alice's sources reach the LLM as *"customer: [name 1] ([email 1], [phone 1], NRIC [NRIC *****567D])
… card [card ending 1111] … account no. [account ending 6789]"*, so her answer can only repeat those tags; Priya's
answer can give the full details. Each source in the API response says how many identifiers were masked
(`redacted`, e.g. `{"card": 1, "nric": 1}`). The answer is checked again before it is returned: an identifier the
model was not shown and the user did not type is masked (challenge §2.5). The audit stores the question and
answer fully masked, even for Priya, because it can never be edited or erased.

Tested by `test_redaction.py`, the Shield tests in `test_query_pipeline.py`, and `test_sync.py` (embeddings only
ever receive masked text). Limits: a name that nothing labels anywhere in the sources, and street names, are not detected; a bare 8-digit
number starting 3, 6, 8 or 9 is masked as a phone (ADR-010).

### Development aids, clearly labelled

The persona switcher, the Slack token form and mock mode exist only in development, and
each is labelled on screen (amber, "DEVELOPMENT ONLY" or "MOCK DATA"), so none can pass for a real feature.

### Planned

- Showing "synced N minutes ago" under answers.

## Part 3: running the demo

**Prepare:** the stack running with the demo data loaded ([RUNNING.md](RUNNING.md) §3–4). For scenarios 2 and 4 live,
also your own Slack workspace connected, a boundary set and a sync run (§5). Two browser windows side by side, so
two personas can ask the same question.

| Order | Show | As |
|---|---|---|
| 1 | Scenario 1: one answer from Slack and Drive, with sources | Alice |
| 2 | Scenario 3: the same kind of question, refused without a trace; then the admin gets the answer | Charlie, then Priya |
| 3 | Company isolation: the same topic, a different company's truth | Dana, next to Alice |
| 4 | Scenario 5: the audit record of Charlie's attempt, and verify | Priya, at `/docs` |
| 5 | Scenario 4: remove someone from a channel, ask again | Your own Slack |
| 6 | Scenario 2: edit a document, sync now, ask again | Your own Drive |

**If something fails during the demo:**
- No LLM (every answer says "The assistant isn't available right now"): show scenarios 3 and 5, which don't depend
  on the answer's wording, and the tests (`-m security`).
- A tool's sign-in is down: use the personas for 1, 3 and 5, and explain 2 and 4 with their tests.
- Troubleshooting: [RUNNING.md](RUNNING.md) §8.
