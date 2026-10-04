# Advanced discovery release — validation evidence

Verified locally on 4 October 2026. This records implementation checks, not customer validation or measured business impact.

## Automated checks

- `python -m unittest discover -s tests`: **119 passed** (latest complete run: 63.644 seconds).
- `node --check mutabi/static/app.js` and `node --check mutabi/static/i18n.js`: passed after the final interface corrections.
- PowerShell launcher parsed successfully; the final preview is launched through `Start-Mutabi.ps1`.
- Git whitespace checks passed. Generated SQLite databases, credentials, environment files and dependencies remain ignored.

The suite includes original OAuth, model-output evidence validation and workflow scenarios, plus new cases for review correction, draft reapproval/history, amendments, installment allocation, mixed cash/credit settlement, ambiguous shared receipts, finance holds, CSV atomicity, participant isolation, restart persistence, retained feedback and safe export.

## Browser checks

Performed in the Codex in-app browser using the actual local HTTP server and interface controls. No live AI calls or real customer messages were made.

| Flow | Observed result |
| --- | --- |
| Nine views | Overview, collections, promises, task board, approvals, analytics, feedback, settings and studio render and navigate. |
| Manual clarification | INV-002 reply “soon” manually confirmed as SAR 1,500 on 8 October; commitment and acknowledgment created, clarification draft invalidated. |
| Draft lifecycle | Revised wording returned to approval; reviewer Sara recorded; separate send produced simulated delivery. |
| Notes and assignment | Internal note retained with author; replacement balance-check task assigned to Lina. |
| Amendment | Date moved from 8 to 10 October with a reason; previous commitment superseded and old check closed. |
| Installment | SAR 1,000 recorded and allocated; commitment fulfilled while INV-001 retained SAR 2,000 outstanding. |
| Dispute and credit | Accepting a SAR 1,000 dispute retained SAR 4,000 balance/hold. Verified synthetic credit reduced balance to SAR 3,000; explicit finance resolution released the hold. Credit was not a cash allocation. |
| Payment review | Fresh ledger review completed without finding a receipt; invoice remained SAR 2,000 open, review displayed “Finance review completed”. |
| CSV onboarding | Preview retained the supplied sample and confirmation; import added one invoice with original SAR 4,500.50 and outstanding SAR 2,000.25. |
| Reply association | MSG-009 linked to INV-009B; missing explicit year resulted in clarification. Latest form offers only invoices belonging to that customer. |
| Arabic reply | Exact curated Arabic SAR 1,000/5 October script interpreted; customer Arabic preference produced Arabic acknowledgment. This does not establish general Arabic model accuracy. |
| Preferences and policy | Customer owner/language/priority updated; demo reviewer changed to Lina; future-check timing changed to three days and saved. |
| Feedback | Explicit five-star **test observation**, clearly labeled as browser validation, saved with real timestamp. Downloaded CSV included that record. It remained after story changes. |
| Feedback bias | Final form has zero selected ratings and requires an explicit choice. |
| Story navigation | Choosing the payment story directly opened INV-003 after the confirmation dialog. |
| Responsive Arabic | 390 × 844 and 320 × 844 screens had no horizontal overflow. Closed navigation was hidden; open/close/Escape worked. Customer dialog fit 320 px, and RTL arrow-key tab navigation worked. |
| Console | No new errors from the completed application. An initial error captured while the old script and new shell were being replaced was resolved before validation. |

The final preview uses a separate clean release database, preserving the development-session test evidence without presenting test ratings as customer feedback. Research/session databases stay local under ignored `runtime/` paths.

Saved views: [English desktop](screenshots/advanced-overview-en.jpg), [Arabic desktop](screenshots/advanced-overview-ar.jpg), and [Arabic mobile](screenshots/advanced-mobile-ar.jpg).

## Arabic refresh regression — 4 October 2026

Reproduced the reported `Cannot read properties of undefined (reading 'map')` in the open browser. Arabic Demo Studio attempted to map a missing scenario steps list. Failed navigation retained the previous screen while leaving Studio selected internally, so clicking تحديث repeated the rendering error.

Scenario steps now use an array-checked Arabic preference, English fallback and empty-list default. The new frontend regression test renders the actual backend snapshot across all nine views in both languages and covers missing, null and malformed optional steps. It runs through Node when available; Node is not required by the application runtime.

Rechecked all nine views in Arabic and English in the running browser, then refreshed successfully in both languages. No new console errors appeared during those checks. The browser remains on Arabic Overview with a successful refresh; [saved screenshot](screenshots/refresh-fixed-ar.jpg).

## Scope of the evidence

Browser checks exercise representative product journeys; automated tests verify the important state and isolation rules. This is not a full accessibility certification, load test, public-hosting security audit, production integration test or new live-provider benchmark. Always-on scheduling, real messaging/accounting integrations and production employee authentication are outside this discovery release.

Use [the product guide](ADVANCED_PRODUCT_GUIDE.md), [Arabic guide](ADVANCED_PRODUCT_GUIDE_AR.md) and [Arabic discovery session script](DISCOVERY_SESSION_AR.md) for demonstrations and participant research.
