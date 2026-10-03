"""Command-line entry point for Gemini interpretation and deterministic workflows."""
import argparse
import json
from pathlib import Path

from .demo import DEFAULT_DB, ROOT
from .gemini import GeminiInterpreter, ModelError, load_local_env
from .workflow import Workflow
from .chatgpt_auth import ChatGPTAuth
from .chatgpt_plan import ChatGPTPlanInterpreter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('process', 'followups', 'context', 'prepare'))
    parser.add_argument('--db', default=str(DEFAULT_DB))
    parser.add_argument('--message')
    parser.add_argument('--provider', choices=('gemini', 'chatgpt_plan'), default='gemini',
                        help='ChatGPT plan uses the connection created in the local browser UI')
    parser.add_argument('--invoice')
    parser.add_argument('--now', help='Timezone-aware ISO timestamp; defaults to stored demo time')
    parser.add_argument('--scenario', help='Host-selected accounting simulator scenario, never model input')
    args = parser.parse_args()
    load_local_env(ROOT / '.env')
    try:
        workflow = Workflow(args.db, now=args.now, scenario_id=args.scenario)
        if args.command == 'process':
            if not args.message:
                parser.error('process requires --message')
            if workflow._stored('message_completed', args.message) is None:
                workflow.interpreter = (ChatGPTPlanInterpreter(ChatGPTAuth(Path(args.db).parent / 'chatgpt'))
                                        if args.provider == 'chatgpt_plan' else GeminiInterpreter())
            result = workflow.process_message(args.message)
        elif args.command == 'followups':
            result = workflow.run_due_followups(args.invoice)
        else:
            if not args.invoice:
                parser.error('context and prepare require --invoice')
            result = (workflow.tools.get_invoice_context(args.invoice) if args.command == 'context'
                      else workflow.prepare_collection_message(args.invoice))
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except (ModelError, ValueError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
