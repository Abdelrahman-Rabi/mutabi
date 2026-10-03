"""Local-only demo web server. Uses standard-library HTTP and persistent tools."""
import argparse
import json
import os
import secrets
import sqlite3
import threading
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from uuid import uuid4

from .database import connect
from .demo import DEFAULT_DB, ROOT, load_demo, timestamp
from .gemini import DEFAULT_MODEL, GeminiInterpreter, ModelError, load_local_env
from .tools import Tools, row
from .workflow import Workflow
from .chatgpt_auth import ChatGPTAuth
from .chatgpt_plan import ChatGPTPlanInterpreter

STATIC = ROOT / 'mutabi' / 'static'


class DemoApp:
    def __init__(self, path=DEFAULT_DB, interpreter_factory=None):
        self.path = Path(path)
        self.interpreter_factory = interpreter_factory
        self.auth = ChatGPTAuth(self.path.parent / 'chatgpt')
        self.provider = self.auth.data.get('provider', 'chatgpt_plan')
        self.lock = threading.RLock()
        load_demo(self.path)
        self.now = Tools(self.path).now

    def snapshot(self):
        with self.lock, connect(self.path) as db:
            invoices = [dict(r) for r in db.execute(
                'SELECT i.*,c.name AS customer_name FROM invoices i JOIN customers c USING(customer_id) ORDER BY invoice_id')]
            tables = ('messages','promises','tasks','drafts','disputes','audit_events','deliveries')
            result = {name: [dict(r) for r in db.execute(f'SELECT * FROM {name}')] for name in tables}
            chatgpt = self.auth.status()
            result.update(invoices=invoices, now=self.now, provider=self.provider, chatgpt=chatgpt,
                          model=(chatgpt['model'] or 'ChatGPT plan') if self.provider == 'chatgpt_plan' else os.environ.get('GEMINI_MODEL', DEFAULT_MODEL),
                          model_ready=chatgpt['ready'] if self.provider == 'chatgpt_plan' else bool(os.environ.get('GEMINI_API_KEY')),
                          accounting_scenarios=[dict(r) for r in db.execute(
                              'SELECT scenario_id,invoice_id,available_at,result,outstanding_minor FROM demo_accounting_events')])
            return result

    def action(self, action, data, callback_uri=None):
        with self.lock:
            if action == 'provider':
                if data.get('provider') not in ('gemini', 'chatgpt_plan'):
                    raise ValueError('Choose Gemini or ChatGPT plan')
                self.provider = data['provider']
                self.auth.data['provider'] = self.provider
                self.auth.store.save(self.auth.data)
                return {'status': 'provider_updated'}
            if action == 'chatgpt_connect':
                if not callback_uri:
                    raise ValueError('ChatGPT sign-in requires a local browser callback')
                return self.auth.start(callback_uri, new_account=bool(data.get('new_account')))
            if action == 'chatgpt_models':
                return self.auth.load_models()
            if action == 'chatgpt_model':
                return self.auth.select_model(data.get('model'))
            if action == 'chatgpt_account':
                return self.auth.select_account(data.get('account'))
            if action == 'chatgpt_disconnect':
                return self.auth.disconnect()
            if action == 'chatgpt_welcome':
                self.auth.welcome = False
                return {'status': 'welcome_dismissed'}
            scenario = data.get('scenario') or None
            if scenario:
                with connect(self.path) as db:
                    if not db.execute('SELECT 1 FROM demo_accounting_events WHERE scenario_id=? AND invoice_id=?',
                                      (scenario, data.get('invoice_id'))).fetchone():
                        raise ValueError('Choose a simulation belonging to the selected invoice')
            if action == 'reset':
                result = load_demo(self.path, reset=True)
                self.now = Tools(self.path).now
                return result
            if action == 'clock':
                new_time = timestamp(data['now'])
                # Prevent inadvertent clock rewinds after state changes; reset starts over.
                from datetime import datetime
                if datetime.fromisoformat(new_time) < datetime.fromisoformat(self.now):
                    raise ValueError('Demo time can only move forward. Reset to return to the baseline.')
                with connect(self.path) as db, db:
                    db.execute("UPDATE metadata SET value=? WHERE key='demo_time'", (new_time,))
                self.now = new_time
                return {'status':'clock_updated', 'now':self.now}
            tools = Tools(self.path, self.now, scenario)
            workflow = Workflow(self.path, now=self.now, scenario_id=scenario)
            if action == 'process':
                # A saved completion can replay without credentials or a provider call.
                if workflow._stored('message_completed', data['message_id']) is None:
                    workflow.interpreter = self.interpreter_factory() if self.interpreter_factory else (
                        ChatGPTPlanInterpreter(self.auth) if self.provider == 'chatgpt_plan' else GeminiInterpreter())
                return workflow.process_message(data['message_id'])
            if action == 'add_reply':
                text = data.get('text', '').strip()
                if not text or len(text) > 12000:
                    raise ValueError('Enter a reply containing 1–12000 characters')
                with connect(self.path) as db, db:
                    invoice = row(db, 'invoices', 'invoice_id', data['invoice_id'])
                    message_id = 'MSG-UI-' + uuid4().hex
                    db.execute('INSERT INTO messages VALUES (?,?,?,?,?,?,?)',
                        (message_id,invoice['customer_id'],invoice['invoice_id'],'inbound',self.now,text,'pending'))
                return {'status':'reply_saved', 'message_id':message_id}
            if action == 'followups':
                return {'status':'followups_checked','results':workflow.run_due_followups(data['invoice_id'])}
            if action == 'verify':
                return tools.get_current_balance(data['invoice_id'])
            if action == 'prepare':
                return workflow.prepare_collection_message(data['invoice_id'])
            if action == 'approve':
                return tools.approve_draft(data['draft_id'],'DEMO-EMPLOYEE')
            if action == 'send':
                return tools.send_approved_message(data['draft_id'])
            raise ValueError('Unknown demo action')


def make_server(app, port=8765):
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass  # No request bodies, credentials, or customer text in terminal logs.

        def respond(self, code, payload, content_type='application/json; charset=utf-8'):
            body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type',content_type)
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")
            self.send_header('Content-Length',str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def valid_host(self):
            return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

        def do_GET(self):
            if not self.valid_host():
                self.respond(403, {'error':'Local demo access only'})
                return
            path = urlsplit(self.path).path
            if path == '/api/state':
                self.respond(200, app.snapshot())
            elif path == '/api/session':
                self.respond(200, {'token':token})
            elif path == '/api/chatgpt':
                self.respond(200, app.auth.status())
            elif path == '/auth/callback':
                try:
                    values = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                    if any(len(v) != 1 for v in values.values()):
                        raise ModelError('Invalid ChatGPT callback parameters.')
                    app.auth.callback({k: v[0] for k, v in values.items()})
                    message = 'ChatGPT account connected. Return to Mutabi to choose a model and analyze a reply.'
                except ModelError as error:
                    message = str(error)
                except Exception:
                    message = 'ChatGPT connection could not be completed. Return to Mutabi and reconnect.'
                page = ('<!doctype html><html lang="en"><meta charset="utf-8"><title>Mutabi — ChatGPT connection</title>'
                        '<link rel="stylesheet" href="/style.css"><main><h1>ChatGPT connection</h1><p>' + escape(message) +
                        '</p><p dir="rtl">ارجع إلى متابع للاطلاع على حالة الاتصال.</p><a href="/">Return to Mutabi / العودة إلى متابع</a></main></html>')
                self.respond(200, page.encode(), 'text/html; charset=utf-8')
            elif path in ('/','/app.js','/i18n.js','/style.css'):
                filename = {'/':'index.html','/app.js':'app.js','/i18n.js':'i18n.js','/style.css':'style.css'}[path]
                mime = {'/':'text/html','/app.js':'text/javascript','/i18n.js':'text/javascript','/style.css':'text/css'}[path]
                self.respond(200,(STATIC / filename).read_bytes(),mime + '; charset=utf-8')
            else:
                self.respond(404, {'error':'Not found'})

        def do_POST(self):
            origin = self.headers.get('Origin')
            allowed_origins = (f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}')
            if not self.valid_host() or self.headers.get('X-Demo-Token') != token or (origin and origin not in allowed_origins):
                self.respond(403, {'error':'Invalid local demo session'})
                return
            try:
                size = int(self.headers.get('Content-Length','0'))
                if size <= 0 or size > 64000:
                    raise ValueError('Invalid request size')
                body = json.loads(self.rfile.read(size))
                if not isinstance(body,dict):
                    raise ValueError('Request must be an object')
                path = urlsplit(self.path).path
                if not path.startswith('/api/action/'):
                    self.respond(404, {'error':'Not found'})
                    return
                self.respond(200, {'result':app.action(path.removeprefix('/api/action/'), body,
                    callback_uri=f'http://127.0.0.1:{self.server.server_port}/auth/callback')})
            except ModelError as error:
                self.respond(503, {'error':str(error), 'retry_after':error.retry_after})
            except (ValueError, KeyError, TypeError, sqlite3.IntegrityError) as error:
                self.respond(400, {'error':str(error)})
            except Exception:
                self.respond(500, {'error':'The action could not be completed. Refresh and review the saved history before retrying.'})

    return ThreadingHTTPServer(('127.0.0.1',port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--db',type=Path,default=DEFAULT_DB)
    args = parser.parse_args()
    load_local_env(ROOT / '.env')
    server = make_server(DemoApp(args.db),args.port)
    print(f'Mutabi demo: http://127.0.0.1:{server.server_port}',flush=True)
    print('Local synthetic workspace. Press Ctrl+C to stop.',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
