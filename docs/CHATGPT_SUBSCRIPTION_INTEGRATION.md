# ChatGPT subscription integration research and migration plan

Researched October 3, 2026 (Asia/Amman). Official OpenAI sources only. This is a design proposal, not an implemented or live-verified connection.

## Decision

Implement a separate `chatgpt_plan` provider using Mutabi's own Sign in with ChatGPT registration and direct Responses API calls. Keep Gemini selectable. First establish a completed authenticated request with synthetic data before changing the working demo.

There are three deployment cases, with different requirements:

| Deployment | Evidence and practical decision |
| --- | --- |
| Open-source Mutabi running on the user's laptop | Documented dynamic registration flow; implement and test this first. |
| The same user's open-source installation on a self-hosted VM | Explicitly documented credential-transfer procedure. Suitable candidate for an owner-operated private demo, subject to actual account admission. |
| Public hosted service where visitors connect their subscriptions | The developer overview directs remotely hosted apps to the interest form. Do not treat dynamic local registration as authorization for this deployment. |

The overview supports open-source/local apps and distinguishes remotely hosted services. Commercial registration currently describes selected partners. No published approval turnaround or guarantee was found. [Overview](https://developers.openai.com/siwc/token-sharing-open-source), [client access](https://developers.openai.com/siwc/request-client-id), [interest form](https://openai.com/form/sign-in-with-chatgpt-interest/).

The end-user guide confirms eligible Plus/Pro subscribers can authorize supported apps to consume their existing plan usage. Sign-in alone does not grant that permission. This does not create a separate allowance. [User guide](https://learn.chatgpt.com/docs/sign-in-with-chatgpt).

**Correction to earlier advice:** remotely running an open-source installation is not categorically excluded. A private self-hosted VM is documented; a visitor-facing hosted service is a separate integration case. Making the repository public does not, by itself, settle the public service's eligibility.

## Authentication contract for a local installation

Persist an opaque host ID before registration, for example a UUIDv4 prefixed with `urn:uuid:`. Keep it stable across restarts and sign-ins; each runtime host has a distinct ID. [Host identity](https://developers.openai.com/siwc/token-sharing-open-source).

Initial authorization parameters:

| Parameter | Value |
| --- | --- |
| `client_id` | `dynamic_agent_client` initially; saved issued ID subsequently |
| `agent_name_hint` | `Mutabi` on initial registration only |
| `ext_agent_host_id` | Persistent opaque host ID |
| `response_type` | `code` |
| `redirect_uri` | `http://127.0.0.1:<port>/auth/callback` |
| `scope` | `openid profile email offline_access resource.invoke chatgpt.tokens.use.direct` |
| `resource` | `https://api.openai.com/v1` |
| `state`, `nonce` | Fresh random values per attempt |
| `code_challenge_method` | `S256` |
| `code_challenge` | SHA-256 PKCE challenge |

Start the callback listener first. Only the callback port may change; preserve scheme, host and path. Validate returned state. Initial registration supplies an issued client ID. Exchange the code with that ID, verifier and identical redirect/resource values; no client secret or partner API key is needed for this OSS flow. Verify the ID-token signature, issuer, audience, expiry and nonce. Require the granted plan-usage scope before inference. [Registration contract](https://developers.openai.com/siwc/token-sharing-open-source/sign-in).

Discover endpoints from [OpenID configuration](https://auth.openai.com/.well-known/openid-configuration). Its current issuer is `https://auth.openai.com`, authorization endpoint `/api/accounts/authorize`, token endpoint `/api/accounts/oauth/token`, JWKS `/.well-known/jwks.json`, and revocation endpoint `/api/accounts/oauth/revoke`.

Use a maintained OIDC/JWT verification library rather than handwritten cryptography. A hosted website identity integration requires its supplied client registration and exact callback URL; its identity-only guide does not automatically grant subscription inference. [Website integration](https://developers.openai.com/siwc/website).

### Proposed Mutabi callback behavior

1. Accept a connection attempt only through an authenticated local action, not an arbitrary URL supplied by another site.
2. Store an expiring, one-use transaction with PKCE verifier, state, nonce and callback URI on the Python side.
3. Open the system browser for user sign-in and consent.
4. Validate callback and identity before activating the connection. On cancellation, leave the current provider intact.
5. Save the issued registration and protected credentials outside the repository and demo database.
6. Fetch the account's model catalog; do not mark the provider operational until a completed smoke request succeeds.

This is our proposed application behavior. Callback transaction expiry, local UI-session binding and storage locations must be implemented and tested.

## Credential lifecycle

Separate registrations by verified identity and issued client ID, not email alone. Store tokens only in protected runtime storage; exclude them from browser storage, logs and Git. Serialize refreshes, save replacement tokens atomically, and refresh with the issued client ID and resource. A sign-out should revoke the renewable session and clear local credentials; distinguish failed revocation from successful local sign-out. Temporary network errors should not destroy credentials. [Accounts and sessions](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions).

The current reference gives one-hour access tokens and rotating refresh tokens with a 30-day lifetime renewed on successful refresh. Implementation should honor returned expiry fields and renewal timing rather than rely solely on hardcoded durations. [Token reference](https://developers.openai.com/siwc/token-sharing-open-source/token-reference).

Proposed Windows storage: a Mutabi-specific record under the user's application-data directory, protected using Windows credential protection/OS storage. A VM needs separately protected storage. Store host identity separately so credential imports cannot overwrite it. Never reuse the desktop app's private credential files as an undocumented integration.

## Inference contract

Use the saved OAuth access token as a bearer credential with `GET https://api.openai.com/v1/models` and `POST https://api.openai.com/v1/responses`. The plan model catalog uses a `models` array with visible entries, `slug` and `display_name`; do not assume the ordinary API-key catalog shape. Use an account-listed model, not a hardcoded entitlement.

HTTP requests must stream, with `store: false`. Success requires `response.completed`; partial text is insufficient. Limits can appear as a failed event after streaming begins. Do not use ChatGPT `backend-api` URLs. [Models and inference](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference).

Proposed request shape (illustrative placeholders; not executable JSON):

```json
{
  "model": "<account-selected slug>",
  "instructions": "<existing Mutabi interpretation instructions>",
  "input": [{"role": "user", "content": "<JSON containing reference_date and customer_reply>"}],
  "store": false,
  "stream": true,
  "text": {
    "format": {
      "type": "json_schema",
      "name": "collection_reply",
      "strict": true,
      "schema": "<existing seven-field SCHEMA object>"
    }
  }
}
```

Structured outputs use `text.format` and strict JSON schema. Our flat schema is a reasonable candidate, but schema acceptance on the selected subscription model remains a live compatibility gate. General API schema documentation is not proof of access on a particular plan. [Structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

The plan preview rejects explicit system-message items and several common parameters, including `temperature`, `max_output_tokens`, `background`, `conversation` and HTTP `previous_response_id`. Use `instructions` and send required context in `input`. Hosted file search, Code Interpreter, computer use and hosted MCP are unavailable on this route. Mutabi needs only text interpretation, so these tool restrictions do not require redesigning its collection workflow. [Preview limitations](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations).

### Our stream processing design

Implement a bounded SSE reader handling event boundaries across network chunks, UTF-8 Arabic, timeouts and output-size limits. Collect the intended output text, reject refusals, incomplete/failed responses and missing completion. Parse JSON only after successful completion; apply the existing exact-quote evidence validator before persisting an interpretation. Do not mutate invoice state on a model/transport error.

## Failure handling and UI

| Condition | Mutabi behavior |
| --- | --- |
| Sign-in succeeded but plan scope absent | Show signed-in identity with plan processing disabled. |
| `subscription_sharing_user_not_eligible` | Explain account/workspace restriction; no repeated login loop. |
| `subscription_sharing_usage_limit_exceeded` | Pause plan requests; offer usage settings. |
| `subscription_sharing_usage_unavailable` | Preserve credentials; bounded retry later. |
| `subscription_sharing_unsupported_capability` | Correct the request, rather than resend unchanged. |
| Terminal refresh failure or confirmed revocation | Require reconnect. |

Responses may fail before SSE opens with a nonstandard body or during streaming. Keep safe error codes/status/request IDs; redact credentials and raw customer text from diagnostics. Do not silently switch billing/provider. [Errors and recovery](https://developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery).

Show `Continue with ChatGPT`, a first-connection usage explanation, the active account, `Using ChatGPT plan`, model choice, disconnect, and a usage-management link. On a limit, usage management is the primary action. Localize the surrounding explanation for our Arabic UI while checking approved button formats. [UI guidance](https://developers.openai.com/siwc/ui-ux-guidelines).

Our proposed neutral process button is `Analyze reply` / `تحليل الرد`, with the active provider displayed separately. This avoids Gemini-specific labels misleading users after switching providers.

## Self-hosted VM procedure and boundary

The VM guide explicitly covers remote open-source installations. Create a stable VM host ID, complete OAuth locally with the same client/user/workspace, securely transfer the protected registration credentials, preserve the VM's distinct host ID and let the VM own subsequent refreshes. Loopback callbacks reach the browser's computer, not the VM. Transferred sessions currently lack host-specific usage attribution and revocation. [VM procedure](https://developers.openai.com/siwc/token-sharing-open-source/self-hosted-vms).

For Mutabi, begin with an owner-only VM accessed privately, such as through an SSH tunnel. This is a proposed deployment arrangement, not proof that arbitrary public visitors may use the owner's allowance. A public multi-user service needs eligibility confirmed through the hosted registration route. The research found no demo-only exception allowing us to ignore that distinction.

## Direct OAuth vs. Codex alternatives

| Approach | Assessment for this project |
| --- | --- |
| Own OAuth + direct Responses adapter | Recommended target. No model shell tools or Codex process needed for this narrowly scoped extraction. |
| Codex CLI signed in with ChatGPT | Potential faster local development fallback; does not create a Mutabi-branded OAuth connection. |
| Codex app-server with Mutabi OAuth token | Official option, but adds process/RPC lifecycle to our simple interpreter. |
| Browser automation of ChatGPT | Unnecessary; use documented endpoints. |

App-server can accept an OAuth token via its child-process environment and a Responses provider pointed at `https://api.openai.com/v1`; no separate Codex login is required for that configuration. The application owns renewal and restarts the process with renewed credentials. Model/list can be cached and is not an entitlement test. [App-server integration](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server).

The CLI supports noninteractive execution and schema outputs. It is appropriate to investigate separately as a local fallback, not to present as equivalent to an approved hosted subscription integration. [Noninteractive mode](https://developers.openai.com/codex/noninteractive).

## Changes mapped to our code

| Component | Proposed change |
| --- | --- |
| New `mutabi/interpretation.py` | Extract SCHEMA, INSTRUCTIONS, evidence validation and provider-neutral errors from gemini.py. Preserve compatibility imports for existing tests if useful. |
| New `mutabi/chatgpt_auth.py` | OIDC discovery, PKCE, callback verification, account records, renewal and disconnect. |
| New `mutabi/chatgpt_plan.py` | Account model catalog, streamed extraction, safe errors and metadata. |
| New `mutabi/providers.py` | Explicit interpreter selection and readiness for Gemini/ChatGPT plan. |
| `mutabi/web.py` | Connection/status/model actions, callback route, session-bound provider selection; expose safe account status only. |
| `mutabi/static/app.js`, `i18n.js`, `index.html` | Provider settings, account/usage status, neutral action labels, bilingual connection messages. |
| `mutabi/agent.py`, `evaluation/live.py` | Explicit provider option and distinct evaluation report. |
| `mutabi/workflow.py` | Keep interpreter contract and deterministic workflow; add provider/model attribution to interpretation audit without saving credentials. |
| Dependencies | Add maintained JWT verification and secure credential storage support; do not hand-code signature validation to preserve stdlib-only status. |

Local inspection confirms `Workflow` already accepts `interpret(text, reference_date)` independently of provider. However, web readiness and labels currently assume Gemini. The current server binds loopback, uses one shared demo token and database, and reloads synthetic baseline on startup; it is not a production multi-user server. Hosted deployment also requires real sessions, account/workspace isolation, HTTPS, correct proxy/origin configuration, persistent startup behavior and request limits. Changing a provider alone cannot supply those properties.

## Implementation sequence and release gates

1. **Eligibility smoke test:** add isolated local registration/connection code; user completes sign-in and consent. Request the model catalog and complete a harmless synthetic request. Record only safe success metadata.
2. **Extraction compatibility:** send our schema and a single synthetic promise; verify completed SSE, evidence and normalized result. If unsupported, establish the exact supported format before modifying the workflow.
3. **Provider integration:** add selection/readiness/settings and reuse the existing workflow. Keep Gemini available through explicit selection.
4. **Failure tests:** rejected state/nonce/signature/audience, missing scope, callback replay, concurrent refresh, expired/revoked credentials, interrupted SSE, refusal, quota and invalid JSON. Confirm no collection-state mutation on failure.
5. **Behavior evaluation:** rerun all existing offline tests and all 15 live cases under the new provider, including Arabic replies as separately labeled additional coverage. Confirm replay does not incur another model call.
6. **Restart and UI checks:** reconnection behavior, both languages, no credential browser exposure, usage/account display and unsaved reply preservation.
7. **Deployment:** private self-hosted VM only after local success and protected-storage checks; public visitor OAuth only after hosted access is established. Keep the video/local setup path available for submission.

Each gate should produce concrete evidence before we retire an existing demo path. Research cannot establish account admission, model entitlement or schema acceptance without a live authorized request.

## What has and has not been verified

- Read the official user, registration, website, account, token, inference, error, preview, UI, VM and app-server documentation and current OIDC discovery metadata.
- Inspected Mutabi's adapter, web server and workflow.
- Installed CLI reports `codex-cli 0.145.0`; `codex login status` reports not logged in in this execution context. The desktop app session does not prove CLI authentication. No credential files were read.
- No OAuth registration, consent, token exchange, model request, deployment, credential transfer or interest-form submission was performed.
- No production code or running provider was changed by this research.

Recommended next action: prove the direct local OAuth connection and schema extraction, then integrate it as an alternative provider. Treat public-hosted registration as an independent dependency, not something hidden inside the implementation.
