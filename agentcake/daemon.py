"""Running cake in the background (S1.1): `start`, `stop`, and running(), the health check behind `status`.

start() launches `python3 -I agentcake/__main__.py _serve` detached from the terminal, logging to $CAKE_HOME/cake.log,
writes its pid to $CAKE_HOME/cake.pid and waits up to start_wait_s until the local page answers. stop() asks that
process to end (SIGTERM) and returns once it has exited, waiting up to stop_wait_s (S6.6: it used to say "stopped" right
after asking, while the server still ran for about half a second, so a start straight after could find the port
taken); one that has not exited by then is reported and keeps its pid file. running() returns the /api/health answer
of the server on the configured port, or None; running_here() says whether that server keeps its data in this
$CAKE_HOME, which `migrate` and `delete` must know (it writes the same files). Started from the .pyz, the server is told
the .pyz in $AGENTCAKE_PYZ, and from an installed wheel's command that command in $AGENTCAKE_COMMAND, so the commands
its pages name run (paths.launcher, S6.1).
"""
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request

from agentcake import paths
from agentcake.config import base_url, ensure_cfg, load_cfg
from agentcake.wording import text


def running():
    c = load_cfg()
    try:
        with urllib.request.urlopen(base_url(c) + "/api/health", timeout=c["health_timeout_s"]) as r:
            return json.load(r)
    except Exception:
        return None


def running_here():
    """Whether a cake answers on the configured port with this data folder: another folder's cake is not this one,
    and neither is an answer that names no folder."""
    health = running()
    home = health.get("home") if isinstance(health, dict) else None
    return bool(home) and os.path.realpath(str(home)) == os.path.realpath(paths.home())


def start():
    c = ensure_cfg()
    if running():
        print(text("already_running", base=base_url(c))); return 0
    # -I: the server imports nothing from the current folder or PYTHON* variables; __main__.py finds the package
    env = os.environ.copy()
    if paths.running_pyz():  # the server runs the unpacked copy; its pages name the .pyz all the same (paths.launcher)
        env[paths.PYZ_ENV] = paths.running_pyz()
    if paths.running_command():  # likewise an installed wheel's command, which the server's own argv does not name
        env[paths.COMMAND_ENV] = paths.running_command()
    with open(paths.log_file(), "a") as log:  # the child keeps its own copy of the file
        p = subprocess.Popen([sys.executable, "-I", paths.MAIN_FILE, "_serve"], stdout=log, stderr=log,
                             stdin=subprocess.DEVNULL, start_new_session=True, env=env)
    with open(paths.pid_file(), "w") as f:
        f.write(str(p.pid))
    deadline = time.monotonic() + c["start_wait_s"]
    while time.monotonic() < deadline:
        time.sleep(c["start_poll_s"])
        if running():
            print(text("started", pid=p.pid, base=base_url(c))); return 0
    print(text("did_not_start", log=paths.log_file())); return 1


def stop():
    c = load_cfg()
    try:
        with open(paths.pid_file()) as f:
            pid = int(f.read())
    except FileNotFoundError:
        print(text("was_not_running")); return 0
    except (OSError, ValueError) as error:
        print(text("stop_pid_unreadable", file=paths.tilde(paths.pid_file()), error=error)); return 1
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:  # it ended without stop (the computer restarted, it crashed): its pid file is stale
        os.remove(paths.pid_file())
        print(text("was_not_running")); return 0
    except PermissionError as error:  # another user's process, or a sandbox (an AI tool's) that forbids signals
        print(text("stop_not_allowed", pid=pid, error=error.strerror, launcher=paths.launcher())); return 1
    if not exited(pid, c["stop_wait_s"], c["stop_poll_s"]):
        print(text("did_not_stop", pid=pid, seconds=c["stop_wait_s"], log=paths.tilde(paths.log_file()),
                   launcher=paths.launcher()))
        return 1
    os.remove(paths.pid_file())
    print(text("stopped")); return 0


def exited(pid, wait_s, poll_s):
    """Whether process pid has exited within wait_s seconds, asked every poll_s."""
    deadline = time.monotonic() + wait_s
    while True:
        try:
            os.kill(pid, 0)  # signal 0: no signal, only whether the process exists
        except ProcessLookupError:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll_s)
