"""Guarded workflow orchestration; language interpretation is injected separately.

Stored decisions allow interrupted runs to resume without reinterpreting a message.
The workflow never reads test expectations or chooses a simulator scenario.
"""
import json
from datetime import date, datetime, timedelta

from .database import connect
from .demo import day, minor
from .tools import Tools, row, stable_id

INTENTS = {'payment_promise', 'incomplete_payment_promise', 'payment_claim',
           'invoice_dispute', 'conditional_offer', 'unknown', 'unsafe_instruction'}


def validate_decision(value):
    if not isinstance(value, dict) or value.get('intent') not in INTENTS:
        raise ValueError('Interpreter returned an unsupported intent')
    result = {'intent': value['intent'], 'amount': value.get('amount'),
              'payment_date': value.get('payment_date'),
              'date_requires_confirmation': value.get('date_requires_confirmation', False),
              'reason': value.get('reason', '')}
    if not isinstance(result['reason'], str) or len(result['reason']) > 2000:
        raise ValueError('Invalid interpretation reason')
    if not isinstance(result['date_requires_confirmation'], bool):
        raise ValueError('Date uncertainty must be a boolean')
    if result['amount'] is not None:
        if not isinstance(result['amount'], str):
            raise ValueError('Amounts must be decimal strings')
        minor(result['amount'])
    if result['payment_date'] is not None:
        day(result['payment_date'])
    return result


def money(amount_minor):
    return f'{amount_minor // 100:,}.{amount_minor % 100:02d}'


TEMPLATES = {
    'clarify': ('Please confirm the payment amount and exact date for {invoice}.', 'يرجى تأكيد مبلغ السداد والتاريخ المحدد للفاتورة {invoice}.'),
    'candidate': (' Did you mean {date}?', ' هل تقصد {date}؟'),
    'promise': ('Thank you. We have recorded your commitment to pay {currency} {amount} for {invoice} on {date}.', 'شكرًا لك. سجلنا التزامك بسداد {amount} {currency} للفاتورة {invoice} بتاريخ {date}.'),
    'verification': ('Thank you. Please provide the transfer reference for {invoice} so our finance team can verify it.', 'شكرًا لك. يرجى تزويدنا بمرجع التحويل للفاتورة {invoice} ليتحقق منه الفريق المالي.'),
    'dispute': ('We have recorded your concern about {invoice} for finance review.', 'سجلنا ملاحظتك بشأن الفاتورة {invoice} للمراجعة لدى الفريق المالي.'),
    'conditional': ('Your request has been referred for review. No discount or revised terms have been approved.', 'أُحيل طلبك للمراجعة. لم يُعتمد أي خصم أو تعديل على شروط السداد.'),
    'collection': ('Please confirm the payment date for {invoice}; the outstanding balance is {currency} {amount}.', 'يرجى تأكيد تاريخ سداد الفاتورة {invoice}؛ الرصيد المستحق هو {amount} {currency}.'),
    'followup': ('The payment promised for {date} on {invoice} has not been fully received. The remaining balance is {currency} {amount}. Please confirm a payment date.', 'لم يُستلم كامل السداد الموعود بتاريخ {date} للفاتورة {invoice}. الرصيد المتبقي هو {amount} {currency}. يرجى تأكيد تاريخ السداد.'),
}


class Workflow:
    def __init__(self, path, interpreter=None, now=None, scenario_id=None):
        self.tools = Tools(path, now, scenario_id)
        self.path = path
        self.interpreter = interpreter

    def _text(self, invoice_id, template, **fields):
        return TEMPLATES[template][int(self.tools.invoice_language(invoice_id) == 'ar')].format(invoice=invoice_id, **fields)

    def _stored(self, action, key):
        with connect(self.path) as db:
            record = db.execute('SELECT details_json FROM audit_events WHERE event_id=?',
                                (stable_id('AUD', action + ':' + key),)).fetchone()
            return json.loads(record[0]) if record else None

    def _store(self, invoice_id, action, key, value):
        with connect(self.path) as db, db:
            self.tools._audit(db, invoice_id, action, key, value)

    def process_message(self, message_id):
        reviewed = self._stored('message_manually_confirmed', message_id)
        if reviewed:
            return {**reviewed, 'replayed': True}
        completed = self._stored('message_completed', message_id)
        if completed:
            return {**completed, 'replayed': True}
        context = self.tools.get_message_context(message_id)
        message = context['message']
        invoice_id = message['invoice_id']
        if message['processing_status'] == 'processed':
            return {'status': 'already_processed_history', 'message_id': message_id}
        decision = self._stored('message_interpreted', message_id)
        if decision is None:
            if self.interpreter is None:
                raise ValueError('A language interpreter is required for new replies')
            # Only the raw message and reference date are passed to the interpreter.
            # It cannot infer an invoice by matching amounts or modify accounting.
            decision = validate_decision(self.interpreter.interpret(message['text'], self.tools.today.isoformat()))
            metadata = getattr(self.interpreter, 'last_metadata', None)
            if metadata:
                self._store(invoice_id, 'interpretation_provider', message_id,
                            {key: metadata[key] for key in ('provider', 'model', 'usage') if key in metadata})
            self._store(invoice_id, 'message_interpreted', message_id, decision)
        result = {'message_id': message_id, 'invoice_id': invoice_id,
                  'intent': decision['intent'], 'status': 'awaiting_clarification',
                  'draft_id': None, 'clarify': []}
        if not invoice_id:
            result['clarify'] = ['invoice_reference']
            result['clarification_text'] = 'Which invoice does this payment concern?'
            self.tools.request_human_review(message_id, 'Invoice reference is missing')
        else:
            invoice = self.tools.get_invoice_context(invoice_id)['invoice']
            balance = invoice['outstanding_minor']
            currency = invoice['currency']
            text = None
            purpose = 'acknowledgment'
            if invoice['status'] == 'settled':
                result['status'] = 'settled'
            elif decision['intent'] in ('payment_promise', 'incomplete_payment_promise'):
                if decision['amount'] is None:
                    result['clarify'].append('amount')
                if decision['payment_date'] is None:
                    result['clarify'].append('payment_date')
                elif decision['date_requires_confirmation']:
                    result['clarify'].append('payment_date_confirmation')
                    result['candidate_date'] = decision['payment_date']
                elif date.fromisoformat(decision['payment_date']) < self.tools.today:
                    result['clarify'].append('future_payment_date')
                if decision['amount'] is not None and not (0 < minor(decision['amount']) <= balance):
                    result['clarify'].append('valid_payment_amount')
                if result['clarify']:
                    text = self._text(invoice_id, 'clarify')
                    if result.get('candidate_date'):
                        text += self._text(invoice_id, 'candidate', date=result['candidate_date'])
                else:
                    try:
                        promise = self.tools.record_payment_promise(message_id, invoice_id,
                            decision['amount'], decision['payment_date'])
                        result.update(status='promise_recorded', promise_id=promise['promise_id'])
                        text = self._text(invoice_id, 'promise', currency=currency, amount=money(promise['amount_minor']), date=promise['promised_date'])
                    except ValueError as error:
                        result['status'] = 'needs_human_review'
                        self.tools.request_human_review(message_id, str(error), invoice_id)
            elif decision['intent'] == 'payment_claim':
                verification = self.tools.get_current_balance(invoice_id)
                result['verification'] = verification
                if verification['verified'] and verification['outstanding_minor'] == 0:
                    result['status'] = 'settled'
                else:
                    result['status'] = 'awaiting_payment_verification'
                    self.tools.create_followup_task(invoice_id, 'payment_verification',
                        self.tools.today.isoformat(), 'verification:' + message_id)
                    text = self._text(invoice_id, 'verification')
                    purpose = 'verification'
            elif decision['intent'] == 'invoice_dispute':
                self.tools.record_dispute(message_id, invoice_id,
                    decision['reason'] or message['text'], decision['amount'])
                result['status'] = 'dispute_pending_review'
                text = self._text(invoice_id, 'dispute')
                purpose = 'dispute'
            else:
                result['status'] = 'needs_human_review'
                self.tools.request_human_review(message_id,
                    decision['reason'] or 'Reply requires employee review', invoice_id)
                if decision['intent'] == 'conditional_offer':
                    text = self._text(invoice_id, 'conditional')
            if text:
                result['draft_id'] = self.tools.draft_message(invoice_id, text, 'reply:' + message_id, purpose=purpose, language=self.tools.invoice_language(invoice_id))['draft_id']
        # Effects use stable IDs. If completion is interrupted, the stored decision
        # is reused and tool calls safely resume before marking the message done.
        with connect(self.path) as db, db:
            self.tools._audit(db, invoice_id, 'message_completed', message_id, result)
            db.execute("UPDATE messages SET processing_status='processed' WHERE message_id=?", (message_id,))
        return result

    def confirm_message(self, message_id, amount, payment_date, actor, replace_promise_id=None, reason=''):
        """A named employee confirms an exact commitment; no reinterpretation."""
        amount_minor = minor(amount)
        day(payment_date)
        if not amount_minor or date.fromisoformat(payment_date) < self.tools.today or not actor.strip():
            raise ValueError('Employee identity, positive amount and future date are required')
        if replace_promise_id and not reason.strip():
            raise ValueError('A reason is required when replacing a commitment')
        with connect(self.path) as db, db:
            db.execute('BEGIN IMMEDIATE')
            message = row(db, 'messages', 'message_id', message_id)
            if message['direction'] != 'inbound' or not message['invoice_id']:
                raise ValueError('Associate an inbound customer reply with an invoice before confirmation')
            _, invoice = self.tools._message(db, message_id, message['invoice_id'])
            existing = db.execute('SELECT * FROM promises WHERE source_message_id=?', (message_id,)).fetchone()
            if existing:
                if existing['amount_minor'] != amount_minor or existing['promised_date'] != payment_date:
                    raise ValueError('Confirmation conflicts with an existing commitment; use an explicit amendment')
                if replace_promise_id:
                    revision = db.execute('SELECT new_promise_id FROM promise_revisions WHERE old_promise_id=?', (replace_promise_id,)).fetchone()
                    if not revision or revision[0] != existing['promise_id']:
                        raise ValueError('Existing commitment does not match the requested replacement')
                promise = dict(existing)
                # Confirm replay must not apply a second revision or draft.
                saved = db.execute('SELECT details_json FROM audit_events WHERE event_id=?', (stable_id('AUD', 'message_manually_confirmed:' + message_id),)).fetchone()
                if saved:
                    return {**json.loads(saved[0]), 'replayed': True}
            else:
                if invoice['status'] != 'open' or amount_minor > invoice['outstanding_minor']:
                    raise ValueError('Commitment exceeds the open invoice balance')
                old = row(db, 'promises', 'promise_id', replace_promise_id) if replace_promise_id else None
                if old and (old['invoice_id'] != invoice['invoice_id'] or old['status'] not in ('active', 'missed', 'partially_fulfilled')):
                    raise ValueError('Replacement must be a current commitment on this invoice')
                promise_id = stable_id('PROM', message_id)
                db.execute('INSERT INTO promises VALUES (?,?,?,?,?,?,?,?)', (promise_id, invoice['invoice_id'], amount_minor,
                           invoice['currency'], payment_date, 'active', self.tools.now, message_id))
                promise = row(db, 'promises', 'promise_id', promise_id)
                if old:
                    self.tools._revise(db, old, promise, reason, actor)
                due = (date.fromisoformat(payment_date) + timedelta(days=self.tools.policy['followup_days_after_promise'])).isoformat()
                self.tools._task(db, invoice['invoice_id'], 'balance_check', due, promise_id, 'promise:' + promise_id)
                self.tools._audit(db, invoice['invoice_id'], 'promise_recorded', message_id,
                                  {'amount_minor': amount_minor, 'promised_date': payment_date, 'balance_at_promise_minor': invoice['outstanding_minor'], 'actor': actor, 'manual': True})
            db.execute("UPDATE messages SET processing_status='processed' WHERE message_id=?", (message_id,))
            db.execute("UPDATE tasks SET status='closed' WHERE task_id=? AND task_type='human_review'", (stable_id('TASK', 'review:' + message_id),))
            # Clarification drafts are no longer relevant after an employee's
            # exact confirmation. The replacement acknowledgment needs approval.
            previous_draft = stable_id('DRAFT', 'reply:' + message_id)
            db.execute("UPDATE drafts SET status='invalidated',approved_by=NULL,approved_at=NULL WHERE draft_id=? AND status IN ('approved','awaiting_approval')", (previous_draft,))
        draft = self.tools.draft_message(invoice['invoice_id'], self._text(invoice['invoice_id'], 'promise',
                                        currency=invoice['currency'], amount=money(amount_minor), date=payment_date),
                                        'confirmed:' + message_id, purpose='acknowledgment', language=self.tools.invoice_language(invoice['invoice_id']))
        result = {'status': 'promise_recorded', 'message_id': message_id, 'invoice_id': invoice['invoice_id'],
                  'promise_id': promise['promise_id'], 'draft_id': draft['draft_id'], 'actor': actor, 'reason': reason, 'manual': True}
        self._store(invoice['invoice_id'], 'message_manually_confirmed', message_id, result)
        return result

    def prepare_collection_message(self, invoice_id):
        verification = self.tools.get_current_balance(invoice_id)
        if not verification['verified']:
            self.tools.create_followup_task(invoice_id, 'human_review', self.tools.today.isoformat(),
                                            'data-review:' + invoice_id)
            return {'status': 'needs_data_review', 'verification': verification}
        if verification['outstanding_minor'] == 0:
            return {'status': 'settled'}
        return {'status': 'draft_ready', 'draft': self.tools.draft_message(invoice_id,
            self._text(invoice_id, 'collection', currency=self.tools.get_invoice_context(invoice_id)['invoice']['currency'], amount=money(verification['outstanding_minor'])),
            'collection:' + invoice_id + ':' + self.tools.today.isoformat(), language=self.tools.invoice_language(invoice_id))}

    def run_due_followups(self, invoice_id=None):
        with connect(self.path) as db:
            tasks = [dict(r) for r in db.execute(
                "SELECT * FROM tasks WHERE status='pending' AND task_type='balance_check' AND due_date<=?",
                (self.tools.today.isoformat(),)) if invoice_id is None or r['invoice_id'] == invoice_id]
        results = []
        for task in tasks:
            with connect(self.path) as db:
                current_promise = row(db, 'promises', 'promise_id', task['promise_id'])
            if current_promise['status'] == 'superseded':
                with connect(self.path) as db, db:
                    db.execute("UPDATE tasks SET status='closed' WHERE task_id=?", (task['task_id'],))
                continue
            saved = self._stored('followup_started', task['task_id'])
            if saved is None:
                context = self.tools.get_invoice_context(task['invoice_id'])
                saved = {'starting_balance_minor': context['invoice']['outstanding_minor']}
                # A reviewer may verify a payment before running the scheduled
                # check. Preserve payment evidence from that verification.
                for audit in context['audit_events']:
                    if audit['action'] == 'balance_verified':
                        details = json.loads(audit['details_json'])
                        if details.get('payment_reference') and details.get('source_reference') == context['invoice']['source_reference']:
                            saved['starting_balance_minor'] = max(saved['starting_balance_minor'],
                                details.get('previous_balance_minor', saved['starting_balance_minor']))
                self._store(task['invoice_id'], 'followup_started', task['task_id'], saved)
            verification = self.tools.get_current_balance(task['invoice_id'])
            result = {'task_id': task['task_id'], 'verification': verification}
            if not verification['verified']:
                result['status'] = 'needs_data_review'
                self.tools.create_followup_task(task['invoice_id'], 'human_review',
                    self.tools.today.isoformat(), 'followup-review:' + task['task_id'])
                results.append(result)
                continue  # Retain check for retry after the source recovers.
            remaining = verification['outstanding_minor']
            if remaining == 0:
                result['status'] = 'settled'
            else:
                reconciled = self.tools.reconcile_promise(task['promise_id'])
                if reconciled['promise']['status'] == 'fulfilled':
                    result['status'] = 'fulfilled'
                    with connect(self.path) as db, db:
                        db.execute("UPDATE tasks SET status='closed' WHERE task_id=?", (task['task_id'],))
                        self.tools._audit(db, task['invoice_id'], 'followup_completed', task['task_id'], result)
                    results.append(result)
                    continue
                if reconciled['allocation_review_required']:
                    result['status'] = 'needs_payment_allocation'
                    self.tools.create_followup_task(task['invoice_id'], 'payment_verification', self.tools.today.isoformat(), 'allocation-review:' + task['task_id'])
                    results.append(result)
                    continue
                context = self.tools.get_invoice_context(task['invoice_id'])
                blocked = bool([d for d in context['disputes'] if d['status'] in ('pending_review', 'pending_credit')]) or any(
                    t['task_type'] == 'payment_verification' and t['status'] == 'pending' for t in context['tasks'])
                if blocked:
                    result['status'] = 'review_pending'
                    results.append(result)
                    continue
                allocated = sum(a['amount_minor'] for a in context['promise_allocations'] if a['promise_id'] == task['promise_id'])
                status = 'partially_fulfilled' if allocated > 0 else 'missed'
                with connect(self.path) as db, db:
                    db.execute('UPDATE promises SET status=? WHERE promise_id=?', (status, task['promise_id']))
                result['status'] = status
                result['followup'] = self.tools.create_followup_task(task['invoice_id'], 'overdue_followup',
                    task['due_date'], 'missed:' + task['task_id'], task['promise_id'])
                promise = next(p for p in context['promises'] if p['promise_id'] == task['promise_id'])
                text = self._text(task['invoice_id'], 'followup', date=promise['promised_date'], currency=context['invoice']['currency'], amount=money(remaining))
                result['draft_id'] = self.tools.draft_message(task['invoice_id'], text, 'followup:' + task['task_id'], language=self.tools.invoice_language(task['invoice_id']))['draft_id']
            with connect(self.path) as db, db:
                db.execute("UPDATE tasks SET status='closed' WHERE task_id=?", (task['task_id'],))
                self.tools._audit(db, task['invoice_id'], 'followup_completed', task['task_id'], result)
            results.append(result)
        return results
