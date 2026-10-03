# Synthetic demo data

This dataset supports the 15 approved cases in `../../TEST_CASES.md`. It contains no real company or customer data, contact details, or credentials. All contact references identify simulated inboxes.

## Files and loading order

1. `policy.json`: provisional settings approved for the demo, pending distributor validation. The 24-hour freshness and contact intervals are explicit synthetic configuration values, not researched business standards.
2. `customers.csv`: customer identities and simulated contact references.
3. `invoices.csv`: initial accounting snapshots. Amounts are decimal strings in SAR; parse using decimal arithmetic, not binary floats.
4. `messages.csv`: historical seed messages and inbound messages for individual scenarios.
5. `promises.csv`: existing commitments sourced from historical seed messages.
6. `tasks.csv`: initial pending tasks, including the existing overdue task for TC-02.
7. `drafts.csv`: initial drafts needed to test invalidation and prior approval.
8. `accounting_updates.csv`: scenario-specific simulated accounting-tool results, applied only when the relevant scenario calls the tool at or after `available_at`.

Dates use ISO 8601. Empty CSV fields mean missing/not applicable, never zero. `is_seed_history` uses `true`/`false`. The baseline starts at October 3, 2026, 10:00 in Asia/Riyadh.

## Scenario isolation

Start every case with a fresh copy of the baseline in a temporary or reset runtime database. Load only messages with `is_seed_history=true` as previously processed history. Other messages are pending scenario inputs: process the selected message only, not every row in the file.

TC-01 and TC-13 intentionally share INV-001 but use different message IDs. Run them independently so one case does not contaminate the other. TC-15 intentionally builds on TC-01 within its own run and preserves state across restarts. TC-09 intentionally has no invoice association on the message.

The `scenario_id` in accounting updates is a simulator routing key, not information for the agent to reason from. The simulator supplies the tool result; the agent sees only the returned accounting facts or error. Do not preload future payments into the current balance.

Successful accounting results carry an authoritative *remaining balance*, not a subtraction instruction. Repeated reads must not deduct `payment_amount` again. Error results have no valid current balance. Record the source reference and event timestamp when verifying payments.

## Mapping

| Case | Input or trigger | Supporting data |
|---|---|---|
| TC-01 | MSG-001 | INV-001 |
| TC-02 | MSG-002 | INV-002, TASK-002 |
| TC-03 | MSG-003 | INV-003, ACC-003 |
| TC-04 | Scheduled check | INV-004, PROM-004, TASK-004, DRAFT-004, ACC-004 |
| TC-05 | Scheduled check | INV-005, PROM-005, TASK-005, ACC-005 |
| TC-06 | Scheduled check | INV-006, PROM-006, TASK-006, ACC-006 |
| TC-07 | MSG-007 | INV-007 |
| TC-08 | MSG-008 | INV-008 |
| TC-09 | MSG-009 | INV-009A and INV-009B |
| TC-10 | MSG-010 | INV-010 |
| TC-11 | Prepare reminder; refresh fails | INV-011, ACC-011 |
| TC-12 | MSG-012 | INV-012 |
| TC-13 | MSG-013; retry and approval actions | INV-001 in an independent run |
| TC-14 | Send approved draft at 10:05 | INV-014, DRAFT-014, ACC-014 |
| TC-15 | MSG-001; restart; advance to October 6 at 10:00 | INV-001, ACC-015 in an independent run |

## Expected outcomes and runtime state

`../../tests/fixtures/expected_results.json` belongs to the evaluator, not the agent. Do not load expected results into prompts, tools, or runtime business data. Field names are conceptual acceptance expectations; implementation can map them to its own state model.

The future application will create `../../runtime/mutabi.db`. Runtime databases are excluded from Git. No database, loader, simulator, application, or test runner is implemented by these data files alone.

A future “Load demo data” action should import the baseline. “Reset demo” should restore only generated demo state, preserving source files. Scenario-specific events and pending messages are applied on demand.

These fixtures use English messages for review. Arabic variants and realistic phrasing remain a separate preparation step before an Arabic-first demo. Structural validation of these files is not evidence that the agent passes the cases.
