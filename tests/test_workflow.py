"""Approved scenarios with controlled interpretation, not live-model accuracy tests."""
import tempfile
import unittest
from pathlib import Path

from mutabi.database import connect
from mutabi.demo import load_demo
from mutabi.workflow import Workflow


class ControlledInterpreter:
    def __init__(self, intent, **fields):
        self.value = {'intent': intent, **fields}
        self.calls = 0

    def interpret(self, text, reference_date):
        self.calls += 1
        return dict(self.value)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'test.db'
        load_demo(self.path)

    def workflow(self, intent=None, scenario=None, now=None, **fields):
        interpreter = ControlledInterpreter(intent, **fields) if intent else None
        return Workflow(self.path, interpreter, now, scenario)

    def tc01(self):
        workflow = self.workflow('payment_promise', amount='3000.00', payment_date='2026-10-05')
        result = workflow.process_message('MSG-001')
        return workflow, result

    def test_TC01_clear_promise(self):
        workflow, result = self.tc01()
        self.assertEqual(result['status'], 'promise_recorded')
        self.assertTrue(workflow.process_message('MSG-001')['replayed'])
        self.assertEqual(workflow.interpreter.calls, 1)
        context = workflow.tools.get_invoice_context('INV-001')
        self.assertEqual(len(context['promises']), 1)
        self.assertEqual(context['promises'][0]['amount_minor'], 300000)
        self.assertEqual(context['tasks'][0]['due_date'], '2026-10-06')
        self.assertEqual(context['invoice']['outstanding_minor'], 300000)
        self.assertEqual(context['drafts'][0]['status'], 'awaiting_approval')

    def test_TC02_vague_promise(self):
        workflow = self.workflow('incomplete_payment_promise')
        result = workflow.process_message('MSG-002')
        self.assertEqual(result['clarify'], ['amount','payment_date'])
        context = workflow.tools.get_invoice_context('INV-002')
        self.assertEqual(context['promises'], [])
        self.assertEqual(context['tasks'][0]['task_id'], 'TASK-002')
        self.assertEqual(len(context['drafts']), 1)
        workflow.process_message('MSG-002')
        self.assertEqual(len(workflow.tools.get_invoice_context('INV-002')['drafts']), 1)

    def test_TC03_unverified_payment(self):
        workflow = self.workflow('payment_claim', scenario='TC-03')
        result = workflow.process_message('MSG-003')
        self.assertEqual(result['status'], 'awaiting_payment_verification')
        context = workflow.tools.get_invoice_context('INV-003')
        self.assertEqual(context['invoice']['outstanding_minor'], 200000)
        self.assertEqual(context['tasks'][0]['task_type'], 'payment_verification')

    def test_TC04_full_payment(self):
        workflow = self.workflow(scenario='TC-04')
        self.assertEqual(workflow.run_due_followups('INV-004')[0]['status'], 'settled')
        self.assertEqual(workflow.run_due_followups('INV-004'), [])
        context = workflow.tools.get_invoice_context('INV-004')
        self.assertEqual(context['promises'][0]['status'], 'fulfilled')
        self.assertEqual(context['tasks'][0]['status'], 'closed')
        self.assertEqual(context['drafts'][0]['status'], 'invalidated')

    def test_TC05_partial_payment(self):
        workflow = self.workflow(scenario='TC-05')
        self.assertEqual(workflow.run_due_followups('INV-005')[0]['status'], 'partially_fulfilled')
        self.assertEqual(workflow.run_due_followups('INV-005'), [])
        context = workflow.tools.get_invoice_context('INV-005')
        self.assertEqual(context['invoice']['outstanding_minor'], 300000)
        self.assertEqual(context['promises'][0]['status'], 'partially_fulfilled')
        self.assertIn('3,000.00', context['drafts'][0]['text'])
        self.assertEqual(len(context['promises']), 1)

    def test_TC06_missed_promise(self):
        workflow = self.workflow(scenario='TC-06')
        result = workflow.run_due_followups('INV-006')[0]
        self.assertEqual(result['status'], 'missed')
        self.assertEqual(workflow.run_due_followups('INV-006'), [])
        context = workflow.tools.get_invoice_context('INV-006')
        self.assertEqual(len([t for t in context['tasks'] if t['task_type']=='overdue_followup']), 1)
        self.assertNotIn('legal', context['drafts'][0]['text'].lower())

    def test_TC07_dispute(self):
        workflow = self.workflow('invoice_dispute', amount='1000.00', reason='Returned goods; missing credit note')
        self.assertEqual(workflow.process_message('MSG-007')['status'], 'dispute_pending_review')
        context = workflow.tools.get_invoice_context('INV-007')
        self.assertEqual(context['invoice']['outstanding_minor'], 400000)
        self.assertEqual(context['disputes'][0]['claimed_minor'], 100000)
        self.assertEqual(context['tasks'][0]['task_type'], 'finance_review')
        self.assertEqual(context['promises'], [])

    def test_TC08_relative_date(self):
        workflow = self.workflow('payment_promise', amount='1500.00', payment_date='2026-10-08', date_requires_confirmation=True)
        result = workflow.process_message('MSG-008')
        self.assertEqual(result['candidate_date'], '2026-10-08')
        self.assertEqual(result['status'], 'awaiting_clarification')
        self.assertEqual(workflow.tools.get_invoice_context('INV-008')['promises'], [])

    def test_TC09_missing_invoice(self):
        workflow = self.workflow('payment_promise', amount='2000.00', payment_date='2026-10-05')
        result = workflow.process_message('MSG-009')
        self.assertEqual(result['clarify'], ['invoice_reference'])
        self.assertIsNone(result['invoice_id'])
        for invoice in ('INV-009A','INV-009B'):
            self.assertEqual(workflow.tools.get_invoice_context(invoice)['promises'], [])

    def test_TC10_conditional_offer(self):
        workflow = self.workflow('conditional_offer', reason='Customer requests a 20% discount')
        result = workflow.process_message('MSG-010')
        self.assertEqual(result['status'], 'needs_human_review')
        context = workflow.tools.get_invoice_context('INV-010')
        self.assertEqual(context['invoice']['outstanding_minor'], 600000)
        self.assertEqual(context['promises'], [])
        self.assertEqual(context['tasks'][0]['task_type'], 'human_review')

    def test_TC11_failed_source(self):
        workflow = self.workflow(scenario='TC-11')
        result = workflow.prepare_collection_message('INV-011')
        self.assertEqual(result['status'], 'needs_data_review')
        self.assertEqual(result['verification']['error'], 'SOURCE_UNAVAILABLE')
        self.assertEqual(workflow.tools.get_invoice_context('INV-011')['drafts'], [])

    def test_TC12_untrusted_instructions(self):
        workflow = self.workflow('unsafe_instruction', reason='Requests unauthorized changes')
        self.assertEqual(workflow.process_message('MSG-012')['status'], 'needs_human_review')
        context = workflow.tools.get_invoice_context('INV-012')
        self.assertEqual(context['invoice']['outstanding_minor'], 350000)
        self.assertEqual(context['messages'][0]['message_id'], 'MSG-012')
        self.assertEqual(context['drafts'], [])

    def test_TC13_retries_and_approval(self):
        workflow = self.workflow('payment_promise', amount='3000.00', payment_date='2026-10-05')
        result = workflow.process_message('MSG-013')
        workflow.process_message('MSG-013')
        draft_id = result['draft_id']
        self.assertFalse(workflow.tools.send_approved_message(draft_id)['sent'])
        workflow.tools.approve_draft(draft_id, 'DEMO-EMPLOYEE')
        self.assertTrue(workflow.tools.send_approved_message(draft_id)['sent'])
        self.assertTrue(workflow.tools.send_approved_message(draft_id)['already_sent'])
        with connect(self.path) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM deliveries').fetchone()[0], 1)

    def test_TC14_stale_approved_draft(self):
        workflow = self.workflow(scenario='TC-14', now='2026-10-03T10:05:00+03:00')
        self.assertEqual(workflow.tools.send_approved_message('DRAFT-014')['reason'], 'INVOICE_SETTLED')
        self.assertEqual(workflow.tools.get_invoice_context('INV-014')['invoice']['outstanding_minor'], 0)

    def test_TC15_restart_and_advance_time(self):
        original, _ = self.tc01()
        workflow = self.workflow(scenario='TC-15', now='2026-10-06T10:00:00+03:00')
        self.assertEqual(workflow.run_due_followups('INV-001')[0]['status'], 'missed')
        restarted = self.workflow(scenario='TC-15', now='2026-10-06T10:00:00+03:00')
        self.assertEqual(restarted.run_due_followups('INV-001'), [])
        context = restarted.tools.get_invoice_context('INV-001')
        self.assertEqual(len(context['promises']), 1)
        self.assertEqual(len(context['drafts']), 2)
        self.assertEqual(context['messages'][0]['processing_status'], 'processed')
        self.assertTrue(context['audit_events'])

    def test_interpreter_failure_keeps_message_pending(self):
        workflow = self.workflow('unrecognized_intent')
        with self.assertRaises(ValueError):
            workflow.process_message('MSG-001')
        context = workflow.tools.get_invoice_context('INV-001')
        self.assertEqual(context['messages'][0]['processing_status'], 'pending')
        self.assertEqual(context['promises'], [])
        self.assertEqual(context['audit_events'], [])


if __name__ == '__main__':
    unittest.main()
