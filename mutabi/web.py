"""Local-only demo web server. Uses standard-library HTTP and persistent tools."""
import argparse
import csv
import io
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
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
from .product import DemoInterpreter, initialize_product, product_snapshot, product_action
from .imports import import_csv

STATIC = ROOT / 'mutabi' / 'static'


class DemoApp:
    def __init__(self, path=DEFAULT_DB, interpreter_factory=None):
        self.path = Path(path)
        self.interpreter_factory = interpreter_factory
        self.auth = ChatGPTAuth(self.path.parent / (self.path.stem + '-auth'))
        self.provider = 'demo'
        self.lock = threading.RLock()
        self.live_requests = []
        load_demo(self.path)
        self.now = Tools(self.path).now
        initialize_product(self.path, self.now)
        with connect(self.path) as db:
            saved = db.execute("SELECT value FROM workspace_settings WHERE key='provider'").fetchone()
            if saved:
                provider = json.loads(saved[0])
                if provider in ('demo', 'gemini', 'chatgpt_plan'):
                    self.provider = provider

    def snapshot(self):
        with self.lock, connect(self.path) as db:
            invoices = [dict(r) for r in db.execute(
                'SELECT i.*,c.name AS customer_name FROM invoices i JOIN customers c USING(customer_id) ORDER BY invoice_id')]
            tables = ('messages','promises','tasks','drafts','disputes','audit_events','deliveries')
            result = {name: [dict(r) for r in db.execute(f'SELECT * FROM {name}')] for name in tables}
            for name in ('draft_options', 'promise_allocations', 'promise_revisions'):
                result[name] = [dict(r) for r in db.execute(f'SELECT * FROM {name}')]
            chatgpt = self.auth.status()
            result.update(invoices=invoices, now=self.now, provider=self.provider, chatgpt=chatgpt,
                          model=('Recorded demo examples' if self.provider == 'demo' else (chatgpt['model'] or 'ChatGPT plan') if self.provider == 'chatgpt_plan' else os.environ.get('GEMINI_MODEL', DEFAULT_MODEL)),
                          model_ready=True if self.provider == 'demo' else chatgpt['ready'] if self.provider == 'chatgpt_plan' else bool(os.environ.get('GEMINI_API_KEY')),
                          accounting_scenarios=[dict(r) for r in db.execute(
                              'SELECT scenario_id,invoice_id,available_at,result,outstanding_minor FROM demo_accounting_events')])
            result.update(product_snapshot(self.path, self.now))
            return result

    def action(self, action, data, callback_uri=None):
        with self.lock:
            if action == 'provider':
                if data.get('provider') not in ('demo', 'gemini', 'chatgpt_plan'):
                    raise ValueError('Choose demo examples, Gemini or ChatGPT plan')
                self.provider = data['provider']
                with connect(self.path) as db, db:
                    db.execute("INSERT OR REPLACE INTO workspace_settings VALUES (?,?)", ('provider', json.dumps(self.provider)))
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
                initialize_product(self.path, self.now)
                self.provider = 'demo'
                with connect(self.path) as db, db:
                    db.execute('INSERT OR REPLACE INTO workspace_settings VALUES (?,?)', ('provider', json.dumps('demo')))
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
                if workflow._stored('message_completed', data['message_id']) is None and workflow._stored('message_manually_confirmed', data['message_id']) is None:
                    if self.provider != 'demo' and self.interpreter_factory is None:
                        current = time.monotonic()
                        self.live_requests = [stamp for stamp in self.live_requests if current - stamp < 60]
                        if len(self.live_requests) >= 8:
                            raise ModelError('This workspace has reached its live interpretation limit. Wait one minute before retrying.', retry_after=60)
                        self.live_requests.append(current)
                    workflow.interpreter = self.interpreter_factory() if self.interpreter_factory else (
                        DemoInterpreter() if self.provider == 'demo' else ChatGPTPlanInterpreter(self.auth) if self.provider == 'chatgpt_plan' else GeminiInterpreter())
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
                return tools.approve_draft(data['draft_id'], data.get('actor') or 'DEMO-EMPLOYEE')
            if action == 'send':
                return tools.send_approved_message(data['draft_id'])
            if action == 'confirm_message':
                return workflow.confirm_message(data['message_id'], data['amount'], data['payment_date'],
                    data.get('actor') or 'DEMO-EMPLOYEE', data.get('replace_promise_id'), data.get('reason', ''))
            if action == 'edit_draft':
                return tools.edit_draft(data['draft_id'], data['text'],
                    language=data.get('language', 'en'), purpose=data.get('purpose', 'collection'))
            if action == 'reject_draft':
                return tools.reject_draft(data['draft_id'], data.get('reason') or 'Rejected during employee review')
            if action == 'amend_promise':
                return tools.amend_promise(data['promise_id'], data['amount'], data['payment_date'],
                    data.get('reason') or 'Rescheduled during employee review', data.get('actor') or 'DEMO-EMPLOYEE')
            if action == 'allocate_payment':
                return tools.allocate_payment(data['promise_id'], data['payment_reference'], data['amount'])
            if action == 'import_csv':
                result = import_csv(self.path, self.now, data)
                if result['status'] == 'imported':
                    initialize_product(self.path, self.now)
                return result
            result = product_action(self.path, self.now, action, data)
            self.now = Tools(self.path).now
            return result


def make_server(app, port=8765):
    sessions = {}
    sessions_lock = threading.RLock()
    session_root = app.path.parent / (app.path.stem + '-sessions')

    class Handler(BaseHTTPRequestHandler):
        def workspace(self, create=True):
            """An opaque browser cookie owns one disposable SQLite workspace."""
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get('Cookie', ''))
            except Exception:
                cookie = SimpleCookie()
            session_id = cookie['mutabi_session'].value if 'mutabi_session' in cookie else None
            with sessions_lock:
                # API clients may use the per-workspace capability token instead
                # of cookies. Browser callers send both and must match both.
                supplied = self.headers.get('X-Demo-Token')
                if not session_id and supplied:
                    for key, value in sessions.items():
                        if secrets.compare_digest(supplied, value[1]):
                            session_id = key
                            break
                valid_id = bool(session_id and re.fullmatch(r'[0-9a-f]{48}', session_id))
                if valid_id and session_id not in sessions:
                    path = session_root / session_id / 'demo.db'
                    if path.is_file():
                        sessions[session_id] = (DemoApp(path, interpreter_factory=app.interpreter_factory), secrets.token_urlsafe(32))
                if not valid_id or session_id not in sessions:
                    if not create:
                        raise ValueError('Invalid demo session. Refresh the page.')
                    session_id = secrets.token_hex(24)
                    path = session_root / session_id / 'demo.db'
                    sessions[session_id] = (DemoApp(path, interpreter_factory=app.interpreter_factory), secrets.token_urlsafe(32))
                    self.session_cookie = f'mutabi_session={session_id}; HttpOnly; SameSite=Lax; Path=/; Max-Age=2592000'
                self.current_session = session_id
                return sessions[session_id]

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
            if getattr(self, 'session_cookie', None):
                self.send_header('Set-Cookie', self.session_cookie)
            if getattr(self, 'download_filename', None):
                self.send_header('Content-Disposition', f'attachment; filename="{self.download_filename}"')
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
                workspace, _ = self.workspace()
                self.respond(200, workspace.snapshot())
            elif path == '/api/session':
                _, token = self.workspace()
                self.respond(200, {'token':token})
            elif path == '/api/chatgpt':
                workspace, _ = self.workspace()
                self.respond(200, workspace.auth.status())
            elif path == '/api/export':
                workspace, _ = self.workspace()
                self.export(workspace)
            elif path == '/api/health':
                self.respond(200, {'status':'ok', 'product':'Mutabi discovery workspace'})
            elif path == '/auth/callback':
                try:
                    workspace, _ = self.workspace()
                    values = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                    if any(len(v) != 1 for v in values.values()):
                        raise ModelError('Invalid ChatGPT callback parameters.')
                    workspace.auth.callback({k: v[0] for k, v in values.items()})
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
                if path == '/':
                    self.workspace()
                filename = {'/':'index.html','/app.js':'app.js','/i18n.js':'i18n.js','/style.css':'style.css'}[path]
                mime = {'/':'text/html','/app.js':'text/javascript','/i18n.js':'text/javascript','/style.css':'text/css'}[path]
                self.respond(200,(STATIC / filename).read_bytes(),mime + '; charset=utf-8')
            else:
                self.respond(404, {'error':'Not found'})

        def export(self, workspace):
            query = parse_qs(urlsplit(self.path).query)
            format_name = query.get('format', ['json'])[0]
            dataset = query.get('dataset', ['feedback'])[0]
            state = workspace.snapshot()
            allowed = ('invoices','customers','profiles','messages','promises','tasks','drafts',
                       'disputes','deliveries','notes','assignments','reviews','feedback',
                       'research_events','draft_options','promise_allocations','promise_revisions','now','assumptions')
            if format_name == 'json':
                self.download_filename = 'mutabi-discovery-workspace.json'
                safe = {key:state[key] for key in allowed if key in state}
                safe['synthetic'] = True
                self.respond(200, json.dumps(safe, ensure_ascii=False, indent=2).encode('utf-8'))
            elif format_name == 'csv' and dataset in ('feedback','invoices','tasks'):
                rows = state.get(dataset, [])
                fields = list(rows[0]) if rows else {'feedback':['feedback_id','rating','category','text','role','created_at','view'],
                    'invoices':['invoice_id','customer_name','outstanding_minor','due_date'],
                    'tasks':['task_id','invoice_id','task_type','due_date','status']}[dataset]
                stream = io.StringIO(newline='')
                writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
                writer.writeheader()
                for item in rows:
                    cleaned = {}
                    for key, value in item.items():
                        value = '' if value is None else str(value)
                        if value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')):
                            value = "'" + value
                        cleaned[key] = value
                    writer.writerow(cleaned)
                self.download_filename = 'mutabi-' + dataset + '.csv'
                self.respond(200, ('\ufeff' + stream.getvalue()).encode('utf-8'), 'text/csv; charset=utf-8')
            else:
                self.respond(400, {'error':'Choose JSON or CSV (feedback, invoices, tasks).'})

        def do_POST(self):
            origin = self.headers.get('Origin')
            allowed_origins = (f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}')
            if not self.valid_host() or (origin and origin not in allowed_origins):
                self.respond(403, {'error':'Invalid local demo origin'})
                return
            try:
                workspace, token = self.workspace(create=False)
            except ValueError:
                self.respond(403, {'error':'Invalid demo session. Refresh the page.'})
                return
            if not secrets.compare_digest(self.headers.get('X-Demo-Token', ''), token):
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
                self.respond(200, {'result':workspace.action(path.removeprefix('/api/action/'), body,
                    callback_uri=f'http://{self.headers.get("Host")}/auth/callback')})
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
