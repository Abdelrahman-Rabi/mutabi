"""Run a credential-free demonstration through the real workflow and tools.

This is a smoke check of curated synthetic examples, not live-model evaluation
or a measurement of business savings. All state is temporary and discarded.
"""
import argparse
import json
import tempfile
import time
from pathlib import Path

from .demo import ROOT, load_demo
from .product import DemoInterpreter
from .web import DemoApp
from .workflow import Workflow


def review_demo():
    started = time.perf_counter()
    checks = []

    def require(condition, name, evidence):
        if not condition:
            raise ValueError('Reviewer check failed: ' + name)
        checks.append({'check': name, 'passed': True, 'evidence': evidence})

    scratch = ROOT / 'runtime'
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='review-check-', dir=scratch) as directory:
        if not Path(directory).resolve().is_relative_to(scratch.resolve()):
            raise ValueError('Reviewer scratch directory must stay inside runtime')
        path = Path(directory) / 'promise.db'
        load_demo(path)
        workflow = Workflow(path, DemoInterpreter())
        result = workflow.process_message('MSG-001')
        context = workflow.tools.get_invoice_context('INV-001')
        promise = next(p for p in context['promises'] if p['promise_id'] == result.get('promise_id'))
        task = next(t for t in context['tasks'] if t['promise_id'] == promise['promise_id'])
        require(result['status'] == 'promise_recorded' and promise['amount_minor'] == 300000
                and promise['promised_date'] == '2026-10-05' and task['due_date'] == '2026-10-06',
                'Promise creates a dated check',
                'INV-001: SAR 3,000 promised on 5 October; balance check due 6 October.')
        draft_id = result['draft_id']
        blocked = workflow.tools.send_approved_message(draft_id)
        require(not blocked['sent'], 'Delivery needs employee approval', 'Unapproved draft was blocked.')
        workflow.tools.approve_draft(draft_id, 'REVIEWER-DEMO-EMPLOYEE')
        sent = workflow.tools.send_approved_message(draft_id)
        replayed = workflow.tools.send_approved_message(draft_id)
        require(sent['sent'] and replayed.get('already_sent')
                and workflow.tools.get_invoice_context('INV-001')['invoice']['outstanding_minor'] == 300000,
                'Approved simulated delivery is retry-safe',
                'One simulated delivery; retry creates no second delivery; balance stays SAR 3,000.')
        due = Workflow(path, now='2026-10-06T10:05:00+03:00', scenario_id='TC-15')
        results = due.run_due_followups('INV-001')
        context = due.tools.get_invoice_context('INV-001')
        require(any(r['status'] == 'missed' and r['verification']['verified'] for r in results)
                and any(d['status'] == 'awaiting_approval' for d in context['drafts'])
                and context['invoice']['outstanding_minor'] == 300000,
                'Fresh accounting evidence drives the missed follow-up',
                'TC-15 confirms SAR 3,000 outstanding; missed promise produces an approval-required draft.')
        replay = due.run_due_followups('INV-001')
        require(replay == [], 'Completed check does not run twice', 'No additional due action on retry.')

        # Unknown text follows the same conservative path used by the browser UI.
        app = DemoApp(Path(directory) / 'manual.db')
        reply = app.action('add_reply', {'invoice_id': 'INV-001', 'text': 'A new uncurated reviewer reply.'})
        decision = app.action('process', {'message_id': reply['message_id']})
        require(decision['status'] == 'needs_human_review', 'Free text needs review in demo mode',
                'An uncurated reply was sent to employee review rather than guessed.')

        installment = DemoApp(Path(directory) / 'installment.db')
        installment.action('story', {'story_id': 'installment'})
        snapshot = installment.snapshot()
        promise = next(p for p in snapshot['promises'] if p['invoice_id'] == 'INV-001'
                       and p['amount_minor'] == 100000 and p['status'] == 'active')
        installment.action('simulate_payment', {'invoice_id': 'INV-001', 'amount': '1000',
                           'reference': 'REVIEWER-INSTALLMENT-001', 'promise_id': promise['promise_id']})
        snapshot = installment.snapshot()
        updated = next(p for p in snapshot['promises'] if p['promise_id'] == promise['promise_id'])
        invoice = next(i for i in snapshot['invoices'] if i['invoice_id'] == 'INV-001')
        require(updated['status'] == 'fulfilled' and invoice['outstanding_minor'] == 200000,
                'Installment fulfillment keeps remaining debt visible',
                'SAR 1,000 installment fulfilled; invoice still has SAR 2,000 outstanding.')

    return {'status': 'passed', 'checks': checks, 'elapsed_seconds': round(time.perf_counter() - started, 3),
            'provider': 'curated demo examples', 'accounting': 'simulated', 'delivery': 'simulated',
            'live_model_calls': 0, 'persistent_workspace_modified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true', help='Print the verification evidence as JSON')
    args = parser.parse_args()
    try:
        report = review_demo()
    except (ValueError, KeyError, StopIteration) as error:
        parser.exit(1, 'Reviewer check failed: ' + str(error) + '\n')
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for check in report['checks']:
            print('PASS: ' + check['check'])
            print('      ' + check['evidence'])
        print(f"\nAll {len(report['checks'])} checks passed in {report['elapsed_seconds']:.3f}s.")
        print('Curated synthetic demo; no live model calls or real messages. Temporary state discarded.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
