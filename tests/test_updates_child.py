"""The monthly update in a process of its own: agentcake/updates.py check(), child_command() and child().

    python3 -I -m unittest discover -s tests -p test_updates_child.py -v      (from the AgentCake folder)

serve's daily check runs the parts that are due in a child process of the same installation, so the code that
downloads and converts never loads into serve, the child's memory goes back to the system when it ends, and it never
holds serve's GIL. These tests start real processes: tests/update_child.py, child() with test_updates.py's offline
downloads and the test's clock; and the real child_command(), from this checkout and from a copy of the package in
another folder (as a wheel's site-packages, or the folder agentcake.pyz unpacks into), on a computer, where the city
database part is skipped and nothing is downloaded.

Checks: the due parts run in another process, which records the run itself, at the lowest CPU priority while serve
keeps its own; a child that is killed or exits with
another status is a failed run of the parts that were due, recorded like any failure, and the check returns (serve
goes on); the setting switched off while the child downloads stops it before its next part; a child and
`agentcake lists update` never run at once, whichever came first; the child writes where serve writes (cake.log);
serve's check loads none of the code that downloads or converts.
"""
import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from test_updates import BUNDLED_BUILT, EVERY, SERVER, ScratchHome  # noqa: E402
from update_child import EXIT_STATUS, POLL_S, SAID  # noqa: E402
from agentcake import geoip, paths, updates  # noqa: E402

ROOT = os.path.dirname(HERE)
CHILD = os.path.join(HERE, "update_child.py")
NOW = BUNDLED_BUILT + EVERY  # the lists are due; on a server without a city database, it is due too
WAIT_S = 60  # how long a test waits for the stand-in to reach its first download
LOWEST_PRIORITY = 19  # the highest nice value Linux allows, so the lowest CPU priority (setpriority(2))
CONVERSION = ("agentcake.detect.lists_build", "agentcake.geoip_build", "agentcake.detect.lists_ranges",
              "agentcake.detect.lists_names", "agentcake.detect.lists_keys", "agentcake.downloads")


class Child(ScratchHome):
    def setUp(self):
        super().setUp()
        self.notes = tempfile.mkdtemp(prefix="cake-child-")
        self.addCleanup(shutil.rmtree, self.notes, True)
        self.c = self.cfg(**SERVER)

    def stand_in(self, mode):
        return lambda parts: [sys.executable, "-I", CHILD, mode, NOW.isoformat(), self.notes, *parts]

    def noted(self, name):
        path = os.path.join(self.notes, name)
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            return f.read()

    def wait_for_note(self, name):
        deadline = time.monotonic() + WAIT_S
        while self.noted(name) is None and time.monotonic() < deadline:
            time.sleep(POLL_S)
        return self.noted(name) is not None


class InAnotherProcess(Child):
    def test_the_due_parts_run_in_another_process_which_records_them(self):
        self.assertIsNone(updates.check(self.c, NOW, command=self.stand_in("ok")))
        child_pid = int(self.noted("pid"))
        self.assertNotEqual(child_pid, os.getpid())
        last = updates.status(self.c)["last"]
        self.assertEqual((last["how"], last["ok"], last["parts"]),
                         (updates.AUTO, True, {updates.LISTS: updates.UPDATED, updates.PLACES: updates.UPDATED}))
        self.assertIsNotNone(geoip.database())

    def test_the_update_runs_at_the_lowest_cpu_priority_and_serve_keeps_its_own(self):
        """On a server with one CPU, converting the city database takes the whole CPU for minutes: at serve's
        priority, collect, the local page and the container's health check waited for it."""
        serves = os.getpriority(os.PRIO_PROCESS, 0)
        updates.check(self.c, NOW, command=self.stand_in("ok"))
        self.assertEqual(int(self.noted("nice")), LOWEST_PRIORITY)
        self.assertEqual(os.getpriority(os.PRIO_PROCESS, 0), serves)

    def test_the_update_stays_in_serves_session_in_a_process_group_of_its_own(self):
        """Its own process group keeps a Ctrl-C meant for serve in a terminal from cutting it short. A session of its
        own would make its nice value count for nothing against serve on Linux: a new session is a new autogroup, and
        nice only weighs a process against the others in its autogroup (sched(7)), so on a server with one CPU the
        update took half of it from serve under systemd."""
        updates.check(self.c, NOW, command=self.stand_in("ok"))
        self.assertEqual(int(self.noted("sid")), os.getsid(0))
        self.assertNotEqual(int(self.noted("pgid")), os.getpgid(0))
        self.assertEqual(int(self.noted("pgid")), int(self.noted("pid")))

    def test_nothing_due_starts_no_process(self):
        self.assertIsNone(updates.check(self.cfg(lists_auto_update=False), NOW, command=self.stand_in("ok")))
        self.assertIsNone(self.noted("pid"))

    def test_the_childs_output_goes_where_serves_goes(self):
        sys.stdout.flush(), sys.stderr.flush()
        with tempfile.TemporaryFile() as log, contextlib.ExitStack() as restore:
            for fd in (1, 2):  # serve's stdout and stderr: cake.log, the journal or the container's log
                saved = os.dup(fd)
                restore.callback(os.close, saved)
                restore.callback(os.dup2, saved, fd)
                os.dup2(log.fileno(), fd)
            updates.check(self.c, NOW, command=self.stand_in("say"))
            restore.close()
            log.seek(0)
            self.assertEqual(log.read().decode().count(SAID), 2)


class Faults(Child):
    def test_a_killed_child_is_a_failed_run_of_the_due_parts_and_the_check_returns(self):
        record = updates.check(self.c, NOW, command=self.stand_in("kill"))
        self.assertEqual((record["how"], record["ok"], record["parts"]),
                         (updates.AUTO, False, {updates.LISTS: updates.FAILED, updates.PLACES: updates.FAILED}))
        self.assertIn("SIGKILL", record["error"])
        self.assertEqual(updates.status(self.c)["failures"], 1)
        self.assertEqual(updates.due(self.c, NOW), [], "a failed part waits retry_after_s, as any failure")

    def test_a_child_that_exits_with_another_status_is_a_failed_run(self):
        record = updates.check(self.c, NOW, command=self.stand_in("exit"))
        self.assertFalse(record["ok"])
        self.assertIn(f"exit status {EXIT_STATUS}", record["error"])

    def test_switched_off_while_the_child_downloads_it_stops_before_the_next_part(self):
        self.assertIsNone(updates.check(self.c, NOW, command=self.stand_in("switch")))
        self.assertEqual(updates.status()["last"]["parts"], {updates.LISTS: updates.UPDATED})
        self.assertIsNone(geoip.database())


class OneAtATime(Child):
    def test_while_lists_update_runs_the_child_skips_its_turn(self):
        with updates.exclusive(wait=True):  # what `agentcake lists update` holds while it runs
            self.assertIsNone(updates.check(self.c, NOW, command=self.stand_in("ok")))
        self.assertIsNotNone(self.noted("pid"))
        self.assertIsNone(self.noted("fetched"))
        self.assertIsNone(updates.status(self.c)["last"])

    def test_while_the_child_runs_lists_update_waits_for_it(self):
        checking = threading.Thread(target=updates.check, args=(self.c, NOW),
                                    kwargs={"command": self.stand_in("hold")})
        checking.start()
        try:
            self.assertTrue(self.wait_for_note("fetched"), "the child never reached its first download")
            with updates.exclusive(wait=False) as held:
                self.assertFalse(held, "the child holds the update lock")
        finally:
            with open(os.path.join(self.notes, "go"), "w", encoding="utf-8"):
                pass
            checking.join(WAIT_S)
        self.assertTrue(updates.status(self.c)["last"]["ok"])


class ServeLoadsNoConversion(Child):
    def test_serves_check_imports_no_code_that_downloads_or_converts(self):
        script = ("import json, sys; sys.path.insert(0, sys.argv[1]); from agentcake import server, updates; "
                  "import datetime; now = datetime.datetime.fromisoformat(sys.argv[2]); "
                  "updates.check(None, now, command=lambda parts: json.loads(sys.argv[3]) + parts); "
                  "print(json.dumps(sorted(set(json.loads(sys.argv[4])) & set(sys.modules))))")
        command = [sys.executable, "-I", CHILD, "ok", NOW.isoformat(), self.notes]
        done = subprocess.run([sys.executable, "-I", "-c", script, ROOT, NOW.isoformat(), json.dumps(command),
                               json.dumps(CONVERSION)], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(done.stdout), [])
        self.assertTrue(updates.status()["last"]["ok"], "the child did update")


class RealChild(ScratchHome):
    """child_command() as serve runs it, on a computer: the city database part is skipped, so nothing is downloaded,
    and the run is recorded by the child."""

    def assert_ran(self, done):
        self.assertEqual(done.returncode, 0, done.stderr)
        last = updates.status(self.cfg())["last"]
        self.assertEqual((last["how"], last["parts"]), (updates.AUTO, {updates.PLACES: updates.SKIPPED}))

    def test_from_this_checkout_the_child_runs_this_agentcake(self):
        with tempfile.TemporaryDirectory() as elsewhere:  # no agentcake in the folder it starts in
            self.assert_ran(subprocess.run(updates.child_command([updates.PLACES]), cwd=elsewhere,
                                           capture_output=True, text=True))

    def test_from_a_copy_elsewhere_the_child_runs_that_copy(self):
        """An installed wheel's site-packages, or the folder agentcake.pyz unpacks itself into: the child imports the
        package from where serve's came from, which this copy's own name for the record shows."""
        with tempfile.TemporaryDirectory() as site:
            copy = os.path.join(site, "agentcake")
            shutil.copytree(paths.PACKAGE_DIR, copy, ignore=shutil.ignore_patterns("__pycache__"))
            sources_file = os.path.join(copy, "data", "lists", "sources.json")
            with open(sources_file, encoding="utf-8") as f:
                sources = json.load(f)
            sources["update"]["auto"]["state_file"] = "updates-from-the-copy.json"
            with open(sources_file, "w", encoding="utf-8") as f:
                json.dump(sources, f)
            script = ("import subprocess, sys; sys.path.insert(0, sys.argv[1]); from agentcake import updates; "
                      "assert updates.__file__.startswith(sys.argv[1]); "
                      "sys.exit(subprocess.run(updates.child_command([updates.PLACES])).returncode)")
            done = subprocess.run([sys.executable, "-I", "-c", script, site], cwd=site, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            with open(os.path.join(self.home, "updates-from-the-copy.json"), encoding="utf-8") as f:
                self.assertEqual(json.load(f)["last"]["parts"], {updates.PLACES: updates.SKIPPED})
            self.assertIsNone(updates.status()["last"], "nothing of this checkout's ran")

if __name__ == "__main__":
    unittest.main()
