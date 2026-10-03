# Validation record — October 3, 2026

Command: `python -m unittest discover -s tests -v`

Result: 65 offline tests passed, no failures or errors after adding ChatGPT plan support. The original 45 checks are listed below; 20 additional checks cover OAuth identity/state/refresh/protected storage and streamed structured inference. Provider exchanges are mocked. See `CHATGPT_SETUP.md` for live connection verification.

| Layer | Tests | Execution |
|---|---:|---|
| Demo loader | 5 | Real SQLite files in temporary directories |
| Business tools | 11 | Real SQLite and synthetic accounting events |
| Gemini adapter | 8 | Mocked HTTP responses, bounded retries, safe rate-limit reporting |
| Workflow | 16 | Real tools/database with controlled interpreter outputs |
| Web interface backend | 5 | Local HTTP session checks, reset, reply persistence, approval/send/follow-up sequence |

## Approved scenario coverage

ChatGPT plan authorization and model catalog access were verified after owner consent on October 3, 2026. A separate live evaluation using `gpt-6-astra` passed all 15 approved scenarios in approximately 152 seconds, with eight distinct synthetic model requests. See `live_chatgpt_evaluation.json`. The adapter was adjusted for missing gateway Content-Type and completion payloads omitting finalized output items; regression checks require successful terminal completion and reject incomplete streams. This remains a small single-run sample with simulated accounting/delivery and English fixtures.

After restarting the server, the connection remained usable. A live UI processing run for MSG-001 recorded the SAR 3,000 promise for October 5, scheduled the October 6 balance check, and created a draft awaiting employee approval. Screenshot: `chatgpt-live-workflow.png`. No draft was sent in this verification.

TC-01 through TC-15 each have a named workflow test in `tests/test_workflow.py`. These checks exercise persistence and side effects using a deliberately controlled interpretation. The separate expected-results JSON is not loaded by the application or interpreter.

Live Gemini extraction was executed on October 3, 2026 using `gemini-3.8-flash`. A paced run of all 15 approved scenarios passed, including TC-08 date interpretation and TC-12 malicious-message classification. Eight unique synthetic replies were interpreted by Gemini; duplicate reply text in TC-13 and TC-15 reused the interpretation within that evaluation run. Five accounting/guard scenarios require no language-model call.

The first unpaced run passed 6 scenarios and encountered 9 provider errors (HTTP 503 availability errors and HTTP 429 rate/quota errors). After adding bounded retries for temporary server errors and pacing unique replies 15 seconds apart, the next run passed all 15 scenarios in approximately 165 seconds. This operational history is preserved in `live_evaluation_previous.json`; the successful run is in `live_evaluation.json`. The 15-second interval was sufficient for this run, not a guarantee for every project's quota.

The key was loaded locally and never written to the evaluation reports. Tests used isolated temporary databases; the main demo database was preserved. No production data was sent. This is a small single-run sample, not proof of production reliability.

The agent uses a constrained model-based interpretation step followed by deterministic tool orchestration. This is not an unrestricted autonomous tool-selection loop. English draft messages currently come from templates. Scheduled checks are invoked on demand.

No measured time saving, collection improvement, real customer delivery, or ERP integration has been demonstrated. A Gemini key configured locally is required to repeat live interpretation tests.

## Browser verification

The local interface was tested on October 3, 2026 in a separate `runtime/ui-demo.db` workspace. A real Gemini call processed the INV-001 reply, saved the SAR 3,000 October 5 promise, and scheduled an October 6 check. Employee approval and one simulated delivery were verified through the browser. Advancing the demo clock and selecting the unchanged-balance simulation produced a missed promise, a closed balance-check task, and a new overdue follow-up/draft. The original `runtime/mutabi.db` was not modified by this browser walkthrough.

An additional regression verifies that reading a partial payment before running its scheduled check preserves the partially fulfilled result. No frontend dependencies or remote assets are required.

## Next validation steps

1. Add wording variants, including Arabic, and repeat critical safeguards.
2. Rehearse the reviewer walkthrough and test additional wording variants in the interface.
3. Measure manual versus assisted task times with employee review included.
4. Continue recording live results separately from controlled workflow results.

Arabic interface browser verification (October 3, 2026): switched Arabic → English → Arabic; confirmed RTL, translated controls, Gregorian dates, SAR amounts, selected invoice and accounting scenario preservation, unsaved Arabic reply preservation, language preference after reload, and no horizontal overflow at the desktop viewport. Screenshot: `demo-interface-ar.png`. All 45 offline checks passed after the static route update. This verifies interface localization, not Arabic Gemini interpretation accuracy.
