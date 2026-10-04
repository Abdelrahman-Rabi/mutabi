"""Validated, atomic CSV onboarding for disposable synthetic workspaces."""
import csv
import io
import re

from .database import connect
from .demo import day, minor

FIELDS = ('invoice_id', 'customer_id', 'customer_name', 'original_amount',
          'outstanding_balance', 'due_date')


def import_csv(path, now, data):
    if data.get('synthetic') is not True:
        raise ValueError('Confirm that this CSV contains synthetic demonstration data only.')
    text = data.get('csv_text')
    if not isinstance(text, str) or not text.strip() or len(text) > 50000:
        raise ValueError('Provide a CSV containing 1–200 synthetic invoices (maximum 50,000 characters).')
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
    if reader.fieldnames != list(FIELDS):
        raise ValueError('CSV headers must be: ' + ','.join(FIELDS))
    prepared = []
    seen = set()
    customer_names = {}
    with connect(path) as db:
        existing_invoices = {r[0] for r in db.execute('SELECT invoice_id FROM invoices')}
        existing_customers = dict(db.execute('SELECT customer_id,name FROM customers'))
    for line, record in enumerate(reader, 2):
        if len(prepared) >= 200:
            raise ValueError('Import at most 200 rows at a time.')
        if None in record or any(value is None for value in record.values()):
            raise ValueError(f'Row {line}: expected exactly six columns.')
        record = {key:value.strip() for key, value in record.items()}
        for key in ('invoice_id', 'customer_id'):
            if not re.fullmatch(r'[A-Za-z0-9._-]{1,48}', record[key]):
                raise ValueError(f'Row {line}: {key} must contain 1–48 letters, digits, dots, underscores or hyphens.')
        invoice_id, customer_id = record['invoice_id'], record['customer_id']
        if invoice_id in seen or invoice_id in existing_invoices:
            raise ValueError(f'Row {line}: invoice {invoice_id} already exists. Nothing was imported.')
        seen.add(invoice_id)
        name = record['customer_name']
        if not name or len(name) > 120:
            raise ValueError(f'Row {line}: enter a customer name containing 1–120 characters.')
        if customer_id in existing_customers and existing_customers[customer_id] != name:
            raise ValueError(f'Row {line}: customer name conflicts with existing customer {customer_id}.')
        if customer_id in customer_names and customer_names[customer_id] != name:
            raise ValueError(f'Row {line}: one customer ID has different names.')
        customer_names[customer_id] = name
        try:
            original = minor(record['original_amount'])
            balance = minor(record['outstanding_balance'])
            due = day(record['due_date'])
        except Exception:
            raise ValueError(f'Row {line}: use exact positive decimal amounts and YYYY-MM-DD dates.') from None
        if original is None or original <= 0 or balance is None or not 0 <= balance <= original:
            raise ValueError(f'Row {line}: balance must be between zero and the positive original amount.')
        prepared.append(dict(invoice_id=invoice_id, customer_id=customer_id, customer_name=name,
                             original_minor=original, outstanding_minor=balance, due_date=due, currency='SAR'))
    if not prepared:
        raise ValueError('CSV has no invoice rows.')
    dry_run = data.get('dry_run', True)
    if not isinstance(dry_run, bool):
        raise ValueError('dry_run must be a boolean.')
    if not dry_run:
        with connect(path) as db, db:
            for customer_id, name in customer_names.items():
                db.execute('INSERT OR IGNORE INTO customers VALUES (?,?,?,?,?,?)',
                           (customer_id, name, 'SAR', 'Asia/Riyadh', 'simulated', 'synthetic-csv'))
            for item in prepared:
                db.execute('INSERT INTO invoices VALUES (?,?,?,?,?,?,?,?,?)',
                           (item['invoice_id'],item['customer_id'],item['original_minor'],item['outstanding_minor'],
                            'SAR',item['due_date'],now,'CSV-SYNTHETIC-' + item['invoice_id'],
                            'settled' if item['outstanding_minor'] == 0 else 'open'))
    return {'status':'preview' if dry_run else 'imported', 'rows':prepared, 'count':len(prepared)}
