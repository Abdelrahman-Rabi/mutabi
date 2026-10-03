# ChatGPT plan setup

Mutabi now supports the documented local public-client Sign in with ChatGPT flow. It uses authorization code + PKCE, validates the ID token signature/issuer/audience/nonce, requests plan permission, loads the account's model catalog, and sends structured, streamed Responses requests using the authorized plan token. It does not read Codex credentials or automate the ChatGPT website.

## Connect and try it

1. Install `requirements.txt` in your Python environment and start `python -m mutabi.web --db runtime/ui-demo.db --port 8765`.
2. Open http://127.0.0.1:8765/ on the same computer. Keep the server running throughout sign-in.
3. Select **ChatGPT plan**, then **Continue with ChatGPT**. Allow the popup if your browser blocks it.
4. Sign in on OpenAI's page and grant the offered ChatGPT plan permission. Account eligibility and provider availability determine whether this succeeds. An identity-only grant cannot run inference.
5. Return to Mutabi. Once the model catalog loads, choose an available model and select **Analyze reply** on the first synthetic case. Expected workflow: an explicit SAR 3,000 promise for October 5, 2026, a follow-up task, and a draft requiring employee approval.
6. Use **Refresh models**, **Add account**, or **Disconnect** as needed. The usage link opens ChatGPT settings. Gemini can be selected explicitly; errors never automatically switch providers or incur API fallback charges.

Sign-in requires human consent initially. Subsequent inference and token refresh run automatically while the grant remains valid and the account has allowance. Revoked/expired authorization requires reconnecting.

## Credentials and data

Credentials are stored separately from business records, in the database parent's `chatgpt/credentials.bin`. For the command above, this is `runtime/chatgpt/credentials.bin`. Windows protects it with current-user DPAPI; macOS/Linux uses file permissions 0600 and directory permissions 0700. This is a local file store, not a cross-platform OS keychain. Do not copy, upload, or commit this directory. The default `runtime/` is ignored by Git; custom database locations need equivalent exclusion.

Browser state exposes connection status, account labels, model choices, and safe errors, never tokens. Reply text and its reference date are sent to OpenAI; invoice balances and evaluation expectations are not part of the model request. Use synthetic data. Validated results and provider/model/usage attribution enter the business audit trail. Accounting checks, approval, and simulated sending retain their existing safeguards.

Run one process using a credential directory at a time. Refresh is serialized inside the server process; coordinating token rotation between separate CLI/server processes is not implemented.

## Validation

```sh
python -m unittest discover -s tests -v
```

65 offline checks pass, including 20 ChatGPT-specific checks for PKCE/state, one-time callbacks, real JWT signature and claim validation, refresh rotation, credential protection on Windows, permission gating, stream completion, quota errors, refusal, and evidence validation. OAuth HTTP exchanges and inference responses are mocked in these tests. Regression checks also cover the observed gateway behavior: omitted Content-Type and finalized message items absent from the terminal completion payload. These still require successful completion before accepting text.

On October 3, 2026, the owner completed real OpenAI sign-in and plan consent. Identity validation and account model catalog access succeeded. All 15 approved scenarios subsequently passed a live subscription evaluation using the account-listed `gpt-6-astra` model, in approximately 152 seconds. Eight distinct synthetic replies were interpreted; duplicate replies reused interpretations within that run, and five scenarios tested deterministic workflows without model calls. Evidence is in `live_chatgpt_evaluation.json`. This is one small evaluation run, not a production reliability or business-impact measurement. An initial request revealed the gateway stream differences described above; those were corrected before the successful run.

After connecting, stop the web server before the opt-in full evaluation to avoid concurrent credential access:

```sh
python -m evaluation.live --provider chatgpt_plan --auth-dir runtime/chatgpt --min-interval 15
```

This consumes the connected account's allowance and writes `docs/live_chatgpt_evaluation.json`. For individual CLI processing, use `python -m mutabi.agent process --provider chatgpt_plan --db runtime/ui-demo.db --message MSG-001` with the same credential directory convention. CLI defaults remain Gemini for compatibility.

## Hosting boundary

This implementation is for the local demo. It binds to loopback and registers a loopback callback. Public hosted visitor sign-in is a separate integration requiring the documented website access/registration path; changing the host binding is insufficient. A private owner VM also requires separate credential provisioning and host identity handling, which this demo does not implement. The demo employee identity is fixed, so production user authentication is still required independently.

See the [official local integration guide](https://developers.openai.com/siwc/token-sharing-open-source), [model inference guide](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference), and [preview limitations](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations). The earlier research and deployment proposal is in `CHATGPT_SUBSCRIPTION_INTEGRATION.md`.
