"""SQLite storage. Monetary amounts are stored as integer minor units."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS customers (
 customer_id TEXT PRIMARY KEY, name TEXT NOT NULL, currency TEXT NOT NULL,
 timezone TEXT NOT NULL, channel TEXT NOT NULL, contact_reference TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS invoices (
 invoice_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(customer_id),
 original_minor INTEGER NOT NULL CHECK(original_minor >= 0),
 outstanding_minor INTEGER NOT NULL CHECK(outstanding_minor >= 0),
 currency TEXT NOT NULL, due_date TEXT NOT NULL, balance_updated_at TEXT NOT NULL,
 source_reference TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open');
CREATE TABLE IF NOT EXISTS messages (
 message_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(customer_id),
 invoice_id TEXT REFERENCES invoices(invoice_id), direction TEXT NOT NULL,
 received_at TEXT NOT NULL, text TEXT NOT NULL,
 processing_status TEXT NOT NULL CHECK(processing_status IN ('pending','processed')));
CREATE TABLE IF NOT EXISTS promises (
 promise_id TEXT PRIMARY KEY, invoice_id TEXT NOT NULL REFERENCES invoices(invoice_id),
 amount_minor INTEGER NOT NULL CHECK(amount_minor > 0), currency TEXT NOT NULL,
 promised_date TEXT NOT NULL, status TEXT NOT NULL, recorded_at TEXT NOT NULL,
 source_message_id TEXT NOT NULL UNIQUE REFERENCES messages(message_id));
CREATE TABLE IF NOT EXISTS tasks (
 task_id TEXT PRIMARY KEY, invoice_id TEXT NOT NULL REFERENCES invoices(invoice_id),
 promise_id TEXT REFERENCES promises(promise_id), task_type TEXT NOT NULL,
 due_date TEXT NOT NULL, status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS drafts (
 draft_id TEXT PRIMARY KEY, invoice_id TEXT NOT NULL REFERENCES invoices(invoice_id),
 text TEXT NOT NULL, status TEXT NOT NULL, approved_by TEXT, approved_at TEXT);
CREATE TABLE IF NOT EXISTS disputes (
 dispute_id TEXT PRIMARY KEY, invoice_id TEXT NOT NULL REFERENCES invoices(invoice_id),
 source_message_id TEXT NOT NULL REFERENCES messages(message_id),
 claimed_minor INTEGER CHECK(claimed_minor >= 0), reason TEXT NOT NULL,
 status TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_events (
 event_id TEXT PRIMARY KEY, invoice_id TEXT REFERENCES invoices(invoice_id),
 occurred_at TEXT NOT NULL, action TEXT NOT NULL, details_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS deliveries (
 delivery_id TEXT PRIMARY KEY, draft_id TEXT NOT NULL UNIQUE REFERENCES drafts(draft_id),
 delivered_at TEXT NOT NULL, channel TEXT NOT NULL CHECK(channel='simulated'));
CREATE TABLE IF NOT EXISTS draft_options (
 draft_id TEXT PRIMARY KEY REFERENCES drafts(draft_id),
 purpose TEXT NOT NULL CHECK(purpose IN ('collection','acknowledgment','verification','dispute')),
 language TEXT NOT NULL CHECK(language IN ('en','ar')));
CREATE TABLE IF NOT EXISTS promise_allocations (
 allocation_id TEXT PRIMARY KEY, promise_id TEXT NOT NULL REFERENCES promises(promise_id),
 payment_reference TEXT NOT NULL, amount_minor INTEGER NOT NULL CHECK(amount_minor > 0),
 created_at TEXT NOT NULL, UNIQUE(promise_id,payment_reference));
CREATE TABLE IF NOT EXISTS promise_revisions (
 old_promise_id TEXT PRIMARY KEY REFERENCES promises(promise_id),
 new_promise_id TEXT NOT NULL UNIQUE REFERENCES promises(promise_id),
 reason TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS demo_accounting_events (
 event_id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL,
 invoice_id TEXT NOT NULL REFERENCES invoices(invoice_id), available_at TEXT NOT NULL,
 result TEXT NOT NULL CHECK(result IN ('success','error')),
 outstanding_minor INTEGER CHECK(outstanding_minor >= 0), currency TEXT NOT NULL,
 payment_minor INTEGER CHECK(payment_minor >= 0), payment_reference TEXT,
 source_reference TEXT NOT NULL, error_code TEXT,
 CHECK((result='success' AND outstanding_minor IS NOT NULL AND error_code IS NULL)
    OR (result='error' AND outstanding_minor IS NULL AND error_code IS NOT NULL)));
CREATE INDEX IF NOT EXISTS tasks_due ON tasks(status, due_date);
CREATE INDEX IF NOT EXISTS messages_invoice ON messages(invoice_id);
"""

@contextmanager
def connect(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    try:
        yield db
    finally:
        db.close()

def initialize(db):
    db.executescript(SCHEMA)

def counts(db):
    tables = ('customers', 'invoices', 'messages', 'promises', 'tasks', 'drafts',
              'disputes', 'audit_events', 'deliveries', 'demo_accounting_events')
    return {table: db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            for table in tables}
