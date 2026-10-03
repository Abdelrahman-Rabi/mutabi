"""Run the approved workflow cases with real Gemini interpretation.

Uses temporary SQLite databases and synthetic replies; makes billable API calls.
Expected outcomes are used by assertions only and never supplied to the model.
"""
import json
import argparse
import sys
import time
import unittest
from datetime import datetime, timezone

from mutabi.demo import ROOT
from mutabi.gemini import GeminiInterpreter, load_local_env
from mutabi.workflow import Workflow
from mutabi.chatgpt_auth import ChatGPTAuth
from mutabi.chatgpt_plan import ChatGPTPlanInterpreter
from tests.test_workflow import WorkflowTests

CALLS = []
CACHE = {}
MIN_INTERVAL = 15
MODEL = None
PROVIDER = 'gemini'
AUTH = None
LAST_CALL = 0


class LiveInterpreter:
    def __init__(self):
        self.model = ChatGPTPlanInterpreter(AUTH) if PROVIDER == 'chatgpt_plan' else GeminiInterpreter(model=MODEL)
        self.calls = 0

    def interpret(self, text, reference_date):
        global LAST_CALL
        self.calls += 1
        key = (PROVIDER, AUTH.status()['model'] if PROVIDER == 'chatgpt_plan' else self.model.model, text, reference_date)
        if key in CACHE:
            return dict(CACHE[key])
        wait = MIN_INTERVAL - (time.monotonic() - LAST_CALL)
        if wait > 0:
            time.sleep(wait)
        started = time.monotonic()
        try:
            decision = self.model.interpret(text, reference_date)
        finally:
            LAST_CALL = time.monotonic()
        CACHE[key] = dict(decision)
        CALLS.append({'reply': text, 'reference_date': reference_date,
                      'decision': decision, 'elapsed_seconds': round(time.monotonic()-started, 3),
                      'metadata': self.model.last_metadata})
        return decision


class LiveWorkflowTests(WorkflowTests):
    def workflow(self, intent=None, scenario=None, now=None, **fields):
        # Ignore controlled interpretation fields; actual customer text goes to Gemini.
        return Workflow(self.path, LiveInterpreter() if intent else None, now, scenario)


class RecordingResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.records.append({'test': test._testMethodName, 'status': 'pass'})

    def addFailure(self, test, error):
        super().addFailure(test, error)
        self.records.append({'test': test._testMethodName, 'status': 'fail', 'detail': str(error[1])})

    def addError(self, test, error):
        super().addError(test, error)
        self.records.append({'test': test._testMethodName, 'status': 'error', 'detail': str(error[1])})


def main():
    global MIN_INTERVAL, MODEL, PROVIDER, AUTH
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', help='Explicit Gemini model override; leaves .env unchanged')
    parser.add_argument('--min-interval', type=float, default=15, help='Seconds between unique replies')
    parser.add_argument('--provider', choices=('gemini', 'chatgpt_plan'), default='gemini')
    parser.add_argument('--auth-dir', default=str(ROOT / 'runtime' / 'chatgpt'),
                        help='Protected ChatGPT connection directory created by the browser UI')
    args = parser.parse_args()
    MIN_INTERVAL, MODEL = max(0, args.min_interval), args.model
    PROVIDER = args.provider
    if PROVIDER == 'chatgpt_plan':
        if MODEL:
            parser.error('Choose the ChatGPT model in the UI; --model overrides Gemini only')
        AUTH = ChatGPTAuth(args.auth_dir)
        if not AUTH.status()['ready']:
            parser.error('Connect ChatGPT and choose a model in the local UI before live evaluation')
    load_local_env(ROOT / '.env')
    CALLS.clear()
    CACHE.clear()
    names = sorted(name for name in dir(LiveWorkflowTests) if name.startswith('test_TC'))
    suite = unittest.TestSuite(LiveWorkflowTests(name) for name in names)
    result = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult).run(suite)
    report = {'run_at_utc': datetime.now(timezone.utc).isoformat(),
              'mode': f'live {PROVIDER} interpretation plus synthetic tools/accounting',
              'tests_run': result.testsRun, 'successful': result.wasSuccessful(),
              'results': result.records, 'model_calls': CALLS,
              'limitations': ['Single run per scenario; not a statistical reliability estimate.',
                              'Accounting and outbound delivery are simulated.',
                              'English fixtures only; Arabic variants not evaluated.',
                              'Duplicate synthetic replies reuse the live interpretation within this run.',
                              'TC-04,05,06,11,14 are deterministic workflows without a language-model call.']}
    path = ROOT / 'docs' / ('live_chatgpt_evaluation.json' if PROVIDER == 'chatgpt_plan' else 'live_evaluation.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        previous = path.with_name(path.stem + '_previous.json')
        previous.write_bytes(path.read_bytes())
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Live evaluation report saved to {path}')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
