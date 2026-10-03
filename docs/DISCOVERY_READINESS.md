# Mutabi: investigation and discovery readiness plan

Investigated October 4, 2026, Asia/Amman. This is an assessment and proposed implementation backlog. Application behavior has not been changed.

## Recommendation

Start with facilitated discovery sessions, using a small, reliable synthetic demo to test whether distributor staff want help tracking payment commitments and deciding their next action. Improve completion of the workflow before adding broad integrations or more AI features. Build a private self-service sandbox after the first sessions establish which workflow and user group matter.

The existing POC is a useful foundation for a guided demonstration. It is not yet suitable as a visitor-facing hosted application or an operational pilot. Its strongest engineering work is persistence, employee approval, accounting authority, retry handling, and safeguards. Its largest product gaps are unfinished exception workflows, promise lifecycle correctness, customer-language support, and a first experience dominated by demo infrastructure.

Working assumptions: the first audience is distributor owners plus finance/collections operators; Arabic/SAR examples are relevant because that is the current fixture market. These are assumptions from the application, not confirmed customer requirements. Recruitment must establish the actual market, channels, accounting tools, decision maker, and daily operator.

## What was investigated

- Read the README, walkthrough, policies, schema, frontend, web server, workflow/tools, interpreter adapters, tests, and saved evaluation records.
- Ran the existing automated suite: **65 tests passed** on October 4, 2026.
- Opened a fresh browser workspace on localhost port 8876 using `runtime/discovery-audit/demo.db`. Confirmed the initial screen, provider barrier, invoice queue, summary metrics, and exposed simulation controls. A 390px viewport DOM check found no horizontal document overflow; that is not a complete mobile usability or accessibility test.
- Ran six offline probes against temporary synthetic databases. Results are in [discovery_audit_evidence.json](discovery_audit_evidence.json). Reproduce with `.\.venv\Scripts\python.exe -m evaluation.discovery_audit`.
- Reviewed current primary sources for research methods, comparable receivables workflows, and hosted ChatGPT integration constraints.

No new live model evaluation was run. No customer messages were sent. The six probes inject controlled interpretations: they demonstrate downstream behavior, not live model accuracy. Existing reports describe a small prior run of 15 approved scenarios per provider, including eight unique model requests per provider and several deterministic accounting cases. Do not describe that evidence as 15 independent language-model accuracy trials or market validation.

## Evidence and readiness

| Area | Current evidence | Implication for sharing |
| --- | --- | --- |
| Core flow | Promise recording, follow-up task, approval, simulated send, and persisted history; existing tests pass | A guided walkthrough can communicate the concept |
| Accounting authority | Customer text cannot settle an invoice; fresh balance and contact checks guard sends | Preserve this trust foundation |
| Language | Arabic interface and RTL; saved live evaluations use English fixtures; draft templates are English | Arabic UI alone cannot demonstrate an Arabic collections workflow |
| Conversation | Each inference receives one reply and a reference date | Clarification responses and changed commitments lack prior context |
| Exceptions | Review and verification tasks are created; there are no staff resolution actions in the web action API | Users can reach a blocked state without a path to finish |
| Sharing | Loopback server, fixed approver, one workspace/provider, server-wide request token | Guided local use is the current supported mode |
| Learning | Business audit trail exists; no research-session model, usability timing, feedback workflow, or pilot funnel | Demo activity alone will not answer demand or usability questions |

### 1. Promise completion is incorrectly coupled to invoice settlement

**Reproduced:** on a SAR 3,000 invoice, record a SAR 1,000 promise and simulate a verified SAR 1,000 payment. The balance correctly remains SAR 2,000. `run_due_followups` marks the promise `partially_fulfilled` and drafts a message saying the promised payment was not fully received.

**Cause:** `mutabi/workflow.py:160` compares remaining invoice balance with the starting balance. It does not compare allocated verified payment with the promised amount. A reduction can therefore be treated as partial promise fulfillment even when the entire promised installment arrived.

**Change:** distinguish invoice balance, promised amount, and verified payment allocated to that promise. A fulfilled installment can coexist with an open invoice. Store baseline/payment evidence at promise creation and apply an explicit allocation rule. Do not attribute the same payment to several promises or infer receipt solely from balance reductions: credits, returns, and adjustments need a separate treatment.

**Acceptance:** SAR 1,000 promised/SAR 1,000 received → fulfilled promise, open SAR 2,000 invoice, no broken-promise wording; SAR 600 received → partially fulfilled with SAR 400 commitment remaining; no received payment → missed. Add overlapping-promise and credit-adjustment cases. This is a correctness fix before broader hands-on validation.

### 2. Changing a promise creates two active commitments

**Reproduced:** two correctly interpreted messages move a SAR 1,000 commitment from October 5 to October 7. Both promises remain active, each with a balance-check task.

**Cause:** `mutabi/tools.py:84` identifies promises by inbound message ID; it has no replacement relationship or commitment-change operation. `mutabi/workflow.py:57` does not supply earlier turns to the interpreter. Stable IDs handle retries of one message, but not changes expressed in a new message.

**Change:** introduce a staff-reviewed operation to replace or amend an existing promise. Preserve the old version, source message, actor, and reason, and cancel its obsolete check. Explicitly distinguish replacement from an additional installment. A second message must not silently erase or create a commitment based only on a matching amount.

**Acceptance:** a rescheduled commitment leaves one active obligation and the appropriate future check, with visible old/new values. Two genuine installments remain two obligations. Duplicate delivery/retry protection remains intact.

### 3. Clarification has no way to use the earlier answer

**Reproduced:** an initial message says SAR 1,000 tomorrow; the next says “Yes, October 4, 2026.” The second interpreter receives only that new text and the reference date. With a controlled interpretation correctly containing a date but no amount, the workflow asks for the amount again.

**Change:** first add an explicit pending-clarification record with invoice, source messages, candidate amount/date, missing fields, and status. Allow staff to confirm those fields. Then supply bounded relevant conversation context to interpretation, with source IDs and evidence for each field. Keep customer content untrusted and invoice selection under staff control.

**Acceptance:** a confirmation can complete the pending promise without repeating already established details; ambiguity remains reviewable; unrelated messages cannot satisfy a clarification accidentally.

### 4. Exception handling records work without completing it

**Inspected:** `mutabi/web.py:49` exposes processing, balance verification, drafting, approval, sending, and follow-ups. It exposes no dispute-resolution, task-completion, invoice-assignment, interpretation-correction, or draft-edit/reject operation. Unassigned replies have a clarification banner but no assignment workflow. Tasks show type/date/status but no owner or resolution.

**Change:** provide a small “Needs review” queue and four concrete actions: assign the invoice, correct/confirm the extracted promise, record a finance decision, and resolve the verification/dispute task. Record staff identity, source/evidence, decision, and reason. A manual financial adjustment must still be authoritative accounting evidence, not a convenient “mark paid” button. Editing an approved draft must revoke its approval.

**Acceptance:** a reviewer can take one ambiguous reply and one disputed invoice from pending to a documented outcome without changing SQLite directly. A resolved task leaves the review queue and contact eligibility is recalculated.

### 5. The workflow drafts responses that its own policy blocks

**Reproduced:** a payment claim creates a draft requesting a transfer reference; even after approval, sending is blocked by `PAYMENT_VERIFICATION_PENDING`. A dispute acknowledgment is blocked by `DISPUTE_REVIEW_REQUIRED`.

**Cause:** `mutabi/tools.py:228` applies the same restrictions to all outbound drafts. There is no draft purpose field. This implements the conservative current demo policy; whether acknowledgments and evidence requests should be allowed is a business-policy question.

**Change:** validate the policy with finance staff. If approved, distinguish collection reminders from verification requests and dispute acknowledgments. Give each type explicit permitted states, approval requirements, and contact limits. Do not remove the dispute/payment-verification guard globally. If policy forbids all contact, do not offer an actionable send button for a draft that cannot be sent.

**Acceptance:** the UI explains the block and offers a valid next step; any allowed administrative response uses the purpose-specific policy; collection reminders remain paused.

### 6. Arabic readiness needs more than translated controls

**Reproduced:** a correct model-shaped interpretation quoting `٥ أكتوبر ٢٠٢٦` is forced to date confirmation by `mutabi/gemini.py:70`, because deterministic date parsing only supports ISO and selected English month formats. This is conservative behavior, not invented payment data, but creates extra confirmation even for an explicit Arabic date.

**Change:** add reviewed Arabic customer templates, language selection at the customer/draft level, and evidence-preserving support for agreed unambiguous date formats. Test Arabic numerals, Arabic month names, mixed Arabic/English, spelling variants, relative dates, vague commitments, rescheduling, and conditional offers. Confirm how the target distributor handles Gregorian/Hijri dates; do not assume conversion rules.

**Acceptance:** the complete demonstrated conversation is usable in the participant's language, unclear dates still require confirmation, and English/Arabic results are reported separately.

## The discovery version to build

Keep the current case detail as the foundation. Change the primary screen into a daily work queue:

1. **Needs your review:** pending extraction, missing invoice, dispute, verification, stale accounting.
2. **Follow up today:** commitments whose checks are due, with owner and why the action is needed.
3. **Awaiting approval:** draft purpose, customer language, current balance/source age, approve/edit/reject.
4. **Promises:** promised amount/date, fulfilled amount, remaining commitment, next check, and version history.

Within a case, put “What needs to happen next?” near the top. Show an interpretation card with source message, amount, date, intent, and “Confirm or correct.” Explain why contact is paused and how staff can resolve it. Avoid uncalibrated numeric confidence scores; evidence and explicit uncertainty are more useful at this stage.

Move provider/model selection to operator settings while retaining required provider consent and usage disclosure where applicable. Move clock, accounting events, and reset into facilitator controls. Preserve a visible synthetic-data/simulated-delivery notice. Make summary tiles open the corresponding filtered queue. Add “due today,” “needs review,” and “awaiting approval” filters before advanced charts. This directly tests whether staff can prioritize work rather than search through invoice IDs.

Offer three independent demo stories: record a commitment; request missing details; check an overdue commitment. Add one finance-review story after the resolution flow exists. A story selection should restore only that participant's synthetic workspace and set its coherent time/accounting state. Curated example replay should work without credentials and be labeled “recorded example”; arbitrary typed replies must not silently receive canned interpretations. Separate replay behavior from live-AI measurements.

Update `docs/DEMO_WALKTHROUGH.md`: it still assumes Gemini-only setup and says no additional packages are required, while the current default is ChatGPT and the README installs the OAuth dependency. Create a short participant guide distinct from the facilitator/technical walkthrough.

## How to share it

| Format | What it can validate | Minimum preparation | Recommendation |
| --- | --- | --- | --- |
| Guided local/remote session | Problem relevance, trust, task comprehension, workflow fit | Reliable examples, honest boundaries, discussion guide, evidence log | Start here |
| Short recording plus invitation | Concept understanding and recruitment interest | One realistic story, simulated-data disclosure, invitation to a session | Useful recruitment aid; views are not product validation |
| Private self-service link | Independent task completion and trial friction | Hosted service, access control, per-session state, reliable entry, telemetry, feedback | Build after first discovery iteration or earlier if independent access is essential |
| Shadow pilot | Fit with actual data/process and staff time | Authorized sample/import, identities, resolution flow, payment allocation, operational logs | Start with manual import and no automated customer contact |
| Live collections pilot | Operational performance | Real accounting/channel integration, scheduler, staff permissions, supported deployment, delivery handling, monitoring | Later stage with a specific design partner |

### Hosted sandbox boundary

`make_server` binds to `127.0.0.1`; Host and Origin checks permit localhost only. `/api/session` returns one server-wide token. Every viewer of the same instance would see the same database and reset/clock/provider settings. The token prevents unwanted cross-site actions in the local design; it is not individual visitor authentication. There is no tenant/session ownership filter in `/api/state`. A public tunnel or changed bind address does not create an isolated trial.

For a first private sandbox, use a normal deployed web service with HTTPS, invite/session access, server-side ownership checks, an isolated synthetic database per participant session (or equivalently enforced workspace partition), expiration, and scoped reset. Keep provider configuration with the operator. Rate-limit model actions and bound usage. Do not expose OAuth/account switching or allow participants to upload real customer data in the synthetic trial.

The existing global `DemoApp.lock` spans model calls and snapshots; Gemini permits 45-second network timeouts with retries and ChatGPT permits a 60-second request timeout. Multi-visitor use could serialize behind one slow model request. Move inference into scoped jobs, provide progress/status, and limit per-session actions. This is a code-based concurrency risk, not a measured load-test result.

For a remotely hosted service, do not assume the locally verified ChatGPT-plan OAuth integration transfers unchanged. Current OpenAI documentation distinguishes open-source/local apps from paid or remotely hosted apps and directs the latter to its interest form. The commercial client-ID page currently describes selected partners. Choose either an operator-managed API route with a usage budget or an appropriately registered hosted integration. No new access or deployment was attempted. [OpenAI plan-usage overview](https://developers.openai.com/siwc/token-sharing-open-source), [commercial client access](https://developers.openai.com/siwc/request-client-id).

SQLite can remain sufficient for an early isolated sandbox; a database rewrite is not the immediate discovery priority. Account for hosted persistence/backups and multi-worker coordination when selecting deployment architecture. Keep synthetic sandbox state separate from any future pilot data.

## Product hypothesis and alternatives

Proposed hypothesis: distributor staff lose payment commitments across customer conversations and accounting checks; turning those conversations into a reviewed, owned next action reduces follow-up effort and missed commitments.

Test who makes and tracks the promise. It may be a sales representative, collector, accountant, or owner. The schema currently centers invoices; staff may organize work around customers with several invoices and one shared conversation. Validate that before expanding the data model. Find out whether replies arrive through WhatsApp, calls, email, or sales visits, and whether anyone can reliably link them to an invoice. These are open questions, not established market facts.

Basic promise tracking and dispute reporting are not sufficient differentiation on their own. Chaser's current help documentation describes promise-to-pay/dispute reporting and operational priority views. Stripe documents automated invoice recovery capabilities. These sources establish feature overlap, not suitability for Saudi FMCG distributors or a complete competitive analysis. [Chaser reports](https://help.chaserhq.com/generating-xlsx-reports-in-chaser), [Chaser operational dashboard](https://help.chaserhq.com/debtor-relationship-management-dashboard), [Stripe invoice recovery](https://docs.stripe.com/invoicing/automatic-collection).

The potential advantage to investigate is handling the target distributor's actual customer language and conversation channels, with finance-safe follow-up and a useful handoff between sales and finance. Compare this with their current WhatsApp-plus-spreadsheet/accounting workflow and their ERP's existing reminder functions. Do not commit to WhatsApp or a specific ERP integration until the target group identifies the relevant channel and data export.

## Discovery and validation cycle

### Round 1: establish the problem before demonstrating the solution

Practical starting target: 6–8 conversations across at least three relevant distributors, including daily collectors/finance operators and owners or finance managers. This is a proposed qualitative recruitment target, not statistical evidence. Record roles separately so buyer enthusiasm does not substitute for operator usefulness.

Use a 40–45 minute session: approximately 15 minutes about recent work, 15–20 minutes on independent prototype tasks, and 10 minutes on fit and next steps. Ask about actual recent episodes before showing the POC. GOV.UK's interview guidance supports focusing on real stories, and its usability guidance supports realistic goal-based tasks without hints. [In-depth interviews](https://www.gov.uk/service-manual/user-research/using-in-depth-interviews), [moderated usability testing](https://www.gov.uk/service-manual/user-research/using-moderated-usability-testing).

Interview prompts:

- “Walk me through the last customer payment promise you followed up.”
- “Where was it recorded, who owned the next action, and how did they know when to act?”
- “Describe the last missed promise. How was it discovered?”
- “What happened the last time a customer said they had paid but accounting had not confirmed it?”
- “How do you handle a changed promise, partial payment, return, or credit note?”
- “Show or describe how you decide whom to contact today.” Use descriptions or redacted artifacts before introducing any real data into the POC.
- “Which existing system or reminder feature could already do this? What prevents you using it?”

Then give tasks as business goals, not button instructions:

| Task | What to observe |
| --- | --- |
| Record this customer's commitment and determine the next action | Can they verify amount/date/invoice and explain the saved check? |
| Handle a reply missing a payment date | Can they identify uncertainty, request/confirm details, and finish? |
| Decide what to do when a promised date has passed | Do they verify accounting before contacting the customer? |
| Handle “I already paid” with no confirmed ledger receipt | Do they understand that a claim is not settlement and find the next step? |

Complete available tasks first and explicitly log unsupported resolution steps as prototype gaps. After fixes, repeat the same tasks on a fresh build. Keep task assistance observable: record any facilitator hint rather than counting a coached walkthrough as independent success. Rotate equivalent examples/order in later rounds to reduce practice effects.

Close with concrete fit questions: “What would replace a part of your current routine?”, “What information is missing before you would trust this?”, “Who would approve a trial?”, and “Would you introduce the colleague who handles this and agree a date for a sample-workflow session?” Praise and hypothetical willingness to pay are weaker signals than a named workflow, colleague introduction, sample export agreement, and scheduled next session.

### Round 2: validate usability and trust

Re-test the revised flow with 4–6 target operators, including some new participants. Measure task completion, intervention count, time to a correct reviewed next action, extraction corrections, and draft editing/rejection. Include manual accounting review and approval time in comparisons. Compare equivalent manual and assisted tasks; distinguish onboarding/learning time from repeat-use time.

Add a small research log with participant pseudonym, role/company segment, prototype version, scenario, replay/live mode, outcome, assistance, error, quote, observed workaround, decision, and next commitment. Store business audit events separately from research feedback. For a hosted trial, capture entry → example opened → reviewed action completed → feedback → pilot interest, with failure stage and duration. Avoid collecting raw customer reply text in analytics by default.

### Round 3: shadow pilot with a design partner

If early evidence supports the hypothesis, select one partner and one named operator for a limited 1–2 week shadow trial. Use an agreed, minimized/redacted sample and start with a CSV/manual import mapping customer, invoice, balance, due date, balance timestamp, and source reference. Preview mapping/errors and reject invalid associations. A manual export establishes data feasibility before spending on an ERP connector.

Keep outbound contact simulated or staff-executed through their existing channel until the workflow is demonstrated and the partner authorizes the operational integration. Measure follow-ups completed on time, verification delays, operator effort, correction/rejection frequency, and repeated voluntary use. Collection improvement and DSO require a longer, appropriately designed operational comparison; a short shadow pilot cannot establish causal cash impact.

### Proposed decision rules

Agree thresholds before recruitment; these are proposed local decision gates, not industry benchmarks:

- Continue product discovery if at least three independent target companies describe recent recurring commitment-tracking pain and can name the workaround and owner. If the dominant issue is something else, revise the problem before adding features.
- Continue usability work if at least four of five target operators can complete the core reviewed task without facilitator intervention. With such a small sample, also inspect every failure; this is not a population estimate.
- Start a shadow pilot when one partner commits an operator, a sample workflow/export, a recurring check-in, and an agreed success measure; seek a second independent partner to test repeatability.
- Hold broader access if installment fulfillment, changed promises, resolution flows, or session isolation can mislead users. Record accurate demo behavior before using it as evidence of product value.

## Prioritized implementation backlog

| Order | Work | Stage | Relative size | Evidence of completion |
| --- | --- | --- | --- | --- |
| 1 | Correct installment fulfillment and define payment allocation | Before broader hands-on sessions | Medium | Focused payment/credit/overlap regressions pass |
| 2 | Add review/confirmation, invoice assignment, and resolution actions | Discovery version | Medium–large | Ambiguous reply and finance exception reach an audited outcome |
| 3 | Handle amended promises and pending clarification state | Discovery version | Medium–large | Changed date replaces the right check; confirmation reuses established fields safely |
| 4 | Simplify first screen; add independent example replay; update walkthrough | Discovery version | Small–medium | Visitor reaches a useful reviewed result without configuring a provider |
| 5 | Arabic customer templates and bilingual challenge evaluation | Before Arabic workflow claims | Medium | Native-language review plus separate reported interpretation results |
| 6 | Draft purpose policy; edit/reject and visible contact blockers | Discovery version | Medium | No impossible next action; edits invalidate prior approval |
| 7 | Discussion guide, evidence log, feedback and session metrics | First discovery round | Small | Findings distinguish observed behavior, opinion, and commitment |
| 8 | Private hosting, session isolation, usage limits and async processing | Before sending an interactive link | Medium–large | Two visitors cannot see/reset each other's state; slow requests are scoped |
| 9 | CSV onboarding, real staff identity and scoped permissions | Before shadow pilot | Medium | Partner can map approved sample data and identify task ownership |
| 10 | One accounting/channel integration and durable scheduled checks | After partner confirms workflow | Large | Retry/restart/delivery failures recover without duplicate effects |

Relative sizes express complexity, not promised timelines. The smallest useful next release combines the correctness fix, one complete review/clarification path, simpler demo entry, and research capture. If the immediate goal is a self-service link, session isolation and hosting move into that release.

Defer broad ERP support, automatic customer sending, risk prediction, legal escalation, and elaborate cash dashboards. Their value depends on the workflow and customer evidence the next cycle should establish.

## Expanded evaluation plan

Preserve the 65 current checks. Convert reproduced correctness gaps into focused regressions when fixes are implemented. Add a held-out challenge set of roughly 40–60 synthetic English/Arabic/mixed messages reviewed by a target-language business reviewer. Cover missing fields, relative/ambiguous dates, Arabic explicit dates, revised commitments, installments, multiple invoices, payment claims, disputes/credits, conditional offers, and malicious instructions. Do not put expected results into interpreter inputs.

Report intent/amount/date/evidence correctness, inappropriate commitment creation, unnecessary clarification, staff correction rate, provider failures, and latency separately. Run critical cases repeatedly without the previous evaluation's within-run text cache when assessing variability. Record model/provider/version and distinguish model errors from workflow errors. Any “paid” state from customer text alone, unsupported discount, reminder despite a blocked state, or incorrect promise allocation is a critical failure in the evaluated set. A clean set is still not a guarantee for unseen messages.

The report and probes make the next improvements reviewable. They do not assert that demand, Arabic interpretation reliability, independent usability, real-channel delivery, or measured time/cash impact has already been established.
