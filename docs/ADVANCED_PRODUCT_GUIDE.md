# Mutabi advanced discovery workspace

This release is a functional discovery product built on explicit assumptions. It supports guided sessions and independent exploration on a local server. All ledger events and message deliveries are simulated; the product does not contact customers.

## Run

From the project directory in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m mutabi.web --db runtime/advanced-demo.db --port 8765
```

For later launches, run `.\Start-Mutabi.ps1`. Optional `-Port` and `-Database` arguments select a different local port or disposable workspace. Dependencies must already be installed.

Open [Mutabi](http://127.0.0.1:8765/). No API key or AI subscription is needed for the recorded demo mode. Stop the server with Ctrl+C.

Each browser profile gets a persistent isolated workspace identified by an HttpOnly cookie. A private/incognito browser window can act as another participant. Separate tabs in the same profile share the same workspace. Session databases live beneath `runtime/advanced-demo-sessions/`; the original POC database is not replaced. Reopening the browser with its cookie restores its workspace. Deleting the cookie starts a fresh workspace; exported evidence and server-side session files remain local.

## What the product includes

- **Overview:** derived financial exposure, open commitments, reviews, approvals, receivables aging, near-term commitments, and suggested next actions.
- **Collections/customer workspace:** searchable invoices and synthetic customer profiles; conversation, review, invoices, commitments, accounting state, notes, and activity trail.
- **Commitments:** amounts, dates, allocations, status, amendments and audit history. A fulfilled installment can coexist with an unpaid invoice.
- **Tasks:** ownership, pending/completed state, due dates, finance exceptions and follow-up actions. Ledger checks are completed by running the workflow rather than a generic close button.
- **Approvals:** draft purpose and language, edit/reject/approve, and simulated delivery with backend eligibility checks. Editing invalidates prior approval.
- **Analytics:** actual synthetic workspace balances, status distributions and operational progress. These are demo-data metrics, not measured customer results or predictions.
- **Feedback:** ratings, category, participant role, current view and written observations persist locally. CSV and JSON export let the facilitator retain the evidence.
- **Settings:** demo team identity, workspace preferences, timing policy, live provider connections and honest integration status. Team identities demonstrate accountability and are not production authentication.
- **Demo studio:** independent stories, synthetic payments, accounting scenarios, date advancement, and workspace reset.
- **CSV onboarding:** validate and preview a synthetic invoice sample, then atomically import it. Invalid rows or conflicting identifiers prevent the entire import.

## Six discovery stories

Use the Demo Studio to select a story. Story selection resets the participant's disposable business state, preserves research feedback/events, and sets up a coherent example. Existing case notes and imported invoices are disposable.

1. **A clear commitment:** inspect SAR 3,000 due on October 5, 2026; review the acknowledgment; edit, approve and deliver to the simulated inbox; advance the date and check accounting.
2. **From vague reply to commitment:** inspect the missing amount/date; supply employee-confirmed values; observe the new promise and scheduled task. The correction remains in the audit trail.
3. **A payment claim needs evidence:** inspect an unverified claim; review the transfer-reference request; simulate a payment and complete finance verification. Customer text itself never settles the balance.
4. **A missing credit note:** review a dispute and record a reasoned decision. Accepting a dispute retains the hold until verified accounting adjustment; it does not reduce the ledger by itself.
5. **Fulfill an installment:** the customer promises SAR 1,000 against a SAR 3,000 invoice. Simulate and allocate SAR 1,000. The commitment is fulfilled while SAR 2,000 remains outstanding.
6. **A changed payment date:** amend a commitment with a reason; the previous obligation is superseded and its check retired; the new commitment and version relationship remain visible.

## Demo interpretation and live AI

The default interpreter recognizes exact curated English/Arabic scripts. It does not learn from test expectations or pretend to understand arbitrary text. A new free-form reply is preserved and routed to employee review. Confirming its amount and date is an explicit manual action.

Select a live provider in Settings to use model-based extraction. Gemini uses the ignored local `.env`. ChatGPT requires explicit sign-in/plan permission and a selected available model. Live calls can consume provider allowance or billable API usage. The earlier saved 15-scenario evaluations remain historical evidence, not proof of this release's expanded language/interaction accuracy.

The current hosted-client eligibility rules still apply to ChatGPT. This release runs on loopback and does not publish a public service or transfer the operator's credentials to participants.

## Arabic and English

Switch the interface language at any time. Arabic uses RTL layout, Gregorian dates and SAR formatting. Customer names include synthetic Arabic profiles. Templates follow the customer's preferred language; draft editing supports either language. Customer messages retain their original text. Arabic explicit date evidence supports the agreed month-name and numeric forms; relative dates still require review.

## Safe CSV import

Use this exact header order. Amounts are decimal SAR values; dates use YYYY-MM-DD:

A ready-made [five-invoice synthetic sample](../data/demo/discovery_import_sample.csv) includes one customer with two invoices and one settled invoice.

```csv
invoice_id,customer_id,customer_name,original_amount,outstanding_balance,due_date
SAMPLE-001,SAMPLE-C1,Synthetic Market,4500.50,2000.25,2026-09-20
SAMPLE-002,SAMPLE-C1,Synthetic Market,1500.00,1500.00,2026-10-05
```

Confirm the file contains synthetic data, preview the rows, then import. At most 200 rows/50,000 characters are accepted. Invoice IDs must be new; one customer ID cannot refer to different names. Exact integer minor-unit values are stored. A zero balance creates a settled invoice. Import is restricted to the current participant workspace.

## Export and feedback

JSON exports contain synthetic business/research records and exclude provider authentication and credentials. CSV exports support feedback, invoices, and tasks; cells that could trigger spreadsheet formulas are escaped. Exports contain the current participant's state only.

Workspace reset and story switching retain feedback/research events but remove disposable business changes. This makes it possible to rehearse several scenarios while preserving participants' observations. For multiple participants, export from each participant session; an organization-wide hosted research administration system is not implemented.

The [Arabic discovery session script](DISCOVERY_SESSION_AR.md) includes neutral interview questions, six practical tasks, and an observation template for distinguishing observed behavior from interpretation.

## Assumptions to validate

- Invoice-level tracking is the right unit of work; users may instead operate at customer/account level.
- Staff approval is required for outgoing messages.
- Ledger verification occurs one day after a commitment by default.
- Pending payment claims and disputes pause collection reminders; verification requests and dispute acknowledgments have separate purposes.
- Arabic/English and SAR fit the first target segment.
- The demo team's collectors, finance reviewer, and manager represent the real handoff.

Policy timing can be changed in Settings and affects new workflow decisions. Existing stored task dates are preserved so a configuration change cannot silently rewrite previously reviewed commitments.

## Validation and boundaries

Run the backend and HTTP checks:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

The suite covers existing safeguards plus manual confirmation, amendments, allocations, editing/approval invalidation, product actions, synthetic import atomicity, browser session isolation, and safe export. Browser validation exercises the user-facing flows separately.

This is a comprehensive discovery prototype. It does not implement production employee authentication, a real ERP/WhatsApp connection, a background always-on scheduler, or a publicly deployed service. Checks run when invoked. Simulated payments are explicit facilitator actions, not live bank events. No time saving, collection uplift, DSO improvement or customer demand is claimed as measured.

The initial investigation reports describe the preceding version and are retained as historical planning artifacts. Several of their findings are addressed in this release; use current tests and this guide for the new behavior.
