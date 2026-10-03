import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from mutabi.database import connect, counts
from mutabi.demo import DEMO_DIR, load_demo, minor

class DemoLoaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'demo.db'

    def test_baseline_and_idempotent_load_preserve_changes(self):
        first = load_demo(self.path)
        self.assertEqual(first['counts']['invoices'], 14)
        self.assertEqual(first['counts']['messages'], 12)
        with connect(self.path) as db, db:
            self.assertEqual(db.execute("SELECT processing_status FROM messages WHERE message_id='MSG-001'").fetchone()[0], 'pending')
            self.assertEqual(db.execute("SELECT COUNT(*) FROM messages WHERE processing_status='processed'").fetchone()[0], 3)
            self.assertIsNone(db.execute("SELECT invoice_id FROM messages WHERE message_id='MSG-009'").fetchone()[0])
            # A future accounting result must not affect the initial invoice.
            self.assertEqual(db.execute("SELECT outstanding_minor FROM invoices WHERE invoice_id='INV-004'").fetchone()[0], 250000)
            db.execute("UPDATE messages SET processing_status='processed' WHERE message_id='MSG-001'")
        second = load_demo(self.path)
        self.assertEqual(second['action'], 'already_loaded')
        self.assertEqual(first['counts'], second['counts'])
        with connect(self.path) as db:
            self.assertEqual(db.execute("SELECT processing_status FROM messages WHERE message_id='MSG-001'").fetchone()[0], 'processed')
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_reset_restores_baseline(self):
        load_demo(self.path)
        with connect(self.path) as db, db:
            db.execute("UPDATE invoices SET outstanding_minor=0 WHERE invoice_id='INV-001'")
            db.execute("INSERT INTO audit_events VALUES ('E1','INV-001','2026-10-03T10:00:00+03:00','test','{}')")
        self.assertEqual(load_demo(self.path, reset=True)['action'], 'reset')
        with connect(self.path) as db:
            self.assertEqual(counts(db)['audit_events'], 0)
            self.assertEqual(db.execute("SELECT outstanding_minor FROM invoices WHERE invoice_id='INV-001'").fetchone()[0], 300000)

    def test_invalid_source_reset_rolls_back(self):
        load_demo(self.path)
        directory = Path(self.temp.name) / 'source'
        shutil.copytree(DEMO_DIR, directory)
        path = directory / 'promises.csv'
        path.write_text(path.read_text().replace('INV-004','INV-MISSING'))
        with self.assertRaises(sqlite3.IntegrityError):
            load_demo(self.path, directory, reset=True)
        with connect(self.path) as db:
            self.assertEqual(counts(db)['promises'], 3)
            self.assertEqual(counts(db)['invoices'], 14)

    def test_unowned_database_is_protected(self):
        with connect(self.path) as db, db:
            db.execute('CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
            db.execute("INSERT INTO metadata VALUES ('owner','another-app')")
        with self.assertRaises(ValueError):
            load_demo(self.path, reset=True)
        with connect(self.path) as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='invoices'").fetchone())

    def test_money_validation(self):
        self.assertEqual(minor('0.29'), 29)
        self.assertIsNone(minor(''))
        for value in ('1.001','-1','NaN','Infinity'):
            with self.assertRaises(ValueError):
                minor(value)

if __name__ == '__main__':
    unittest.main()
