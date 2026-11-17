"""`agentcake doctor`, the lines about this computer: agentcake/doctor_machine.py.

    python3 -I -m unittest discover -s tests -p test_doctor_machine.py -v      (from the AgentCake folder)

Python and compression.zstd; the free disk space against disk_min_free_mb (below it new replays are not stored and
none is deleted for it, a failure that says they start again on their own and how to change it), with
shutil.disk_usage replaced by a nearly full disk; the age of the name
and address lists against their age limit (over max_age_days: a warning naming `agentcake lists update`); and every `agentcake` on
PATH (`which -a`): one that is not this installation coming first is named.
"""
import contextlib
import datetime
import io
import json
import os
import shutil
import stat
import sys
import tempfile
import time
import unittest
from collections import namedtuple
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from agentcake import codecs, config, doctor, doctor_lines, doctor_machine, store, streams, wording  # noqa: E402
from agentcake.detect import lists  # noqa: E402
from agentcake.units import BYTES_PER_MB  # noqa: E402
from cake_server import free_port  # noqa: E402
from space_sessions import DAY, add_session, replay  # noqa: E402

DiskUsage = namedtuple("DiskUsage", "total used free")  # what shutil.disk_usage returns


class ScratchHome(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="cake-test-")
        self.addCleanup(shutil.rmtree, self.home, True)
        env = mock.patch.dict(os.environ, {"CAKE_HOME": self.home, "CAKE_PORT": str(free_port())})
        env.start()
        self.addCleanup(env.stop)

    def settings(self, **values):
        with open(os.path.join(self.home, "config.json"), "w", encoding="utf-8") as f:
            json.dump(values, f)


class PythonLine(unittest.TestCase):
    def test_names_this_python_and_says_zstd_is_there(self):
        name, ok, info = doctor_machine.python_check()
        self.assertEqual(name, wording.text("doctor_python"))
        self.assertIs(ok, True)
        self.assertIn(".".join(map(str, sys.version_info[:3])), info)
        if codecs.ZSTD is not None:
            self.assertIn(wording.text("doctor_python_zstd"), info)

    def test_without_zstd_it_passes_and_says_replays_take_more_disk(self):
        with mock.patch.object(codecs, "ZSTD", None):
            _, ok, info = doctor_machine.python_check()
        self.assertIs(ok, True)
        self.assertIn(wording.text("doctor_python_no_zstd"), info)


class Disk(ScratchHome):
    """doctor never fills a disk: shutil.disk_usage answers for a pretend one."""

    def disk_line(self, free_mb):
        usage = DiskUsage(1000 * 1000 * BYTES_PER_MB, 0, int(free_mb * BYTES_PER_MB))
        with mock.patch("shutil.disk_usage", return_value=usage):
            return doctor_machine.disk_check(config.load_cfg())

    def test_plenty_of_room_passes(self):
        name, ok, info = self.disk_line(50000)
        self.assertEqual(name, wording.text("doctor_disk"))
        self.assertIs(ok, True)
        self.assertIn("50,000 MB", info)

    def test_below_the_floor_says_replays_are_not_stored_and_how_to_change_it(self):
        self.settings(disk_min_free_mb=2000)
        _, ok, info = self.disk_line(1500)
        self.assertIs(ok, False)
        self.assertIn("1,500 MB", info)
        self.assertIn("2,000 MB", info)
        self.assertIn(wording.text("doctor_disk_replays_stop"), info)
        self.assertIn("config set disk_min_free_mb", info)

    def test_a_floor_of_zero_turns_the_check_off(self):
        self.settings(disk_min_free_mb=0)
        _, ok, info = self.disk_line(1)
        self.assertIs(ok, True)
        self.assertIn(wording.text("doctor_disk_off"), info)

    def old_replay(self):
        """A session that ended a day ago; returns the bytes of its replay."""
        con = store.db()
        try:
            add_session(None, con, "old", verdict="human", agent_pct=0, group="H1/L?",
                        end_ms=int(time.time() * 1000) - DAY)
            con.commit()
            return streams.replay_bytes(con, "old")
        finally:
            con.close()

    def test_below_the_floor_it_fails_says_new_replays_resume_on_their_own_and_deletes_none(self):
        self.old_replay()
        for auto_free in (True, False):
            self.settings(disk_min_free_mb=2000, auto_free=auto_free)
            _, ok, info = self.disk_line(1999.5)
            self.assertIs(ok, False, auto_free)
            self.assertIn("below the 2,000 MB set in disk_min_free_mb", info)
            self.assertIn(wording.text("doctor_disk_replays_stop"), info)
            self.assertIn(wording.text("doctor_disk_replays_resume"), info)
            self.assertIn("config set disk_min_free_mb", info)
            con = store.db()
            try:
                self.assertEqual(replay(con, "old"), 60, "doctor only looks, and nothing is deleted for the disk")
            finally:
                con.close()

    def test_before_the_data_folder_exists_the_line_is_about_the_disk_it_will_be_on(self):
        with mock.patch.dict(os.environ, {"CAKE_HOME": os.path.join(self.home, "not", "there")}):
            name, ok, info = doctor_machine.disk_check(config.load_cfg())
        self.assertEqual(name, wording.text("doctor_disk"))
        self.assertIn(" MB free", info)

    def test_doctor_prints_the_low_disk_line(self):
        self.settings(disk_min_free_mb=2000)
        usage = DiskUsage(1000 * 1000 * BYTES_PER_MB, 0, 100 * BYTES_PER_MB)
        with mock.patch("shutil.disk_usage", return_value=usage):
            lines, code = run_doctor()
        disk_line = next(line for line in lines if f"] {wording.text('doctor_disk')}: " in line)
        self.assertTrue(disk_line.startswith("[FAIL]"), disk_line)
        self.assertEqual(code, 1)


class Lists(ScratchHome):
    def test_lists_in_their_age_limit_pass(self):
        built = lists.current().status()["built"]
        name, ok, info = doctor_machine.lists_check(today=datetime.date.fromisoformat(built))
        self.assertEqual(name, wording.text("doctor_lists"))
        self.assertIs(ok, True)
        self.assertIn(built, info)

    def test_lists_older_than_the_limit_warn_and_name_the_update_command(self):
        built = datetime.date.fromisoformat(lists.current().status()["built"])
        later = built + datetime.timedelta(days=lists.update_settings()["max_age_days"] + 1)
        _, verdict, info = doctor_machine.lists_check(today=later)
        self.assertEqual(verdict, doctor_lines.WARN)
        self.assertIn("lists update", info)


class OnPath(unittest.TestCase):
    """`which -a agentcake`: fake executables in scratch folders stand for what PATH may hold."""

    def setUp(self):
        self.folders = [tempfile.mkdtemp(prefix="cake-test-path-") for _ in range(3)]
        for folder in self.folders:
            self.addCleanup(shutil.rmtree, folder, True)

    def command_in(self, folder):
        path = os.path.join(folder, wording.product()["command"])
        with open(path, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\n")
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
        return path

    def check(self, ours):
        return doctor_machine.path_check(path=os.pathsep.join(self.folders), ours=ours)

    def test_none_on_path_passes_and_says_to_use_the_full_path(self):
        _, ok, info = self.check(ours=[])
        self.assertIs(ok, True)
        self.assertIn(wording.text("doctor_path_none", launcher=doctor_machine.paths.launcher()), info)

    def test_this_installation_first_passes(self):
        mine = self.command_in(self.folders[1])
        _, ok, info = self.check(ours=[mine])
        self.assertIs(ok, True)
        self.assertIn(mine, info)

    def test_another_one_first_warns_and_names_it(self):
        other, mine = self.command_in(self.folders[0]), self.command_in(self.folders[2])
        _, verdict, info = self.check(ours=[mine])
        self.assertEqual(verdict, doctor_lines.WARN)
        self.assertIn(other, info)

    def test_another_one_after_this_installation_is_listed(self):
        mine, other = self.command_in(self.folders[0]), self.command_in(self.folders[1])
        _, ok, info = self.check(ours=[mine])
        self.assertIs(ok, True)
        self.assertIn(other, info)

    def test_a_folder_listed_twice_counts_once(self):
        mine = self.command_in(self.folders[0])
        _, ok, info = doctor_machine.path_check(path=os.pathsep.join([self.folders[0]] * 2), ours=[mine])
        self.assertIs(ok, True)
        self.assertEqual(info.count(mine), 1)


def run_doctor(folder=None, url=None):
    """doctor's printed lines and its exit code."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = doctor.doctor(folder, url)
    return out.getvalue().splitlines(), code


if __name__ == "__main__":
    unittest.main()
