"""A real `agentcake serve` for the server-mode tests, and the small helpers they share.

CakeServer starts one in a scratch CAKE_HOME, its local page and public listener on free ports of 127.0.0.1, with the
settings SERVER.md tells `agentcake config set` to make, written the way that command writes them (config.coerce,
config.save_user) in one go: a command per key cost a Python start each. test_server_docs.py runs SERVER.md's own
commands. A test never opens a port to the network, so the public listener
binds 127.0.0.1 here where a server binds 0.0.0.0; the code path is the same. test_server_mode.py runs the listeners,
test_server_docs.py reads SERVER.md and the deploy files; documented_public_routes() is the one reading of SERVER.md's
table of what the public listener answers that both use. pages_stub() stands in for the compiled local pages
($CAKE_WEB_DIR): the Python tests never build web/, and a real `agentcake serve` answers / with them.
"""
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from agentcake import config  # noqa: E402  (needs the repository first)

AGENTCAKE = [sys.executable, "-I", os.path.join(ROOT, "agentcake", "__main__.py")]  # what bin/agentcake runs
SERVER_MD = os.path.join(ROOT, "SERVER.md")
PREFIX = "/cake"  # the path_prefix SERVER.md uses
SITE_KEY = "ck_servermode"
START_TIMEOUT_S = 10
# How often a test asks whether a server it started answers yet, and how often a test server running in a thread looks
# for shutdown() (serve_forever's poll_interval): with the default 0.5 s every stop waited about that long.
POLL_S = 0.01


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def http(url, body=None, headers=None, method=None):
    """(status, headers, body) of one request; an HTTP error status is returned, not raised."""
    request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=START_TIMEOUT_S) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        with error:
            return error.code, dict(error.headers), error.read()


def pages_stub():
    """A folder holding an index.html, for $CAKE_WEB_DIR: what / answers when the pages are built."""
    folder = tempfile.mkdtemp(prefix="agentcake-pages-")
    with open(os.path.join(folder, "index.html"), "w", encoding="utf-8") as f:
        f.write("<!doctype html><title>pages</title>")
    return folder


def run_cli(env, *args):
    return subprocess.run(AGENTCAKE + list(args), env=env, capture_output=True, text=True)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def documented_public_routes(markdown):
    """(method, path) of each row of SERVER.md's table of what the public listener answers."""
    return set(re.findall(r"^\|\s*(GET|POST)\s*\|\s*`([^`]+)`", markdown, re.M))


class CakeServer:
    """One `agentcake serve` in a scratch CAKE_HOME, its local page and public listener on free ports of 127.0.0.1."""

    def __init__(self, trust_lb):
        self.home = tempfile.mkdtemp(prefix="agentcake-server-mode-")
        self.env = dict(os.environ, CAKE_HOME=self.home, CAKE_WEB_DIR=pages_stub())
        self.env.pop("CAKE_PORT", None)
        self.local_port, self.public_port = free_port(), free_port()
        self.local, self.public = f"http://127.0.0.1:{self.local_port}", f"http://127.0.0.1:{self.public_port}{PREFIX}"
        settings = (("port", self.local_port), ("public_listen", f"127.0.0.1:{self.public_port}"),
                    ("path_prefix", PREFIX), ("trust_lb", str(trust_lb).lower()), ("site_key", SITE_KEY))
        with mock.patch.dict(os.environ, {"CAKE_HOME": self.home}):
            config.save_user(**{key: config.coerce(key, str(value)) for key, value in settings})
        self.process = subprocess.Popen(AGENTCAKE + ["serve"], env=self.env, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True)
        self.wait_until_both_listeners_answer()

    def wait_until_both_listeners_answer(self):
        deadline = time.monotonic() + START_TIMEOUT_S
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError("agentcake serve exited: " + self.process.stdout.read())
            try:
                if http(self.public + "/healthz")[0] == 200 and http(self.local + "/api/health")[0] == 200:
                    return
            except OSError:  # not listening yet
                time.sleep(POLL_S)
        raise RuntimeError(f"agentcake serve did not answer within {START_TIMEOUT_S} s")

    def stop(self):
        """Ends the server and returns everything it printed."""
        self.process.terminate()
        output, _ = self.process.communicate(timeout=START_TIMEOUT_S)
        return output

    def remove(self):
        if self.process.poll() is None:
            self.stop()
        shutil.rmtree(self.home, ignore_errors=True)

    def database(self):
        return sqlite3.connect(os.path.join(self.home, "cake.db"))

    def net_of(self, session_id):
        """sessions.net of one session: the network facts collect kept, or None."""
        con = self.database()
        try:
            row = con.execute("SELECT net FROM sessions WHERE id=?", (session_id,)).fetchone()
        finally:
            con.close()
        if row is None:
            raise AssertionError(f"session {session_id} was not recorded")
        return json.loads(row[0]) if row[0] else None
