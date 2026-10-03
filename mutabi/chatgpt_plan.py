"""ChatGPT-plan Responses interpreter: no model tools, no browser automation."""
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .gemini import INSTRUCTIONS, SCHEMA, ModelError, validate_evidence
from .chatgpt_auth import RESOURCE

ERRORS = {
    'subscription_sharing_user_not_eligible': 'ChatGPT plan usage is not available for this account or workspace.',
    'subscription_sharing_usage_limit_exceeded': 'ChatGPT plan usage limit reached. Review your limits in ChatGPT settings.',
    'subscription_sharing_usage_unavailable': 'ChatGPT usage availability could not be checked. Try again later.',
    'subscription_sharing_unsupported_capability': 'This ChatGPT model or request format is not supported. Select another model.',
    'subscription_sharing_route_not_supported': 'ChatGPT plan routing is not available for this integration.',
    'subscription_sharing_invalid_user': 'ChatGPT account authorization could not be validated. Reconnect your account.',
}


def safe_error(body, status=None):
    error = body.get('error', {}) if isinstance(body, dict) else {}
    code = error.get('code') if isinstance(error, dict) else None
    return ModelError(ERRORS.get(code, 'ChatGPT request failed. Review the connection and try again.'), status)


def read_sse(response):
    """Parse bounded, multi-line SSE; never accept partial model output."""
    total = 0; lines = []; completed = None; finished_items = {}
    while True:
        raw = response.readline(1024 * 1024 + 1)
        total += len(raw)
        if total > 2 * 1024 * 1024 or len(raw) > 1024 * 1024:
            raise ModelError('ChatGPT response exceeded the allowed size.')
        if not raw:
            if lines:
                raise ModelError('ChatGPT stream ended before completion. No interpretation was saved.')
            break
        line = raw.decode('utf-8').rstrip('\r\n')
        if line.startswith('data:'):
            lines.append(line[5:].lstrip(' '))
        elif not line and lines:
            data = '\n'.join(lines); lines = []
            if data == '[DONE]':
                break
            event = json.loads(data)
            kind = event.get('type')
            if kind in ('response.refusal.delta', 'response.refusal.done'):
                raise ModelError('ChatGPT declined to interpret this reply. Request employee review.')
            if kind == 'response.output_item.done':
                item = event.get('item', {})
                index = event.get('output_index')
                if item.get('type') == 'message':
                    if index in finished_items:
                        raise ModelError('ChatGPT returned conflicting completion events.')
                    if item.get('status') != 'completed':
                        raise ModelError('ChatGPT returned an incomplete response. No interpretation was saved.')
                    finished_items[index] = item
            if kind in ('response.failed', 'error'):
                raise safe_error(event.get('response', event))
            if kind == 'response.incomplete':
                raise ModelError('ChatGPT returned an incomplete response. No interpretation was saved.')
            if kind == 'response.completed':
                if completed is not None:
                    raise ModelError('ChatGPT returned conflicting completion events.')
                completed = event.get('response', {})
    if not completed or completed.get('status') != 'completed':
        raise ModelError('ChatGPT stream ended before completion. No interpretation was saved.')
    pieces = []
    # Some plan gateway streams omit output items from response.completed.
    # Only use items explicitly finalized before that successful completion.
    for item in (completed.get('output') or [finished_items[k] for k in sorted(finished_items)]):
        if item.get('type') != 'message':
            continue
        for part in item.get('content', []):
            if part.get('type') == 'refusal':
                raise ModelError('ChatGPT declined to interpret this reply. Request employee review.')
            if part.get('type') == 'output_text':
                pieces.append(part['text'])
    return ''.join(pieces), completed


class ChatGPTPlanInterpreter:
    def __init__(self, auth, transport=urlopen):
        self.auth, self.transport = auth, transport
        self.last_metadata = None

    def interpret(self, text, reference_date):
        if not isinstance(text, str) or not text.strip() or len(text) > 12000:
            raise ModelError('Customer reply must contain 1–12000 characters.')
        token = self.auth.access_token()
        model = self.auth.status()['model']
        if not model:
            raise ModelError('Refresh the ChatGPT model catalog and choose a model first.')
        payload = {'model': model, 'instructions': INSTRUCTIONS,
                   'input': [{'role': 'user', 'content': json.dumps({'reference_date': reference_date,
                              'customer_reply': text}, ensure_ascii=False)}],
                   'store': False, 'stream': True,
                   'text': {'format': {'type': 'json_schema', 'name': 'collection_reply',
                                      'strict': True, 'schema': SCHEMA}}}
        request = Request(RESOURCE + '/responses', data=json.dumps(payload).encode(),
                          headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json',
                                   'Accept': 'text/event-stream'}, method='POST')
        try:
            with self.transport(request, timeout=60) as response:
                # The plan gateway may omit Content-Type; the bounded reader still
                # requires well-formed SSE and a successful completion event.
                content_type = response.headers.get('Content-Type')
                if content_type and 'text/event-stream' not in content_type:
                    raise ModelError('ChatGPT did not return a response stream. No interpretation was saved.')
                output, body = read_sse(response)
            result = validate_evidence(json.loads(output), text)
            self.last_metadata = {'provider': 'chatgpt_plan', 'model': model, 'usage': body.get('usage', {})}
            return result
        except HTTPError as error:
            try:
                body = json.loads(error.read(8192))
            except (ValueError, UnicodeError):
                body = {}
            raise safe_error(body, error.code) from None
        except (URLError, TimeoutError):
            raise ModelError('ChatGPT request failed or timed out. No interpretation was saved.') from None
        except (ValueError, KeyError, TypeError, UnicodeError):
            raise ModelError('ChatGPT returned invalid extraction data. No interpretation was saved.') from None
