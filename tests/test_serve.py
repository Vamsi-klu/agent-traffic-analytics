"""`agentcake serve` ends cleanly on SIGINT and SIGTERM: agentcake/server.py's serve().

    python3 -I -m unittest discover -s tests -p test_serve.py -v      (from the AgentCake folder)

serve runs in the foreground under systemd, in a container (where Python is PID 1 and gets no default action for
SIGTERM) and in a terminal (Ctrl+C is SIGINT). Each signal ends it with exit status 0, one line saying it stopped, no
traceback, and its port free again. Every run uses a scratch CAKE_HOME and a free port.
"""
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from agentcake import wording  # noqa: E402
from cake_server import AGENTCAKE, START_TIMEOUT_S, POLL_S, free_port, http  # noqa: E402


class Serve(unittest.TestCase):
    def start(self, *settings):
        home = tempfile.mkdtemp(prefix="agentcake-serve-")
        self.addCleanup(shutil.rmtree, home, True)
        self.port = free_port()
        env = dict(os.environ, CAKE_HOME=home, CAKE_PORT=str(self.port))
        for key, value in settings:
            subprocess.run(AGENTCAKE + ["config", "set", key, value], env=env, capture_output=True, check=True)
        process = subprocess.Popen(AGENTCAKE + ["serve"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True)
        self.addCleanup(lambda: process.poll() is None and process.kill())
        deadline = time.monotonic() + START_TIMEOUT_S
        while time.monotonic() < deadline:
            try:
                if http(f"http://127.0.0.1:{self.port}/api/health")[0] == 200:
                    return process
            except OSError:  # not listening yet
                time.sleep(POLL_S)
        raise AssertionError("agentcake serve did not answer: " + process.stdout.read())

    def stop_with(self, process, signum):
        process.send_signal(signum)
        output, _ = process.communicate(timeout=START_TIMEOUT_S)
        return process.returncode, output

    def assert_clean(self, code, output):
        self.assertEqual(code, 0, output)
        self.assertNotIn("Traceback", output)
        self.assertNotIn("KeyboardInterrupt", output)
        self.assertEqual(output.splitlines()[-1], wording.text("serve_stopped"))

    def test_sigterm_ends_it_cleanly(self):
        self.assert_clean(*self.stop_with(self.start(), signal.SIGTERM))

    def test_sigint_ends_it_cleanly(self):
        self.assert_clean(*self.stop_with(self.start(), signal.SIGINT))

    def test_server_mode_ends_with_both_listeners(self):
        public = free_port()
        process = self.start(("public_listen", f"127.0.0.1:{public}"), ("path_prefix", "/cake"))
        self.assertEqual(http(f"http://127.0.0.1:{public}/cake/healthz")[0], 200)
        self.assert_clean(*self.stop_with(process, signal.SIGTERM))

    def test_a_signal_while_a_request_waits_still_ends_it(self):
        process = self.start()
        with socket.create_connection(("127.0.0.1", self.port)):  # a client that connected and sends nothing
            self.assert_clean(*self.stop_with(process, signal.SIGTERM))


if __name__ == "__main__":
    unittest.main()
