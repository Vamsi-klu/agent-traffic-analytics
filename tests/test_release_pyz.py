"""tools/releasing/pyz.py and pyz_main.py: `python3 agentcake.pyz <command>` unpacks the package once
into <CAKE_HOME>/pyz/<version>-<hash>/, runs it from there in the same process with sys.argv[0] the .pyz's full path
(paths.launcher reads it), and the real package answers --version, and on an older Python says which it needs.

    python3 -I -m unittest discover -s tests -v      (from the repository root)
"""
import ast
import json
import os
import shutil
import subprocess
import sys
import unittest
import zipfile

from release_trees import ROOT, VERSION, make_tree, scratch, settings

import agentcake  # noqa: E402  (release_trees puts the repository on sys.path)
from tools.releasing import pyz
from tools.releasing.project import Project

EPOCH = 1794528000  # 2026-11-12 00:00:00 UTC, a made-up commit time
OLDEST_GRAMMAR = (3, 6)  # the oldest grammar ast can check; the bootstrap must parse on every Python 3 near it
REPORTING_MAIN = '''import json, os, sys
import agentcake
if sys.argv[1:] == ["fail"]:
    sys.exit(3)
print(json.dumps({"argv": sys.argv, "package": os.path.dirname(os.path.abspath(agentcake.__file__)),
                  "name": __name__}))
'''
PATHS = 'import os\n\ndef home():\n    return os.path.abspath(os.path.expanduser(os.environ.get("CAKE_HOME") or "~/.cake"))\n'


def bootstrap_source():
    with open(os.path.join(ROOT, "tools", "releasing", "pyz_main.py"), encoding="utf-8") as f:
        return f.read()


def made_up_tree(test, extra=None):
    """A package whose __main__ prints where it runs from (agentcake.paths.home() as the real one has it)."""
    files = {"agentcake/__main__.py": REPORTING_MAIN, "agentcake/paths.py": PATHS,
             "tools/releasing/pyz_main.py": bootstrap_source()}
    return make_tree(test, {**files, **(extra or {})})


def run(path, *args, home, python=sys.executable, flags=()):
    return subprocess.run([python, *flags, path, *args], capture_output=True, text=True,
                          env=dict(os.environ, CAKE_HOME=home), cwd=os.path.dirname(path))


class Bootstrap(unittest.TestCase):
    def setUp(self):
        self.tree = made_up_tree(self)
        self.path = pyz.build(Project(self.tree, settings()), scratch(self), EPOCH, settings())
        self.home = os.path.join(scratch(self), "cake home")
        self.unpack_root = os.path.join(self.home, settings()["pyz"]["unpack_folder"])

    def report(self, *args, flags=()):
        out = run(self.path, *args, home=self.home, flags=flags)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_the_file_is_executable_and_starts_with_the_shebang(self):
        self.assertTrue(os.access(self.path, os.X_OK))
        with open(self.path, "rb") as f:
            self.assertEqual(f.readline(), (settings()["pyz"]["shebang"] + "\n").encode())

    def test_the_package_runs_from_the_unpacked_folder_with_argv0_the_pyz(self):
        report = self.report("status", "--json")
        (build,) = os.listdir(self.unpack_root)
        self.assertTrue(build.startswith(f"{VERSION}-"))
        self.assertEqual(report["package"], os.path.join(self.unpack_root, build, "agentcake"))
        self.assertEqual(report["argv"], [os.path.abspath(self.path), "status", "--json"])
        self.assertEqual(report["name"], "__main__")

    def test_a_second_run_uses_the_same_folder_without_unpacking_again(self):
        self.report()
        (build,) = os.listdir(self.unpack_root)
        stamp = os.stat(os.path.join(self.unpack_root, build, "agentcake", "cli.py")).st_mtime_ns
        self.report()
        self.assertEqual(os.listdir(self.unpack_root), [build])
        self.assertEqual(os.stat(os.path.join(self.unpack_root, build, "agentcake", "cli.py")).st_mtime_ns, stamp)

    def test_isolated_mode_runs_it_too(self):
        self.assertEqual(self.report(flags=("-I",))["name"], "__main__")

    def test_the_exit_status_is_the_commands(self):
        self.assertEqual(run(self.path, "fail", home=self.home).returncode, 3)

    def test_other_contents_unpack_into_another_folder(self):
        self.report()
        other_tree = made_up_tree(self, {"agentcake/extra.py": "EXTRA = 1\n"})
        other = pyz.build(Project(other_tree, settings()), scratch(self), EPOCH, settings())
        self.assertEqual(run(other, home=self.home).returncode, 0)
        self.assertEqual(len(os.listdir(self.unpack_root)), 2)

    def test_the_same_tree_gives_the_same_bytes(self):
        again = pyz.build(Project(self.tree, settings()), scratch(self), EPOCH, settings())
        with open(self.path, "rb") as one, open(again, "rb") as two:
            self.assertEqual(one.read(), two.read())

    def test_the_bootstrap_parses_with_an_old_python_grammar(self):
        ast.parse(bootstrap_source(), feature_version=OLDEST_GRAMMAR)


class Licence(unittest.TestCase):
    """The .pyz carries the project's license files at its top, as the wheel (.dist-info/licenses/) and the release
    folder do; they are not unpacked, and they do not change the folder the package is unpacked into."""

    def build(self, files=None):
        return pyz.build(Project(made_up_tree(self, files), settings()), scratch(self), EPOCH, settings())

    def test_the_license_files_are_at_the_top_of_the_zip(self):
        path = self.build({"LICENSE": "made-up licence text\n", "NOTICE": "made-up notice\n"})
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            self.assertEqual(archive.read("LICENSE"), b"made-up licence text\n")
        self.assertEqual(names[:3], [pyz.MAIN, "LICENSE", "NOTICE"])

    def test_they_are_not_unpacked_and_leave_the_unpack_folder_as_it_was(self):
        home = os.path.join(scratch(self), "cake home")
        for path in (self.build(), self.build({"LICENSE": "made-up licence text\n"})):
            self.assertEqual(run(path, home=home).returncode, 0)
        folder, = os.listdir(os.path.join(home, settings()["pyz"]["unpack_folder"]))
        self.assertEqual(os.listdir(os.path.join(home, settings()["pyz"]["unpack_folder"], folder)), ["agentcake"])


class RealPackage(unittest.TestCase):
    def setUp(self):
        self.path = pyz.build(Project(ROOT, settings()), scratch(self), EPOCH, settings())
        self.home = scratch(self)

    def test_the_repositorys_license_files_are_in_it(self):
        with zipfile.ZipFile(self.path) as archive:
            names = archive.namelist()
        for name in ("LICENSE", "THIRD_PARTY.md"):
            self.assertIn(name, names)

    def test_version(self):
        out = run(self.path, "--version", home=self.home)
        self.assertEqual((out.returncode, out.stdout.strip()), (0, f"agentcake {agentcake.__version__}"))

    def test_version_and_help_come_from_the_zip_and_leave_no_data_folder(self):
        """A coding agent's sandbox (Codex workspace-write) cannot write CAKE_HOME; checking the version must
        work there all the same, and must not make the data folder anywhere."""
        locked = os.path.join(self.home, "read-only")
        os.makedirs(locked)
        os.chmod(locked, 0o555)
        self.addCleanup(os.chmod, locked, 0o755)
        home = os.path.join(locked, "cake")
        for args, expected in ((["--version"], f"agentcake {agentcake.__version__}"), (["help"], "Commands:"),
                               (["--help"], "Commands:")):
            out = run(self.path, *args, home=home)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn(expected, out.stdout)
        self.assertEqual(os.listdir(locked), [])

    def test_an_older_python_is_told_which_python_is_needed(self):
        older = shutil.which("python3.9") or "/usr/bin/python3"
        if not os.path.exists(older):
            self.skipTest("no older Python on this computer")
        version = subprocess.run([older, "-c", "import sys; print(sys.version_info[:2] < (3, 11))"],
                                 capture_output=True, text=True).stdout.strip()
        if version != "True":
            self.skipTest(f"{older} is not older than 3.11")
        out = run(self.path, "--version", home=self.home, python=older)
        self.assertEqual(out.returncode, 1)
        self.assertIn("3.11", out.stderr)
        self.assertNotIn("Traceback", out.stderr)


if __name__ == "__main__":
    unittest.main()
