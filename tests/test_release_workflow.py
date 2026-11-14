""".github/workflows/release.yml (plan step S6.4): on a v<version> tag it runs the same tools/release.py build twice,
compares the two, and only creates a draft release, with the Python and Node release.json names, every action pinned
by commit.

    python3 -I -m unittest discover -s tests -v      (from the repository root)

The file is read as text (no YAML parser in the standard library): each check looks for the line that does the thing.
"""
import os
import re
import unittest

from release_trees import ROOT, settings

WORKFLOW = os.path.join(ROOT, ".github", "workflows", "release.yml")
BUILD = 'python3 -I tools/release.py build --tag "$GITHUB_REF_NAME"'


def setting(text, key):
    match = re.search(rf'^\s+{re.escape(key)}:\s*"([^"]+)"', text, re.M)
    return match.group(1) if match else None


class Workflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(WORKFLOW, encoding="utf-8") as f:
            cls.text = f.read()

    def test_it_runs_on_version_tags_only(self):
        self.assertRegex(self.text, r'(?m)^on:\n  push:\n    tags: \["v\*"\]\n\n')

    def test_it_builds_twice_with_the_local_command_and_compares(self):
        self.assertEqual(self.text.count(BUILD), 2)
        self.assertIn("cmp dist/SHA256SUMS dist-again/SHA256SUMS", self.text)
        self.assertIn("sha256sum -c SHA256SUMS", self.text)

    def test_python_and_node_are_the_release_toolchain(self):
        toolchain = settings()["toolchain"]
        self.assertEqual(setting(self.text, "python-version"), toolchain["python"])
        self.assertEqual(setting(self.text, "node-version"), toolchain["node"])

    def test_every_action_is_pinned_by_commit(self):
        uses = re.findall(r"uses:\s*(\S+)", self.text)
        self.assertTrue(uses)
        for action in uses:
            self.assertRegex(action, r"^[\w-]+/[\w-]+@[0-9a-f]{40}$")

    def test_it_only_makes_a_draft_and_publishes_nothing(self):
        self.assertIn("gh release create", self.text)
        self.assertIn("--draft", self.text)
        for publishing in ("--draft=false", "gh release edit", "twine", "npm publish", "docker push", "--latest"):
            self.assertNotIn(publishing, self.text)

    def test_the_token_can_write_only_where_the_release_is_made(self):
        self.assertRegex(self.text, r"(?m)^permissions:\n  contents: read\n")
        self.assertEqual(self.text.count("contents: write"), 1)


if __name__ == "__main__":
    unittest.main()
