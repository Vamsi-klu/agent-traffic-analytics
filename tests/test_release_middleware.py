"""tools/releasing/middleware.py (plan step S6.4): edge/ is copied into the package, into the folder the data file
names, without its tests, development scripts and node_modules.

    python3 -I -m unittest discover -s tests -v      (from the repository root)
"""
import os
import unittest

from release_trees import make_tree, settings

from tools.releasing import middleware
from tools.releasing.settings import ReleaseError

RULE = settings()["edge"]
NAMES_FILE = {RULE["settings_file"]: '{"edge_folder": "edge"}\n'}
EDGE = {
    "edge/node/index.js": "module.exports = {}\n",
    "edge/node/README.md": "# Node\n",
    "edge/node/test/token.test.js": "test\n",
    "edge/node/scripts/make-vectors.js": "script\n",
    "edge/node/node_modules/dep/index.js": "dependency\n",
    "edge/php/cake_edge.php": "<?php\n",
    "edge/php/tests/run.php": "<?php\n",
    "edge/python/cake_edge.py": "X = 1\n",
    "edge/python/__pycache__/cake_edge.cpython-314.pyc": "compiled\n",
    "edge/wordpress/agentcake/README.md": "# WordPress\n",
}


def copied(root):
    return sorted(os.path.relpath(os.path.join(folder, name), root).replace(os.sep, "/")
                  for folder, _, names in os.walk(root) for name in names)


class Copy(unittest.TestCase):
    def test_edge_goes_into_the_package_without_tests_scripts_and_junk(self):
        tree = make_tree(self, {**NAMES_FILE, **EDGE})
        target = middleware.build(tree, settings())
        self.assertEqual(target, os.path.join(tree, "agentcake", "edge"))
        self.assertEqual(copied(target), ["node/README.md", "node/index.js", "php/cake_edge.php",
                                          "python/cake_edge.py", "wordpress/agentcake/README.md"])

    def test_without_the_data_file_the_release_stops(self):
        with self.assertRaisesRegex(ReleaseError, RULE["settings_file"]):
            middleware.build(make_tree(self, EDGE), settings())

    def test_a_skipped_path_the_commit_does_not_have_stops_the_release(self):
        tree = make_tree(self, {**NAMES_FILE, **{k: v for k, v in EDGE.items() if "/php/tests/" not in k}})
        with self.assertRaisesRegex(ReleaseError, "skip"):
            middleware.build(tree, settings())

    def test_a_package_that_already_has_the_folder_stops_the_release(self):
        tree = make_tree(self, {**NAMES_FILE, **EDGE, "agentcake/edge/old.js": "old\n"})
        with self.assertRaisesRegex(ReleaseError, "already"):
            middleware.build(tree, settings())


if __name__ == "__main__":
    unittest.main()
