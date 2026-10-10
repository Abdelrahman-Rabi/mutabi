import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from mutabi.web import DemoApp, make_server


class Interpreter:
    def interpret(self, text, reference_date):
        return {'intent':'payment_promise','amount':'3000','payment_date':'2026-10-05',
                'date_requires_confirmation':False,'reason':'Explicit promise'}


class WebTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'web.db'
        self.app = DemoApp(self.path,interpreter_factory=Interpreter)

    def test_review_process_approve_send_then_followup(self):
        result = self.app.action('process',{'message_id':'MSG-001'})
        self.assertEqual(result['status'],'promise_recorded')
        data = {'draft_id':result['draft_id']}
        self.assertFalse(self.app.action('send',data)['sent'])
        self.app.action('approve',data)
        self.assertTrue(self.app.action('send',data)['sent'])
        self.assertTrue(self.app.action('send',data)['already_sent'])
        self.app.action('clock',{'now':'2026-10-06T10:05:00+03:00'})
        result = self.app.action('followups',{'invoice_id':'INV-001','scenario':'TC-15'})
        self.assertEqual(result['results'][0]['status'],'missed')
        self.assertEqual(len(self.app.snapshot()['deliveries']),1)
        self.assertEqual(DemoApp(self.path).now,'2026-10-06T10:05:00+03:00')

    def test_verify_partial_payment_before_followup(self):
        data = {'invoice_id':'INV-005','scenario':'TC-05'}
        self.app.action('verify',data)
        self.app.action('verify',data)
        self.assertEqual(self.app.action('followups',data)['results'][0]['status'],'partially_fulfilled')

    def test_add_reply_is_pending_and_safe_to_display(self):
        result = self.app.action('add_reply',{'invoice_id':'INV-001','text':'<script>alert(1)</script>'})
        message = next(r for r in self.app.snapshot()['messages'] if r['message_id']==result['message_id'])
        self.assertEqual(message['processing_status'],'pending')
        self.assertEqual(message['text'],'<script>alert(1)</script>')
        self.assertNotIn('api_key',json.dumps(self.app.snapshot()).lower())

    def test_reset_and_simulation_validation(self):
        with self.assertRaises(ValueError):
            self.app.action('verify',{'invoice_id':'INV-001','scenario':'TC-04'})
        self.app.action('clock',{'now':'2026-10-06T10:05:00+03:00'})
        with self.assertRaises(ValueError):
            self.app.action('clock',{'now':'2026-10-03T10:00:00+03:00'})
        self.app.action('reset',{})
        self.assertEqual(self.app.now,'2026-10-03T10:00:00+03:00')

    def test_http_session_and_static_assets(self):
        server = make_server(self.app,0)
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            base = f'http://127.0.0.1:{server.server_port}'
            with urlopen(base+'/api/session') as response:
                token = json.load(response)['token']
            with urlopen(base+'/') as response:
                self.assertIn('id="app"',response.read().decode())
                self.assertIn("script-src 'self'",response.headers['Content-Security-Policy'])
            bad = Request(base+'/api/action/reset',data=b'{}',headers={'Content-Type':'application/json'})
            with self.assertRaises(HTTPError) as error:
                urlopen(bad)
            self.assertEqual(error.exception.code,403)
            good = Request(base+'/api/action/verify',data=json.dumps({'invoice_id':'INV-001'}).encode(),
                           headers={'Content-Type':'application/json','X-Demo-Token':token})
            with urlopen(good) as response:
                self.assertTrue(json.load(response)['result']['verified'])
            foreign = Request(base+'/api/action/reset',data=b'{}',
                              headers={'X-Demo-Token':token,'Origin':'https://foreign.example'})
            with self.assertRaises(HTTPError) as error:
                urlopen(foreign)
            self.assertEqual(error.exception.code,403)
        finally:
            server.shutdown();server.server_close();thread.join()

    def test_second_listener_cannot_take_an_occupied_demo_port(self):
        server = make_server(self.app, 0)
        try:
            with self.assertRaises(OSError):
                make_server(self.app, server.server_port)
        finally:
            server.server_close()


if __name__ == '__main__':
    unittest.main()
