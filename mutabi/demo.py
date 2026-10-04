"""Transactional synthetic-data loader; never applies future accounting events."""
import argparse
import csv
import hashlib
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .database import connect, counts, initialize

ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / 'data' / 'demo'
DEFAULT_DB = ROOT / 'runtime' / 'mutabi.db'
CSV_FILES = ('customers', 'invoices', 'messages', 'promises', 'tasks', 'drafts', 'accounting_updates')
OWNER = 'mutabi-synthetic-demo-v1'

def minor(value):
    if not value:
        return None
    try:
        amount = Decimal(value) * 100
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError('Invalid monetary value') from None
    if not amount.is_finite() or amount != amount.to_integral_value() or amount < 0:
        raise ValueError(f'Invalid monetary value: {value}')
    return int(amount)

def timestamp(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError('Timestamp requires a timezone')
    return value

def day(value):
    date.fromisoformat(value)
    return value

def read_source(directory):
    result = {}
    digest = hashlib.sha256()
    for name in (*CSV_FILES, 'policy'):
        path = directory / (name + ('.json' if name == 'policy' else '.csv'))
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
        with path.open(encoding='utf-8-sig', newline='') as stream:
            result[name] = json.load(stream) if name == 'policy' else list(csv.DictReader(stream))
    if result['policy'].get('synthetic') is not True:
        raise ValueError('Only explicitly synthetic demo data may be loaded')
    timestamp(result['policy']['reference_time'])
    return result, digest.hexdigest()

def insert(db, table, values):
    placeholders = ','.join('?' for _ in values)
    db.execute(f'INSERT INTO {table} VALUES ({placeholders})', values)

def load_demo(path=DEFAULT_DB, directory=DEMO_DIR, reset=False):
    source, fingerprint = read_source(Path(directory))
    with connect(path) as db:
        existing_tables = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if existing_tables:
            if 'metadata' not in existing_tables:
                raise ValueError('Refusing to modify an unowned database')
            existing_metadata = dict(db.execute('SELECT key,value FROM metadata').fetchall())
            if existing_metadata.get('owner') != OWNER:
                raise ValueError('Refusing to modify a database not owned by the demo loader')
        initialize(db)
        metadata = dict(db.execute('SELECT key,value FROM metadata').fetchall())
        if metadata.get('owner') != OWNER and (metadata or any(counts(db).values())):
            raise ValueError('Refusing to overwrite a database not owned by the demo loader')
        if metadata.get('loaded') == 'true' and not reset:
            if metadata.get('source_fingerprint') != fingerprint:
                raise ValueError('Demo source changed; use reset to explicitly restore the baseline')
            return {'action': 'already_loaded', 'counts': counts(db)}
        with db:
            if reset:
                # Discovery extensions reference base rows. Keep participant
                # feedback and research history through disposable demo resets.
                extensions = ('reviews', 'notes', 'task_assignments', 'customer_profiles',
                              'draft_options', 'promise_allocations', 'promise_revisions')
                for table in extensions:
                    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                        db.execute(f'DELETE FROM {table}')
                for table in ('deliveries', 'audit_events', 'disputes', 'tasks', 'drafts',
                              'promises', 'demo_accounting_events', 'messages', 'invoices', 'customers', 'metadata'):
                    db.execute(f'DELETE FROM {table}')
            for r in source['customers']:
                insert(db, 'customers', tuple(r[k] for k in ('customer_id','name','currency','timezone','channel','contact_reference')))
            for r in source['invoices']:
                original, balance = minor(r['original_amount']), minor(r['outstanding_balance'])
                if original is None or balance is None or balance > original:
                    raise ValueError('Invalid invoice balance')
                insert(db, 'invoices', (r['invoice_id'],r['customer_id'],original,balance,r['currency'],
                    day(r['due_date']),timestamp(r['balance_updated_at']),r['source_reference'], 'settled' if balance == 0 else 'open'))
            for r in source['messages']:
                if r['is_seed_history'] not in ('true','false'):
                    raise ValueError('Invalid seed-history boolean')
                insert(db, 'messages', (r['message_id'],r['customer_id'],r['invoice_id'] or None,
                    r['direction'],timestamp(r['received_at']),r['text'],
                    'processed' if r['is_seed_history'] == 'true' else 'pending'))
            for r in source['promises']:
                insert(db, 'promises', (r['promise_id'],r['invoice_id'],minor(r['amount']),r['currency'],
                    day(r['promised_date']),r['status'],timestamp(r['recorded_at']),r['source_message_id']))
            for r in source['tasks']:
                insert(db, 'tasks', (r['task_id'],r['invoice_id'],r['promise_id'] or None,r['task_type'],day(r['due_date']),r['status']))
            for r in source['drafts']:
                if r['status'] == 'approved' and not (r['approved_by'] and r['approved_at']):
                    raise ValueError('Approved draft requires approval evidence')
                insert(db, 'drafts', (r['draft_id'],r['invoice_id'],r['text'],r['status'],
                    r['approved_by'] or None,timestamp(r['approved_at']) if r['approved_at'] else None))
            for r in source['accounting_updates']:
                insert(db, 'demo_accounting_events', (r['event_id'],r['scenario_id'],r['invoice_id'],
                    timestamp(r['available_at']),r['result'],minor(r['outstanding_balance']),r['currency'],
                    minor(r['payment_amount']),r['payment_reference'] or None,r['source_reference'],r['error_code'] or None))
            db.executemany('INSERT INTO metadata VALUES (?,?)', [
                ('owner', OWNER), ('loaded','true'), ('source_fingerprint',fingerprint),
                ('schema_version','1'), ('policy',json.dumps(source['policy'])),
                ('demo_time',source['policy']['reference_time'])])
        return {'action': 'reset' if reset else 'loaded', 'counts': counts(db)}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('load','reset','status'))
    parser.add_argument('--db', type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    if args.command == 'status':
        if not args.db.exists():
            parser.error('Database does not exist; run load first')
        with connect(args.db) as db:
            result = {'counts': counts(db), 'metadata': dict(db.execute('SELECT key,value FROM metadata').fetchall())}
    else:
        result = load_demo(args.db, reset=args.command == 'reset')
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
