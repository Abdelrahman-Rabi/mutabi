"""Reviewer entry point: local UI or an offline end-to-end workflow check."""
import errno
import sys


def main():
    if sys.version_info < (3, 10):
        print('Mutabi requires Python 3.10 or newer.', file=sys.stderr)
        return 1
    if '--check' in sys.argv[1:]:
        from mutabi.reviewer_check import main as check
        sys.argv.remove('--check')
        return check()
    from mutabi.web import main as serve
    try:
        serve()
    except OSError as error:
        if error.errno == errno.EADDRINUSE or getattr(error, 'winerror', None) == 10048:
            print('Port is already in use. Try: python run_demo.py --port 8766', file=sys.stderr)
            return 1
        raise
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
