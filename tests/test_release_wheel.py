"""tools/releasing/wheel.py: a wheel of the package with METADATA, WHEEL, entry_points.txt and a RECORD
that matches every file; the same tree gives the same bytes; pip installs the real one and its command runs.

    python3 -I -m unittest discover -s tests -v      (from the repository root)
"""
import base64
import csv
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

from release_trees import ROOT, VERSION, make_tree, scratch, settings

import agentcake  # noqa: E402  (release_trees puts the repository on sys.path)
from agentcake import cli, wording
from tools.releasing import wheel
from tools.releasing.project import Project

EPOCH = 1794528000  # 2026-11-12 00:00:00 UTC, a made-up commit time
DIST_INFO = f"agentcake-{VERSION}.dist-info"


def build(test, tree):
    return wheel.build(Project(tree, settings()), scratch(test), EPOCH, settings())


class Contents(unittest.TestCase):
    def setUp(self):
        self.path = build(self, make_tree(self, {"agentcake/__pycache__/cli.cpython-314.pyc": "x",
                                                 "LICENSE": "made-up licence text\n"}))
        self.zip = zipfile.ZipFile(self.path)
        self.addCleanup(self.zip.close)

    def test_the_file_name_follows_the_format(self):
        self.assertEqual(os.path.basename(self.path), f"agentcake-{VERSION}-py3-none-any.whl")

    def test_the_package_comes_first_and_record_last(self):
        self.assertEqual(self.zip.namelist(), [
            "agentcake/__init__.py", "agentcake/cli.py", "agentcake/data/product.json",
            f"{DIST_INFO}/METADATA", f"{DIST_INFO}/WHEEL", f"{DIST_INFO}/entry_points.txt",
            f"{DIST_INFO}/licenses/LICENSE", f"{DIST_INFO}/RECORD"])

    def test_wheel_says_pure_python_for_any_platform(self):
        lines = self.zip.read(f"{DIST_INFO}/WHEEL").decode().splitlines()
        self.assertIn("Wheel-Version: 1.0", lines)
        self.assertIn("Root-Is-Purelib: true", lines)
        self.assertIn("Tag: py3-none-any", lines)

    def test_record_lists_every_file_with_its_hash_and_size(self):
        rows = list(csv.reader(io.StringIO(self.zip.read(f"{DIST_INFO}/RECORD").decode())))
        self.assertEqual([row[0] for row in rows], self.zip.namelist())
        self.assertEqual(rows[-1], [f"{DIST_INFO}/RECORD", "", ""])
        for name, digest, size in rows[:-1]:
            data = self.zip.read(name)
            expected = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
            self.assertEqual((digest, int(size)), (f"sha256={expected}", len(data)), name)

    def test_metadata_is_the_projects(self):
        metadata = self.zip.read(f"{DIST_INFO}/METADATA").decode()
        self.assertTrue(metadata.startswith("Metadata-Version: 2.4\nName: agentcake\n"))
        self.assertIn("License-File: LICENSE\n", metadata)


class Reproducible(unittest.TestCase):
    def test_the_same_tree_gives_the_same_bytes(self):
        tree = make_tree(self)
        with open(build(self, tree), "rb") as one, open(build(self, tree), "rb") as two:
            self.assertEqual(one.read(), two.read())


class RealLicence(unittest.TestCase):
    """The repository's own wheel carries LICENSE and THIRD_PARTY.md, and its metadata names the licence."""

    def test_the_licence_files_and_expression_are_in_the_wheel(self):
        project = Project(ROOT, settings())
        self.assertIn("LICENSE", project.license_files())
        with zipfile.ZipFile(build(self, ROOT)) as archive:
            names = archive.namelist()
            metadata = archive.read(f"{project.dist_info()}/METADATA").decode()
        for name in project.license_files():
            self.assertIn(f"{project.dist_info()}/licenses/{name}", names)
            self.assertIn(f"License-File: {name}\n", metadata)
        self.assertIn(f"License-Expression: {project.table['license']}\n", metadata)


class Installs(unittest.TestCase):
    """The real package, installed by pip into a scratch environment, run from a folder that is not a checkout."""

    @classmethod
    def setUpClass(cls):
        if subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True).returncode != 0:
            raise unittest.SkipTest("this Python has no pip")
        cls.folder = tempfile.mkdtemp(prefix="agentcake-release-venv-")
        cls.addClassCleanup(shutil.rmtree, cls.folder, True)
        path = wheel.build(Project(ROOT, settings()), cls.folder, EPOCH, settings())
        venv = os.path.join(cls.folder, "venv")
        subprocess.run([sys.executable, "-m", "venv", "--without-pip", venv], check=True)
        installed = subprocess.run([sys.executable, "-m", "pip", "--python", os.path.join(venv, "bin", "python"),
                                    "install", "--no-index", "--no-deps", "--disable-pip-version-check", path],
                                   capture_output=True, text=True)
        if installed.returncode != 0:
            raise AssertionError(installed.stderr)
        cls.command = os.path.join(venv, "bin", "agentcake")

    def agentcake(self, *args):
        home = scratch(self)
        return subprocess.run([self.command, *args], capture_output=True, text=True,
                              env=dict(os.environ, CAKE_HOME=home), cwd=home)

    def test_the_command_runs(self):
        out = self.agentcake("--version")
        self.assertEqual((out.returncode, out.stdout.strip()), (0, f"agentcake {agentcake.__version__}"))

    def test_eval_says_it_runs_from_a_checkout(self):
        """The evaluation stays in the checkout with its data sets (release.json "package_files"): the installed
        command says where it runs, for --help too."""
        for args in (("eval",), ("eval", "--help")):
            out = self.agentcake(*args)
            self.assertEqual((out.returncode, out.stderr.strip()), (cli.EXIT_USAGE, wording.text("eval_from_checkout")))
            self.assertIn("bin/agentcake eval", out.stderr)


if __name__ == "__main__":
    unittest.main()
