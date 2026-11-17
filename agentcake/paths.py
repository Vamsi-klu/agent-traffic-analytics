"""Where AgentCake's files are: the data folder $CAKE_HOME and the files that ship inside the package.

Data lives in $CAKE_HOME (default ~/.cake, the folder 0.3.x used): config.json, cake.db, cake.pid, cake.log and
srv_secret are named here; replays/ (replay_chunks.py) and lists/ (detect/lists.py, `agentcake lists update`) sit next
to them. The functions read $CAKE_HOME on every call instead of once at import, so a test, or a process started with
another CAKE_HOME, gets its own folder without reloading anything. The package's own files (static/, data/, schema.sql)
sit next to this module, wherever the package was installed. launcher() is the command people are told to run, whichever
way this copy was installed. The compiled local pages (web/, built with `npm run build`) are found by
web_folder(): $CAKE_WEB_DIR when it is set; else the folder a release carries inside the package (the .pyz's unpacked
copy too); else web/dist next to the package, as a checkout has it (folder names: data/web.json; read here with json,
since datafiles.py reads its files through this module). nearest_existing() is where a folder not made yet would be
made: doctor, before the first start or after the data folder was deleted, asks that one.
"""
import functools
import json
import os
import shlex
import sys
import zipfile

PYZ_ENV = "AGENTCAKE_PYZ"  # the .pyz a run started from, handed to the processes it starts (daemon.start)
COMMAND_ENV = "AGENTCAKE_COMMAND"  # likewise the installed wheel's command a run started from
PYZ_SUFFIX = ".pyz"  # protocol: the file name ending of a Python zip application (zipapp)

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_FILE = os.path.join(PACKAGE_DIR, "__main__.py")
STATIC_DIR = os.path.join(PACKAGE_DIR, "static")
SCHEMA_FILE = os.path.join(PACKAGE_DIR, "schema.sql")
WEB_FILE = os.path.join(PACKAGE_DIR, "data", "web.json")
PRODUCT_FILE = os.path.join(PACKAGE_DIR, "data", "product.json")


def home():
    return os.path.abspath(os.path.expanduser(os.environ.get("CAKE_HOME") or "~/.cake"))


def nearest_existing(path):
    """path, or the nearest path above it that exists."""
    path = os.path.abspath(path)
    while not os.path.exists(path) and os.path.dirname(path) != path:
        path = os.path.dirname(path)
    return path


def archive():
    """The zip the package is imported from, or None. tools/releasing/pyz_main.py runs --version and help from inside
    agentcake.pyz without unpacking it into CAKE_HOME (a coding agent's sandbox may not write there), and the
    package's own files are then read from the zip (datafiles.read)."""
    found = nearest_existing(PACKAGE_DIR)
    return found if found != PACKAGE_DIR and zipfile.is_zipfile(found) else None


def config_file():
    return os.path.join(home(), "config.json")


def db_file():
    return os.path.join(home(), "cake.db")


def pid_file():
    return os.path.join(home(), "cake.pid")


def log_file():
    return os.path.join(home(), "cake.log")


def secret_file():
    return os.path.join(home(), "srv_secret")


def web_folder(package_dir=PACKAGE_DIR):
    """The compiled local pages (not part of the data folder, so not a *_dir like the others here)."""
    if os.environ.get("CAKE_WEB_DIR"):
        return os.path.abspath(os.path.expanduser(os.environ["CAKE_WEB_DIR"]))
    folders = _web_folders()
    released = os.path.join(package_dir, folders["release"])
    if os.path.isdir(released):
        return released
    return os.path.join(os.path.dirname(package_dir), *folders["checkout"])


@functools.lru_cache(maxsize=None)
def _web_folders():
    with open(WEB_FILE, encoding="utf-8") as f:
        return json.load(f)["folders"]


@functools.lru_cache(maxsize=None)
def _command_name():
    """The command's name, data/product.json "command" (read here with json, as data/web.json is)."""
    with open(PRODUCT_FILE, encoding="utf-8") as f:
        return json.load(f)["command"]


def running_pyz():
    """The .pyz AgentCake runs from, by its full path, or None. The .pyz unpacks the package under
    $CAKE_HOME/pyz/ and runs it in the same process, so the script this process was started with is the .pyz; a process
    started from such a run (daemon.start, or a bootstrap that starts a new Python) is told it in $AGENTCAKE_PYZ."""
    for candidate in (sys.argv[0] if sys.argv else "", os.environ.get(PYZ_ENV, "")):
        if candidate.endswith(PYZ_SUFFIX) and zipfile.is_zipfile(candidate):
            return os.path.abspath(candidate)
    return None


def running_command():
    """The `agentcake` command an installed wheel put in its environment's bin folder (pip, pipx, uv), by its full path,
    when this process was started with it, or None. That folder may be on no PATH (uv's often is not), so people are
    told to run the command by this path. A process started from such a run (daemon.start) is told it in
    $AGENTCAKE_COMMAND, since its own argv names agentcake/__main__.py."""
    for candidate in (sys.argv[0] if sys.argv else "", os.environ.get(COMMAND_ENV, "")):
        if os.path.basename(candidate) == _command_name() and os.path.isfile(candidate):
            return os.path.abspath(candidate)
    return None


def bin_script():
    """bin/agentcake of this release folder or checkout, or None (an installed wheel, the .pyz's unpacked copy)."""
    script = os.path.join(os.path.dirname(PACKAGE_DIR), "bin", "agentcake")
    return script if os.path.isfile(script) else None


def launcher():
    """The command people are told to run, a command line that works from any folder: when AgentCake runs from
    its .pyz, this Python and the .pyz, both by their full paths (the unpacked copy has no bin/, `agentcake` may be on
    no PATH, and the python3 on PATH may be too old); bin/agentcake of this release folder or checkout, by its full
    path; an installed wheel's command by its full path (running_command); else the bare command name:
    `python3 -m agentcake` started this run, which SERVER.md's alias and docker exec give that name."""
    pyz = running_pyz()
    if pyz:
        return f"{shlex.quote(sys.executable)} {shlex.quote(pyz)}"
    script = bin_script() or running_command()
    return shlex.quote(script) if script else _command_name()


def tilde(s):
    """Pages show the home folder as ~ (no user name on screen); the shell expands ~ back."""
    h = os.path.expanduser("~")
    return s.replace(h + "/", "~/") if h and h != "/" else s
