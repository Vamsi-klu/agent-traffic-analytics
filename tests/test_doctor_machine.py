"""`agentcake doctor`, the lines about this computer: agentcake/doctor_machine.py.

    python3 -I -m unittest discover -s tests -p test_doctor_machine.py -v      (from the AgentCake folder)

Python and compression.zstd; the free disk space against disk_min_free_mb (below it new replays are not stored and
none is deleted for it, a failure that says they start again on their own and how to change it), with
shutil.disk_usage replaced by a nearly full disk; the age of the name
and address lists against their age limit (over max_age_days: a warning naming `agentcake lists update`); on a server
(public_listen with trust_lb), the city database: missing or more than a month old, a warning naming the same command,
and no line at all on this computer; the monthly update: on or off, when the last one ran and how it went, and failed
updates in a row as a warning naming the same command; and every `agentcake` on PATH (`which -a`): one that is not this
installation coming first is named.
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
import geo_fixtures  # noqa: E402
from agentcake import (codecs, config, doctor, doctor_lines, doctor_machine, geoip, geoip_build, store,  # noqa: E402
                       streams, timezone, updates, wording)
from agentcake.detect import lists, lists_build  # noqa: E402
from agentcake.units import BYTES_PER_MB, S_PER_MIN  # noqa: E402
from cake_server import free_port  # noqa: E402
from space_sessions import DAY, add_session, replay  # noqa: E402
from test_lists_build import fetcher, recipe, world  # noqa: E402

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


class AutomaticUpdates(ScratchHome):
    """The line about the monthly update (updates.py): on or off, when the last update ran and how it went; failed runs
    in a row are a warning that names the command, as is lists that are too old (Lists above)."""

    def setUp(self):
        super().setUp()
        lists.reload()
        self.addCleanup(lists.reload)

    def line(self, **settings):
        self.settings(**settings)
        return next(line for line in doctor_machine.machine_checks(config.load_cfg())
                    if line[0] == wording.text("doctor_updates"))

    def shown_date(self):
        """The last update's date as doctor writes it, in AgentCake's time zone: the record's UTC time is a day ahead
        of it in the evening west of UTC, so the record's own date would be the wrong one then."""
        at = datetime.datetime.fromisoformat(updates.status()["last"]["at"])
        return at.astimezone(timezone.chosen(config.load_cfg())).date().isoformat()

    def fail_updates(self, times=1):
        def unreachable(url, accept=None):
            raise lists_build.BuildError(f"{url}: unreachable")

        for _ in range(times):
            updates.run(updates.AUTO, parts=[updates.LISTS], fetchers={updates.LISTS: unreachable})

    def test_on_before_any_update_it_passes_and_says_how_often(self):
        _, ok, info = self.line()
        self.assertIs(ok, True)
        self.assertIn(str(updates.settings()["every_days"]), info)

    def test_off_it_passes_and_names_the_command(self):
        _, ok, info = self.line(lists_auto_update=False)
        self.assertIs(ok, True)
        self.assertIn(f"{doctor_machine.paths.launcher()} lists update", info)

    def test_one_failed_update_passes_and_says_when_and_why(self):
        self.fail_updates()
        _, ok, info = self.line()
        self.assertIs(ok, True)
        self.assertIn("unreachable", info)
        self.assertIn(self.shown_date(), info)

    def test_failed_updates_in_a_row_warn_and_name_the_command(self):
        self.fail_updates(updates.settings()["warn_after_failures"])
        for settings in ({}, {"lists_auto_update": False}):
            with self.subTest(**settings):
                _, verdict, info = self.line(**settings)
                self.assertEqual(verdict, doctor_lines.WARN)
                self.assertIn("unreachable", info)
                self.assertIn(f"{doctor_machine.paths.launcher()} lists update", info)

    def test_an_error_without_a_full_stop_still_ends_its_sentence(self):
        self.fail_updates(updates.settings()["warn_after_failures"])
        _, _, info = self.line()
        self.assertIn("unreachable. To update now", info.replace(updates.status()["last"]["error"], "unreachable"))

    def test_a_successful_update_says_when_it_ran(self):
        sources = recipe()
        with mock.patch.object(lists_build, "read_recipe", return_value=(sources, lists_build.read_recipe()[1])):
            updates.run(updates.MANUAL, parts=[updates.LISTS], fetchers={updates.LISTS: fetcher(world(sources))})
        _, ok, info = self.line()
        self.assertIs(ok, True)
        self.assertIn(self.shown_date(), info)
        self.assertNotIn("lists update", info)


class CityDatabase(ScratchHome):
    SERVER = {"public_listen": "127.0.0.1:8080", "trust_lb": True}

    def line(self, settings, today=None):
        c = dict(config.load_cfg(), **settings)
        return next((line for line in doctor_machine.machine_checks(c, today=today)
                     if line[0] == wording.text("doctor_places")), None)

    def test_on_this_computer_there_is_no_line(self):
        self.assertIsNone(self.line({}))
        geo_fixtures.install(geoip.user_folder())
        self.assertIsNone(self.line({}), "a database is no use without visitor addresses")

    def first_check_minutes(self):
        return [seconds // S_PER_MIN for seconds in updates.settings()["first_check_s"]]

    def fail_download(self):
        """One automatic update whose city database download failed, recorded as serve's child records it."""
        def unreachable(url, path):
            raise geoip_build.BuildError(f"{url}: unreachable")

        self.settings(**self.SERVER)
        updates.run(updates.AUTO, parts=[updates.PLACES], fetchers={updates.PLACES: unreachable})

    def test_on_a_server_before_its_first_automatic_update_it_says_when_and_names_no_command(self):
        """A new server: serve downloads the database at its first check, minutes after it starts, so the line says
        when, and gives no command for a coding agent to run in the meantime."""
        _, verdict, info = self.line(self.SERVER)
        self.assertEqual(verdict, doctor_lines.WARN, "until then every visit's country is Not set")
        first, last = self.first_check_minutes()
        self.assertRegex(info, rf"\b{first}\b\D+\b{last}\b minutes")
        self.assertNotIn("lists update", info)

    def test_on_a_server_with_automatic_updates_off_it_names_the_update_command(self):
        _, verdict, info = self.line(dict(self.SERVER, lists_auto_update=False))
        self.assertEqual(verdict, doctor_lines.WARN)
        self.assertIn(f"{doctor_machine.paths.launcher()} lists update", info)

    def test_after_a_failed_download_it_names_the_update_command(self):
        """The next try waits for a daily check (retry_after_s), so the command is the way to have it now."""
        self.fail_download()
        _, verdict, info = self.line(self.SERVER)
        self.assertEqual(verdict, doctor_lines.WARN)
        self.assertIn(f"{doctor_machine.paths.launcher()} lists update", info)

    def test_a_database_of_this_month_or_the_last_passes_and_names_its_month(self):
        geo_fixtures.install(geoip.user_folder())
        for today in (datetime.date(2026, 11, 18), datetime.date(2026, 12, 31)):
            _, ok, info = self.line(self.SERVER, today)
            self.assertIs(ok, True, today)
            self.assertIn(geo_fixtures.MONTH, info)

    def test_one_more_than_a_month_old_warns_and_names_the_update_command(self):
        geo_fixtures.install(geoip.user_folder())
        _, verdict, info = self.line(self.SERVER, datetime.date(2027, 1, 2))
        self.assertEqual(verdict, doctor_lines.WARN)
        self.assertIn(geo_fixtures.MONTH, info)
        self.assertIn("lists update", info)

    def test_one_that_cannot_be_read_warns_and_says_why(self):
        geo_fixtures.install(geoip.user_folder())
        with open(os.path.join(geoip.user_folder(), geoip.FILES["places"]), "wb") as f:
            f.write(b"not places")
        os.utime(os.path.join(geoip.user_folder(), geoip.FILES["about"]), ns=(1, 1))
        _, verdict, info = self.line(self.SERVER)
        self.assertEqual(verdict, doctor_lines.WARN)
        self.assertIn("places", info)
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
