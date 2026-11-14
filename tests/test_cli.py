"""The command line, the way people run it (S1.1): start, status, ping, doctor, stop and --version, and the 0.3.x
entry points (bin/cake, cake.py) that existing installs and older deploy/cake.service files still use. A Python
older than Agent Cake needs gets a sentence saying so from every entry point (M1 clean-up).

    python3 -I -m unittest discover -s tests -v      (from the Agent Cake folder)

Every command runs in its own process against a scratch CAKE_HOME and a free port, never the user's ~/.cake. Each
command imports its own module when it runs (M4 clean-up): `--version` loads only the settings, the words and the paths,
and the commands that need no database load no storage, judging or server.
"""
import json, os, shutil, socket, subprocess, sys, tempfile, tomllib, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import agentcake  # noqa: E402
from agentcake import wording  # noqa: E402
from cake_server import free_port, pages_stub  # noqa: E402

MAIN_FILE = os.path.join(ROOT, "agentcake", "__main__.py")
AGENTCAKE = [sys.executable, "-I", MAIN_FILE]  # what bin/agentcake runs
LEGACY_FILE = os.path.join(ROOT, "cake.py")
LEGACY = [sys.executable, "-I", LEGACY_FILE]
VERSION_LINE = f"agentcake {agentcake.__version__}"
OLD_PYTHON = (3, 10, 4, "final", 0)  # one minor version below the 3.11 that pyproject.toml asks for
# What every command needs: the command line itself, the settings, the shipped data files, the words and the paths.
CORE = {"agentcake", "agentcake.cli", "agentcake.config", "agentcake.datafiles", "agentcake.paths", "agentcake.units",
        "agentcake.wording"}
# The database, the judging and the server: whatever loads one of them loads them through these.
HEAVY = {"agentcake.store", "agentcake.streams", "agentcake.judging", "agentcake.server"}
# Runs one command through cli.main in a fresh Python, then writes the agentcake modules it imported to a file.
IMPORTS_PROBE = """\
import json, sys
sys.path.insert(0, sys.argv[1])
from agentcake import cli
cli.main(sys.argv[3:])
with open(sys.argv[2], "w", encoding="utf-8") as f:
    json.dump(sorted(name for name in sys.modules if name.split(".")[0] == "agentcake"), f)
"""


def scratch_env():
    """Environment for one cake of its own: a new CAKE_HOME, a free port, and local pages to serve."""
    return dict(os.environ, CAKE_HOME=tempfile.mkdtemp(prefix="agentcake-cli-"), CAKE_PORT=str(free_port()),
                CAKE_WEB_DIR=pages_stub())


def run(command, env, *args, cwd=None):
    return subprocess.run(command + list(args), env=env, cwd=cwd, capture_output=True, text=True)


class Version(unittest.TestCase):
    def setUp(self):
        self.env = scratch_env()
        self.addCleanup(shutil.rmtree, self.env["CAKE_HOME"], True)

    def test_version_flag_prints_the_package_version(self):
        out = run(AGENTCAKE, self.env, "--version")
        self.assertEqual((out.returncode, out.stdout.strip()), (0, VERSION_LINE))

    def test_python_dash_m_runs_the_package(self):
        # -m finds agentcake on sys.path: here the current folder; for an installed wheel, site-packages
        out = run([sys.executable, "-m", "agentcake"], self.env, "--version", cwd=ROOT)
        self.assertEqual((out.returncode, out.stdout.strip()), (0, VERSION_LINE))

    def test_bin_agentcake_launcher(self):
        out = run([os.path.join(ROOT, "bin", "agentcake")], self.env, "--version")
        self.assertEqual((out.returncode, out.stdout.strip()), (0, VERSION_LINE))

    def test_bin_cake_forwards_to_bin_agentcake(self):
        out = run([os.path.join(ROOT, "bin", "cake")], self.env, "--version")
        self.assertEqual((out.returncode, out.stdout.strip()), (0, VERSION_LINE))


class CommandsImportWhatTheyRun(unittest.TestCase):
    """Every command is a Python process of its own: importing every command's module made each of them, --version
    too, load the server, the judging and the storage first (M2 clean-up: 0.35 s of a 0.7 s start)."""

    def setUp(self):
        self.env = scratch_env()
        self.addCleanup(shutil.rmtree, self.env["CAKE_HOME"], True)

    def modules_after(self, *args):
        listing = os.path.join(self.env["CAKE_HOME"], "modules.json")
        out = subprocess.run([sys.executable, "-I", "-c", IMPORTS_PROBE, ROOT, listing, *args], env=self.env,
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        with open(listing, encoding="utf-8") as f:
            return set(json.load(f))

    def test_version_loads_only_the_settings_the_words_and_the_paths(self):
        self.assertEqual(self.modules_after("--version"), CORE)

    def test_commands_that_need_no_database_load_no_storage_judging_or_server(self):
        for args in (["help"], ["status"], ["stop"], ["config", "get"], ["secret", "print"], ["snippet"],
                     ["sentence"], ["setup", "--print"], ["logs", "formats"]):
            with self.subTest(command=" ".join(args)):
                self.assertEqual(self.modules_after(*args) & HEAVY, set())


class Lifecycle(unittest.TestCase):
    """One cake started with `start` and checked with status, ping and doctor; stopped afterwards."""

    @classmethod
    def setUpClass(cls):
        cls.env = scratch_env()
        cls.started = run(AGENTCAKE, cls.env, "start")

    @classmethod
    def tearDownClass(cls):
        run(AGENTCAKE, cls.env, "stop")
        shutil.rmtree(cls.env["CAKE_HOME"], ignore_errors=True)

    def test_start_names_the_local_page(self):
        self.assertEqual(self.started.returncode, 0, self.started.stdout)
        self.assertIn(f"http://127.0.0.1:{self.env['CAKE_PORT']}/", self.started.stdout)

    def test_status_prints_the_health_answer(self):
        out = run(AGENTCAKE, self.env, "status")
        self.assertEqual(out.returncode, 0, out.stdout)
        health = json.loads(out.stdout)
        self.assertTrue(health["ok"])
        self.assertEqual(health["version"], agentcake.__version__)
        self.assertEqual(health["home"], self.env["CAKE_HOME"])

    def test_doctor_passes_after_ping(self):
        self.assertEqual(run(AGENTCAKE, self.env, "ping").returncode, 0)
        out = run(AGENTCAKE, self.env, "doctor")
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertNotIn("[FAIL]", out.stdout)


class Stop(unittest.TestCase):
    def test_stop_ends_the_background_cake(self):
        env = scratch_env()
        self.addCleanup(shutil.rmtree, env["CAKE_HOME"], True)
        self.assertEqual(run(AGENTCAKE, env, "start").returncode, 0)
        self.assertEqual(run(AGENTCAKE, env, "stop").returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(env["CAKE_HOME"], "cake.pid")))
        self.assertEqual(run(AGENTCAKE, env, "status").returncode, 1)

    def test_stop_returns_once_the_cake_has_exited_and_left_its_port(self):
        """S6.6: stop said "stopped" right after asking, while the server still ran for about half a second, so a
        start straight after could find the port taken."""
        env = scratch_env()
        self.addCleanup(shutil.rmtree, env["CAKE_HOME"], True)
        self.assertEqual(run(AGENTCAKE, env, "start").returncode, 0)
        with open(os.path.join(env["CAKE_HOME"], "cake.pid")) as f:
            pid = int(f.read())
        self.assertEqual(run(AGENTCAKE, env, "stop").returncode, 0)
        with self.assertRaises(ProcessLookupError, msg="the server still runs"):
            os.kill(pid, 0)  # signal 0: no signal, only whether the process exists
        with socket.socket() as listener:  # as the server binds it (http.server: SO_REUSEADDR)
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", int(env["CAKE_PORT"])))


class LegacyEntryPoint(unittest.TestCase):
    """`python3 cake.py <command>`, the way 0.3.x installs and older deploy/cake.service files start cake."""

    def test_cake_py_starts_reports_and_stops(self):
        env = scratch_env()
        self.addCleanup(shutil.rmtree, env["CAKE_HOME"], True)
        started = run(LEGACY, env, "start")
        self.addCleanup(run, LEGACY, env, "stop")
        self.assertEqual(started.returncode, 0, started.stdout)
        self.assertEqual(json.loads(run(LEGACY, env, "status").stdout)["version"], agentcake.__version__)


def run_in_python(version_info, entry, env, *args):
    """entry run as a script, as bin/agentcake runs __main__.py, by a Python that says it is version_info: the
    version is replaced before the entry's first line runs, so whatever the entry imports sees it too."""
    code = (f"import runpy, sys; sys.version_info = {version_info!r}; sys.argv = [{entry!r}, *{list(args)!r}]; "
            f"runpy.run_path({entry!r}, run_name='__main__')")
    return subprocess.run([sys.executable, "-I", "-c", code], env=env, capture_output=True, text=True)


class OlderPython(unittest.TestCase):
    """Agent Cake needs the Python that data/product.json names (pyproject.toml's requires-python says the same)."""

    def setUp(self):
        self.env = scratch_env()
        self.addCleanup(shutil.rmtree, self.env["CAKE_HOME"], True)

    def assert_told_to_upgrade(self, out):
        self.assertEqual((out.returncode, out.stdout), (1, ""), out.stderr)
        self.assertNotIn("Traceback", out.stderr)
        self.assertIn(f"Python {wording.product()['python']} or newer", out.stderr)
        self.assertIn("3.10.4", out.stderr)  # the version in use, so the reader knows which Python is too old
        self.assertEqual(os.listdir(self.env["CAKE_HOME"]), [])  # the command itself never ran

    def test_bin_agentcake_entry_says_to_upgrade(self):
        self.assert_told_to_upgrade(run_in_python(OLD_PYTHON, MAIN_FILE, self.env, "--version"))

    def test_cake_py_entry_says_to_upgrade(self):
        self.assert_told_to_upgrade(run_in_python(OLD_PYTHON, LEGACY_FILE, self.env, "doctor"))

    def test_the_minimum_version_runs(self):
        minimum = tuple(int(part) for part in wording.product()["python"].split("."))
        out = run_in_python((*minimum, 0, "final", 0), MAIN_FILE, self.env, "--version")
        self.assertEqual((out.returncode, out.stdout.strip()), (0, VERSION_LINE), out.stderr)

    def test_pyproject_requires_the_same_python(self):
        with open(os.path.join(ROOT, "pyproject.toml"), "rb") as f:
            requires = tomllib.load(f)["project"]["requires-python"]
        self.assertEqual(requires, ">=" + wording.product()["python"])


if __name__ == "__main__":
    unittest.main()
