"""Guarded workflow orchestration; language interpretation is injected separately.

Stored decisions allow interrupted runs to resume without reinterpreting a message.
The workflow never reads test expectations or chooses a simulator scenario.
"""
import json
from datetime import date

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


class Workflow:
    def __init__(self, path, interpreter=None, now=None, scenario_id=None):
        self.tools = Tools(path, now, scenario_id)
        self.path = path
        self.interpreter = interpreter

    def _stored(self, action, key):
        with connect(self.path) as db:
            record = db.execute('SELECT details_json FROM audit_events WHERE event_id=?',
                                (stable_id('AUD', action + ':' + key),)).fetchone()
            return json.loads(record[0]) if record else None

    def _store(self, invoice_id, action, key, value):
        with connect(self.path) as db, db:
            self.tools._audit(db, invoice_id, action, key, value)

    def process_message(self, message_id):
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
                    text = f'Please confirm the payment amount and exact date for {invoice_id}.'
                    if result.get('candidate_date'):
                        text += f' Did you mean {result["candidate_date"]}?'
                else:
                    try:
                        promise = self.tools.record_payment_promise(message_id, invoice_id,
                            decision['amount'], decision['payment_date'])
                        result.update(status='promise_recorded', promise_id=promise['promise_id'])
                        text = (f'Thank you. We have recorded your commitment to pay {currency} '
                                f'{money(promise["amount_minor"])} for {invoice_id} on {promise["promised_date"]}.')
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
                    text = f'Thank you. Please provide the transfer reference for {invoice_id} so our finance team can verify it.'
            elif decision['intent'] == 'invoice_dispute':
                self.tools.record_dispute(message_id, invoice_id,
                    decision['reason'] or message['text'], decision['amount'])
                result['status'] = 'dispute_pending_review'
                text = f'We have recorded your concern about {invoice_id} for finance review.'
            else:
                result['status'] = 'needs_human_review'
                self.tools.request_human_review(message_id,
                    decision['reason'] or 'Reply requires employee review', invoice_id)
                if decision['intent'] == 'conditional_offer':
                    text = 'Your request has been referred for review. No discount or revised terms have been approved.'
            if text:
                result['draft_id'] = self.tools.draft_message(invoice_id, text, 'reply:' + message_id)['draft_id']
        # Effects use stable IDs. If completion is interrupted, the stored decision
        # is reused and tool calls safely resume before marking the message done.
        with connect(self.path) as db, db:
            self.tools._audit(db, invoice_id, 'message_completed', message_id, result)
            db.execute("UPDATE messages SET processing_status='processed' WHERE message_id=?", (message_id,))
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
            f'Please confirm the payment date for {invoice_id}; the outstanding balance is SAR {money(verification["outstanding_minor"])}.',
            'collection:' + invoice_id + ':' + self.tools.today.isoformat())}

    def run_due_followups(self, invoice_id=None):
        with connect(self.path) as db:
            tasks = [dict(r) for r in db.execute(
                "SELECT * FROM tasks WHERE status='pending' AND task_type='balance_check' AND due_date<=?",
                (self.tools.today.isoformat(),)) if invoice_id is None or r['invoice_id'] == invoice_id]
        results = []
        for task in tasks:
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
                context = self.tools.get_invoice_context(task['invoice_id'])
                blocked = bool([d for d in context['disputes'] if d['status'] == 'pending_review']) or any(
                    t['task_type'] == 'payment_verification' and t['status'] == 'pending' for t in context['tasks'])
                if blocked:
                    result['status'] = 'review_pending'
                    results.append(result)
                    continue
                status = 'partially_fulfilled' if remaining < saved['starting_balance_minor'] else 'missed'
                with connect(self.path) as db, db:
                    db.execute('UPDATE promises SET status=? WHERE promise_id=?', (status, task['promise_id']))
                result['status'] = status
                result['followup'] = self.tools.create_followup_task(task['invoice_id'], 'overdue_followup',
                    task['due_date'], 'missed:' + task['task_id'], task['promise_id'])
                promise = next(p for p in context['promises'] if p['promise_id'] == task['promise_id'])
                text = (f'The payment promised for {promise["promised_date"]} on {task["invoice_id"]} '
                        f'has not been fully received. The remaining balance is {context["invoice"]["currency"]} '
                        f'{money(remaining)}. Please confirm a payment date.')
                result['draft_id'] = self.tools.draft_message(task['invoice_id'], text, 'followup:' + task['task_id'])['draft_id']
            with connect(self.path) as db, db:
                db.execute("UPDATE tasks SET status='closed' WHERE task_id=?", (task['task_id'],))
                self.tools._audit(db, task['invoice_id'], 'followup_completed', task['task_id'], result)
            results.append(result)
        return results
