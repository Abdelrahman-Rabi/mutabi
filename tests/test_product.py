import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from mutabi.database import connect, counts
from mutabi.demo import load_demo
from mutabi.product import DemoInterpreter, initialize_product, product_action, product_snapshot
from mutabi.tools import Tools
from mutabi.workflow import Workflow


class ProductTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'product.db'
        initialize_product(self.path)
        self.now = Tools(self.path).now

    def action(self, action, **data):
        return product_action(self.path, self.now, action, data)

    def test_initializer_is_idempotent_and_preserves_participant_work(self):
        self.action('add_note', invoice_id='INV-001', text='Call the finance contact', actor='collector_sara')
        with connect(self.path) as db:
            before = counts(db)
            fingerprint = db.execute("SELECT value FROM metadata WHERE key='source_fingerprint'").fetchone()[0]
        initialize_product(self.path)
        with connect(self.path) as db:
            self.assertEqual(before, counts(db))
            self.assertEqual(fingerprint, db.execute("SELECT value FROM metadata WHERE key='source_fingerprint'").fetchone()[0])
        snapshot = product_snapshot(self.path)
        self.assertEqual(len(snapshot['notes']), 1)
        self.assertEqual(len(snapshot['profiles']), 13)
        self.assertIn('awaiting_clarification', {r['status'] for r in snapshot['reviews']})

    def test_demo_interpreter_requires_exact_script_and_never_infers_free_text(self):
        interpreter = DemoInterpreter()
        known = interpreter.interpret('سأدفع ١٠٠٠ ريال بتاريخ ٥ أكتوبر ٢٠٢٦.', '2026-10-03')
        self.assertEqual((known['amount'], known['payment_date']), ('1000.00', '2026-10-05'))
        unknown = interpreter.interpret('Actually I will pay 1200 tomorrow instead', '2026-10-03')
        self.assertEqual(unknown['intent'], 'unknown')
        self.assertIsNone(unknown['amount'])
        self.assertIsNone(unknown['payment_date'])
        with self.assertRaises(ValueError):
            interpreter.interpret('', '2026-10-03')

    def test_settings_change_policy_and_reject_invalid_updates_atomically(self):
        self.action('settings', settings={'language': 'ar', 'followup_days_after_promise': 3})
        self.assertEqual(Tools(self.path).policy['followup_days_after_promise'], 3)
        with self.assertRaises(ValueError):
            self.action('settings', settings={'language': 'en', 'balance_freshness_hours': -2})
        self.assertEqual(product_snapshot(self.path)['settings']['language'], 'ar')
        self.action('story', story_id='promise')
        self.assertEqual(Tools(self.path).policy['followup_days_after_promise'], 3)
        promise = Tools(self.path).get_invoice_context('INV-001')['promises'][0]
        tasks = Tools(self.path).get_invoice_context('INV-001')['tasks']
        self.assertEqual(next(t['due_date'] for t in tasks if t['promise_id'] == promise['promise_id']), '2026-10-08')

    def test_customer_language_and_owner_update_persist_and_drive_templates(self):
        self.action('update_customer', customer_id='C002', language='ar', owner='collector_omar', priority='high')
        self.assertEqual(Tools(self.path).invoice_language('INV-002'), 'ar')
        draft = Workflow(self.path, now=self.now).prepare_collection_message('INV-002')['draft']
        self.assertIn('يرجى', draft['text'])
        self.assertIn('4,500.00', draft['text'])
        initialize_product(self.path)
        profile = next(p for p in product_snapshot(self.path)['profiles'] if p['customer_id'] == 'C002')
        self.assertEqual((profile['owner'], profile['priority'], profile['language']), ('collector_omar', 'high', 'ar'))
        with self.assertRaises(ValueError):
            self.action('update_customer', customer_id='C002', language='de', owner='finance_lina')
        self.assertEqual(Tools(self.path).invoice_language('INV-002'), 'ar')

    def test_feedback_and_research_survive_story_reset_while_notes_are_disposable(self):
        self.action('feedback', rating=4, category='workflow', text='Need grouped approvals', role='finance', view='approvals')
        self.action('event', event='view_opened', view='overview', details={'token': 'secret', 'nested': {'api_key': 'secret', 'task_id': 'demo'}})
        self.action('add_note', invoice_id='INV-001', text='Disposable story note', actor='collector_sara')
        result = self.action('story', story_id='payment')
        self.assertEqual(result['invoice_id'], 'INV-003')
        snapshot = product_snapshot(self.path)
        self.assertEqual(len(snapshot['feedback']), 1)
        self.assertEqual(len(snapshot['notes']), 0)
        self.assertGreaterEqual(len(snapshot['research_events']), 3)
        details = next(json.loads(r['details_json']) for r in snapshot['research_events'] if r['event'] == 'view_opened')
        self.assertEqual(details, {'nested': {'task_id': 'demo'}})

    def test_research_and_feedback_use_real_time_independent_of_simulated_business_clock(self):
        before = datetime.now(timezone.utc)
        future_business_time = '2099-10-03T10:00:00+03:00'
        product_action(self.path, future_business_time, 'feedback', {'rating': 4, 'text': 'Actual session observation'})
        product_action(self.path, future_business_time, 'event', {'event': 'task_attempted', 'view': 'tasks'})
        after = datetime.now(timezone.utc)
        snapshot = product_snapshot(self.path)
        timestamps = [snapshot['feedback'][0]['created_at'], *(r['created_at'] for r in snapshot['research_events'])]
        for value in timestamps:
            observed = datetime.fromisoformat(value)
            self.assertIsNotNone(observed.tzinfo)
            self.assertLessEqual(before, observed)
            self.assertLessEqual(observed, after)
            self.assertNotEqual(value, future_business_time)

    def test_direct_loader_reset_clears_foreign_keys_but_preserves_feedback(self):
        self.action('feedback', rating=3, text='A useful test')
        self.action('add_note', invoice_id='INV-001', text='Reset me', actor='collector_sara')
        load_demo(self.path, reset=True)
        initialize_product(self.path)
        self.assertEqual(len(product_snapshot(self.path)['feedback']), 1)
        with connect(self.path) as db:
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_installment_is_fulfilled_while_invoice_remains_open_and_payment_is_idempotent(self):
        self.action('story', story_id='installment')
        context = Tools(self.path).get_invoice_context('INV-001')
        promise = next(p for p in context['promises'] if p['status'] == 'active')
        self.assertEqual(promise['amount_minor'], 100000)
        # The story replaces the baseline obligation. Its old acknowledgment
        # cannot remain an actionable draft describing an obsolete commitment.
        actionable = [d for d in context['drafts'] if d['status'] == 'awaiting_approval']
        self.assertEqual(len(actionable), 1)
        self.assertIn('1,000.00', actionable[0]['text'])
        data = {'invoice_id': 'INV-001', 'amount': '1000', 'reference': 'TEST-INSTALLMENT', 'promise_id': promise['promise_id']}
        first = self.action('simulate_payment', **data)
        second = self.action('simulate_payment', **data)
        self.assertTrue(first['simulated'])
        self.assertEqual(second['status'], 'already_recorded')
        context = Tools(self.path).get_invoice_context('INV-001')
        self.assertEqual(context['invoice']['outstanding_minor'], 200000)
        self.assertEqual(context['invoice']['status'], 'open')
        self.assertEqual(next(p for p in context['promises'] if p['promise_id'] == promise['promise_id'])['status'], 'fulfilled')
        self.assertEqual(len(context['promise_allocations']), 1)

    def test_invalid_payment_allocation_does_not_post_a_partial_action(self):
        self.action('story', story_id='installment')
        promise = next(p for p in Tools(self.path).get_invoice_context('INV-001')['promises'] if p['status'] == 'active')
        with self.assertRaises(ValueError):
            self.action('simulate_payment', invoice_id='INV-001', amount='1200', reference='BAD-ALLOC', promise_id=promise['promise_id'])
        self.assertEqual(Tools(self.path).get_invoice_context('INV-001')['invoice']['outstanding_minor'], 300000)
        with connect(self.path) as db:
            self.assertIsNone(db.execute("SELECT 1 FROM demo_accounting_events WHERE payment_reference='BAD-ALLOC'").fetchone())

    def test_payment_reference_conflict_cannot_change_another_invoice(self):
        self.action('simulate_payment', invoice_id='INV-001', amount='100', reference='UNIQUE-REF')
        with self.assertRaises(ValueError):
            self.action('simulate_payment', invoice_id='INV-002', amount='100', reference='UNIQUE-REF')
        self.assertEqual(Tools(self.path).get_invoice_context('INV-002')['invoice']['outstanding_minor'], 450000)

    def test_dispute_acceptance_preserves_balance_and_hold_until_verified_adjustment(self):
        context = Tools(self.path).get_invoice_context('INV-007')
        dispute = context['disputes'][0]
        self.action('resolve_dispute', dispute_id=dispute['dispute_id'], resolution='approved', reason='Return receipt reviewed', actor='finance_lina')
        self.assertEqual(Tools(self.path).get_invoice_context('INV-007')['invoice']['outstanding_minor'], 400000)
        with self.assertRaises(ValueError):
            self.action('resolve_dispute', dispute_id=dispute['dispute_id'], resolution='adjusted', reason='No ledger change yet', actor='finance_lina')
        draft = Tools(self.path).draft_message('INV-007', 'Collection reminder', 'TEST-COLLECTION')
        Tools(self.path).approve_draft(draft['draft_id'], 'finance_lina')
        self.assertEqual(Tools(self.path).send_approved_message(draft['draft_id'])['reason'], 'DISPUTE_REVIEW_REQUIRED')
        self.action('simulate_credit', invoice_id='INV-007', amount='1000', reference='SYNTHETIC-ADJUSTMENT', actor='finance_lina')
        self.action('resolve_dispute', dispute_id=dispute['dispute_id'], resolution='adjusted', reason='Synthetic ledger adjustment verified', actor='finance_lina')
        context = Tools(self.path).get_invoice_context('INV-007')
        self.assertEqual(context['disputes'][0]['status'], 'resolved')
        self.assertFalse(any(t['task_type'] == 'finance_review' and t['status'] == 'pending' for t in context['tasks']))

    def test_credit_note_is_not_a_cash_receipt_and_does_not_fulfill_promise(self):
        context = Tools(self.path).get_invoice_context('INV-007')
        dispute = context['disputes'][0]
        self.action('resolve_dispute', dispute_id=dispute['dispute_id'], resolution='approved', reason='Accepted return', actor='finance_lina')
        with connect(self.path) as db, db:
            db.execute('INSERT INTO messages VALUES (?,?,?,?,?,?,?)',
                       ('MSG-CREDIT-TEST', 'C007', 'INV-007', 'inbound', self.now, 'Curated promise', 'processed'))
        promise = Tools(self.path).record_payment_promise('MSG-CREDIT-TEST', 'INV-007', '1000', '2026-10-05')
        result = self.action('simulate_credit', invoice_id='INV-007', amount='1000', reference='CREDIT-TEST', actor='finance_lina')
        self.assertEqual(result['status'], 'synthetic_credit_recorded')
        self.assertEqual(self.action('simulate_credit', invoice_id='INV-007', amount='1000', reference='CREDIT-TEST')['status'], 'already_recorded')
        with connect(self.path) as db:
            event = dict(db.execute("SELECT * FROM demo_accounting_events WHERE source_reference='CREDIT-CREDIT-TEST'").fetchone())
            self.assertIsNone(event['payment_minor'])
            self.assertIsNone(event['payment_reference'])
        reconciled = Tools(self.path).reconcile_promise(promise['promise_id'])
        self.assertEqual(reconciled['promise']['status'], 'active')
        self.assertEqual(Tools(self.path).get_invoice_context('INV-007')['promise_allocations'], [])
        with self.assertRaises(ValueError):
            self.action('simulate_credit', invoice_id='INV-007', amount='1', reference='EXCESS-CREDIT')

    def test_cash_payment_does_not_prove_a_disputed_credit_note_was_posted(self):
        dispute = Tools(self.path).get_invoice_context('INV-007')['disputes'][0]
        self.action('resolve_dispute', dispute_id=dispute['dispute_id'], resolution='approved', reason='Accepted return')
        self.action('simulate_payment', invoice_id='INV-007', amount='1000', reference='CASH-NOT-CREDIT')
        with self.assertRaises(ValueError):
            self.action('resolve_dispute', dispute_id=dispute['dispute_id'], resolution='adjusted', reason='Payment is not credit')

    def test_finance_review_cannot_be_bypassed_by_completing_task(self):
        task = next(t for t in Tools(self.path).get_invoice_context('INV-007')['tasks'] if t['task_type'] == 'finance_review')
        self.action('assign_task', task_id=task['task_id'], owner='finance_lina')
        with self.assertRaises(ValueError):
            self.action('complete_task', task_id=task['task_id'], reason='Skip dispute')
        with self.assertRaises(ValueError):
            self.action('assign_task', task_id=task['task_id'], owner='invented-user')
        self.assertEqual(next(a['owner'] for a in product_snapshot(self.path)['assignments'] if a['task_id'] == task['task_id']), 'finance_lina')

    def test_verification_requires_fresh_accounting_and_records_reason(self):
        reason = 'Reviewed ledger; receipt not posted yet'
        result = self.action('resolve_verification', invoice_id='INV-003', reason=reason, actor='finance_lina')
        self.assertEqual(result['status'], 'verified_review_closed')
        for _ in range(3):
            review = next(r for r in product_snapshot(self.path)['reviews'] if r['message_id'] == 'MSG-003')
            self.assertEqual((review['status'], review['reason']), ('verification_reviewed', reason))
        # Original interpretation completion remains an audit fact; replaying it
        # cannot reopen the employee's later finance decision in the inbox.
        Workflow(self.path, DemoInterpreter(), self.now).process_message('MSG-003')
        review = next(r for r in product_snapshot(self.path)['reviews'] if r['message_id'] == 'MSG-003')
        self.assertEqual(review['status'], 'verification_reviewed')
        context = Tools(self.path).get_invoice_context('INV-003')
        self.assertEqual(context['invoice']['status'], 'open')
        self.assertEqual(context['invoice']['outstanding_minor'], 200000)
        self.assertFalse(any(t['task_type'] == 'payment_verification' and t['status'] == 'pending' for t in context['tasks']))
        with self.assertRaises(ValueError):
            self.action('resolve_verification', invoice_id='INV-011', reason='Stale ledger', actor='finance_lina')

    def test_unlinked_reply_can_only_be_assigned_to_its_customer(self):
        Workflow(self.path, DemoInterpreter(), self.now).process_message('MSG-009')
        with self.assertRaises(ValueError):
            self.action('assign_message', message_id='MSG-009', invoice_id='INV-001')
        self.action('assign_message', message_id='MSG-009', invoice_id='INV-009A')
        result = Workflow(self.path, DemoInterpreter(), self.now).process_message('MSG-009')
        self.assertEqual(result['invoice_id'], 'INV-009A')
        self.assertEqual(result['status'], 'awaiting_clarification')
        Workflow(self.path, now=self.now).confirm_message('MSG-009', '2000', '2026-10-05', 'collector_sara')
        review = next(r for r in product_snapshot(self.path)['reviews'] if r['message_id'] == 'MSG-009')
        self.assertEqual(review['status'], 'confirmed')
        self.assertEqual((review['amount'], review['payment_date']), ('2000.00', '2026-10-05'))

    def test_every_curated_story_can_be_loaded_and_preserves_integrity(self):
        for story in product_snapshot(self.path)['stories']:
            result = self.action('story', story_id=story['id'])
            self.assertEqual(result['story_id'], story['id'])
            with connect(self.path) as db:
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_export_contains_feedback_but_no_authentication_metadata(self):
        self.action('feedback', rating=5, text='Export this feedback')
        with connect(self.path) as db, db:
            db.execute('INSERT INTO workspace_settings VALUES (?,?)', ('auth_token', json.dumps('do-not-export')))
        exported = self.action('export')
        serialized = json.dumps(exported)
        self.assertIn('Export this feedback', serialized)
        self.assertNotIn('do-not-export', serialized)
        self.assertNotIn('integrations', exported['workspace'])
        for invalid in (True, 0, 6, '5'):
            with self.assertRaises(ValueError):
                self.action('feedback', rating=invalid, text='Invalid rating')


if __name__ == '__main__':
    unittest.main()
