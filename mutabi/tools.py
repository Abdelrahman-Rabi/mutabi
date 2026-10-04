"""Persistent tools. Simulation routing is supplied by the host, not the model."""
import hashlib
import json
from datetime import date, datetime, timedelta
from uuid import uuid4

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
            result['draft_options'] = [dict(r) for r in db.execute(
                'SELECT o.* FROM draft_options o JOIN drafts d ON d.draft_id=o.draft_id WHERE d.invoice_id=?', (invoice_id,))]
            result['promise_allocations'] = [dict(r) for r in db.execute(
                'SELECT a.* FROM promise_allocations a JOIN promises p ON p.promise_id=a.promise_id WHERE p.invoice_id=?', (invoice_id,))]
            result['promise_revisions'] = [dict(r) for r in db.execute(
                'SELECT r.* FROM promise_revisions r JOIN promises p ON p.promise_id=r.old_promise_id WHERE p.invoice_id=?', (invoice_id,))]
            return result

    def invoice_language(self, invoice_id):
        with connect(self.path) as db:
            invoice = row(db, 'invoices', 'invoice_id', invoice_id)
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='customer_profiles' AND type='table'").fetchone():
                profile = db.execute('SELECT language FROM customer_profiles WHERE customer_id=?', (invoice['customer_id'],)).fetchone()
                if profile and profile[0] in ('ar', 'en'):
                    return profile[0]
        return 'en'

    def _revise(self, db, old, new, reason, actor):
        if not reason.strip() or not actor.strip():
            raise ValueError('Amendment requires a reason and employee identity')
        if old['invoice_id'] != new['invoice_id'] or old['status'] not in ('active', 'missed', 'partially_fulfilled'):
            raise ValueError('Only a current commitment on the same invoice can be amended')
        db.execute("UPDATE promises SET status='superseded' WHERE promise_id=?", (old['promise_id'],))
        db.execute("UPDATE tasks SET status='closed' WHERE promise_id=? AND status='pending'", (old['promise_id'],))
        db.execute("UPDATE drafts SET status='invalidated',approved_by=NULL,approved_at=NULL WHERE invoice_id=? AND status IN ('approved','awaiting_approval')", (old['invoice_id'],))
        db.execute('INSERT INTO promise_revisions VALUES (?,?,?,?,?)', (old['promise_id'], new['promise_id'], reason, actor, self.now))
        self._audit(db, old['invoice_id'], 'promise_amended', old['promise_id'],
                    {'old_promise_id': old['promise_id'], 'new_promise_id': new['promise_id'], 'reason': reason, 'actor': actor})

    def amend_promise(self, promise_id, amount, payment_date, reason, actor):
        """Replace a commitment explicitly, retaining its original evidence."""
        amount_minor = minor(amount)
        day(payment_date)
        if not amount_minor or date.fromisoformat(payment_date) < self.today or not reason.strip() or not actor.strip():
            raise ValueError('A positive amount, future date, reason and employee identity are required')
        with connect(self.path) as db, db:
            db.execute('BEGIN IMMEDIATE')
            old = row(db, 'promises', 'promise_id', promise_id)
            invoice = row(db, 'invoices', 'invoice_id', old['invoice_id'])
            revision = db.execute('SELECT * FROM promise_revisions WHERE old_promise_id=?', (promise_id,)).fetchone()
            if revision:
                new = row(db, 'promises', 'promise_id', revision['new_promise_id'])
                if new['amount_minor'] == amount_minor and new['promised_date'] == payment_date and revision['reason'] == reason and revision['actor'] == actor:
                    return new
                raise ValueError('This promise has already been amended; amend its current replacement')
            if old['status'] not in ('active', 'missed', 'partially_fulfilled') or invoice['status'] != 'open' or amount_minor > invoice['outstanding_minor']:
                raise ValueError('Amendment is not eligible for this commitment or invoice balance')
            message_id = stable_id('MSG', 'amend:' + promise_id)
            db.execute('INSERT INTO messages VALUES (?,?,?,?,?,?,?)',
                       (message_id, invoice['customer_id'], invoice['invoice_id'], 'internal', self.now,
                        f'Employee-reviewed amendment: {reason}', 'processed'))
            new_id = stable_id('PROM', message_id)
            db.execute('INSERT INTO promises VALUES (?,?,?,?,?,?,?,?)',
                       (new_id, old['invoice_id'], amount_minor, old['currency'], payment_date, 'active', self.now, message_id))
            new = row(db, 'promises', 'promise_id', new_id)
            self._revise(db, old, new, reason, actor)
            due = (date.fromisoformat(payment_date) + timedelta(days=self.policy['followup_days_after_promise'])).isoformat()
            self._task(db, old['invoice_id'], 'balance_check', due, new_id, 'promise:' + new_id)
            return new

    def _payment_evidence(self, db, invoice_id, payment_reference):
        evidence = []
        for event in db.execute("SELECT occurred_at,details_json FROM audit_events WHERE invoice_id=? AND action='balance_verified'", (invoice_id,)):
            details = json.loads(event['details_json'])
            if details.get('payment_reference') == payment_reference and details.get('payment_minor'):
                received = details.get('payment_received_at') or event['occurred_at']
                if datetime.fromisoformat(received) <= datetime.fromisoformat(self.now):
                    evidence.append({**details, 'received_at': received})
        if not evidence:
            raise ValueError('Payment reference requires verified accounting evidence for this invoice')
        if len({e['payment_minor'] for e in evidence}) != 1:
            raise ValueError('Conflicting amounts for the same payment reference require finance review')
        return evidence[0]

    def _allocate(self, db, promise_id, payment_reference, amount_minor):
        promise = row(db, 'promises', 'promise_id', promise_id)
        evidence = self._payment_evidence(db, promise['invoice_id'], payment_reference)
        existing = db.execute('SELECT * FROM promise_allocations WHERE promise_id=? AND payment_reference=?', (promise_id, payment_reference)).fetchone()
        if existing:
            if existing['amount_minor'] != amount_minor:
                raise ValueError('Conflicting payment allocation replay')
            return dict(existing)
        if promise['status'] not in ('active', 'missed', 'partially_fulfilled', 'fulfilled'):
            raise ValueError('Cannot allocate payment to a superseded commitment')
        if datetime.fromisoformat(evidence['received_at']) < datetime.fromisoformat(promise['recorded_at']):
            raise ValueError('Payment predates this commitment')
        spent = db.execute('SELECT COALESCE(SUM(amount_minor),0) FROM promise_allocations WHERE payment_reference=?', (payment_reference,)).fetchone()[0]
        covered = db.execute('SELECT COALESCE(SUM(amount_minor),0) FROM promise_allocations WHERE promise_id=?', (promise_id,)).fetchone()[0]
        if amount_minor <= 0 or spent + amount_minor > evidence['payment_minor'] or covered + amount_minor > promise['amount_minor']:
            raise ValueError('Allocation exceeds the verified payment or remaining commitment amount')
        allocation_id = stable_id('ALLOC', promise_id + ':' + payment_reference)
        db.execute('INSERT INTO promise_allocations VALUES (?,?,?,?,?)',
                   (allocation_id, promise_id, payment_reference, amount_minor, self.now))
        status = 'fulfilled' if covered + amount_minor == promise['amount_minor'] else 'partially_fulfilled'
        db.execute('UPDATE promises SET status=? WHERE promise_id=?', (status, promise_id))
        if status == 'fulfilled':
            db.execute("UPDATE tasks SET status='closed' WHERE promise_id=? AND status='pending'", (promise_id,))
            # Acknowledgments remain available; a missed-payment draft cannot
            # survive evidence that the relevant installment was fulfilled.
            draft = stable_id('DRAFT', 'followup:' + stable_id('TASK', 'promise:' + promise_id))
            db.execute("UPDATE drafts SET status='invalidated',approved_by=NULL,approved_at=NULL WHERE draft_id=? AND status IN ('approved','awaiting_approval')", (draft,))
        self._audit(db, promise['invoice_id'], 'payment_allocated', allocation_id,
                    {'promise_id': promise_id, 'payment_reference': payment_reference, 'amount_minor': amount_minor, 'promise_status': status})
        return row(db, 'promise_allocations', 'allocation_id', allocation_id)

    def allocate_payment(self, promise_id, payment_reference, amount):
        amount_minor = minor(amount)
        if not isinstance(payment_reference, str) or not payment_reference.strip() or not amount_minor:
            raise ValueError('Payment reference and positive amount are required')
        with connect(self.path) as db, db:
            db.execute('BEGIN IMMEDIATE')
            return self._allocate(db, promise_id, payment_reference, amount_minor)

    def reconcile_promise(self, promise_id):
        """Match verified receipts only when allocation has one eligible target.

        Shared payments with multiple current commitments require an employee's
        explicit allocation rather than guessing the intended installment.
        """
        with connect(self.path) as db, db:
            db.execute('BEGIN IMMEDIATE')
            return self._reconcile_promise(db, promise_id)

    def _reconcile_promise(self, db, promise_id):
        promise = row(db, 'promises', 'promise_id', promise_id)
        if promise['status'] in ('fulfilled', 'superseded', 'cancelled'):
            return {'promise': promise, 'allocation_review_required': False}
        references = set()
        for event in db.execute("SELECT details_json FROM audit_events WHERE invoice_id=? AND action='balance_verified'", (promise['invoice_id'],)):
            details = json.loads(event[0])
            if details.get('payment_reference') and details.get('payment_minor'):
                references.add(details['payment_reference'])
        review = False
        for reference in sorted(references):
            if db.execute('SELECT 1 FROM promise_allocations WHERE promise_id=? AND payment_reference=?', (promise_id, reference)).fetchone():
                continue
            evidence = self._payment_evidence(db, promise['invoice_id'], reference)
            if datetime.fromisoformat(evidence['received_at']) < datetime.fromisoformat(promise['recorded_at']):
                continue
            available = evidence['payment_minor'] - db.execute('SELECT COALESCE(SUM(amount_minor),0) FROM promise_allocations WHERE payment_reference=?', (reference,)).fetchone()[0]
            covered = db.execute('SELECT COALESCE(SUM(amount_minor),0) FROM promise_allocations WHERE promise_id=?', (promise_id,)).fetchone()[0]
            if available <= 0 or covered >= promise['amount_minor']:
                continue
            eligible = [r for r in db.execute("SELECT * FROM promises WHERE invoice_id=? AND status IN ('active','missed','partially_fulfilled')", (promise['invoice_id'],))
                        if datetime.fromisoformat(r['recorded_at']) <= datetime.fromisoformat(evidence['received_at'])]
            if len(eligible) != 1:
                review = True
                continue
            self._allocate(db, promise_id, reference, min(available, promise['amount_minor'] - covered))
        return {'promise': row(db, 'promises', 'promise_id', promise_id), 'allocation_review_required': review}

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
            candidates = db.execute('SELECT rowid AS accounting_order,* FROM demo_accounting_events WHERE invoice_id=? AND scenario_id=?',
                                    (invoice_id, self.scenario_id)).fetchall()
            available = [r for r in candidates if datetime.fromisoformat(r['available_at']) <= datetime.fromisoformat(self.now)]
            event = max(available, key=lambda r: (datetime.fromisoformat(r['available_at']), r['accounting_order'])) if available else None
        if event and event['result'] == 'error':
            self._audit(db, invoice_id, 'balance_verification_failed', event['event_id'], {'error': event['error_code']})
            return {'verified': False, 'error': event['error_code'], 'cached_minor': invoice['outstanding_minor']}
        if event:
            # Do not allow a simulator read to rewind a newer accounting snapshot.
            current_source = db.execute('SELECT rowid FROM demo_accounting_events WHERE invoice_id=? AND source_reference=? AND available_at=? ORDER BY rowid DESC LIMIT 1',
                                        (invoice_id, invoice['source_reference'], invoice['balance_updated_at'])).fetchone()
            later = datetime.fromisoformat(event['available_at']) > datetime.fromisoformat(invoice['balance_updated_at'])
            same_time_current_or_newer = (event['available_at'] == invoice['balance_updated_at'] and
                                         (not current_source or event['accounting_order'] >= current_source[0]))
            if later or same_time_current_or_newer:
                if event['currency'] != invoice['currency']:
                    raise ValueError('Accounting currency mismatch')
                db.execute('UPDATE invoices SET outstanding_minor=?,balance_updated_at=?,source_reference=? WHERE invoice_id=?',
                           (event['outstanding_minor'], event['available_at'], event['source_reference'], invoice_id))
                invoice = row(db, 'invoices', 'invoice_id', invoice_id)
        age = (datetime.fromisoformat(self.now) - datetime.fromisoformat(invoice['balance_updated_at'])).total_seconds() / 3600
        if age < 0 or age > self.policy['balance_freshness_hours']:
            self._audit(db, invoice_id, 'balance_verification_failed', invoice_id + ':' + self.now, {'error': 'STALE_BALANCE'})
            return {'verified': False, 'error': 'STALE_BALANCE', 'cached_minor': invoice['outstanding_minor']}
        current_event = event if event and event['available_at'] == invoice['balance_updated_at'] and event['source_reference'] == invoice['source_reference'] else None
        self._audit(db, invoice_id, 'balance_verified', invoice_id + ':' + invoice['balance_updated_at'] + ':' + invoice['source_reference'],
                    {'outstanding_minor': invoice['outstanding_minor'], 'source_reference': invoice['source_reference'],
                     'previous_balance_minor': previous_balance,
                     'payment_minor': current_event['payment_minor'] if current_event else None,
                     'payment_reference': current_event['payment_reference'] if current_event else None,
                     'payment_received_at': current_event['available_at'] if current_event else None})
        if invoice['outstanding_minor'] == 0:
            # Settlement can include credits and overlapping commitments. Only
            # verified, conserved cash allocations constitute fulfillment.
            live = [r['promise_id'] for r in db.execute("SELECT promise_id FROM promises WHERE invoice_id=? AND status IN ('active','missed','partially_fulfilled')", (invoice_id,))]
            reviews = []
            for promise_id in live:
                reconciled = self._reconcile_promise(db, promise_id)
                if reconciled['allocation_review_required']:
                    reviews.append(promise_id)
            db.execute("UPDATE promises SET status='cancelled' WHERE invoice_id=? AND status IN ('active','missed','partially_fulfilled')", (invoice_id,))
            db.execute("UPDATE invoices SET status='settled' WHERE invoice_id=?", (invoice_id,))
            db.execute("UPDATE tasks SET status='closed' WHERE invoice_id=? AND status='pending'", (invoice_id,))
            db.execute("UPDATE drafts SET status='invalidated' WHERE invoice_id=? AND status IN ('approved','awaiting_approval')", (invoice_id,))
            self._audit(db, invoice_id, 'invoice_settled', invoice_id + ':' + invoice['source_reference'],
                        {'source_reference': invoice['source_reference'], 'unallocated_commitment_ids': reviews,
                         'promise_closure_basis': 'verified_cash_allocations'})
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

    def draft_message(self, invoice_id, text, idempotency_key, purpose='collection', language='en'):
        if not text.strip():
            raise ValueError('Message text is required')
        if purpose not in ('collection', 'acknowledgment', 'verification', 'dispute') or language not in ('en', 'ar'):
            raise ValueError('Unsupported draft purpose or language')
        with connect(self.path) as db, db:
            invoice = row(db, 'invoices', 'invoice_id', invoice_id)
            draft_id = stable_id('DRAFT', idempotency_key)
            existing = db.execute('SELECT * FROM drafts WHERE draft_id=?', (draft_id,)).fetchone()
            if existing:
                if existing['invoice_id'] != invoice_id or existing['text'] != text:
                    raise ValueError('Conflicting draft replay')
                options = db.execute('SELECT purpose,language FROM draft_options WHERE draft_id=?', (draft_id,)).fetchone()
                if options and (options['purpose'], options['language']) != (purpose, language):
                    raise ValueError('Conflicting draft purpose or language replay')
                return dict(existing)
            db.execute('INSERT INTO drafts VALUES (?,?,?,?,?,?)', (draft_id, invoice_id, text, 'awaiting_approval', None, None))
            db.execute('INSERT INTO draft_options VALUES (?,?,?)', (draft_id, purpose, language))
            self._audit(db, invoice_id, 'draft_created', draft_id,
                        {'draft_id': draft_id, 'balance_minor': invoice['outstanding_minor'],
                         'text': text, 'purpose': purpose, 'language': language,
                         'status': 'awaiting_approval', 'approved_by': None, 'approved_at': None})
            return row(db, 'drafts', 'draft_id', draft_id)

    def edit_draft(self, draft_id, text, language='en', purpose='collection'):
        if not isinstance(text, str) or not text.strip() or len(text) > 12000:
            raise ValueError('Message text must contain 1–12000 characters')
        if language not in ('en', 'ar') or purpose not in ('collection', 'acknowledgment', 'verification', 'dispute'):
            raise ValueError('Unsupported draft purpose or language')
        with connect(self.path) as db, db:
            draft = row(db, 'drafts', 'draft_id', draft_id)
            if draft['status'] == 'sent':
                raise ValueError('Delivered messages cannot be edited')
            invoice = row(db, 'invoices', 'invoice_id', draft['invoice_id'])
            previous_options = db.execute('SELECT purpose,language FROM draft_options WHERE draft_id=?', (draft_id,)).fetchone()
            db.execute("UPDATE drafts SET text=?,status='awaiting_approval',approved_by=NULL,approved_at=NULL WHERE draft_id=?", (text.strip(), draft_id))
            db.execute('INSERT OR REPLACE INTO draft_options VALUES (?,?,?)', (draft_id, purpose, language))
            self._audit(db, draft['invoice_id'], 'draft_edited', draft_id + ':' + uuid4().hex,
                        {'draft_id': draft_id, 'text': text.strip(), 'purpose': purpose, 'language': language,
                         'balance_minor': invoice['outstanding_minor'], 'previous_text': draft['text'],
                         'previous_status': draft['status'], 'previous_approved_by': draft['approved_by'],
                         'previous_approved_at': draft['approved_at'],
                         'previous_purpose': previous_options['purpose'] if previous_options else 'collection',
                         'previous_language': previous_options['language'] if previous_options else 'en'})
            return row(db, 'drafts', 'draft_id', draft_id)

    def reject_draft(self, draft_id, reason):
        if not reason.strip():
            raise ValueError('Rejection reason is required')
        with connect(self.path) as db, db:
            draft = row(db, 'drafts', 'draft_id', draft_id)
            if draft['status'] == 'sent':
                raise ValueError('Delivered messages cannot be rejected')
            db.execute("UPDATE drafts SET status='rejected',approved_by=NULL,approved_at=NULL WHERE draft_id=?", (draft_id,))
            self._audit(db, draft['invoice_id'], 'draft_rejected', draft_id + ':' + uuid4().hex, {'draft_id': draft_id, 'reason': reason})
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
            options = db.execute('SELECT purpose,language FROM draft_options WHERE draft_id=?', (draft_id,)).fetchone()
            self._audit(db, draft['invoice_id'], 'draft_approved', draft_id + ':' + uuid4().hex,
                        {'draft_id': draft_id, 'employee_id': employee_id, 'text': draft['text'],
                         'purpose': options['purpose'] if options else 'collection',
                         'language': options['language'] if options else 'en'})
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
                options = db.execute('SELECT purpose FROM draft_options WHERE draft_id=?', (draft_id,)).fetchone()
                purpose = options[0] if options else 'collection'
                administrative = purpose in ('verification', 'dispute')
                before = row(db, 'invoices', 'invoice_id', draft['invoice_id'])
                snapshot = db.execute('SELECT details_json FROM audit_events WHERE event_id=?',
                                      (stable_id('AUD', 'draft_created:' + draft_id),)).fetchone()
                # Keep the creation evidence intact; an edited draft captures a
                # fresh balance and requires a new employee approval.
                for edit in db.execute("SELECT details_json FROM audit_events WHERE invoice_id=? AND action='draft_edited' ORDER BY rowid DESC", (draft['invoice_id'],)):
                    if json.loads(edit[0]).get('draft_id') == draft_id:
                        snapshot = edit
                        break
                drafted_balance = json.loads(snapshot[0])['balance_minor'] if snapshot else before['outstanding_minor']
                balance = self._verify(db, draft['invoice_id'])
                if not balance['verified']:
                    reason = balance['error']
                elif balance['outstanding_minor'] == 0:
                    reason = 'INVOICE_SETTLED'
                elif balance['outstanding_minor'] != drafted_balance:
                    db.execute("UPDATE drafts SET status='invalidated' WHERE draft_id=?", (draft_id,))
                    reason = 'BALANCE_CHANGED_REVIEW_REQUIRED'
                elif not administrative and db.execute("SELECT 1 FROM disputes WHERE invoice_id=? AND status IN ('pending_review','pending_credit')", (draft['invoice_id'],)).fetchone():
                    reason = 'DISPUTE_REVIEW_REQUIRED'
                elif not administrative and db.execute("SELECT 1 FROM tasks WHERE invoice_id=? AND task_type='payment_verification' AND status='pending'", (draft['invoice_id'],)).fetchone():
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
