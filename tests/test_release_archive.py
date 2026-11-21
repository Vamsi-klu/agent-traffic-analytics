"""tools/releasing/archive.py: the release folder holds what pyproject.toml's [tool.flit.sdist] names,
the package, PKG-INFO and the wheel in dist/; the real one has what a server install needs, leaves tests and tools
out, and its bin/agentcake runs.

    python3 -I -m unittest discover -s tests -v      (from the repository root)
"""
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest

from release_trees import ROOT, VERSION, edit_pyproject, make_tree, scratch, settings

import agentcake  # noqa: E402  (release_trees puts the repository on sys.path)
from tools.releasing import archive, wheel
from tools.releasing.project import Project
from tools.releasing.settings import ReleaseError

EPOCH = 1794528000  # 2026-11-12 00:00:00 UTC, a made-up commit time
TOP = f"agentcake-{VERSION}"
# Every file of the release folder besides the package (test_release_contents.py) and the wheel in dist/, with who
# uses it where AgentCake is installed: a file nobody uses has no place on people's servers.
BESIDE_THE_PACKAGE = {
    ".dockerignore": "docker build: only the wheel goes into the image",
    "AGENTS.md": "the coding agent that installs AgentCake from this folder",
    "Dockerfile": "docker build, and docker compose (SERVER.md)",
    "INSTALL.md": "the install steps AGENTS.md sends that coding agent to",
    "LICENSE": "the licence",
    "PKG-INFO": "pip, for which the folder is a source distribution",
    "PRIVACY.md": "what AgentCake records, which the commands and the pages point to",
    "README.md": "the folder's own description",
    "SERVER.md": "installing AgentCake on a server",
    "THIRD_PARTY.md": "the notices of what AgentCake carries of others",
    "bin/agentcake": "running AgentCake from the folder (INSTALL.md)",
    "deploy/Caddyfile": "Caddy in front of AgentCake on its own subdomain (docker-compose.yml, SERVER.md)",
    "deploy/cake.service": "systemd (SERVER.md)",
    "docker-compose.yml": "AgentCake and Caddy on a server, `docker compose up -d` (SERVER.md)",
    "docs/Caddyfile.example": "Caddy's log lines that `agentcake logs import` reads (SERVER.md)",
    "docs/FAQ.md": "answers to common questions (README.md)",
    "docs/apache.conf.example": "Apache's log lines that `agentcake logs import` reads (SERVER.md)",
    "docs/collect-format.md": "what an upload holds (PRIVACY.md)",
    "docs/hosting.md": "what AgentCake needs and what it costs on each hosting platform (SERVER.md)",
    "docs/locales/zh-CN/README.md": "README.md in Chinese",
    "docs/nginx.conf.example": "nginx's log lines that `agentcake logs import` reads (SERVER.md)",
    "docs/privacy-notice-template.md": "the privacy notice a website adapts (INSTALL.md, PRIVACY.md)",
    "pyproject.toml": "pip, building the wheel from the folder",
}


def build(test, tree):
    project, out = Project(tree, settings()), scratch(test)
    wheel_path = wheel.build(project, out, EPOCH, settings())
    return archive.build(project, out, EPOCH, settings(), wheel_path), wheel_path


class Chosen(unittest.TestCase):
    def test_include_and_exclude_patterns_choose_the_files(self):
        tree = make_tree(self, {"bin/__pycache__/x.pyc": "x", "notes.txt": "not included\n"})
        self.assertEqual(archive.chosen_files(Project(tree, settings()), settings()),
                         ["README.md", "SERVER.md", "bin/agentcake", "pyproject.toml"])

    def test_license_files_come_along(self):
        tree = make_tree(self, {"LICENSE": "made-up licence text\n"})
        self.assertIn("LICENSE", archive.chosen_files(Project(tree, settings()), settings()))

    def test_an_include_pattern_that_matches_nothing_stops_the_release(self):
        tree = make_tree(self)
        edit_pyproject(tree, '"SERVER.md"', '"SERVER.md", "deploy/"')
        with self.assertRaisesRegex(ReleaseError, "deploy/"):
            archive.chosen_files(Project(tree, settings()), settings())


class Built(unittest.TestCase):
    def setUp(self):
        self.path, self.wheel_path = build(self, make_tree(self))
        self.tar = tarfile.open(self.path)
        self.addCleanup(self.tar.close)
        self.members = {m.name: m for m in self.tar.getmembers()}

    def test_one_top_folder_named_after_the_version(self):
        self.assertEqual(os.path.basename(self.path), f"{TOP}.tar.gz")
        self.assertTrue(all(name == TOP or name.startswith(TOP + "/") for name in self.members))

    def test_files_folders_and_modes(self):
        names = [name for name, member in self.members.items() if member.isfile()]
        self.assertEqual(names, [f"{TOP}/{n}" for n in [
            "PKG-INFO", "README.md", "SERVER.md", "agentcake/__init__.py", "agentcake/cli.py",
            "agentcake/data/product.json", "bin/agentcake", f"dist/agentcake-{VERSION}-py3-none-any.whl",
            "pyproject.toml"]])
        self.assertEqual(self.members[f"{TOP}/bin/agentcake"].mode, 0o755)
        self.assertEqual(self.members[f"{TOP}/README.md"].mode, 0o644)
        self.assertTrue(self.members[f"{TOP}/agentcake/data"].isdir())

    def test_pkg_info_is_the_metadata_and_the_wheel_is_the_same_file(self):
        self.assertEqual(self.tar.extractfile(f"{TOP}/PKG-INFO").read().decode(),
                         Project(make_tree(self), settings()).metadata())
        with open(self.wheel_path, "rb") as f:
            self.assertEqual(self.tar.extractfile(f"{TOP}/dist/{os.path.basename(self.wheel_path)}").read(), f.read())


class RealReleaseFolder(unittest.TestCase):
    """The repository's own release folder, built once for these tests."""

    @classmethod
    def setUpClass(cls):
        out = tempfile.mkdtemp(prefix="agentcake-release-out-")
        cls.addClassCleanup(shutil.rmtree, out, True)
        project = Project(ROOT, settings())
        cls.path = archive.build(project, out, EPOCH, settings(), wheel.build(project, out, EPOCH, settings()))
        cls.top = project.sdist_base()
        with tarfile.open(cls.path) as tar:
            cls.names = {m.name[len(cls.top) + 1:] for m in tar.getmembers() if m.isfile()}

    def test_it_has_what_a_server_install_needs(self):
        for name in ("Dockerfile", ".dockerignore", "docker-compose.yml", "deploy/Caddyfile", "SERVER.md",
                     "deploy/cake.service", "INSTALL.md", "PRIVACY.md", "LICENSE", "THIRD_PARTY.md", "bin/agentcake",
                     "docs/collect-format.md", "PKG-INFO"):
            self.assertIn(name, self.names)
        self.assertIn(f"dist/{Project(ROOT, settings()).wheel_name()}", self.names)

    def test_bin_agentcake_is_its_only_way_to_run_agentcake(self):
        """bin/cake and cake.py, cake 0.3.x's command and entry point, are not in the folder."""
        self.assertEqual(sorted(self.names & {"bin/cake", "cake.py"}), [])

    def test_beside_the_package_and_its_wheel_it_holds_only_files_someone_uses(self):
        wheel_file = f"dist/{Project(ROOT, settings()).wheel_name()}"
        beside = {name for name in self.names if not name.startswith("agentcake/")} - {wheel_file}
        self.assertEqual(sorted(beside), sorted(BESIDE_THE_PACKAGE))

    def test_tests_tools_web_sources_and_eval_stay_out(self):
        for folder in ("tests/", "tools/", "web/", "eval/", "edge/"):
            self.assertFalse([n for n in self.names if n.startswith(folder)], folder)

    def test_readmes_pictures_stay_out_while_the_rest_of_docs_comes_along(self):
        """docs/assets/ holds README's icon and screenshots, for the repository's page on GitHub only."""
        self.assertFalse([n for n in self.names if n.startswith("docs/assets/")])
        self.assertIn("README.md", self.names)
        self.assertIn("docs/collect-format.md", self.names)

    def test_bin_agentcake_of_the_unpacked_folder_runs(self):
        out = scratch(self)
        with tarfile.open(self.path) as tar:
            tar.extractall(out, filter="data")
        env = dict(os.environ, CAKE_HOME=scratch(self))
        done = subprocess.run([os.path.join(out, self.top, "bin", "agentcake"), "--version"], capture_output=True,
                              text=True, env=env)
        self.assertEqual((done.returncode, done.stdout.strip()), (0, f"agentcake {agentcake.__version__}"))


if __name__ == "__main__":
    unittest.main()
