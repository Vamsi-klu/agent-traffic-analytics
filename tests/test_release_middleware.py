"""tools/releasing/middleware.py: edge/ is copied into the package, into the folder the data file
names, without its tests, development scripts and node_modules; the WordPress plugin's header names the version
being released, read as WordPress reads it, and the release stops when it names another.

    python3 -I -m unittest discover -s tests -v      (from the repository root)
"""
import os
import unittest

from release_trees import ROOT, VERSION, make_tree, settings

from tools.releasing import middleware
from tools.releasing.project import Project
from tools.releasing.settings import ReleaseError

RULE = settings()["edge"]
PLUGIN = f"{RULE['folder']}/{RULE['plugin']['file']}"


def plugin_file(version_line):
    """A made-up plugin main file whose header has version_line where the real one names its version."""
    return f"<?php\n/**\n * Plugin Name:       AgentCake\n{version_line}\n * Requires PHP:      7.4\n */\n"
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


class PluginVersion(unittest.TestCase):
    def test_the_repositorys_wordpress_plugin_names_the_packages_version(self):
        self.assertEqual(middleware.plugin_version(ROOT, settings()), Project(ROOT, settings()).version)

    def test_a_plugin_that_names_the_version_being_released_passes(self):
        tree = make_tree(self, {PLUGIN: plugin_file(f" * Version:           {VERSION}")})
        middleware.check_plugin_version(tree, settings(), VERSION)

    def test_a_plugin_that_names_another_version_stops_the_release(self):
        tree = make_tree(self, {PLUGIN: plugin_file(" * Version:           0.0.0")})
        with self.assertRaisesRegex(ReleaseError, f"0.0.0.*{VERSION}"):
            middleware.check_plugin_version(tree, settings(), VERSION)

    def test_a_plugin_without_the_version_field_stops_the_release(self):
        tree = make_tree(self, {PLUGIN: plugin_file(" * Stable tag:        trunk")})
        with self.assertRaisesRegex(ReleaseError, f"has no {RULE['plugin']['version_field']} field"):
            middleware.check_plugin_version(tree, settings(), VERSION)

    def test_the_field_is_read_as_wordpress_reads_it(self):
        """get_file_data(): any case, after the comment's marks, cut before */ or ?>, and only in the first 8 KB."""
        self.assertEqual(middleware.header_field("<?php /* version: 1.2.3 */\n", "Version"), "1.2.3")
        self.assertEqual(middleware.header_field("<?php\n# Version:\t1.2.3 ?>\n", "Version"), "1.2.3")
        far = plugin_file(" * Description: " + "x" * middleware.HEADER_BYTES + f"\n * Version: {VERSION}")
        tree = make_tree(self, {PLUGIN: far})
        self.assertIsNone(middleware.plugin_version(tree, settings()))


if __name__ == "__main__":
    unittest.main()
