import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from mutabi.web import DemoApp


class FrontendContractTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node.js is needed for frontend rendering checks')
    def test_bilingual_views_render_actual_snapshot_with_optional_story_steps(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot = DemoApp(Path(directory) / 'frontend.db').snapshot()
            result = subprocess.run(
                [shutil.which('node'), str(Path(__file__).with_name('frontend_render_check.js'))],
                input=json.dumps(snapshot, ensure_ascii=False),
                encoding='utf-8', capture_output=True, timeout=20,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
