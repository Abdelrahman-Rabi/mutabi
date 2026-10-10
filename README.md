# Mutabi — payment-promise follow-up for small businesses

Mutabi helps a distributor turn customer replies into recorded payment commitments, owned balance checks, and reviewed follow-up. An employee approves every outgoing message. Accounting evidence determines whether a commitment is paid, partly paid, missed, or needs finance review.

**Reviewers: start with the credential-free demo below.** The source includes a working bilingual web interface, SQLite persistence, workflow/tool code, synthetic fixtures, and automated tests. The default interpretation provider recognizes exact curated examples; arbitrary replies require manual review. Optional live Gemini and ChatGPT providers are separate from the offline demonstration.

## Run in under five minutes

Prerequisites: **Python 3.10+** and a current browser. Installing Python, if it is not already present, is outside this startup target. The default demo needs **no API key, sign-in, pip install, Node.js, Docker, or frontend build**.

Download/extract the submission source ZIP, or clone the public repository:

```sh
git clone https://github.com/Abdelrahman-Rabi/mutabi.git
cd mutabi
```

Open a terminal in the folder containing `run_demo.py` and `README.md`.

**Windows:**

```powershell
py -3 run_demo.py
```

**macOS / Linux:**

```sh
python3 run_demo.py
```

If your Python command is `python`, use `python run_demo.py` instead. Open **http://127.0.0.1:8765/**. The server creates and seeds the demo database automatically. Leave the terminal running; **Ctrl+C** stops it.

The module entry point is equivalent: `python -m mutabi.web`. Windows users can also use the existing `Start-Mutabi.ps1` launcher.

### Verify the agent workflow immediately

In a second terminal, run:

```powershell
py -3 run_demo.py --check
```

On macOS/Linux: `python3 run_demo.py --check`. Add `--json` for machine-readable evidence.

This executes the actual workflow and business tools in disposable databases. It verifies promise capture and scheduling, blocked delivery before approval, approved simulated delivery, safe retries, a missed promise after fresh accounting verification, review of uncurated text, and installment fulfillment with debt still outstanding. It makes **zero live model calls** and does not modify your browser workspace. A failure exits with a nonzero code.

## A three-minute reviewer walkthrough

The baseline deliberately includes already-processed curated conversations so the workspace is useful immediately. Use the command above to see a fresh promise processed end to end.

1. **Collections → Demo Grocery A (INV-001).** Open **Promises**: SAR 3,000 promised for 5 October 2026. Open **Tasks**: Sara owns the balance check due 6 October. The invoice balance is still SAR 3,000.
2. **Conversation.** Find the acknowledgment draft, review it, click **Approve**, then **Send to simulated inbox**. Approval and delivery are separate actions. The delivery receipt is visible; no real customer is contacted.
3. **Demo studio → Workspace clock.** Advance to **6 October 2026**. Under **Accounting scenario**, select **TC-15 · INV-001** and click **Verify scenario**. This supplies the fresh synthetic unpaid snapshot; advancing the date alone does not refresh accounting.
4. **Collections → INV-001 → Run due follow-ups.** The promise becomes **Missed**, the balance remains SAR 3,000, and a new follow-up draft awaits employee approval.
5. **Impact calculator.** The illustrative inputs project **50 hours freed per month**, not measured savings. At 0% cash realization, monthly net cash is **SAR -500**. Change **Saved capacity converted to cash** to **40%**: monthly net cash becomes **SAR 500**. Capacity value and cash benefit overlap; do not add them.

Optional: **Demo studio → Fulfill an installment → Load story**, confirm the reset, and record a synthetic **SAR 1,000** payment for **INV-001**, allocating it to the **SAR 1,000** commitment. That promise becomes **Fulfilled** while the invoice still has **SAR 2,000** outstanding. Loading a story resets disposable business state in that browser workspace.

Use the **العربية / English** button for the bilingual interface. Customer text and draft language follow the customer profile, independently of the interface language.

## What is implemented

- Structured reply interpretation followed by validation and guarded workflow actions.
- Promise creation/revision, owner assignment, dated tasks, drafts, explicit approval, simulated delivery, and persisted audit history.
- Verified payment allocation to individual commitments; invoice balance and installment fulfillment remain distinct.
- Clarification and human review for ambiguous replies; finance holds for payment claims and disputes.
- Checks for stale/changed accounting, unresolved finance review, excessive contact frequency, and retry duplication.
- Session-isolated SQLite workspaces and Arabic/English views, plus an assumption-based impact calculator.

The workflow runs checks **on demand**. This prototype has no always-on scheduler, live ERP/bank integration, real WhatsApp delivery, or production employee authentication. Demo team identities record actions but are not authenticated accounts. Synthetic records use SAR; the calculator can label scenarios in EGP and other currencies without exchange-rate conversion. No real SME savings or revenue uplift have been measured.

## Optional live AI interpretation

The offline path above is sufficient to run the workflow. To evaluate live extraction, choose a provider in **Settings**, then submit a **new synthetic reply**. Processing a completed reply replays the saved decision and does not call the model again.

**Gemini:** copy `.env.example` to `.env`, enter your own `GEMINI_API_KEY`, and restart the server. Set `GEMINI_MODEL` to a compatible model available to your project; the adapter default is defined in [mutabi/gemini.py](mutabi/gemini.py). The adapter uses the standard library and sends the reply and reference date to the provider. Provider access, quotas, and usage charges apply.

**ChatGPT:** install the optional OAuth dependency in an isolated environment, then follow [ChatGPT setup](docs/CHATGPT_SETUP.md).

```sh
python -m venv .venv
```

Windows:

```powershell
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe run_demo.py
```

macOS/Linux:

```sh
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run_demo.py
```

Keep credentials local. The default demo does not call a provider even if a key is configured. Live evaluation is opt-in; see [evaluation/live.py](evaluation/live.py) and the setup guide before running it.

## Validation

The offline reviewer check is the fastest way to verify the main journey. For the complete suite, install the optional requirements above and run:

```sh
python -m unittest discover -s tests -v
```

Use your virtual environment's Python for this command. Node.js enables the two frontend rendering/calculator checks; those two checks are skipped when Node is absent. No live provider calls are required by the suite. Workflow tests use controlled interpretations, and provider adapter tests simulate responses; they do not establish general live-model accuracy or business impact.

See [current validation evidence](docs/ADVANCED_VALIDATION.md) and [clean-package startup evidence](docs/REVIEWER_READINESS.md).

## Troubleshooting and saved state

| Symptom | Action |
|---|---|
| `py` or `python` is not found | Install Python 3.10+ and reopen the terminal. On Windows, try `py -3` to bypass a Store alias. |
| Port 8765 is occupied | Run `python run_demo.py --port 8766`; open http://127.0.0.1:8766/. |
| Follow-up needs data review | Verify a fresh accounting snapshot for the same invoice and date, then retry. For the walkthrough use TC-15 after advancing to 6 October. |
| New text is not interpreted in demo mode | Confirm amount/date through employee review, or explicitly configure a live provider. Curated examples are not a general language model. |
| You want a fresh workspace | Use a private browser window or a new browser profile. **Demo studio → Reset workspace** replaces that session's synthetic business state. |
| You want a separate database | Run `python run_demo.py --db runtime/reviewer-demo.db --port 8766`. |

Generated state is stored under ignored `runtime/`; browser session databases persist across restarts. Source fixtures remain unchanged. The server binds to `127.0.0.1`, so use it locally rather than exposing it as a production service.

## Source map and further reading

| Path | Purpose |
|---|---|
| [mutabi/workflow.py](mutabi/workflow.py) | Validated orchestration and saved decisions for replay. |
| [mutabi/tools.py](mutabi/tools.py) | Accounting verification, commitments, approvals, guarded delivery, and allocations. |
| [mutabi/product.py](mutabi/product.py) | Curated demo provider, discovery stories, profiles, assignments, and synthetic payment sandbox. |
| [mutabi/web.py](mutabi/web.py) / [mutabi/static](mutabi/static) | Local HTTP server, session isolation, and bilingual interface. |
| [mutabi/reviewer_check.py](mutabi/reviewer_check.py) | Disposable end-to-end reviewer verification. |
| [data/demo](data/demo) / [tests](tests) | Synthetic business inputs and offline regression suite. |
| [mutabi/gemini.py](mutabi/gemini.py) / [mutabi/chatgpt_plan.py](mutabi/chatgpt_plan.py) | Optional live interpretation adapters. |

[Product walkthrough](docs/ADVANCED_PRODUCT_GUIDE.md) · [Arabic guide](docs/ADVANCED_PRODUCT_GUIDE_AR.md) · [Calculator definitions](docs/IMPACT_CALCULATOR.md) · [Scenario behavior](TEST_CASES.md) · [SMB impact evidence](docs/SMB_IMPACT_EVIDENCE.md)

Test expectations in `tests/fixtures/` are evaluation artifacts, never agent inputs. Accounting scenario selection belongs to the host/reviewer, not the model.
