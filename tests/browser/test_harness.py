"""tests/browser/harness.py missing(): what the browser tests need and this computer lacks, so that a browser test is
skipped and says why instead of failing. Chromium counts as there only when it starts (tests/browser/chromium.mjs).

    python3 -I -m unittest discover -s tests -p test_harness.py -v      (from the repository root)
"""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from . import harness


class Missing(unittest.TestCase):
    def test_a_chromium_that_does_not_start_is_named_with_how_to_give_one(self):
        if not shutil.which("node") or not os.path.isdir(harness.playwright_dir()):
            self.skipTest("needs node and playwright-core to look for Chromium")
        absent = os.path.join(tempfile.mkdtemp(prefix="cake-no-chromium-"), "chrome")
        self.addCleanup(shutil.rmtree, os.path.dirname(absent), True)
        with mock.patch.dict(os.environ, {"CAKE_CHROME": absent}):
            lacking = harness.missing()
        self.assertEqual(len(lacking), 1, lacking)
        self.assertIn("CAKE_CHROME", lacking[0])


if __name__ == "__main__":
    unittest.main()
