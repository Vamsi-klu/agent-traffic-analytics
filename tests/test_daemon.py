"""Running cake in the background: agentcake/daemon.py. start, stop and status run end to end in test_cli.py;
here, running_here(), the one answer to "is a cake running on this data folder?" that `migrate` and `delete` act on
(each used to have its own copy), and stop() against stand-ins for the background server: stop returns
once the process has exited, says so when it has not within stop_wait_s and keeps its pid file, and says why when it
may not stop it or cannot read the pid file; a pid file whose process has ended is removed.

    python3 -I -m unittest discover -s tests -p test_daemon.py -v      (from the Agent Cake folder)
"""
import contextlib
import errno
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from agentcake import daemon, paths  # noqa: E402
from agentcake.wording import text  # noqa: E402
from cake_server import free_port  # noqa: E402

NO_SUCH_PID = 2 ** 31 - 1  # the largest pid_t: above every system's pid limit, so no process has it
EXIT_DELAY_S = 0.5  # how long the slow stand-in takes to exit, about the real server's (serve_forever's poll interval)
# Stand-ins for the background server. Each prints "ready" once its SIGTERM handling is in place.
SLOW_TO_EXIT = f"""\
import os, signal, time
def exit_slowly(signum, frame):
    time.sleep({EXIT_DELAY_S})
    os._exit(0)
signal.signal(signal.SIGTERM, exit_slowly)
print("ready", flush=True)
while True:
    signal.pause()
"""
IGNORES_SIGTERM = """\
import signal
signal.signal(signal.SIGTERM, signal.SIG_IGN)
print("ready", flush=True)
while True:
    signal.pause()
"""
# Starts a stand-in the way `agentcake start` starts the server, by a process that then exits, so that the stand-in is
# not this test's child (an ended child stays visible to os.kill until its parent collects it); prints its pid. The
# stand-in keeps none of the launcher's output pipes open, or reading the launcher's output would never end.
LAUNCHER = """\
import subprocess, sys
stand_in = subprocess.Popen([sys.executable, "-I", "-c", sys.argv[1]], stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
stand_in.stdout.readline()
print(stand_in.pid)
"""


class RunningHere(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="agentcake-daemon-")
        self.addCleanup(shutil.rmtree, self.home, True)
        patch = mock.patch.dict(os.environ, {"CAKE_HOME": self.home, "CAKE_PORT": str(free_port())})
        patch.start()
        self.addCleanup(patch.stop)

    def answering(self, health):
        return mock.patch.object(daemon, "running", return_value=health)

    def test_nothing_answers_on_the_port(self):
        self.assertFalse(daemon.running_here())

    def test_a_cake_on_this_data_folder(self):
        with self.answering({"ok": True, "home": self.home}):
            self.assertTrue(daemon.running_here())

    def test_this_data_folder_by_another_path(self):
        link = os.path.join(tempfile.mkdtemp(prefix="agentcake-daemon-link-"), "home")
        self.addCleanup(shutil.rmtree, os.path.dirname(link), True)
        os.symlink(self.home, link)
        with self.answering({"ok": True, "home": link}):
            self.assertTrue(daemon.running_here())

    def test_a_cake_on_another_data_folder_is_not_this_one(self):
        other = tempfile.mkdtemp(prefix="agentcake-daemon-other-")
        self.addCleanup(shutil.rmtree, other, True)
        with self.answering({"ok": True, "home": other}):
            self.assertFalse(daemon.running_here())

    def test_an_answer_that_names_no_folder_is_not_this_one(self):
        previous = os.getcwd()
        os.chdir(self.home)  # an empty path reads as the current folder, here the data folder itself
        self.addCleanup(os.chdir, previous)
        for health in ({"ok": True}, {"ok": True, "home": ""}, {"ok": True, "home": None}):
            with self.subTest(health=health), self.answering(health):
                self.assertFalse(daemon.running_here())


def alive(pid):
    try:
        os.kill(pid, 0)  # signal 0: no signal, only whether the process exists
    except ProcessLookupError:
        return False
    return True


class Stop(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="agentcake-daemon-stop-")
        self.addCleanup(shutil.rmtree, self.home, True)
        patch = mock.patch.dict(os.environ, {"CAKE_HOME": self.home, "CAKE_PORT": str(free_port())})
        patch.start()
        self.addCleanup(patch.stop)

    def stand_in(self, code):
        """A stand-in server's pid, written to cake.pid as `agentcake start` does; killed after the test."""
        launched = subprocess.run([sys.executable, "-I", "-c", LAUNCHER, code], capture_output=True, text=True,
                                  check=True)
        pid = int(launched.stdout)
        self.addCleanup(self.kill, pid)
        self.write_pid_file(str(pid))
        return pid

    @staticmethod
    def kill(pid):
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)

    def write_pid_file(self, content):
        with open(paths.pid_file(), "w") as f:
            f.write(content)

    def settings(self, **values):
        with open(paths.config_file(), "w", encoding="utf-8") as f:
            json.dump(values, f)

    def stop(self):
        """stop()'s exit code and printed text."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = daemon.stop()
        return code, out.getvalue().strip()

    def test_stop_returns_once_the_process_has_exited(self):
        pid = self.stand_in(SLOW_TO_EXIT)
        self.assertEqual(self.stop(), (0, text("stopped")))
        self.assertFalse(alive(pid), "stop said stopped while the process still ran")
        self.assertFalse(os.path.exists(paths.pid_file()))

    def test_a_process_that_has_not_exited_in_time_is_reported_and_its_pid_file_kept(self):
        self.settings(stop_wait_s=0.2)
        pid = self.stand_in(IGNORES_SIGTERM)
        code, said = self.stop()
        self.assertEqual(code, 1)
        self.assertEqual(said, text("did_not_stop", pid=pid, seconds=0.2, log=paths.tilde(paths.log_file()),
                                    launcher=paths.launcher()))
        self.assertTrue(alive(pid))
        self.assertTrue(os.path.exists(paths.pid_file()), "kept, so that a second stop can try again")

    def test_without_a_pid_file_it_was_not_running(self):
        self.assertEqual(self.stop(), (0, text("was_not_running")))

    def test_the_pid_file_of_a_process_that_has_ended_is_removed(self):
        self.write_pid_file(str(NO_SUCH_PID))
        self.assertEqual(self.stop(), (0, text("was_not_running")))
        self.assertFalse(os.path.exists(paths.pid_file()))

    def test_a_stop_that_is_not_allowed_is_reported_not_swallowed(self):
        # a sandbox (an AI tool's) or another user's process: os.kill fails with EPERM
        self.write_pid_file(str(NO_SUCH_PID))
        refused = PermissionError(errno.EPERM, os.strerror(errno.EPERM))
        with mock.patch("os.kill", side_effect=refused):
            code, said = self.stop()
        self.assertEqual(code, 1)
        self.assertEqual(said, text("stop_not_allowed", pid=NO_SUCH_PID, error=os.strerror(errno.EPERM),
                                    launcher=paths.launcher()))
        self.assertTrue(os.path.exists(paths.pid_file()))

    def test_a_pid_file_without_a_pid_is_reported(self):
        self.write_pid_file("not a pid")
        code, said = self.stop()
        self.assertEqual(code, 1)
        self.assertTrue(said.startswith(text("stop_pid_unreadable", file=paths.tilde(paths.pid_file()), error="")),
                        said)
        self.assertTrue(os.path.exists(paths.pid_file()))


if __name__ == "__main__":
    unittest.main()
