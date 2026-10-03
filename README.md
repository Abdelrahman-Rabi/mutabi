# Mutabi

FMCG payment-promise follow-up prototype with a bilingual local browser interface, SQLite storage, synthetic demo loader, persistent business tools, and guarded workflows. Reply interpretation supports ChatGPT plan authorization or Gemini API. All 15 approved scenarios passed separate live evaluations using each provider, with simulated accounting and delivery.

## Start the demo interface

Create a Python environment and install the OAuth identity-validation dependency:

```sh
python -m venv .venv
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m mutabi.web
```

On macOS/Linux, activate `.venv`, install `requirements.txt`, and run:

```sh
python -m mutabi.web
```

Open http://127.0.0.1:8765/ in your browser. Select **ChatGPT plan**, click **Continue with ChatGPT**, and complete OpenAI sign-in and permission. The server loads the synthetic baseline if needed, keeps credentials server-side, and preserves state across restarts. No frontend build is required. Stop with Ctrl+C. See [ChatGPT setup](docs/CHATGPT_SETUP.md) for connection and testing steps. Gemini remains a selectable alternative using your local `.env`.

For a separate demo workspace:

```sh
python -m mutabi.web --db runtime/ui-demo.db --port 8765
```

The interface runs locally, not as a public hosted service. Demo approval uses the fixed identity `DEMO-EMPLOYEE`; production authentication is not implemented. It accepts synthetic replies only for reviewer testing. See `docs/DEMO_WALKTHROUGH.md` for the main story and other scenarios.

## Requirements

Python 3.10 or later. The loader uses only the Python standard library; no installation or API credentials are needed.

## Load and inspect demo data

Run from the repository root:

```sh
python -m mutabi.demo load
python -m mutabi.demo status
python -m unittest discover -s tests -v
```

The database is created at `runtime/mutabi.db`, which is excluded from Git. Repeating `load` preserves runtime changes and does not duplicate rows. If source fixtures change, an explicit reset is required.

```sh
python -m mutabi.demo reset
```

Reset replaces generated demo state with the baseline, including tasks, approvals, and audit records. Use only for disposable synthetic runs. The loader refuses to replace databases with a different owner marker or existing unowned application data. Override the path with `--db path/to/demo.db` for independent scenarios.

Money is stored as integer halalas, not floating-point values. Foreign-key constraints protect data relationships. Seed messages are marked processed; scenario messages remain pending. Accounting events are stored separately and do not automatically settle invoices. Loading does not execute the agent test cases.

See `data/demo/README.md` for scenario mapping and `TEST_CASES.md` for approved behavior. Expected results in `tests/fixtures/` must never be supplied to the agent.

## Business tools

`mutabi.tools.Tools` exposes invoice/message context, policy, accounting verification, promise recording with an atomic follow-up task, disputes, human review, drafts, and simulated sending. Supply a database path and an optional timezone-aware demo timestamp. A host-selected `scenario_id` routes simulated accounting reads; this routing must not be chosen by the model.

Promise, task, dispute, draft, and delivery effects use stable identifiers for retries. Invoice association is validated. Sending requires employee approval, rechecks balances, and blocks stale balances, changed amounts, pending disputes, pending payment verification, and excessive contact frequency. `approve_draft` is an employee/UI action and must not be registered as a model-callable tool. The prototype does not yet implement authenticated employee sessions.

The tool layer accepts structured arguments; it does not itself infer whether a customer's text contains an explicit promise or distinguish a malicious message. Interpretation is handled by the selected provider, followed by workflow validation and policy checks. Tool tests and controlled workflow tests are distinct from live-model evaluation.

## Gemini setup and workflow

Create a Gemini API key in Google AI Studio: https://aistudio.google.com/apikey
Copy `.env.example` to `.env` and enter your key locally. Do not put it in chat or commit it. You can alternatively set `GEMINI_API_KEY` in your environment. The adapter sends the reply and reference date to Google; it does not send invoice data or test expectations. Use synthetic messages for the demo.

`GEMINI_MODEL` defaults to `gemini-3.8-flash` and can be changed to a compatible model available to your project. API access and quotas depend on the Google project. The adapter uses the documented REST `generateContent` endpoint with structured JSON output; no third-party packages are required.

```sh
python -m mutabi.agent process --message MSG-001
python -m mutabi.agent context --invoice INV-001
python -m mutabi.agent followups --invoice INV-001 --now 2026-10-06T10:00:00+03:00 --scenario TC-15
python -m mutabi.agent prepare --invoice INV-011 --scenario TC-11
```

`process` uses live Gemini for a new reply. Its validated interpretation is persisted; completed replies replay the saved result without new mutations. The workflow creates drafts for employee approval, never automatically sends them. `followups`, `prepare`, and `context` run without a model key. Follow-ups execute on demand; an always-on background scheduler is not implemented.

The workflow supports clear/vague promises, payment claims, disputes, ambiguous dates, missing invoice references, conditional offers, and suspicious instructions. It records full settlement, partial/missed promises, review tasks, and audit history. Draft wording currently uses English templates; Gemini handles structured interpretation rather than message generation. Arabic response templates remain future work.

### Validation evidence

On October 3, 2026, all 65 offline automated checks passed: 5 loader checks, 11 tool checks, 8 mocked Gemini adapter checks, 20 ChatGPT OAuth/stream checks, 16 workflow checks, and 5 web backend/HTTP checks. A browser walkthrough also exercised live reply processing, approval, simulated delivery, and a missed-promise follow-up.

The workflow tests use controlled interpreter responses. They prove database/workflow behavior given those interpretations, not live Gemini classification accuracy. The adapter tests simulate API responses and do not call Google. See `docs/validation.md`. No real ERP or customer channel is connected.

### Opt-in live evaluation

```sh
python -m evaluation.live --min-interval 15
```

This command calls Gemini using the local key and synthetic replies, uses isolated temporary databases, and saves `docs/live_evaluation.json`. It can incur API usage charges. The interval paces unique replies; duplicate fixture text reuses the interpretation within the run. `--model MODEL_NAME` explicitly overrides the model for evaluation without modifying `.env`. Temporary server errors receive bounded retries; rate/quota errors are reported without displaying API response bodies or credentials.

The current report and previous report distinguish actual live execution from offline tests, including service errors. A successful small sample does not establish production reliability or measured business impact.

### Interface language

Use the العربية / English button to switch interfaces. Arabic includes right-to-left layout, Gregorian dates, and SAR amounts. The browser remembers your preference. Switching preserves the selected case, accounting scenario, and unsaved reply text. Customer replies and stored drafts retain their original text; outbound draft templates currently remain English.
