import tempfile
import unittest
from pathlib import Path

from mutabi.database import connect
from mutabi.demo import load_demo
from mutabi.imports import import_csv


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'demo.db'
        load_demo(self.path)
        self.now = '2026-10-03T10:00:00+03:00'
        self.csv = ('invoice_id,customer_id,customer_name,original_amount,outstanding_balance,due_date\n'
                    'IMPORT-1,NEW-1,متجر تجريبي,4500.50,2000.25,2026-09-20\n')

    def run_import(self, **kwargs):
        return import_csv(self.path, self.now, dict(csv_text=self.csv, synthetic=True, **kwargs))

    def test_preview_does_not_mutate_and_import_is_exact(self):
        preview = self.run_import(dry_run=True)
        self.assertEqual(preview['rows'][0]['outstanding_minor'], 200025)
        with connect(self.path) as db:
            self.assertIsNone(db.execute("SELECT 1 FROM invoices WHERE invoice_id='IMPORT-1'").fetchone())
        self.assertEqual(self.run_import(dry_run=False)['count'], 1)
        with connect(self.path) as db:
            item = db.execute("SELECT * FROM invoices WHERE invoice_id='IMPORT-1'").fetchone()
            self.assertEqual(item['outstanding_minor'], 200025)
            self.assertEqual(item['source_reference'], 'CSV-SYNTHETIC-IMPORT-1')

    def test_invalid_later_row_imports_nothing(self):
        self.csv += 'IMPORT-2,NEW-1,متجر تجريبي,100,200,2026-09-20\n'
        with self.assertRaises(ValueError):
            self.run_import(dry_run=False)
        with connect(self.path) as db:
            self.assertIsNone(db.execute("SELECT 1 FROM customers WHERE customer_id='NEW-1'").fetchone())

    def test_duplicate_retry_is_rejected_without_mutation(self):
        self.run_import(dry_run=False)
        with self.assertRaises(ValueError):
            self.run_import(dry_run=False)
        with connect(self.path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM invoices WHERE invoice_id='IMPORT-1'").fetchone()[0], 1)

    def test_requires_explicit_synthetic_confirmation(self):
        with self.assertRaises(ValueError):
            import_csv(self.path, self.now, dict(csv_text=self.csv,synthetic='true',dry_run=False))

    def test_conflicting_customer_names_are_rejected(self):
        self.csv += 'IMPORT-2,NEW-1,Other customer,100,100,2026-09-20\n'
        with self.assertRaises(ValueError):
            self.run_import(dry_run=False)


if __name__ == '__main__':
    unittest.main()
