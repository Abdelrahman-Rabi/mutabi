"""Regressions for commitments, money conservation and reviewed corrections."""
import json
import tempfile
import unittest
from pathlib import Path

from mutabi.database import connect
from mutabi.demo import load_demo, minor
from mutabi.gemini import validate_evidence
from mutabi.tools import Tools
from mutabi.workflow import Workflow
from tests.test_workflow import ControlledInterpreter


class AdvancedCoreTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'workspace.db'
        load_demo(self.path)
        self.tools = Tools(self.path)

    def add_reply(self, message_id, invoice='INV-001'):
        with connect(self.path) as db, db:
            customer = db.execute('SELECT customer_id FROM invoices WHERE invoice_id=?', (invoice,)).fetchone()[0]
            db.execute('INSERT INTO messages VALUES (?,?,?,?,?,?,?)',
                       (message_id, customer, invoice, 'inbound', self.tools.now, 'Reviewed synthetic reply', 'pending'))

    def receipt(self, invoice='INV-001', outstanding=200000, amount=100000, reference='PAY-TEST', when='2026-10-06T10:00:00+03:00'):
        with connect(self.path) as db, db:
            db.execute('INSERT INTO demo_accounting_events VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                       ('ACC-TEST-' + reference, 'TEST', invoice, when, 'success', outstanding,
                        'SAR', amount, reference, 'LEDGER-' + reference, None))
        tools = Tools(self.path, now=when, scenario_id='TEST')
        tools.get_current_balance(invoice)
        return tools

    def test_installment_fulfilled_while_invoice_remains_open(self):
        promise = self.tools.record_payment_promise('MSG-001', 'INV-001', '1000', '2026-10-05')
        tools = self.receipt()
        workflow = Workflow(self.path, now=tools.now, scenario_id='TEST')
        result = workflow.run_due_followups('INV-001')
        self.assertEqual(result[0]['status'], 'fulfilled')
        context = tools.get_invoice_context('INV-001')
        self.assertEqual(context['invoice']['status'], 'open')
        self.assertEqual(context['invoice']['outstanding_minor'], 200000)
        self.assertEqual(context['promises'][0]['status'], 'fulfilled')
        self.assertEqual(context['drafts'], [])
        self.assertEqual(sum(a['amount_minor'] for a in context['promise_allocations']), 100000)
        self.assertEqual(workflow.run_due_followups('INV-001'), [])
        self.assertEqual(context['promises'][0]['promise_id'], promise['promise_id'])

    def test_allocations_require_verified_reference_and_conserve_shared_money(self):
        first = self.tools.record_payment_promise('MSG-001', 'INV-001', '600', '2026-10-05')
        self.add_reply('SECOND')
        second = self.tools.record_payment_promise('SECOND', 'INV-001', '600', '2026-10-05')
        with self.assertRaises(ValueError):
            self.tools.allocate_payment(first['promise_id'], 'UNVERIFIED', '600')
        tools = self.receipt()
        allocation = tools.allocate_payment(first['promise_id'], 'PAY-TEST', '600')
        self.assertEqual(allocation, tools.allocate_payment(first['promise_id'], 'PAY-TEST', '600'))
        for promise, amount in ((first, '500'), (second, '500')):
            with self.assertRaises(ValueError):
                tools.allocate_payment(promise['promise_id'], 'PAY-TEST', amount)
        tools.allocate_payment(second['promise_id'], 'PAY-TEST', '400')
        with connect(self.path) as db:
            self.assertEqual(db.execute('SELECT SUM(amount_minor) FROM promise_allocations').fetchone()[0], 100000)
        promises = tools.get_invoice_context('INV-001')['promises']
        self.assertEqual({p['status'] for p in promises}, {'fulfilled', 'partially_fulfilled'})

    def test_unallocated_shared_payment_requires_review(self):
        self.tools.record_payment_promise('MSG-001', 'INV-001', '600', '2026-10-05')
        self.add_reply('SECOND')
        self.tools.record_payment_promise('SECOND', 'INV-001', '600', '2026-10-05')
        tools = self.receipt()
        results = Workflow(self.path, now=tools.now, scenario_id='TEST').run_due_followups('INV-001')
        self.assertTrue(all(r['status'] == 'needs_payment_allocation' for r in results))
        self.assertEqual(tools.get_invoice_context('INV-001')['promise_allocations'], [])

    def test_payment_from_before_commitment_cannot_fulfill_it(self):
        self.receipt(when='2026-10-03T10:00:00+03:00')
        later = Tools(self.path, now='2026-10-03T11:00:00+03:00')
        promise = later.record_payment_promise('MSG-001', 'INV-001', '1000', '2026-10-05')
        with self.assertRaises(ValueError):
            later.allocate_payment(promise['promise_id'], 'PAY-TEST', '1000')

    def test_same_clock_receipts_keep_distinct_evidence_and_cannot_rewind(self):
        promise = self.tools.record_payment_promise('MSG-001', 'INV-001', '1000', '2026-10-05')
        self.tools.get_current_balance('INV-001')
        first = self.receipt(outstanding=260000, amount=40000, reference='FIRST', when=self.tools.now)
        first.allocate_payment(promise['promise_id'], 'FIRST', '400')
        with connect(self.path) as db, db:
            db.execute("UPDATE demo_accounting_events SET scenario_id='FIRST-SCENARIO' WHERE payment_reference='FIRST'")
        second = self.receipt(outstanding=200000, amount=60000, reference='SECOND', when=self.tools.now)
        second.allocate_payment(promise['promise_id'], 'SECOND', '600')
        context = second.get_invoice_context('INV-001')
        self.assertEqual(context['promises'][0]['status'], 'fulfilled')
        receipts = {json.loads(a['details_json']).get('payment_reference') for a in context['audit_events'] if a['action'] == 'balance_verified'}
        self.assertTrue({'FIRST', 'SECOND'}.issubset(receipts))
        older = Tools(self.path, self.tools.now, 'FIRST-SCENARIO')
        self.assertEqual(older.get_current_balance('INV-001')['outstanding_minor'], 200000)

    def test_amendment_supersedes_tasks_and_approval_without_losing_history(self):
        promise = self.tools.record_payment_promise('MSG-001', 'INV-001', '1000', '2026-10-05')
        draft = self.tools.draft_message('INV-001', 'Old commitment', 'OLD')
        self.tools.approve_draft(draft['draft_id'], 'EMPLOYEE')
        replacement = self.tools.amend_promise(promise['promise_id'], '800', '2026-10-07', 'Customer corrected date and amount', 'EMPLOYEE')
        self.assertEqual(replacement, self.tools.amend_promise(promise['promise_id'], '800', '2026-10-07', 'Customer corrected date and amount', 'EMPLOYEE'))
        context = self.tools.get_invoice_context('INV-001')
        self.assertEqual(len(context['promise_revisions']), 1)
        self.assertEqual(next(p for p in context['promises'] if p['promise_id'] == promise['promise_id'])['status'], 'superseded')
        self.assertEqual(next(t for t in context['tasks'] if t['promise_id'] == promise['promise_id'])['status'], 'closed')
        self.assertEqual(next(t for t in context['tasks'] if t['promise_id'] == replacement['promise_id'])['due_date'], '2026-10-08')
        self.assertEqual(context['drafts'][0]['status'], 'invalidated')
        self.assertEqual(context['invoice']['outstanding_minor'], 300000)
        with self.assertRaises(ValueError):
            self.tools.amend_promise(promise['promise_id'], '900', '2026-10-07', 'Different amendment', 'EMPLOYEE')

    def test_amendment_invalid_amount_rolls_back(self):
        promise = self.tools.record_payment_promise('MSG-001', 'INV-001', '1000', '2026-10-05')
        with self.assertRaises(ValueError):
            self.tools.amend_promise(promise['promise_id'], '9000', '2026-10-07', 'Reviewed', 'EMPLOYEE')
        self.assertEqual(self.tools.get_invoice_context('INV-001')['promises'], [promise])

    def test_manual_confirmation_completes_clarification_and_replays_reviewed_result(self):
        interpreter = ControlledInterpreter('incomplete_payment_promise', amount='1500')
        workflow = Workflow(self.path, interpreter)
        old = workflow.process_message('MSG-008')
        result = workflow.confirm_message('MSG-008', '1500', '2026-10-08', 'EMPLOYEE')
        self.assertEqual(result['status'], 'promise_recorded')
        self.assertTrue(workflow.process_message('MSG-008')['manual'])
        self.assertTrue(workflow.confirm_message('MSG-008', '1500', '2026-10-08', 'EMPLOYEE')['replayed'])
        self.assertEqual(interpreter.calls, 1)
        context = self.tools.get_invoice_context('INV-008')
        self.assertEqual(len(context['promises']), 1)
        self.assertEqual(next(d for d in context['drafts'] if d['draft_id'] == old['draft_id'])['status'], 'invalidated')
        with self.assertRaises(ValueError):
            workflow.confirm_message('MSG-008', '1400', '2026-10-08', 'EMPLOYEE')

    def test_manual_confirmation_rejects_wrong_replacement_atomically(self):
        promise = self.tools.record_payment_promise('MSG-001', 'INV-001', '1000', '2026-10-05')
        workflow = Workflow(self.path)
        with self.assertRaises(ValueError):
            workflow.confirm_message('MSG-008', '1500', '2026-10-08', 'EMPLOYEE', promise['promise_id'], 'Date correction')
        self.assertEqual(self.tools.get_invoice_context('INV-008')['promises'], [])

    def test_manual_confirmation_explicit_replacement_closes_old_commitment(self):
        promise = self.tools.record_payment_promise('MSG-001', 'INV-001', '1000', '2026-10-05')
        self.add_reply('NEW')
        result = Workflow(self.path).confirm_message('NEW', '1000', '2026-10-09', 'EMPLOYEE', promise['promise_id'], 'Customer requested reschedule')
        context = self.tools.get_invoice_context('INV-001')
        self.assertEqual(context['promise_revisions'][0]['new_promise_id'], result['promise_id'])
        self.assertEqual(len([t for t in context['tasks'] if t['status'] == 'pending']), 1)

    def test_edit_requires_reapproval_and_retains_old_audit_evidence(self):
        draft = self.tools.draft_message('INV-005', 'Old SAR 5000', 'EDIT')
        self.tools.approve_draft(draft['draft_id'], 'EMPLOYEE')
        tools = Tools(self.path, scenario_id='TC-05')
        tools.get_current_balance('INV-005')
        revised = tools.edit_draft(draft['draft_id'], 'Current SAR 3000', 'en', 'collection')
        self.assertIsNone(revised['approved_by'])
        self.assertEqual(tools.send_approved_message(draft['draft_id'])['reason'], 'APPROVAL_REQUIRED')
        tools.approve_draft(draft['draft_id'], 'EMPLOYEE')
        self.assertTrue(tools.send_approved_message(draft['draft_id'])['sent'])
        with self.assertRaises(ValueError):
            tools.edit_draft(draft['draft_id'], 'After delivery')
        audits = tools.get_invoice_context('INV-005')['audit_events']
        created = next(a for a in audits if a['action'] == 'draft_created')
        self.assertEqual(json.loads(created['details_json'])['balance_minor'], 500000)

    def test_repeated_draft_reviews_preserve_each_true_approval_and_rejection(self):
        draft = self.tools.draft_message('INV-001', 'First wording', 'REVIEW-HISTORY', purpose='verification', language='ar')
        self.tools.approve_draft(draft['draft_id'], 'FIRST-EMPLOYEE')
        self.tools.approve_draft(draft['draft_id'], 'FIRST-EMPLOYEE')  # Retry has no new transition.
        self.tools.edit_draft(draft['draft_id'], 'Second wording')
        self.tools.approve_draft(draft['draft_id'], 'SECOND-EMPLOYEE')
        self.tools.reject_draft(draft['draft_id'], 'Revise tone')
        self.tools.edit_draft(draft['draft_id'], 'Third wording')
        self.tools.reject_draft(draft['draft_id'], 'Correct date')
        context = self.tools.get_invoice_context('INV-001')
        approvals = [json.loads(a['details_json']) for a in context['audit_events'] if a['action'] == 'draft_approved']
        rejections = [json.loads(a['details_json']) for a in context['audit_events'] if a['action'] == 'draft_rejected']
        creation = next(json.loads(a['details_json']) for a in context['audit_events'] if a['action'] == 'draft_created')
        edits = [json.loads(a['details_json']) for a in context['audit_events'] if a['action'] == 'draft_edited']
        self.assertEqual([a['employee_id'] for a in approvals], ['FIRST-EMPLOYEE', 'SECOND-EMPLOYEE'])
        self.assertEqual([a['text'] for a in approvals], ['First wording', 'Second wording'])
        self.assertEqual([r['reason'] for r in rejections], ['Revise tone', 'Correct date'])
        self.assertEqual(creation['text'], 'First wording')
        self.assertEqual((creation['purpose'], creation['language']), ('verification', 'ar'))
        self.assertEqual(edits[0]['previous_text'], 'First wording')
        self.assertEqual(edits[0]['text'], 'Second wording')
        self.assertEqual(edits[0]['previous_status'], 'approved')
        self.assertEqual(edits[0]['previous_approved_by'], 'FIRST-EMPLOYEE')
        self.assertEqual(edits[0]['previous_approved_at'], self.tools.now)
        self.assertEqual((edits[0]['previous_purpose'], edits[0]['previous_language']), ('verification', 'ar'))
        self.assertEqual((edits[0]['purpose'], edits[0]['language']), ('collection', 'en'))

    def test_full_credit_cancels_unpaid_commitments_without_cash_allocations_and_can_resolve_dispute(self):
        from mutabi.product import initialize_product, product_action
        initialize_product(self.path)
        self.add_reply('FULL-CREDIT-DISPUTE')
        dispute = self.tools.record_dispute('FULL-CREDIT-DISPUTE', 'INV-001', 'Entire invoice was duplicated', '3000')
        product_action(self.path, self.tools.now, 'resolve_dispute',
                       {'dispute_id': dispute['dispute_id'], 'resolution': 'approved', 'reason': 'Confirmed duplicate', 'actor': 'finance_lina'})
        product_action(self.path, self.tools.now, 'simulate_credit',
                       {'invoice_id': 'INV-001', 'amount': '3000', 'reference': 'FULL-CREDIT', 'actor': 'finance_lina'})
        context = self.tools.get_invoice_context('INV-001')
        self.assertEqual(context['invoice']['status'], 'settled')
        self.assertTrue(context['promises'])
        self.assertTrue(all(p['status'] == 'cancelled' for p in context['promises']))
        self.assertEqual(context['promise_allocations'], [])
        self.assertFalse(any(t['status'] == 'pending' for t in context['tasks']))
        result = product_action(self.path, self.tools.now, 'resolve_dispute',
                                {'dispute_id': dispute['dispute_id'], 'resolution': 'adjusted', 'reason': 'Full credit verified', 'actor': 'finance_lina'})
        self.assertEqual(result['status'], 'resolved')

    def test_credit_settlement_preserves_already_cash_fulfilled_installment(self):
        first = self.tools.record_payment_promise('MSG-001', 'INV-001', '1000', '2026-10-05')
        tools = self.receipt()
        tools.allocate_payment(first['promise_id'], 'PAY-TEST', '1000')
        self.add_reply('UNPAID-REMAINDER')
        second = tools.record_payment_promise('UNPAID-REMAINDER', 'INV-001', '2000', '2026-10-07')
        with connect(self.path) as db, db:
            db.execute('INSERT INTO demo_accounting_events VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                       ('CREDIT-ACC', 'CREDIT-SCENARIO', 'INV-001', tools.now, 'success', 0, 'SAR', None, None, 'CREDIT-REMAINDER', None))
        credit_tools = Tools(self.path, tools.now, 'CREDIT-SCENARIO')
        credit_tools.get_current_balance('INV-001')
        context = credit_tools.get_invoice_context('INV-001')
        statuses = {p['promise_id']: p['status'] for p in context['promises']}
        self.assertEqual(statuses[first['promise_id']], 'fulfilled')
        self.assertEqual(statuses[second['promise_id']], 'cancelled')
        self.assertEqual(sum(a['amount_minor'] for a in context['promise_allocations']), 100000)

    def test_mixed_credit_and_cash_settlement_only_allocates_actual_cash(self):
        with connect(self.path) as db, db:
            db.execute("UPDATE invoices SET original_minor=100000,outstanding_minor=100000 WHERE invoice_id='INV-001'")
        promise = self.tools.record_payment_promise('MSG-001', 'INV-001', '1000', '2026-10-05')
        with connect(self.path) as db, db:
            db.execute('INSERT INTO demo_accounting_events VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                       ('CREDIT-HALF', 'HALF-CREDIT', 'INV-001', self.tools.now, 'success', 50000, 'SAR', None, None, 'CREDIT-HALF', None))
        Tools(self.path, self.tools.now, 'HALF-CREDIT').get_current_balance('INV-001')
        tools = self.receipt(outstanding=0, amount=50000, reference='CASH-HALF', when=self.tools.now)
        context = tools.get_invoice_context('INV-001')
        self.assertEqual(context['invoice']['status'], 'settled')
        self.assertEqual(context['promises'][0]['status'], 'cancelled')
        self.assertEqual(context['promises'][0]['promise_id'], promise['promise_id'])
        self.assertEqual(sum(a['amount_minor'] for a in context['promise_allocations']), 50000)
        self.assertEqual(len(context['promise_allocations']), 1)
        self.assertEqual(context['promise_allocations'][0]['payment_reference'], 'CASH-HALF')
        tools.get_current_balance('INV-001')
        self.assertEqual(sum(a['amount_minor'] for a in tools.get_invoice_context('INV-001')['promise_allocations']), 50000)

    def test_full_cash_settlement_does_not_reuse_cash_for_overlapping_commitments(self):
        with connect(self.path) as db, db:
            db.execute("UPDATE invoices SET original_minor=100000,outstanding_minor=100000 WHERE invoice_id='INV-001'")
        self.tools.record_payment_promise('MSG-001', 'INV-001', '600', '2026-10-05')
        self.add_reply('OVERLAPPING')
        self.tools.record_payment_promise('OVERLAPPING', 'INV-001', '600', '2026-10-05')
        tools = self.receipt(outstanding=0, amount=100000, reference='SHARED-CASH', when=self.tools.now)
        context = tools.get_invoice_context('INV-001')
        self.assertEqual(context['invoice']['status'], 'settled')
        self.assertEqual(context['promise_allocations'], [])
        self.assertTrue(all(p['status'] == 'cancelled' for p in context['promises']))
        settlement = next(json.loads(a['details_json']) for a in context['audit_events'] if a['action'] == 'invoice_settled')
        self.assertEqual(len(settlement['unallocated_commitment_ids']), 2)

    def test_verification_and_dispute_acknowledgments_can_be_sent_with_pending_reviews(self):
        workflow = Workflow(self.path, ControlledInterpreter('payment_claim'))
        result = workflow.process_message('MSG-003')
        self.tools.approve_draft(result['draft_id'], 'EMPLOYEE')
        self.assertTrue(self.tools.send_approved_message(result['draft_id'])['sent'])
        self.tools.record_dispute('MSG-007', 'INV-007', 'Missing credit note', '1000')
        draft = self.tools.draft_message('INV-007', 'Acknowledged for finance review', 'DISPUTE-ACK', purpose='dispute')
        self.tools.approve_draft(draft['draft_id'], 'EMPLOYEE')
        self.assertTrue(self.tools.send_approved_message(draft['draft_id'])['sent'])

    def test_administrative_drafts_still_obey_freshness_and_contact_interval(self):
        stale = self.tools.draft_message('INV-011', 'Reference request', 'STALE-ADMIN', purpose='verification')
        self.tools.approve_draft(stale['draft_id'], 'EMPLOYEE')
        self.assertEqual(self.tools.send_approved_message(stale['draft_id'])['reason'], 'STALE_BALANCE')
        for number in (1, 2):
            draft = self.tools.draft_message('INV-001', 'Please confirm reference', 'RATE-' + str(number), purpose='verification')
            self.tools.approve_draft(draft['draft_id'], 'EMPLOYEE')
            result = self.tools.send_approved_message(draft['draft_id'])
        self.assertEqual(result['reason'], 'CONTACT_INTERVAL')

    def test_rejected_draft_cannot_be_approved_or_sent(self):
        draft = self.tools.draft_message('INV-001', 'Reminder', 'REJECT')
        self.tools.reject_draft(draft['draft_id'], 'Needs a softer tone')
        with self.assertRaises(ValueError):
            self.tools.approve_draft(draft['draft_id'], 'EMPLOYEE')
        self.assertEqual(self.tools.send_approved_message(draft['draft_id'])['reason'], 'APPROVAL_REQUIRED')

    def test_invalid_money_and_conflicting_purpose_are_safe_validation_errors(self):
        for value in ('abc', '١٬٢٣٤', {'invalid': True}):
            with self.assertRaises(ValueError):
                minor(value)
        draft = self.tools.draft_message('INV-001', 'Verify transfer', 'PURPOSE', purpose='verification')
        with self.assertRaises(ValueError):
            self.tools.draft_message('INV-001', 'Verify transfer', 'PURPOSE', purpose='collection')

    def test_arabic_customer_draft_is_localized(self):
        with connect(self.path) as db, db:
            db.execute('CREATE TABLE customer_profiles(customer_id TEXT PRIMARY KEY,language TEXT)')
            db.execute("INSERT INTO customer_profiles VALUES ('C001','ar')")
        result = Workflow(self.path, ControlledInterpreter('payment_promise', amount='1000', payment_date='2026-10-05')).process_message('MSG-001')
        context = self.tools.get_invoice_context('INV-001')
        draft = next(d for d in context['drafts'] if d['draft_id'] == result['draft_id'])
        self.assertIn('سجلنا التزامك', draft['text'])
        self.assertEqual(context['draft_options'][0]['language'], 'ar')


class ArabicEvidenceTests(unittest.TestCase):
    def test_explicit_arabic_date_and_amount(self):
        text = 'سأسدد ١٬٥٠٠ ريال يوم ٥ أكتوبر ٢٠٢٦'
        decision = {'intent': 'payment_promise', 'amount': '1500', 'payment_date': '2026-10-05',
                    'amount_evidence': '١٬٥٠٠ ريال', 'date_evidence': 'يوم ٥ أكتوبر ٢٠٢٦', 'reason': 'Explicit', 'date_requires_confirmation': False}
        self.assertFalse(validate_evidence(decision, text)['date_requires_confirmation'])
        with self.assertRaises(ValueError):
            validate_evidence({**decision, 'payment_date': '2026-10-06'}, text)

    def test_arabic_iso_digits_and_ambiguous_date(self):
        base = {'intent': 'payment_promise', 'amount': '1500', 'payment_date': '2026-10-05',
                'amount_evidence': '١٥٠٠', 'date_evidence': '٢٠٢٦-١٠-٠٥', 'date_requires_confirmation': False}
        self.assertFalse(validate_evidence(base, '١٥٠٠ في ٢٠٢٦-١٠-٠٥')['date_requires_confirmation'])
        self.assertTrue(validate_evidence({**base, 'date_evidence': '٠٥/١٠/٢٠٢٦'}, '١٥٠٠ في ٠٥/١٠/٢٠٢٦')['date_requires_confirmation'])


if __name__ == '__main__':
    unittest.main()
