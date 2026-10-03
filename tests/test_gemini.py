import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from mutabi.gemini import GeminiInterpreter, ModelError, validate_evidence

TEXT = 'I will pay SAR 3,000 on October 5, 2026.'
VALUE = {'intent': 'payment_promise', 'amount': '3000.00', 'payment_date': '2026-10-05',
         'date_requires_confirmation': False, 'reason': 'Explicit promise',
         'amount_evidence': 'SAR 3,000', 'date_evidence': 'October 5, 2026'}


class GeminiTests(unittest.TestCase):
    def test_structured_request_and_parsing(self):
        requests = []
        def transport(request, timeout):
            requests.append(request)
            return io.BytesIO(json.dumps({'candidates': [{'finishReason': 'STOP',
                'content': {'parts': [{'text': json.dumps(VALUE)}]}}]}).encode())
        interpreter = GeminiInterpreter(api_key='fake-test-key', transport=transport)
        self.assertEqual(interpreter.interpret(TEXT, '2026-10-03')['amount'], '3000.00')
        payload = json.loads(requests[0].data)
        self.assertEqual(payload['generationConfig']['responseFormat']['text']['mimeType'], 'APPLICATION_JSON')
        self.assertNotIn('fake-test-key', requests[0].full_url)
        self.assertNotIn('invoice', json.loads(payload['contents'][0]['parts'][0]['text']))

    def test_relative_date_forces_confirmation(self):
        value = {**VALUE, 'date_evidence': 'next Thursday', 'payment_date': '2026-10-08'}
        result = validate_evidence(value, 'I will pay SAR 3,000 next Thursday.')
        self.assertTrue(result['date_requires_confirmation'])

    def test_unsupported_amount_or_date_is_rejected(self):
        for changed in ({'amount': '5000.00'}, {'payment_date': '2026-10-06'}, {'amount_evidence': 'SAR 8,000'}):
            with self.assertRaises(ValueError):
                validate_evidence({**VALUE, **changed}, TEXT)

    def test_http_error_redacts_api_body_and_key(self):
        def transport(request, timeout):
            raise HTTPError(request.full_url, 403, 'secret-api-key', {}, io.BytesIO(b'private body'))
        with self.assertRaises(ModelError) as error:
            GeminiInterpreter(api_key='secret-api-key', transport=transport).interpret(TEXT, '2026-10-03')
        self.assertNotIn('secret-api-key', str(error.exception))
        self.assertNotIn('private body', str(error.exception))

    def test_truncated_or_invalid_response_is_rejected(self):
        for body in ({'candidates': []}, {'candidates': [{'finishReason':'MAX_TOKENS'}]},
                     {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'not json'}]}}]}):
            with self.subTest(body=body), self.assertRaises(ModelError):
                GeminiInterpreter(api_key='fake', transport=lambda *args, **kwargs: io.BytesIO(json.dumps(body).encode())).interpret(TEXT,'2026-10-03')

    def test_missing_key_is_actionable(self):
        with patch.dict('os.environ', {}, clear=True), self.assertRaises(ModelError):
            GeminiInterpreter()

    def test_transient_failure_retries_then_succeeds(self):
        calls = []
        def transport(request, timeout):
            calls.append(request)
            if len(calls) == 1:
                raise HTTPError(request.full_url,503,'unavailable',{},io.BytesIO(b'{}'))
            return io.BytesIO(json.dumps({'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(VALUE)}]}}]}).encode())
        model = GeminiInterpreter(api_key='fake',transport=transport,sleeper=lambda seconds: None)
        self.assertEqual(model.interpret(TEXT,'2026-10-03')['amount'],'3000.00')
        self.assertEqual(len(calls),2)

    def test_rate_limit_exposes_safe_retry_delay(self):
        def transport(request, timeout):
            body = {'error':{'details':[{'@type':'type.googleapis.com/google.rpc.RetryInfo','retryDelay':'30s'}]}}
            raise HTTPError(request.full_url,429,'limit',{},io.BytesIO(json.dumps(body).encode()))
        with self.assertRaises(ModelError) as error:
            GeminiInterpreter(api_key='fake',transport=transport).interpret(TEXT,'2026-10-03')
        self.assertEqual(error.exception.retry_after,30)


if __name__ == '__main__':
    unittest.main()
