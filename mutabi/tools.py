"""Persistent tools. Simulation routing is supplied by the host, not the model."""
import hashlib
import json
from datetime import date, datetime, timedelta

from .database import connect
from .demo import day, minor, timestamp


def stable_id(kind, key):
    return kind + '-' + hashlib.sha256(key.encode()).hexdigest()[:24]


def row(db, table, key, value):
    result = db.execute(f'SELECT * FROM {table} WHERE {key}=?', (value,)).fetchone()
    if result is None:
        raise ValueError(f'Unknown {key}: {value}')
    return dict(result)


class Tools:
    def __init__(self, path, now=None, scenario_id=None):
        self.path = path
        self.scenario_id = scenario_id
        with connect(path) as db:
            self.policy = json.loads(row(db, 'metadata', 'key', 'policy')['value'])
            self.now = timestamp(now or row(db, 'metadata', 'key', 'demo_time')['value'])

    @property
    def today(self):
        # Demo policy uses a fixed UTC+03 offset; do not depend on host timezone.
        return datetime.fromisoformat(self.now).astimezone(
            datetime.fromisoformat(self.policy['reference_time']).tzinfo).date()

    def _audit(self, db, invoice_id, action, key, details):
        db.execute('INSERT OR IGNORE INTO audit_events VALUES (?,?,?,?,?)',
                   (stable_id('AUD', action + ':' + key), invoice_id, self.now,
                    action, json.dumps(details, ensure_ascii=False)))

    def get_collection_policy(self):
        return dict(self.policy)

    def get_message_context(self, message_id):
        with connect(self.path) as db:
            message = row(db, 'messages', 'message_id', message_id)
            invoices = [dict(r) for r in db.execute(
                'SELECT * FROM invoices WHERE customer_id=?', (message['customer_id'],))]
            return {'message': message, 'customer_invoices': invoices}

    def request_human_review(self, message_id, reason, invoice_id=None):
        if not reason.strip():
            raise ValueError('Review reason is required')
        with connect(self.path) as db, db:
            message = row(db, 'messages', 'message_id', message_id)
            if invoice_id:
                self._message(db, message_id, invoice_id)
                task = self._task(db, invoice_id, 'human_review', self.today.isoformat(),
                                  None, 'review:' + message_id)
            else:
                task = None
            self._audit(db, invoice_id, 'human_review_requested', message_id,
                        {'message_id': message_id, 'customer_id': message['customer_id'], 'reason': reason})
            return {'review_required': True, 'task': task}

    def get_invoice_context(self, invoice_id):
        with connect(self.path) as db:
            invoice = row(db, 'invoices', 'invoice_id', invoice_id)
            result = {'invoice': invoice,
                      'customer': row(db, 'customers', 'customer_id', invoice['customer_id'])}
            for table in ('messages', 'promises', 'tasks', 'drafts', 'disputes', 'audit_events'):
                result[table] = [dict(r) for r in db.execute(
                    f'SELECT * FROM {table} WHERE invoice_id=?', (invoice_id,))]
            return result

    def _message(self, db, message_id, invoice_id):
        message = row(db, 'messages', 'message_id', message_id)
        if message['invoice_id'] != invoice_id:
            raise ValueError('Message must be explicitly associated with this invoice')
        invoice = row(db, 'invoices', 'invoice_id', invoice_id)
        if invoice['customer_id'] != message['customer_id']:
            raise ValueError('Message customer does not match invoice')
        return message, invoice

    def record_payment_promise(self, message_id, invoice_id, amount, promised_date):
        amount_minor = minor(amount)
        day(promised_date)
        if amount_minor is None or amount_minor <= 0:
            raise ValueError('An explicit positive amount is required')
        if date.fromisoformat(promised_date) < self.today:
            raise ValueError('A new promise cannot use a past date')
        with connect(self.path) as db, db:
            message, invoice = self._message(db, message_id, invoice_id)
            existing = db.execute('SELECT * FROM promises WHERE source_message_id=?', (message_id,)).fetchone()
            if existing:
                if existing['amount_minor'] != amount_minor or existing['promised_date'] != promised_date:
                    raise ValueError('Replay conflicts with the recorded promise')
                return dict(existing)
            if invoice['status'] != 'open' or amount_minor > invoice['outstanding_minor']:
                raise ValueError('Promise is not eligible for this invoice balance or state')
            promise_id = stable_id('PROM', message_id)
            db.execute('INSERT INTO promises VALUES (?,?,?,?,?,?,?,?)',
                       (promise_id, invoice_id, amount_minor, invoice['currency'], promised_date,
                        'active', self.now, message_id))
            task_date = (date.fromisoformat(promised_date) + timedelta(
                days=self.policy['followup_days_after_promise'])).isoformat()
            self._task(db, invoice_id, 'balance_check', task_date, promise_id, 'promise:' + promise_id)
            self._audit(db, invoice_id, 'promise_recorded', message_id,
                        {'amount_minor': amount_minor, 'promised_date': promised_date,
                         'balance_at_promise_minor': invoice['outstanding_minor']})
            return row(db, 'promises', 'promise_id', promise_id)

    def _task(self, db, invoice_id, task_type, due_date, promise_id, key):
        day(due_date)
        task_id = stable_id('TASK', key)
        existing = db.execute('SELECT * FROM tasks WHERE task_id=?', (task_id,)).fetchone()
        if existing:
            if (existing['invoice_id'], existing['task_type'], existing['due_date'], existing['promise_id']) != (invoice_id, task_type, due_date, promise_id):
                raise ValueError('Conflicting task replay')
            return dict(existing)
        db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?)',
                   (task_id, invoice_id, promise_id, task_type, due_date, 'pending'))
        return row(db, 'tasks', 'task_id', task_id)

    def create_followup_task(self, invoice_id, task_type, due_date, idempotency_key, promise_id=None):
        if task_type not in ('balance_check', 'overdue_followup', 'payment_verification', 'finance_review', 'human_review'):
            raise ValueError('Unsupported task type')
        with connect(self.path) as db, db:
            invoice = row(db, 'invoices', 'invoice_id', invoice_id)
            if invoice['status'] == 'settled':
                raise ValueError('Cannot create collection tasks for settled invoices')
            if promise_id and row(db, 'promises', 'promise_id', promise_id)['invoice_id'] != invoice_id:
                raise ValueError('Promise belongs to another invoice')
            result = self._task(db, invoice_id, task_type, due_date, promise_id, idempotency_key)
            self._audit(db, invoice_id, 'task_created', idempotency_key, result)
            return result

    def _verify(self, db, invoice_id):
        invoice = row(db, 'invoices', 'invoice_id', invoice_id)
        previous_balance = invoice['outstanding_minor']
        event = None
        if self.scenario_id:
            candidates = db.execute('SELECT * FROM demo_accounting_events WHERE invoice_id=? AND scenario_id=?',
                                    (invoice_id, self.scenario_id)).fetchall()
            available = [r for r in candidates if datetime.fromisoformat(r['available_at']) <= datetime.fromisoformat(self.now)]
            event = max(available, key=lambda r: datetime.fromisoformat(r['available_at'])) if available else None
        if event and event['result'] == 'error':
            self._audit(db, invoice_id, 'balance_verification_failed', event['event_id'], {'error': event['error_code']})
            return {'verified': False, 'error': event['error_code'], 'cached_minor': invoice['outstanding_minor']}
        if event:
            # Do not allow a simulator read to rewind a newer accounting snapshot.
            if datetime.fromisoformat(event['available_at']) >= datetime.fromisoformat(invoice['balance_updated_at']):
                if event['currency'] != invoice['currency']:
                    raise ValueError('Accounting currency mismatch')
                db.execute('UPDATE invoices SET outstanding_minor=?,balance_updated_at=?,source_reference=? WHERE invoice_id=?',
                           (event['outstanding_minor'], event['available_at'], event['source_reference'], invoice_id))
                invoice = row(db, 'invoices', 'invoice_id', invoice_id)
        age = (datetime.fromisoformat(self.now) - datetime.fromisoformat(invoice['balance_updated_at'])).total_seconds() / 3600
        if age < 0 or age > self.policy['balance_freshness_hours']:
            self._audit(db, invoice_id, 'balance_verification_failed', invoice_id + ':' + self.now, {'error': 'STALE_BALANCE'})
            return {'verified': False, 'error': 'STALE_BALANCE', 'cached_minor': invoice['outstanding_minor']}
        if invoice['outstanding_minor'] == 0:
            db.execute("UPDATE invoices SET status='settled' WHERE invoice_id=?", (invoice_id,))
            db.execute("UPDATE promises SET status='fulfilled' WHERE invoice_id=? AND status IN ('active','missed','partially_fulfilled')", (invoice_id,))
            db.execute("UPDATE tasks SET status='closed' WHERE invoice_id=? AND status='pending'", (invoice_id,))
            db.execute("UPDATE drafts SET status='invalidated' WHERE invoice_id=? AND status IN ('approved','awaiting_approval')", (invoice_id,))
        self._audit(db, invoice_id, 'balance_verified', invoice_id + ':' + invoice['balance_updated_at'],
                    {'outstanding_minor': invoice['outstanding_minor'], 'source_reference': invoice['source_reference'],
                     'previous_balance_minor': previous_balance,
                     'payment_minor': event['payment_minor'] if event else None,
                     'payment_reference': event['payment_reference'] if event else None})
        return {'verified': True, 'outstanding_minor': invoice['outstanding_minor'],
                'source_reference': invoice['source_reference'], 'verified_at': self.now}

    def get_current_balance(self, invoice_id):
        with connect(self.path) as db, db:
            return self._verify(db, invoice_id)

    def record_dispute(self, message_id, invoice_id, reason, claimed_amount=None):
        if not reason.strip():
            raise ValueError('Dispute reason is required')
        amount_minor = minor(claimed_amount)
        with connect(self.path) as db, db:
            _, invoice = self._message(db, message_id, invoice_id)
            if amount_minor is not None and amount_minor > invoice['outstanding_minor']:
                raise ValueError('Disputed amount exceeds balance')
            dispute_id = stable_id('DISPUTE', message_id)
            existing = db.execute('SELECT * FROM disputes WHERE dispute_id=?', (dispute_id,)).fetchone()
            if existing:
                if existing['claimed_minor'] != amount_minor or existing['reason'] != reason:
                    raise ValueError('Conflicting dispute replay')
                return dict(existing)
            db.execute('INSERT INTO disputes VALUES (?,?,?,?,?,?,?)',
                       (dispute_id, invoice_id, message_id, amount_minor, reason, 'pending_review', self.now))
            self._task(db, invoice_id, 'finance_review', self.today.isoformat(), None, 'dispute:' + message_id)
            self._audit(db, invoice_id, 'dispute_recorded', message_id, {'reason': reason, 'claimed_minor': amount_minor})
            return row(db, 'disputes', 'dispute_id', dispute_id)

    def draft_message(self, invoice_id, text, idempotency_key):
        if not text.strip():
            raise ValueError('Message text is required')
        with connect(self.path) as db, db:
            invoice = row(db, 'invoices', 'invoice_id', invoice_id)
            draft_id = stable_id('DRAFT', idempotency_key)
            existing = db.execute('SELECT * FROM drafts WHERE draft_id=?', (draft_id,)).fetchone()
            if existing:
                if existing['invoice_id'] != invoice_id or existing['text'] != text:
                    raise ValueError('Conflicting draft replay')
                return dict(existing)
            db.execute('INSERT INTO drafts VALUES (?,?,?,?,?,?)', (draft_id, invoice_id, text, 'awaiting_approval', None, None))
            self._audit(db, invoice_id, 'draft_created', draft_id,
                        {'draft_id': draft_id, 'balance_minor': invoice['outstanding_minor']})
            return row(db, 'drafts', 'draft_id', draft_id)

    def approve_draft(self, draft_id, employee_id):
        # Host/UI-only method: do not expose this tool to the model.
        if not employee_id.strip():
            raise ValueError('Employee identity is required')
        with connect(self.path) as db, db:
            draft = row(db, 'drafts', 'draft_id', draft_id)
            if draft['status'] != 'awaiting_approval':
                if draft['status'] == 'approved':
                    return draft
                raise ValueError('Draft is no longer awaiting approval')
            db.execute("UPDATE drafts SET status='approved',approved_by=?,approved_at=? WHERE draft_id=?", (employee_id, self.now, draft_id))
            self._audit(db, draft['invoice_id'], 'draft_approved', draft_id, {'employee_id': employee_id})
            return row(db, 'drafts', 'draft_id', draft_id)

    def send_approved_message(self, draft_id):
        with connect(self.path) as db, db:
            # Serialize sends so two callers cannot deliver the same draft twice.
            db.execute('BEGIN IMMEDIATE')
            draft = row(db, 'drafts', 'draft_id', draft_id)
            delivered = db.execute('SELECT * FROM deliveries WHERE draft_id=?', (draft_id,)).fetchone()
            if delivered:
                return {'sent': True, 'already_sent': True, 'delivery': dict(delivered)}
            reason = None
            if draft['status'] != 'approved' or not draft['approved_by'] or not draft['approved_at']:
                reason = 'APPROVAL_REQUIRED'
            else:
                before = row(db, 'invoices', 'invoice_id', draft['invoice_id'])
                snapshot = db.execute('SELECT details_json FROM audit_events WHERE event_id=?',
                                      (stable_id('AUD', 'draft_created:' + draft_id),)).fetchone()
                drafted_balance = json.loads(snapshot[0])['balance_minor'] if snapshot else before['outstanding_minor']
                balance = self._verify(db, draft['invoice_id'])
                if not balance['verified']:
                    reason = balance['error']
                elif balance['outstanding_minor'] == 0:
                    reason = 'INVOICE_SETTLED'
                elif balance['outstanding_minor'] != drafted_balance:
                    db.execute("UPDATE drafts SET status='invalidated' WHERE draft_id=?", (draft_id,))
                    reason = 'BALANCE_CHANGED_REVIEW_REQUIRED'
                elif db.execute("SELECT 1 FROM disputes WHERE invoice_id=? AND status='pending_review'", (draft['invoice_id'],)).fetchone():
                    reason = 'DISPUTE_REVIEW_REQUIRED'
                elif db.execute("SELECT 1 FROM tasks WHERE invoice_id=? AND task_type='payment_verification' AND status='pending'", (draft['invoice_id'],)).fetchone():
                    reason = 'PAYMENT_VERIFICATION_PENDING'
                else:
                    recent = db.execute('SELECT d.delivered_at FROM deliveries d JOIN drafts f ON f.draft_id=d.draft_id WHERE f.invoice_id=?', (draft['invoice_id'],)).fetchall()
                    if any((datetime.fromisoformat(self.now) - datetime.fromisoformat(r[0])).total_seconds() < self.policy['minimum_contact_interval_hours'] * 3600 for r in recent):
                        reason = 'CONTACT_INTERVAL'
            if reason:
                self._audit(db, draft['invoice_id'], 'send_blocked', draft_id + ':' + self.now + ':' + reason, {'reason': reason})
                return {'sent': False, 'reason': reason}
            delivery_id = stable_id('DELIVERY', draft_id)
            db.execute('INSERT INTO deliveries VALUES (?,?,?,?)', (delivery_id, draft_id, self.now, 'simulated'))
            db.execute("UPDATE drafts SET status='sent' WHERE draft_id=?", (draft_id,))
            self._audit(db, draft['invoice_id'], 'simulated_delivery', draft_id, {'delivery_id': delivery_id})
            return {'sent': True, 'already_sent': False, 'delivery': row(db, 'deliveries', 'delivery_id', delivery_id)}
