"""Retrieval evaluation corpus (scripts/eval_retrieval.py): one fictional company, Lumen Pay.

Long documents in the shape each connector writes them (Confluence storage HTML through `storage_text`, Jira fields
through `issue_text`, Slack threads as "Name: message" lines titled by `thread_title`, Drive as plain text), so a
change to chunking or to a connector's text shows up in the scores. UPDATES are written after DOCUMENTS with a later
`updated_at`, as a sync would. Questions name their gold documents and snippets that answer them.
All names, numbers and policies are invented.
"""
from app.connectors.confluence import storage_text
from app.connectors.jira import issue_text
from app.connectors.slack import thread_title

DOMAIN = "lumenpay.example"
# Eve also holds a seeded user's principals, so she sees that user's share of the Company A-sized filler
# (app/seed_scale.py) that eval_retrieval.py adds as distractors.
EVE = ["slack:members", "slack:user:UEVE", f"google:domain:{DOMAIN}", f"google:user:eve@{DOMAIN}", "atlassian:user:AEVE",
       "slack:user:U001", "atlassian:user:A001", "google:user:alice@merlionpay.example", "google:domain:merlionpay.example"]
REX = ["slack:members", "slack:user:UREX", f"google:domain:{DOMAIN}", f"google:user:rex@{DOMAIN}", "atlassian:user:AREX"]
USERS = [  # email, name, is_admin, principals (seed.seed_company format)
    (f"eve@{DOMAIN}", "Eve Lim", True, EVE),  # sees everything
    (f"rex@{DOMAIN}", "Rex Goh", False, REX),  # not on the security page: the leak check
    (f"mei@{DOMAIN}", "Mei Chen", False, []),
    (f"daniel@{DOMAIN}", "Daniel Ong", False, []),
    (f"farah@{DOMAIN}", "Farah Aziz", False, []),
]
BOUNDARY = [
    ("confluence", "OPS", "space", "Operations"),
    ("confluence", "SEC", "space", "Security"),
    ("drive", "F_OPS", "folder", "Operations"),
    ("jira", "PAY", "project", "Payments"),
    ("slack", "C_PAYENG", "channel", "#payments-eng"),
    ("slack", "C_STANDUP", "channel", "#standup"),
]
TEAM = ["atlassian:user:AEVE", "atlassian:user:AREX"]
SECURITY = ["atlassian:user:AEVE"]
DRIVE_ACL = [f"google:domain:{DOMAIN}"]
SLACK_ACL = ["slack:members"]


def _doc(source, source_id, scope_id, title, updated_at, acl, text):
    return {"source": source, "source_id": source_id, "scope_id": scope_id, "title": title,
            "url": f"https://{DOMAIN}/{source}/{source_id}", "updated_at": updated_at, "acl": acl, "text": text}


def _page(page_id, space, title, updated_at, acl, html):
    return _doc("confluence", page_id, space, title, updated_at, acl, storage_text(html))


def _adf(*blocks):
    """("h", level, text) or ("p", text) blocks as Atlassian Document Format."""
    def node(b):
        if b[0] == "h":
            return {"type": "heading", "attrs": {"level": b[1]}, "content": [{"type": "text", "text": b[2]}]}
        return {"type": "paragraph", "content": [{"type": "text", "text": b[1]}]}
    return {"type": "doc", "content": [node(b) for b in blocks]}


def _ticket(issue_id, key, summary, status, assignee, priority, labels, updated_at, description, comments=()):
    fields = {"summary": summary, "description": description, "updated": updated_at,
              "status": {"name": status}, "assignee": {"displayName": assignee} if assignee else None,
              "priority": {"name": priority}, "labels": list(labels),
              "comment": {"comments": [{"body": _adf(("p", c))} for c in comments]}}
    return _doc("jira", issue_id, "PAY", f"{key}: {summary}", updated_at, TEAM, issue_text(fields))


def _thread(channel_id, channel_name, ts, updated_at, lines):
    return _doc("slack", f"{channel_id}:{ts}", channel_id, thread_title(channel_name, ts), updated_at, SLACK_ACL,
                "\n".join(lines))


DISPUTES = _page("P100", "OPS", "Card Dispute Handling Runbook", "2026-08-02T03:00:00+00:00", TEAM, """
<h1>Card Dispute Handling Runbook</h1>
<p>This runbook covers how the Disputes team at Lumen Pay receives, investigates and responds to card disputes
raised by cardholders through their issuing bank. It applies to Visa and Mastercard transactions acquired by
Lumen Pay for our merchants in Singapore and Malaysia.</p>
<h2>Intake</h2>
<p>Disputes arrive from the acquiring processor as a daily file at 06:00 SGT. The on-duty analyst loads the file
into the disputes queue in the back office and assigns each case within two hours of arrival. Cases that arrive
outside the file, for example by email from a merchant, are logged by hand with the same fields.</p>
<p>Every case records the reason code, the transaction amount, the merchant ID, the original authorisation code
and the response deadline. The deadline is set by the scheme and is never extended by us.</p>
<h2>Response deadlines</h2>
<p>We must submit our representment within 7 calendar days of the dispute arriving, even though the schemes allow
longer. The shorter internal window leaves time for a second review and for the merchant to send late evidence.
A case that misses the internal window is escalated to the Disputes Lead the same day.</p>
<p>Disputes above SGD 5,000 always need a second review by a senior analyst before submission. Disputes from the
same merchant that exceed ten in one week are reported to the Merchant Risk team, who decide whether to put the
merchant on enhanced monitoring.</p>
<h2>Evidence pack</h2>
<p>The evidence pack must include the authorisation log, the proof of delivery or service, the merchant's refund
policy as shown to the customer at checkout, and any correspondence with the cardholder. For card-not-present
transactions we also attach the 3-D Secure authentication result, which shifts liability to the issuer when the
cardholder was successfully authenticated.</p>
<p>Evidence is uploaded as PDF only. Screenshots are combined into one PDF per case so the scheme reviewer sees
them in order. Never include full card numbers in the pack; use the last four digits.</p>
<h2>Reason codes we see most</h2>
<p>Visa reason code 13.1 (merchandise or services not received) is the most common, followed by 10.4 (other
fraud, card-absent environment). For 13.1 the delivery confirmation with a signature or a photo at the door is
the strongest evidence. For 10.4 the 3-D Secure result decides most cases.</p>
<h2>Escalation</h2>
<p>The Disputes Lead is Farah Aziz. Escalate to her when a deadline is at risk, when a merchant disputes our
decision to accept liability, or when the same cardholder files more than three disputes in a month, which may
indicate first-party fraud. Outside office hours, escalate through the #payments-eng channel.</p>
<h2>Closing a case</h2>
<p>When the scheme rules on a case, the analyst records the outcome, moves the funds through the ledger, and
notifies the merchant within one business day. Won and lost cases both feed the monthly disputes report.</p>
""")

AML = _page("P200", "OPS", "AML Transaction Monitoring Policy", "2026-07-15T02:00:00+00:00", TEAM, """
<h1>AML Transaction Monitoring Policy</h1>
<p>This policy sets out how Lumen Pay monitors payment activity for money laundering and terrorism financing,
as required by our licence. It applies to every merchant account and every payout.</p>
<h2>Monitoring rules</h2>
<p>The monitoring engine runs every transaction against a set of rules. The structuring rule flags a merchant
whose payouts total more than SGD 20,000 across any 3 consecutive days while each single payout stays below
SGD 5,000. The velocity rule flags more than 50 refunds from one merchant in a day. The geography rule flags
payouts to a bank account in a high-risk jurisdiction on the internal list, which Compliance reviews quarterly.</p>
<h2>Alert triage</h2>
<p>Every alert must be triaged within 24 hours of being raised. Triage decides one of three outcomes: close as a
false positive with a written reason, request information from the merchant, or escalate to an investigation.
Requests for information give the merchant five business days to reply.</p>
<h3>Investigations</h3>
<p>An investigation is opened by a Compliance analyst and reviewed by the Money Laundering Reporting Officer.
The investigation file records the alerts, the merchant's explanation, the transaction history for the last six
months and the analyst's conclusion.</p>
<h2>Suspicious transaction reports</h2>
<p>When an investigation finds reasonable grounds for suspicion, the Money Laundering Reporting Officer files a
suspicious transaction report with the authorities within 15 business days of the investigation being opened.
Staff must never tell the merchant that a report is being considered or has been filed; this is tipping off and
is a criminal offence.</p>
<h2>Record keeping</h2>
<p>Alerts, investigation files and reports are kept for 5 years after the merchant relationship ends. Records
are stored in the compliance archive, which only Compliance and Internal Audit can read.</p>
<h2>Training</h2>
<p>All staff complete AML training when they join and every year after that. Analysts complete an additional
scenario-based course each quarter.</p>
""")

REFUND_V1 = """
<h1>Refund Policy</h1>
<p>This page describes how refunds work for payments processed by Lumen Pay, for merchants and for our support
team. Merchants decide whether to refund; we decide how the money moves.</p>
<h2>How refunds are paid</h2>
<p>Refunds are always paid back to the original payment method. A card refund appears on the cardholder's
statement as a credit from the merchant. Refunds are paid within 10 business days of the merchant approving them.
PayNow payments are refunded to the same PayNow account; we do not refund to a different account even if the
customer asks.</p>
<h2>Partial refunds</h2>
<p>A payment can be partially refunded up to 3 times, as long as the total refunded never exceeds the original
amount. Each partial refund is a separate ledger entry linked to the original payment.</p>
<h2>Late refunds</h2>
<p>Refunds requested more than 90 days after the purchase need approval from the Finance team, because the
original settlement has already been reconciled and closed. Finance approves or rejects within two business days.</p>
<h2>Refund fees</h2>
<p>We do not return the processing fee on a refunded payment. Merchants on the Growth plan get the fee back on
refunds made within 24 hours of the payment.</p>
<h2>Disputes</h2>
<p>A payment that is already under dispute cannot be refunded; the dispute process decides the outcome. See the
Card Dispute Handling Runbook.</p>
"""
REFUND = _page("P300", "OPS", "Refund Policy", "2026-06-01T01:00:00+00:00", TEAM, REFUND_V1)

SECURITY_PM = _page("P400", "SEC", "Security Incident Postmortem: leaked API key", "2026-09-20T05:00:00+00:00", SECURITY, """
<h1>Postmortem: leaked merchant API key</h1>
<h2>Summary</h2>
<p>On 14 September a merchant's live API key was committed to a public code repository by a contractor working
for the merchant. Our secret scanning partner reported it 40 minutes later. The key was revoked within 12 minutes
of the report and no fraudulent payouts were made.</p>
<h2>Timeline</h2>
<p>09:10 the key was pushed. 09:50 the scanning partner alerted security@. 09:58 the on-call security engineer
confirmed the key was live. 10:02 the key was revoked and the merchant was told to rotate.</p>
<h2>Root cause</h2>
<p>Merchant keys did not expire and were not limited by IP address, so a leaked key stayed useful indefinitely.</p>
<h2>Actions</h2>
<p>All live keys now expire after 180 days, and merchants can restrict a key to a list of IP addresses. The
security team will review key usage anomalies weekly. Owner of the actions: the Head of Security.</p>
""")

INCIDENT = _doc("drive", "D100", "F_OPS", "Incident Response Playbook", "2026-05-10T04:00:00+00:00", DRIVE_ACL, """\
Incident Response Playbook

Purpose
This playbook tells the on-call engineer what to do when a production incident affects payments. It covers
severity levels, who to page, how to communicate and what happens after the incident is resolved.

Severity levels
SEV1 means payments are failing for more than 5 percent of traffic or settlement is blocked for all merchants.
SEV2 means a single payment method or a single large merchant is affected. SEV3 means degraded performance with
no failed payments. When in doubt, declare the higher severity; it can be lowered later.

Paging
For a SEV1 the incident commander must be paged within 5 minutes of the incident being declared. The incident
commander rotation is in the on-call schedule. The incident commander pages the payments engineering lead and,
if merchants are affected, the merchant support lead.

Communication
During a SEV1 the status page is updated every 30 minutes, even when there is no news. The first update goes out
within 15 minutes of declaring the incident. Internal updates go to the incident channel; do not discuss the
incident in direct messages, so the timeline can be rebuilt later.

Working the incident
The incident commander coordinates and does not debug. One engineer owns the investigation, one owns
communication. Changes to production during an incident need the incident commander's approval and are written
in the incident channel before they are made. Rolling back the last deploy is the default first action when an
incident starts within an hour of a deploy.

After the incident
Every SEV1 and SEV2 has a written postmortem within 5 business days. The postmortem is blameless and lists the
timeline, the root cause, what went well, what went badly and the actions with owners and dates. Actions are
tracked as tickets in the PAY project and reviewed in the weekly operations meeting until they are closed.

Drills
The team runs a game day every quarter, in which a simulated SEV1 is declared in the staging environment and the
whole process is followed, including status page updates to a private test page.
""")

KYC = _doc("drive", "D200", "F_OPS", "Merchant KYC Onboarding Procedure", "2026-04-22T04:00:00+00:00", DRIVE_ACL, """\
Merchant KYC Onboarding Procedure

Scope
Every new merchant goes through know-your-customer checks before their account can take live payments. This
procedure lists the documents we collect, the checks we run and who signs off.

Documents
We collect the business registration extract, the constitution of the company, proof of the business address,
and identity documents for every director and every ultimate beneficial owner. Address proofs and registration
extracts must be no older than 3 months on the day we receive them.

Ultimate beneficial owners
An ultimate beneficial owner is any person who owns or controls 25 percent or more of the merchant, directly or
through other companies. If no person reaches 25 percent, we record the senior managing official instead. We
verify every beneficial owner against sanctions and politically exposed persons lists.

Risk rating
Each merchant gets a risk rating of low, medium or high when onboarded. Merchants in high-risk categories, such as
gambling (merchant category code 7995), crypto exchanges and money transfer businesses, are always rated high and
need enhanced due diligence. Enhanced due diligence adds a source of funds explanation, a review of the website
and a call with a director.

Sign-off
Low and medium risk merchants are approved by an onboarding analyst. High risk merchants need approval from the
Head of Compliance. Onboarding should take no more than 3 business days for low risk merchants once all documents
are in.

Periodic review
High risk merchants are reviewed every 12 months, medium risk every 24 months and low risk every 36 months, or
earlier when monitoring raises an alert.
""")

TICKETS = [
    _ticket("10101", "PAY-101", "Migrate card authentication to 3-D Secure 2", "In Progress", "Mei Chen", "High",
            ["3ds2", "q4"], "2026-10-08T06:00:00+00:00",
            _adf(("h", 2, "Goal"),
                 ("p", "Move every card-not-present payment from 3-D Secure 1 to 3-D Secure 2 before the scheme "
                       "deadline on 15 November. 3DS2 sends more device data to the issuer, so fewer customers get "
                       "a challenge screen."),
                 ("h", 2, "Plan"),
                 ("p", "Roll out by merchant cohort: 10 percent in week one, 50 percent in week two, everyone in "
                       "week three. Watch the authentication success rate per issuer and roll back a cohort if it "
                       "drops by more than 2 points."),
                 ("h", 2, "Status"),
                 ("p", "Cohort one is live. Cohort two starts on Monday.")),
            ["Mei: cohort one success rate is 96.1 percent, slightly above 3DS1."]),
    _ticket("10102", "PAY-102", "Fix ledger reconciliation drift", "In Progress", "Daniel Ong", "Highest",
            ["ledger"], "2026-10-07T03:00:00+00:00",
            _adf(("h", 2, "Problem"),
                 ("p", "The nightly reconciliation between the ledger and the bank statement shows a drift of a few "
                       "cents on some days. The drift comes from rounding when converting MYR payouts to SGD."),
                 ("h", 2, "Fix"),
                 ("p", "Round once, at settlement, using banker's rounding, and store the unrounded amount on every "
                       "ledger entry.")),
            ["Daniel: the fix is in review."]),
    _ticket("10103", "PAY-103", "Support refunds for PayNow QR payments", "To Do", None, "Medium",
            ["paynow"], "2026-09-30T02:00:00+00:00",
            _adf(("p", "Merchants want to refund PayNow QR payments from the dashboard. Today support does it by "
                       "hand. Needs the bank's refund API, which is in their sandbox from October."))),
    _ticket("10099", "PAY-99", "Upgrade TLS on the payment gateway", "Done", "Daniel Ong", "High",
            ["security"], "2026-08-20T02:00:00+00:00",
            _adf(("p", "Disable TLS 1.0 and 1.1 on the payment gateway and require TLS 1.2 or newer.")),
            ["Daniel: deployed, monitoring shows no merchant on old TLS."]),
]

SETTLEMENT_LINES = [
    "Daniel Ong: settlement batch was late again last night, the bank file landed at 22:40",
    "Mei Chen: that's the third time this week. is it the bank or us?",
    "Daniel Ong: us. the batch starts at the 22:00 cutoff but the MYR conversion step waits on the rates feed",
    "Farah Aziz: merchants noticed, two asked support why funds arrived a day late",
    "Daniel Ong: proposal: move the settlement cutoff from 22:00 to 23:30 SGT so the rates feed is always in",
    "Eve Lim: what does that do to same-day settlement for SG merchants?",
    "Daniel Ong: nothing, the bank accepts files until 00:30 for same-day value",
    "Mei Chen: +1, and we should alert if the rates feed is later than 23:00",
    "Eve Lim: agreed. decision: settlement cutoff moves to 23:30 SGT from next Monday. Daniel owns the change",
    "Daniel Ong: will do, I'll add the rates feed alert too",
]
SETTLEMENT = _thread("C_PAYENG", "payments-eng", "1758700000.000100", "2026-09-24T09:00:00+00:00", SETTLEMENT_LINES)

STANDUP = _thread("C_STANDUP", "standup", "1759900000.000200", "2026-10-08T01:30:00+00:00", [
    "Mei Chen: yesterday 3DS2 cohort one went live. today watching issuer success rates, preparing cohort two",
    "Daniel Ong: yesterday the reconciliation drift fix went into review. today load testing the ledger change",
    "Farah Aziz: yesterday closed 14 disputes. today the monthly disputes report for September",
    "Rex Goh: yesterday onboarding calls with two high-risk merchants. today their enhanced due diligence files",
    "Eve Lim: today planning Q4 priorities: 3DS2 rollout, ledger accuracy, PayNow QR refunds",
])

DOCUMENTS = [DISPUTES, AML, REFUND, SECURITY_PM, INCIDENT, KYC, *TICKETS, SETTLEMENT, STANDUP]

# Written later, as a sync would after the source changed: only these versions may answer.
UPDATES = [
    _page("P300", "OPS", "Refund Policy", "2026-10-01T01:00:00+00:00", TEAM,
          REFUND_V1.replace("within 10 business days", "within 5 business days")),
    _ticket("10102", "PAY-102", "Fix ledger reconciliation drift", "Done", "Daniel Ong", "Highest",
            ["ledger"], "2026-10-10T08:00:00+00:00",
            _adf(("h", 2, "Problem"),
                 ("p", "The nightly reconciliation between the ledger and the bank statement shows a drift of a few "
                       "cents on some days. The drift comes from rounding when converting MYR payouts to SGD."),
                 ("h", 2, "Fix"),
                 ("p", "Round once, at settlement, using banker's rounding, and store the unrounded amount on every "
                       "ledger entry.")),
            ["Daniel: the fix is in review.", "Daniel: deployed on 10 October, reconciliation is clean."]),
    _thread("C_PAYENG", "payments-eng", "1758700000.000100", "2026-10-02T09:00:00+00:00", [
        *SETTLEMENT_LINES,
        "Daniel Ong: update: the bank asked us to send by 23:45 at the latest, so the cutoff is now 23:45 SGT",
    ]),
]
STALE = ["within 10 business days"]  # superseded text: must not be anywhere in the index after UPDATES

# kind, question, gold document keys (any counts), snippets (any counts; matched case-insensitively)
QUESTIONS = [
    ("specific", "How many days do we have to respond to a card dispute?", ["confluence:P100"], ["7 calendar days"]),
    ("specific", "Which disputes need a second review before submission?", ["confluence:P100"], ["above SGD 5,000"]),
    ("specific", "What evidence goes in a dispute evidence pack?", ["confluence:P100"], ["authorisation log"]),
    ("specific", "Who is the Disputes Lead?", ["confluence:P100"], ["Farah Aziz"]),
    ("specific", "What is the most common Visa dispute reason code?", ["confluence:P100"], ["13.1"]),
    ("specific", "What does the structuring rule flag?", ["confluence:P200"], ["SGD 20,000"]),
    ("specific", "How quickly must AML alerts be triaged?", ["confluence:P200"], ["within 24 hours"]),
    ("specific", "When must a suspicious transaction report be filed?", ["confluence:P200"], ["15 business days"]),
    ("specific", "How long do we keep AML records?", ["confluence:P200"], ["5 years"]),
    ("specific", "What is tipping off?", ["confluence:P200"], ["tipping off"]),
    ("specific", "How many times can a payment be partially refunded?", ["confluence:P300"], ["up to 3 times"]),
    ("specific", "Who approves refunds requested after 90 days?", ["confluence:P300"], ["Finance team"]),
    ("specific", "Do we return the processing fee on refunds?", ["confluence:P300"], ["processing fee"]),
    ("specific", "How fast must the incident commander be paged for a SEV1?", ["drive:D100"], ["within 5 minutes"]),
    ("specific", "How often is the status page updated during a SEV1?", ["drive:D100"], ["every 30 minutes"]),
    ("specific", "When is a postmortem due after an incident?", ["drive:D100"], ["within 5 business days"]),
    ("specific", "What counts as a SEV2 incident?", ["drive:D100"], ["single payment method"]),
    ("specific", "What ownership makes someone an ultimate beneficial owner?", ["drive:D200"], ["25 percent"]),
    ("specific", "Which merchants need enhanced due diligence?", ["drive:D200"], ["7995"]),
    ("specific", "How old can a business registration extract be?", ["drive:D200"], ["3 months"]),
    ("specific", "Who signs off high risk merchants?", ["drive:D200"], ["Head of Compliance"]),
    ("specific", "What is the deadline for moving to 3-D Secure 2?", ["jira:10101"], ["15 November"]),
    ("specific", "What causes the ledger reconciliation drift?", ["jira:10102"], ["rounding"]),
    ("specific", "Why was the settlement batch late?", ["slack:C_PAYENG:1758700000.000100"], ["rates feed"]),
    ("specific", "How long did it take to revoke the leaked API key?", ["confluence:P400"], ["12 minutes"]),
    ("broad", "What is the team working on right now?",
     ["slack:C_STANDUP:1759900000.000200", "jira:10101", "jira:10102"], ["3DS2", "reconciliation", "cohort"]),
    ("broad", "What is Mei working on?", ["slack:C_STANDUP:1759900000.000200", "jira:10101"], ["3DS2", "3-D Secure 2"]),
    ("broad", "What are our Q4 priorities?", ["slack:C_STANDUP:1759900000.000200", "jira:10101"],
     ["Q4 priorities", "3DS2 rollout"]),
    ("broad", "Which payments tickets are still open?", ["jira:10101", "jira:10103"], ["3-D Secure 2", "PayNow QR"]),
    ("broad", "What decisions did the payments team make recently?", ["slack:C_PAYENG:1758700000.000100"],
     ["cutoff"]),
    ("broad", "Give me an overview of our compliance obligations.", ["confluence:P200", "drive:D200"],
     ["triaged within 24 hours", "know-your-customer"]),
    ("fresh", "How long do refunds take to reach the customer?", ["confluence:P300"], ["5 business days"]),
    ("fresh", "Is the ledger reconciliation drift fixed?", ["jira:10102"], ["deployed on 10 October", "Done"]),
    ("fresh", "What is the settlement cutoff time now?", ["slack:C_PAYENG:1758700000.000100"], ["23:45"]),
    ("fresh", "What is the status of PAY-102?", ["jira:10102"], ["Done"]),
    ("fresh", "Is anyone assigned to PayNow QR refunds?", ["jira:10103"], ["To Do", "Unassigned"]),
    ("offtopic", "What's the weather in Tokyo tomorrow?", [], []),
    ("offtopic", "Give me a recipe for chicken rice.", [], []),
    ("offtopic", "Who won the 2022 World Cup?", [], []),
    ("offtopic", "How do I renew my passport?", [], []),
    ("offtopic", "What is the best gaming laptop?", [], []),
]
