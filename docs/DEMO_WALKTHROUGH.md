# Mutabi reviewer walkthrough

## Setup

1. Use Python 3.10+ and copy `.env.example` to `.env`. Enter a Gemini API key locally. Never share the key or put it in Git.
2. From the repository root, run `python -m mutabi.web`.
3. Open http://127.0.0.1:8765/. No additional packages or frontend build are required.

The browser shows synthetic customer accounts, a demo clock, and simulated accounting controls. The server sends only the synthetic reply and reference date to Gemini. All deliveries remain in the local simulated inbox. Reviewer approval uses the fixed demo employee identity.

## Main story: promise → approval → missed commitment

1. If previous demo activity exists, choose **Reset demo workspace**, then confirm **Reset demo**. This restores disposable synthetic state and sets the clock to October 3, 2026.
2. Open **Demo Grocery A / INV-001**. The balance is SAR 3,000 and the reply promises full payment on October 5.
3. Choose **Process with Gemini**. Wait for the status banner. Observe the active promise, the October 6 balance-check task, and an acknowledgment awaiting approval.
4. Choose **Approve draft**. Approval does not send the message.
5. Choose **Send to simulated inbox**. Observe the delivery receipt and saved history. No customer is contacted.
6. Set the demo date to **October 6, 2026** using **Set date**.
7. Under **Accounting simulation**, select **Promise date passed — no payment**.
8. Choose **Run due follow-ups**. The promise becomes missed, the balance-check task closes, and a new overdue follow-up plus draft appears.
9. Expand **Activity history** to inspect the recorded interpretation, tool actions, approval, delivery, and follow-up.

## Other review examples

Start these from a reset baseline so future dates do not make unrelated accounting snapshots stale.

| Example | Steps | Expected result |
|---|---|---|
| Vague promise | Grocery B → Process with Gemini | Ask for date and amount; no confirmed promise |
| Unverified payment | Grocery C → choose payment-claim accounting simulation → process reply | Verification task; invoice remains unpaid |
| Full payment | Grocery D → choose full-payment simulation → run due follow-ups | Zero balance, fulfilled promise, closed tasks, invalidated draft |
| Partial payment | Grocery E → choose partial-payment simulation → verify balance → run due follow-ups | SAR 3,000 remaining; partially fulfilled promise |
| Dispute | Grocery G → process reply | Finance-review task; claimed dispute recorded without reducing balance |
| Relative date | Grocery H → process reply | Candidate date requires confirmation |
| Missing reference | Unassigned replies → process reply | Invoice clarification; no assignment based on amount |
| Conditional discount | Grocery J → process reply | Human review; no discount accepted |
| Unavailable accounting | Grocery K → choose source-unavailable simulation → prepare reminder | Review needed; no collection draft created |
| Unsafe instructions | Grocery L → process reply | Human review; no balance change or history deletion |

**Add a synthetic customer reply** saves new text for the selected invoice. Choose its **Process with Gemini** button separately. Each saved reply is a new message; **View saved result** replays an existing completion without generating duplicate effects.

## Operational notes

- Gemini requests can encounter service or quota errors. The interface displays a safe error and the reply remains pending if interpretation fails. Temporary server errors receive bounded retries. Wait before retrying a rate-limit error.
- Model configuration remains server-side. Restart the server after editing `.env`.
- The demo clock moves forward only; reset restores October 3. Set-date uses 10:05 Riyadh time so the October 3 simulated payment event can be tested.
- Accounting events are applied only when the selected simulation is eligible at the demo time. Choosing an event does not change the balance until a tool reads it.
- Approvals and contact checks remain enforced by backend tools. Stale data, settled balances, disputes, pending payment verification, or contact frequency can block a send.
- Clock changes and other actions persist. Tests use temporary databases; the browser uses the database path chosen when starting the server.
- This is a local prototype with simulated accounting and delivery. English response templates, live Gemini interpretation, and configurable demo policies are used. Production authentication, ERP integration, and real messaging are outside the current demo.
