import tempfile
import unittest
from pathlib import Path

from mutabi.database import connect
from mutabi.demo import load_demo
from mutabi.tools import Tools


class ToolTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'demo.db'
        load_demo(self.path)
        self.tools = Tools(self.path)

    def test_promise_atomic_and_idempotent(self):
        promise = self.tools.record_payment_promise('MSG-001','INV-001','3000.00','2026-10-05')
        self.assertEqual(promise, self.tools.record_payment_promise('MSG-001','INV-001','3000.00','2026-10-05'))
        context = Tools(self.path).get_invoice_context('INV-001')
        self.assertEqual(len(context['promises']), 1)
        self.assertEqual(context['tasks'][0]['due_date'], '2026-10-06')
        self.assertEqual(context['invoice']['outstanding_minor'], 300000)
        with self.assertRaises(ValueError):
            self.tools.record_payment_promise('MSG-001','INV-001','2500','2026-10-05')

    def test_reject_wrong_invoice_or_invalid_promise(self):
        for args in [('MSG-009','INV-009A','2000','2026-10-05'),
                     ('MSG-001','INV-001','4000','2026-10-05'),
                     ('MSG-001','INV-001','3000','2026-10-02')]:
            with self.assertRaises(ValueError):
                self.tools.record_payment_promise(*args)
        self.assertEqual(self.tools.get_invoice_context('INV-001')['promises'], [])

    def test_verified_payment_closes_and_invalidates(self):
        tools = Tools(self.path, scenario_id='TC-04')
        self.assertEqual(tools.get_current_balance('INV-004')['outstanding_minor'], 0)
        self.assertTrue(tools.get_current_balance('INV-004')['verified'])
        context = tools.get_invoice_context('INV-004')
        self.assertEqual(context['invoice']['status'], 'settled')
        self.assertEqual(context['promises'][0]['status'], 'fulfilled')
        self.assertEqual(context['tasks'][0]['status'], 'closed')
        self.assertEqual(context['drafts'][0]['status'], 'invalidated')

    def test_partial_payment_not_subtracted_twice(self):
        tools = Tools(self.path, scenario_id='TC-05')
        for _ in range(2):
            self.assertEqual(tools.get_current_balance('INV-005')['outstanding_minor'], 300000)

    def test_error_and_future_event_do_not_change_balance(self):
        tools = Tools(self.path, scenario_id='TC-11')
        self.assertEqual(tools.get_current_balance('INV-011')['error'], 'SOURCE_UNAVAILABLE')
        self.assertEqual(tools.get_invoice_context('INV-011')['invoice']['outstanding_minor'], 200000)
        tools = Tools(self.path, scenario_id='TC-14')
        self.assertEqual(tools.get_current_balance('INV-014')['outstanding_minor'], 200000)

    def test_dispute_preserves_balance_and_blocks_send(self):
        dispute = self.tools.record_dispute('MSG-007','INV-007','Missing credit note','1000')
        self.assertEqual(dispute, self.tools.record_dispute('MSG-007','INV-007','Missing credit note','1000'))
        draft = self.tools.draft_message('INV-007','Please pay SAR 4000.','dispute-draft')
        self.tools.approve_draft(draft['draft_id'],'DEMO-EMPLOYEE')
        self.assertEqual(self.tools.send_approved_message(draft['draft_id'])['reason'], 'DISPUTE_REVIEW_REQUIRED')
        self.assertEqual(self.tools.get_invoice_context('INV-007')['invoice']['outstanding_minor'],400000)

    def test_approval_and_single_delivery(self):
        draft = self.tools.draft_message('INV-001','Thank you for your promise.','ack-001')
        self.assertEqual(self.tools.send_approved_message(draft['draft_id'])['reason'],'APPROVAL_REQUIRED')
        self.tools.approve_draft(draft['draft_id'],'DEMO-EMPLOYEE')
        self.assertTrue(self.tools.send_approved_message(draft['draft_id'])['sent'])
        self.assertTrue(self.tools.send_approved_message(draft['draft_id'])['already_sent'])
        with connect(self.path) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM deliveries').fetchone()[0],1)

    def test_balance_change_invalidates_approved_draft(self):
        tools = Tools(self.path, now='2026-10-03T10:05:00+03:00', scenario_id='TC-14')
        self.assertEqual(tools.send_approved_message('DRAFT-014')['reason'],'INVOICE_SETTLED')
        self.assertEqual(tools.get_invoice_context('INV-014')['drafts'][0]['status'],'invalidated')

    def test_pending_verification_and_stale_data_block_send(self):
        self.tools.create_followup_task('INV-003','payment_verification','2026-10-03','verify-003')
        for invoice, reason in [('INV-003','PAYMENT_VERIFICATION_PENDING'),('INV-011','STALE_BALANCE')]:
            draft = self.tools.draft_message(invoice,'Reminder',invoice)
            self.tools.approve_draft(draft['draft_id'],'DEMO-EMPLOYEE')
            self.assertEqual(self.tools.send_approved_message(draft['draft_id'])['reason'],reason)

    def test_partial_update_before_send_still_invalidates_old_draft(self):
        draft = self.tools.draft_message('INV-005','Please pay SAR 5000.','old-balance')
        self.tools.approve_draft(draft['draft_id'],'DEMO-EMPLOYEE')
        tools = Tools(self.path, scenario_id='TC-05')
        tools.get_current_balance('INV-005')
        self.assertEqual(tools.send_approved_message(draft['draft_id'])['reason'], 'BALANCE_CHANGED_REVIEW_REQUIRED')

    def test_unlinked_message_context_and_human_review(self):
        context = self.tools.get_message_context('MSG-009')
        self.assertEqual(len(context['customer_invoices']), 2)
        self.assertIsNone(context['message']['invoice_id'])
        result = self.tools.request_human_review('MSG-009','Invoice reference is missing')
        self.assertTrue(result['review_required'])
        with connect(self.path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM audit_events WHERE action='human_review_requested'").fetchone()[0], 1)

if __name__ == '__main__':
    unittest.main()
