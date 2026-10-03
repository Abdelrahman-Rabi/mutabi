"""Offline investigation probes; temporary synthetic databases, no model calls.

Run: python -m evaluation.discovery_audit
These observations expose product gaps, not provider classification accuracy.
"""
import json
import tempfile
from pathlib import Path

from mutabi.database import connect
from mutabi.demo import ROOT, load_demo
from mutabi.gemini import validate_evidence
from mutabi.tools import Tools
from mutabi.workflow import Workflow


class ControlledInterpreter:
    def __init__(self, intent, amount=None, payment_date=None, uncertain=False):
        self.decision = dict(intent=intent, amount=amount, payment_date=payment_date,
                             date_requires_confirmation=uncertain, reason='Controlled audit input')
        self.inputs = []

    def interpret(self, text, reference_date):
        self.inputs.append(dict(text=text, reference_date=reference_date))
        return dict(self.decision)


def add_reply(path, message_id, invoice_id, text):
    with connect(path) as db, db:
        customer = db.execute('SELECT customer_id FROM invoices WHERE invoice_id=?',
                              (invoice_id,)).fetchone()[0]
        db.execute('INSERT INTO messages VALUES (?,?,?,?,?,?,?)',
                   (message_id, customer, invoice_id, 'inbound',
                    '2026-10-03T10:00:00+03:00', text, 'pending'))


def main():
    observations = []
    with tempfile.TemporaryDirectory(prefix='mutabi-discovery-') as directory:
        path = Path(directory) / 'probe.db'
        load_demo(path)
        for message, invoice, intent in [('MSG-003', 'INV-003', 'payment_claim'),
                                         ('MSG-007', 'INV-007', 'invoice_dispute')]:
            workflow = Workflow(path, ControlledInterpreter(intent))
            result = workflow.process_message(message)
            workflow.tools.approve_draft(result['draft_id'], 'AUDIT-EMPLOYEE')
            send = workflow.tools.send_approved_message(result['draft_id'])
            observations.append(dict(probe=intent + '_response_blocked',
                                     workflow_status=result['status'], send=send))

        add_reply(path, 'AUDIT-PART', 'INV-001', 'I will pay SAR 1,000 on October 5, 2026.')
        Workflow(path, ControlledInterpreter('payment_promise', '1000', '2026-10-05')).process_message('AUDIT-PART')
        with connect(path) as db, db:
            db.execute("UPDATE demo_accounting_events SET outstanding_minor=200000, "
                       "payment_minor=100000, payment_reference='AUDIT-PAY' WHERE scenario_id='TC-15'")
        followups = Workflow(path, now='2026-10-06T10:05:00+03:00', scenario_id='TC-15').run_due_followups('INV-001')
        context = Tools(path).get_invoice_context('INV-001')
        observations.append(dict(probe='full_payment_of_partial_promise',
                                 promised_minor=100000, verified_payment_minor=100000,
                                 invoice_remaining_minor=200000,
                                 actual_status=followups[0]['status'],
                                 expected_status='fulfilled promise; invoice still open',
                                 actual_draft=context['drafts'][-1]['text']))

        add_reply(path, 'AUDIT-REVISED', 'INV-002', 'I will pay SAR 1,000 on October 5, 2026.')
        add_reply(path, 'AUDIT-REVISED-2', 'INV-002', 'Change that to SAR 1,000 on October 7, 2026.')
        for message, payment_date in [('AUDIT-REVISED', '2026-10-05'), ('AUDIT-REVISED-2', '2026-10-07')]:
            Workflow(path, ControlledInterpreter('payment_promise', '1000', payment_date)).process_message(message)
        promises = Tools(path).get_invoice_context('INV-002')['promises']
        observations.append(dict(probe='revised_promise_has_no_supersession',
                                 active_promises=[dict(date=p['promised_date'], amount_minor=p['amount_minor'])
                                                  for p in promises if p['status'] == 'active']))

        add_reply(path, 'AUDIT-CLARIFY', 'INV-008', 'I will pay SAR 1,000 tomorrow.')
        Workflow(path, ControlledInterpreter('payment_promise', '1000', '2026-10-04', True)).process_message('AUDIT-CLARIFY')
        add_reply(path, 'AUDIT-CONFIRM', 'INV-008', 'Yes, October 4, 2026.')
        interpreter = ControlledInterpreter('incomplete_payment_promise', payment_date='2026-10-04')
        result = Workflow(path, interpreter).process_message('AUDIT-CONFIRM')
        observations.append(dict(probe='clarification_has_no_prior_turn_context',
                                 interpreter_inputs=interpreter.inputs,
                                 actual_status=result['status'], still_missing=result['clarify']))

        text = 'سأدفع ٣٠٠٠ ريال بتاريخ ٥ أكتوبر ٢٠٢٦'
        validated = validate_evidence(dict(intent='payment_promise', amount='3000',
                                          payment_date='2026-10-05', date_requires_confirmation=False,
                                          reason='Explicit Arabic date', amount_evidence='٣٠٠٠',
                                          date_evidence='٥ أكتوبر ٢٠٢٦'), text)
        observations.append(dict(probe='explicit_arabic_date_forced_to_confirmation',
                                 validated_decision=validated))
    report = dict(date='2026-10-04', mode='offline controlled interpretations; temporary synthetic databases',
                  live_model_calls=0, observations=observations)
    output = ROOT / 'docs' / 'discovery_audit_evidence.json'
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2, ensure_ascii=True))
    print(f'Saved {output}')


if __name__ == '__main__':
    main()
