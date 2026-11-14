"""paths.launcher(): the command setup, doctor and the pages tell people to run has to run; and
paths.web_folder(): where the compiled local pages are.

    python3 -I -m unittest discover -s tests -p test_paths.py -v      (from the Agent Cake folder)

From a release folder or a checkout it is bin/agentcake by its full path. From the .pyz it is this Python and the .pyz
(the release's bootstrap unpacks the package under $CAKE_HOME/pyz/<version>-<n>/ and runs it in the same process, where `agentcake` may be
on no PATH); a background server started from the .pyz is told the .pyz in $AGENTCAKE_PYZ and says the same. A .pyz
built here the way a release's is (a stand-in bootstrap: unpack, then run in the same process) prints that command in
setup --print, and the command runs. From an installed wheel's `agentcake` (pip, pipx, uv), whose bin folder may be on
no PATH, it is that command by its full path, and the background server is told it in $AGENTCAKE_COMMAND (M4
clean-up); `python3 -m agentcake` (SERVER.md's alias, docker exec) keeps the bare command name, which is what the alias
is called. Every run uses a scratch CAKE_HOME and a free port.

The compiled pages are found in three places, in order: $CAKE_WEB_DIR when it is set; else the folder a release
carries inside the package (agentcake/web/: wheel, .pyz and unpacked release alike); else web/dist next to the
package, as a checkout has it after `npm run build`. Each is checked with a scratch package folder that has the one or
the other.
"""
import contextlib
import io
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipapp
import zipfile
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import agentcake  # noqa: E402
from agentcake import daemon, paths  # noqa: E402
from cake_server import free_port  # noqa: E402

VERSION_LINE = f"agentcake {agentcake.__version__}"
BOOTSTRAP = """\
import os, runpy, sys, zipfile
pyz = os.path.abspath(sys.argv[0])
target = os.path.join(os.environ["CAKE_HOME"], "pyz", "test-1")
if not os.path.isdir(os.path.join(target, "agentcake")):
    with zipfile.ZipFile(pyz) as archive:
        archive.extractall(target, [name for name in archive.namelist() if name.startswith("agentcake/")])
sys.argv[0] = pyz
sys.path[:] = [entry for entry in sys.path if os.path.abspath(entry) != pyz]
sys.path.insert(0, target)
runpy.run_module("agentcake", run_name="__main__", alter_sys=False)
"""  # what the release's bootstrap does: unpack, then agentcake/__main__.py in this process, argv[0] still the .pyz


class Scratch(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.mkdtemp(prefix="agentcake-paths-")
        self.addCleanup(shutil.rmtree, self.scratch, True)
        self.env = dict(os.environ, CAKE_HOME=os.path.join(self.scratch, "home"), CAKE_PORT=str(free_port()))
        self.env.pop(paths.PYZ_ENV, None)

    def build_pyz(self):
        """agentcake.pyz the way a release makes it: the package and a bootstrap that unpacks it and runs it."""
        staging = os.path.join(self.scratch, "staging")
        shutil.copytree(os.path.join(ROOT, "agentcake"), os.path.join(staging, "agentcake"),
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        with open(os.path.join(staging, "__main__.py"), "w", encoding="utf-8") as f:
            f.write(BOOTSTRAP)
        pyz = os.path.join(self.scratch, "downloads", "agentcake.pyz")
        os.makedirs(os.path.dirname(pyz))
        zipapp.create_archive(staging, pyz)
        return pyz


class FromThePyz(Scratch):
    def test_setup_print_names_a_command_that_runs(self):
        pyz = self.build_pyz()
        printed = subprocess.run([sys.executable, pyz, "setup", "--print"], env=self.env, capture_output=True, text=True)
        self.assertEqual(printed.returncode, 0, printed.stderr)
        command = re.search(r"Step 1\. Self-check:  (.+) doctor$", printed.stdout, re.M).group(1)
        self.assertIn(pyz, command)
        ran = subprocess.run(shlex.split(command) + ["--version"], env=self.env, capture_output=True, text=True)
        self.assertEqual((ran.returncode, ran.stdout.strip()), (0, VERSION_LINE), ran.stderr)

    def test_the_package_ran_from_its_unpacked_copy(self):
        pyz = self.build_pyz()
        subprocess.run([sys.executable, pyz, "--version"], env=self.env, capture_output=True, check=True)
        self.assertTrue(os.path.isfile(os.path.join(self.env["CAKE_HOME"], "pyz", "test-1", "agentcake", "cli.py")))


class Launcher(Scratch):
    def test_started_from_a_pyz_it_is_this_python_and_the_pyz(self):
        pyz = self.build_pyz()
        with mock.patch.object(sys, "argv", [pyz, "doctor"]):
            command = paths.launcher()
        self.assertEqual(shlex.split(command), [sys.executable, pyz])

    def test_a_server_started_from_a_pyz_is_told_it(self):
        pyz = self.build_pyz()
        with mock.patch.dict(os.environ, {paths.PYZ_ENV: pyz}), mock.patch.object(sys, "argv", ["__main__.py", "_serve"]):
            self.assertEqual(shlex.split(paths.launcher())[1:], [pyz])

    def test_a_pyz_name_that_is_no_zip_is_not_taken_for_one(self):
        fake = os.path.join(self.scratch, "agentcake.pyz")
        with open(fake, "w", encoding="utf-8") as f:
            f.write("not a zip\n")
        with mock.patch.object(sys, "argv", [fake]), mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(paths.PYZ_ENV, None)
            self.assertEqual(paths.launcher(), shlex.quote(os.path.join(ROOT, "bin", "agentcake")))

    def installed_command(self, folder="venv"):
        """An installed wheel's `agentcake`: a script in an environment's bin folder, beside no bin/agentcake."""
        script = os.path.join(self.scratch, folder, "bin", "agentcake")
        os.makedirs(os.path.dirname(script))
        with open(script, "w", encoding="utf-8") as f:
            f.write(f"#!{sys.executable}\n")
        return script

    def as_installed_wheel(self, argv, **env):
        """paths.launcher() as an installed wheel sees it: no bin/agentcake next to the package, no .pyz."""
        environment = {key: value for key, value in os.environ.items() if key not in (paths.PYZ_ENV, paths.COMMAND_ENV)}
        environment.update(env)
        return [mock.patch.object(paths, "bin_script", return_value=None), mock.patch.object(sys, "argv", argv),
                mock.patch.dict(os.environ, environment, clear=True)]

    def launcher_as_installed_wheel(self, argv, **env):
        with contextlib.ExitStack() as stack:
            for patch in self.as_installed_wheel(argv, **env):
                stack.enter_context(patch)
            return paths.launcher()

    def test_started_as_an_installed_wheels_command_it_is_that_command_by_its_full_path(self):
        script = self.installed_command("uv tools")  # a space in the path is quoted
        self.assertEqual(shlex.split(self.launcher_as_installed_wheel([script, "setup", "--print"])), [script])

    def test_the_command_started_by_a_relative_path_is_named_by_its_full_path(self):
        script = self.installed_command()
        previous = os.getcwd()
        os.chdir(self.scratch)
        self.addCleanup(os.chdir, previous)
        [command] = shlex.split(self.launcher_as_installed_wheel([os.path.join("venv", "bin", "agentcake"), "doctor"]))
        self.assertTrue(os.path.isabs(command), command)
        self.assertTrue(os.path.samefile(command, script))

    def test_a_server_started_from_the_wheels_command_is_told_it(self):
        script = self.installed_command()
        launcher = self.launcher_as_installed_wheel(["__main__.py", "_serve"], **{paths.COMMAND_ENV: script})
        self.assertEqual(launcher, shlex.quote(script))

    def test_python_dash_m_keeps_the_bare_command_name(self):
        main_file = os.path.join(self.scratch, "site-packages", "agentcake", "__main__.py")
        self.assertEqual(self.launcher_as_installed_wheel([main_file, "doctor"]), "agentcake")

    def test_start_hands_the_wheels_command_to_the_background_server(self):
        script = self.installed_command()
        started = mock.Mock(pid=4242)
        with contextlib.ExitStack() as stack:
            for patch in self.as_installed_wheel([script, "start"], CAKE_HOME=self.env["CAKE_HOME"],
                                                 CAKE_PORT=self.env["CAKE_PORT"]):
                stack.enter_context(patch)
            stack.enter_context(mock.patch.object(daemon, "running", side_effect=[None, {"ok": True}]))
            popen = stack.enter_context(mock.patch("subprocess.Popen", return_value=started))
            stack.enter_context(mock.patch("time.sleep"))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            os.makedirs(self.env["CAKE_HOME"], exist_ok=True)
            self.assertEqual(daemon.start(), 0)
        self.assertEqual(popen.call_args.kwargs["env"][paths.COMMAND_ENV], script)

    def test_start_hands_the_pyz_to_the_background_server(self):
        pyz = self.build_pyz()
        started = mock.Mock(pid=4242)
        with mock.patch.dict(os.environ, {"CAKE_HOME": self.env["CAKE_HOME"], "CAKE_PORT": self.env["CAKE_PORT"]}), \
                mock.patch.object(sys, "argv", [pyz, "start"]), \
                mock.patch.object(daemon, "running", side_effect=[None, {"ok": True}]), \
                mock.patch("subprocess.Popen", return_value=started) as popen, \
                mock.patch("time.sleep"), contextlib.redirect_stdout(io.StringIO()):
            os.makedirs(self.env["CAKE_HOME"], exist_ok=True)
            self.assertEqual(daemon.start(), 0)
        self.assertEqual(popen.call_args.kwargs["env"][paths.PYZ_ENV], pyz)



class WebFolder(unittest.TestCase):
    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="cake-paths-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.package = os.path.join(self.root, "agentcake")
        os.makedirs(self.package)
        unset = mock.patch.dict(os.environ)
        unset.start()
        self.addCleanup(unset.stop)
        os.environ.pop("CAKE_WEB_DIR", None)

    def make(self, *parts):
        folder = os.path.join(self.root, *parts)
        os.makedirs(folder)
        return folder

    def test_cake_web_dir_comes_first(self):
        self.make("agentcake", "web")
        chosen = self.make("elsewhere")
        os.environ["CAKE_WEB_DIR"] = chosen
        self.assertEqual(paths.web_folder(self.package), chosen)

    def test_a_release_carries_the_pages_inside_the_package(self):
        inside = self.make("agentcake", "web")
        self.make("web", "dist")
        self.assertEqual(paths.web_folder(self.package), inside)

    def test_a_checkout_has_them_in_web_dist_next_to_the_package(self):
        built = self.make("web", "dist")
        self.assertEqual(paths.web_folder(self.package), built)


class Archive(unittest.TestCase):
    """paths.archive(): the .pyz the package is imported from, when the bootstrap runs a command from the zip
    without unpacking it (--version, help), so that the package's files are read from inside it."""

    def test_a_package_in_a_folder_is_in_no_archive(self):
        self.assertIsNone(paths.archive())

    def test_a_package_imported_from_a_zip_names_the_zip(self):
        folder = os.path.realpath(tempfile.mkdtemp(prefix="cake-paths-"))
        self.addCleanup(shutil.rmtree, folder, True)
        archive = os.path.join(folder, "agentcake.pyz")
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr("agentcake/__init__.py", "")
        with mock.patch.object(paths, "PACKAGE_DIR", os.path.join(archive, "agentcake")):
            self.assertEqual(paths.archive(), archive)
        with mock.patch.object(paths, "PACKAGE_DIR", os.path.join(folder, "gone", "agentcake")):
            self.assertIsNone(paths.archive())


if __name__ == "__main__":
    unittest.main()
