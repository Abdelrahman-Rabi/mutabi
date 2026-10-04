"""HTTP-level participant isolation and export regression checks."""
import csv
import io
import json
import tempfile
import threading
import unittest
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

from mutabi.web import DemoApp, make_server


class Participant:
    def __init__(self, base):
        self.base = base
        self.cookies = CookieJar()
        self.client = build_opener(HTTPCookieProcessor(self.cookies))
        self.token = self.get('/api/session')['token']

    def get(self, path):
        with self.client.open(self.base + path) as response:
            return json.load(response)

    def raw(self, path):
        with self.client.open(self.base + path) as response:
            return response.read().decode('utf-8-sig'), response.headers

    def action(self, name, data, token=None):
        request = Request(self.base + '/api/action/' + name,
                          data=json.dumps(data).encode(),
                          headers={'Content-Type':'application/json','X-Demo-Token':token or self.token})
        with self.client.open(request) as response:
            return json.load(response)['result']


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'participants.db'
        self.app = DemoApp(self.path)
        self.server = make_server(self.app, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def test_independent_participants_cannot_see_or_reset_each_other(self):
        first, second = Participant(self.base), Participant(self.base)
        reply = first.action('add_reply', {'invoice_id':'INV-001','text':'Participant A synthetic reply'})
        self.assertTrue(any(m['message_id'] == reply['message_id'] for m in first.get('/api/state')['messages']))
        self.assertFalse(any(m['message_id'] == reply['message_id'] for m in second.get('/api/state')['messages']))
        second.action('reset', {})
        self.assertTrue(any(m['message_id'] == reply['message_id'] for m in first.get('/api/state')['messages']))
        with self.assertRaises(HTTPError) as error:
            second.action('reset', {}, token=first.token)
        self.assertEqual(error.exception.code, 403)

    def test_browser_cookie_is_http_only_and_reloads_preserve_state(self):
        participant = Participant(self.base)
        cookie = list(participant.cookies)[0]
        self.assertTrue(cookie.has_nonstandard_attr('HttpOnly'))
        self.assertEqual(cookie.get_nonstandard_attr('SameSite'), 'Lax')
        result = participant.action('add_note', {'invoice_id':'INV-001','text':'Persistent synthetic note','actor':'collector_sara'})
        state = participant.get('/api/state')
        self.assertTrue(any(n['text'] == 'Persistent synthetic note' for n in state['notes']))
        self.assertEqual(participant.get('/api/session')['token'], participant.token)
        self.assertTrue(result)

    def test_reset_retains_feedback_but_removes_case_changes(self):
        participant = Participant(self.base)
        participant.action('feedback', {'rating':4,'category':'usability','text':'Keep this research evidence',
                                        'role':'Collector','view':'overview'})
        participant.action('add_note', {'invoice_id':'INV-001','text':'Discard this case note','actor':'collector_sara'})
        participant.action('reset', {})
        state = participant.get('/api/state')
        self.assertTrue(any(f['text'] == 'Keep this research evidence' for f in state['feedback']))
        self.assertFalse(any(n['text'] == 'Discard this case note' for n in state['notes']))

    def test_export_excludes_auth_and_protects_spreadsheet_cells(self):
        participant = Participant(self.base)
        participant.action('feedback', {'rating':3,'category':'usability','text':'=1+1','role':'Collector','view':'overview'})
        data = participant.get('/api/export?format=json')
        self.assertTrue(data['synthetic'])
        self.assertNotIn('chatgpt', data)
        self.assertNotIn('settings', data)
        self.assertNotIn('token', json.dumps(data).lower())
        text, headers = participant.raw('/api/export?format=csv')
        rows = list(csv.DictReader(io.StringIO(text)))
        self.assertEqual(rows[0]['text'], "'=1+1")
        self.assertIn('attachment', headers['Content-Disposition'])

    def test_foreign_origin_blocked_and_demo_processing_needs_no_key(self):
        participant = Participant(self.base)
        request = Request(self.base + '/api/action/reset', data=b'{}',
                          headers={'X-Demo-Token':participant.token,'Origin':'https://external.example'})
        with self.assertRaises(HTTPError) as error:
            participant.client.open(request)
        self.assertEqual(error.exception.code, 403)
        result = participant.action('process', {'message_id':'MSG-001'})
        self.assertEqual(result['status'], 'promise_recorded')
        self.assertEqual(participant.get('/api/state')['provider'], 'demo')

    def test_restart_restores_cookie_workspace_with_new_request_token(self):
        participant = Participant(self.base)
        participant.action('feedback', {'rating':5,'category':'workflow','text':'Persist through server restart',
                                        'role':'Finance','view':'feedback'})
        participant.action('settings', {'settings':{'workspace_name':'Participant research workspace'}})
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.server = make_server(DemoApp(self.path), 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        participant.base = f'http://127.0.0.1:{self.server.server_port}'
        previous_token = participant.token
        participant.token = participant.get('/api/session')['token']
        self.assertNotEqual(previous_token, participant.token)
        state = participant.get('/api/state')
        self.assertEqual(state['settings']['workspace_name'], 'Participant research workspace')
        self.assertTrue(any(f['text'] == 'Persist through server restart' for f in state['feedback']))

    def test_reset_keeps_timing_settings_consistent_and_returns_demo_provider(self):
        participant = Participant(self.base)
        participant.action('settings', {'settings':{'followup_days_after_promise':3}})
        participant.action('provider', {'provider':'gemini'})
        participant.action('reset', {})
        state = participant.get('/api/state')
        self.assertEqual(state['provider'], 'demo')
        self.assertEqual(state['settings']['provider'], 'demo')
        self.assertEqual(state['settings']['followup_days_after_promise'], 3)
        promise = next(p for p in state['promises'] if p['source_message_id'] == 'MSG-001')
        task = next(t for t in state['tasks'] if t['promise_id'] == promise['promise_id'])
        self.assertEqual(task['due_date'], '2026-10-08')


if __name__ == '__main__':
    unittest.main()
