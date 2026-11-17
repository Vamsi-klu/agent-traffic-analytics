""".github/workflows/pypi.yml: when the maintainer publishes a GitHub release, it uploads that release's wheel to PyPI
with Trusted Publishing: no token, the wheel checked against the release's SHA256SUMS first, nothing built again and
nothing else uploaded, every action pinned by commit.

    python3 -I -m unittest discover -s tests -v      (from the repository root)

PyPI's trusted publisher for the project names this repository, the file name pypi.yml and the environment pypi, so
neither name may change. The file is read as text (no YAML parser in the standard library): each check looks for the
line that does the thing.
"""
import os
import re
import unittest

from release_trees import ROOT

WORKFLOW = os.path.join(ROOT, ".github", "workflows", "pypi.yml")  # the file name PyPI's trusted publisher names
ENVIRONMENT = "pypi"  # the environment PyPI's trusted publisher names
PUBLISH_ACTION = "pypa/gh-action-pypi-publish"


def without_comments(text):
    """The workflow's lines without YAML comments (a line that is one, or a ` # ...` at the end), which may name what
    the workflow leaves out."""
    lines = (re.sub(r"\s+#\s.*$", "", line) for line in text.splitlines() if not line.lstrip().startswith("#"))
    return "\n".join(lines)


class Workflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(WORKFLOW, encoding="utf-8") as f:
            cls.text = f.read()
        cls.code = without_comments(cls.text)

    def test_it_runs_when_a_release_is_published_only(self):
        self.assertRegex(self.text, r"(?m)^on:\n  release:\n    types: \[published\]\n\n")

    def test_it_runs_in_the_environment_pypi_trusts(self):
        self.assertEqual(re.findall(r"(?m)^\s+environment:\n\s+name: (\S+)$", self.text), [ENVIRONMENT])

    def test_it_uploads_with_trusted_publishing_and_no_token(self):
        self.assertEqual(self.text.count("id-token: write"), 1)
        self.assertRegex(self.text, r"(?m)^permissions:\n  contents: read\n")
        self.assertNotIn("contents: write", self.text)
        for token in ("password:", "secrets.", "PYPI_TOKEN", "TWINE_"):
            self.assertNotIn(token, self.code)
        self.assertEqual(len(re.findall(rf"uses:\s*{PUBLISH_ACTION}@", self.text)), 1)

    def test_it_uploads_the_released_wheel_alone_after_checking_it(self):
        """The wheel and SHA256SUMS come from the release that was published; the wheel is checked against them and
        is the only file in the folder the upload reads. Nothing is built again (the release's own bytes go to PyPI),
        and the release folder (.tar.gz) and agentcake.pyz are no packages PyPI takes."""
        download = re.search(r"gh release download .+", self.text)
        self.assertTrue(download, "the release's files are downloaded")
        for pattern in ('--pattern "*.whl"', "--pattern SHA256SUMS"):
            self.assertIn(pattern, download.group(0))
        self.assertIn("SHA256SUMS | sha256sum -c", self.text)
        self.assertLess(self.text.index("sha256sum -c"), self.text.index(f"uses: {PUBLISH_ACTION}@"))
        self.assertRegex(self.text, r"(?m)^\s+packages-dir: dist$")
        self.assertIn("mv release/*.whl dist/", self.text)
        for other in ("tools/release.py", "tar.gz", ".pyz", "skip-existing"):
            self.assertNotIn(other, self.code)

    def test_every_action_is_pinned_by_commit(self):
        uses = re.findall(r"uses:\s*(\S+)", self.text)
        self.assertTrue(uses)
        for action in uses:
            self.assertRegex(action, r"^[\w-]+/[\w-]+@[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main()
