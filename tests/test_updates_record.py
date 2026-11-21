"""The monthly update's record and its switch where other code meets them: agentcake/updates.py.

    python3 -I -m unittest discover -s tests -p test_updates_record.py -v      (from the AgentCake folder)

test_updates.py covers the update itself; this file covers what it reads back. updates.json as it may be found besides
missing or cut short: JSON whose values are not the ones a run writes (edited by hand, or written by another version)
reads as no record, so the settings page, /api/health, doctor and the daily check keep working and the next run writes
it again from the start. A city database whose download time can't be read is downloaded again, and the lists are
still checked. A lists download the connection cuts off is a failed run, recorded like any other. Turning the setting
off while an automatic run downloads starts no further download; a run someone starts with `agentcake lists update`
runs every part whatever the setting. Every test and tool that starts a real `agentcake serve` turns the setting off
in its scratch CAKE_HOME, as tests/cake_server.py does: one that runs past the first check (a minute or more after the
start) would otherwise go online, and on a server download the city database.
"""
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import geo_fixtures  # noqa: E402
from api_client import Client, contract_problems  # noqa: E402
from test_lists_build import fetcher, world  # noqa: E402
from test_updates import (BUNDLED_BUILT, EVERY, SERVER, Recorder, ScratchHome, check_here, city_database,  # noqa: E402
                          unreachable_lists)
from agentcake import config, doctor_machine, geoip, updates  # noqa: E402
from agentcake.detect import lists, lists_build  # noqa: E402

AT = "2026-11-19T03:12:40+00:00"
LAST = {"at": AT, "how": updates.AUTO, "ok": True, "error": None, "parts": {updates.LISTS: updates.UPDATED}}
# Records no run writes, each with the value that is wrong; every other value is one a run writes.
ROOT = os.path.dirname(HERE)
STARTS_SERVE = re.compile(r"""["']serve["']""")  # `serve` as a command's argument, in Python and in JavaScript
NO_SERVE = {os.path.join("tests", "test_server_docs.py"): "names `serve` among the SERVER.md commands it never runs"}
DAMAGED = {
    "failures is not a number": {"last": LAST, "failures": "2"},
    "failures is true": {"last": LAST, "failures": True},
    "parts is not an object": {"parts": []},
    "a part is not an object": {"parts": {updates.LISTS: AT}},
    "a part's time can't be read": {"parts": {updates.LISTS: {"failed_at": "yesterday"}}},
    "a part's time is not text": {"parts": {updates.LISTS: {"ok_at": 1795131223}}},
    "last is not an object": {"last": "yesterday", "failures": 0},
    "last has no time": {"last": {key: value for key, value in LAST.items() if key != "at"}, "failures": 0},
    "last's time can't be read": {"last": dict(LAST, at="yesterday"), "failures": 0},
    "last's ok is not true or false": {"last": dict(LAST, ok="yes"), "failures": 0},
    "last's error is not text": {"last": dict(LAST, ok=False, error=["timed out"]), "failures": 1},
    "last's way is neither auto nor manual": {"last": dict(LAST, how="cron"), "failures": 0},
    "last's parts is not an object": {"last": dict(LAST, parts=[updates.LISTS]), "failures": 0},
}


class DamagedRecord(ScratchHome):
    def write_record(self, state):
        with open(os.path.join(self.home, updates.settings()["state_file"]), "w", encoding="utf-8") as f:
            json.dump(state, f)

    def test_a_record_with_values_no_run_writes_reads_as_no_record(self):
        c = self.cfg()
        for name, state in DAMAGED.items():
            with self.subTest(name):
                self.write_record(state)
                self.assertEqual(updates.read_state(), {})
                self.assertEqual(updates.status(c), {"auto": True, "last": None, "failures": 0, "failing": False})

    def test_the_settings_page_health_doctor_and_the_daily_check_keep_working(self):
        c, client = self.cfg(), Client()
        for name, state in DAMAGED.items():
            with self.subTest(name):
                self.write_record(state)
                for path, contract in (("/api/settings", "settings"), ("/api/health", "health")):
                    answer = client.get(path)
                    self.assertEqual(answer.status, 200, answer.body)
                    self.assertEqual(contract_problems(answer.body, contract), [])
                self.assertIs(doctor_machine.updates_check(c)[1], True)
                self.assertEqual(updates.due(c, BUNDLED_BUILT + EVERY), [updates.LISTS])

    def test_the_next_run_writes_the_record_again_from_the_start(self):
        for name, state in DAMAGED.items():
            with self.subTest(name):
                self.write_record(state)
                record = updates.run(updates.MANUAL, self.cfg(), BUNDLED_BUILT + EVERY, [updates.LISTS],
                                     self.fetchers(lists_fetch=unreachable_lists))
                self.assertIs(record["ok"], False)
                self.assertEqual(updates.status(self.cfg())["failures"], 1)

    def test_a_record_a_run_writes_reads_back_as_it_was(self):
        marks = {updates.LISTS: {"ok_at": AT}, updates.PLACES: {"failed_at": AT}}
        state = {"last": LAST, "failures": 0, "parts": marks}
        self.write_record(state)
        self.assertEqual(updates.read_state(), state)


class DatabaseTime(ScratchHome):
    def test_a_city_database_whose_download_time_cant_be_read_is_due_and_the_lists_are_still_checked(self):
        folder = geoip.user_folder()
        geo_fixtures.install(folder)
        about = os.path.join(folder, geoip.SETTINGS["files"]["about"])
        with open(about, encoding="utf-8") as f:
            found = json.load(f)
        with open(about, "w", encoding="utf-8") as f:
            json.dump(dict(found, built_at="not a time"), f)
        self.assertIsNotNone(geoip.database())
        self.assertEqual(updates.due(self.cfg(**SERVER), BUNDLED_BUILT + EVERY), [updates.LISTS, updates.PLACES])


class CutOff(ScratchHome):
    def test_a_lists_download_the_connection_cuts_off_is_a_failed_run_that_is_recorded(self):
        from test_downloads import CutShort
        stand_in = CutShort()
        self.addCleanup(stand_in.close)
        real = lists_build.http_fetch({"user_agent": "test", "timeout_s": 5, "retries": 0, "max_bytes": 1000})

        def cut_off(url, accept=None):  # every source answers with a chunked body the connection ends halfway
            return real(stand_in.base + "/chunked", accept)

        record = updates.run(updates.MANUAL, self.cfg(), BUNDLED_BUILT + EVERY, [updates.LISTS],
                             {updates.LISTS: cut_off})
        self.assertEqual((record["ok"], record["parts"]), (False, {updates.LISTS: updates.FAILED}))
        self.assertEqual(updates.status(self.cfg())["failures"], 1)
        self.assertEqual(lists.current().location, "bundled")


class Switch(ScratchHome):
    def test_turning_the_setting_off_during_an_automatic_run_starts_no_further_download(self):
        lists_fetch = fetcher(world(self.sources))

        def lists_then_off(url, accept=None):  # the settings page's switch, turned off while the lists download
            config.save_user(**{updates.SETTING: False})
            return lists_fetch(url, accept)

        places_fetch = Recorder(city_database)
        record = check_here(self.cfg(**SERVER), BUNDLED_BUILT + EVERY, self.fetchers(lists_then_off, places_fetch))
        self.assertEqual(places_fetch.urls, [])
        self.assertEqual(record["parts"], {updates.LISTS: updates.UPDATED})
        self.assertIsNone(geoip.database())

    def test_turned_off_before_an_automatic_run_starts_it_records_nothing(self):
        c = self.cfg(**SERVER)  # due checked with the setting on, then turned off before the run takes the lock
        config.save_user(**{updates.SETTING: False})
        fetchers = {part: Recorder(fetch) for part, fetch in self.fetchers().items()}
        self.assertIsNone(updates.run(updates.AUTO, c, BUNDLED_BUILT + EVERY, list(updates.PARTS), fetchers))
        self.assertEqual([fetch.urls for fetch in fetchers.values()], [[], []])
        self.assertIsNone(updates.status(self.cfg())["last"])

    def test_a_manual_run_updates_every_part_with_the_setting_off(self):
        c = self.cfg(**SERVER, **{updates.SETTING: False})
        record = updates.run(updates.MANUAL, c, BUNDLED_BUILT + EVERY, list(updates.PARTS), self.fetchers())
        self.assertEqual(record["parts"], {updates.LISTS: updates.UPDATED, updates.PLACES: updates.UPDATED})


@unittest.skipIf(os.geteuid() == 0, "root may write any file")
class LockOfAnotherUser(ScratchHome):
    """root running `agentcake lists update` on the data folder leaves a lock file only root may write. Opening it to
    write raised PermissionError before an update of AgentCake's own user started: it never ran and recorded nothing,
    while doctor and the settings page went on saying it would. flock() needs no write access to the file."""

    def setUp(self):
        super().setUp()
        lock = os.path.join(self.home, updates.settings()["lock_file"])
        with open(lock, "w", encoding="utf-8"):
            pass
        os.chmod(lock, 0o444)  # protocol: readable by all, writable by none: another user's file, as this one sees it

    def test_the_update_still_runs_and_is_recorded(self):
        record = updates.run(updates.AUTO, self.cfg(), BUNDLED_BUILT + EVERY, [updates.LISTS], self.fetchers())
        self.assertEqual((record["ok"], record["parts"]), (True, {updates.LISTS: updates.UPDATED}))
        self.assertEqual(updates.status(self.cfg())["last"]["parts"], {updates.LISTS: updates.UPDATED})

    def test_the_lock_still_lets_one_update_run_at_a_time(self):
        with updates.exclusive(wait=True) as held:
            self.assertTrue(held)
            self.assertIsNone(updates.run(updates.AUTO, self.cfg(), BUNDLED_BUILT + EVERY, [updates.LISTS],
                                          self.fetchers()))
        self.assertIsNone(updates.status(self.cfg())["last"])


class TestsStayOffline(unittest.TestCase):
    def test_every_test_and_tool_that_starts_serve_turns_the_monthly_update_off(self):
        online = []
        for folder in ("tests", "tools", os.path.join("web", "scripts")):
            for where, _, names in os.walk(os.path.join(ROOT, folder)):
                for name in (name for name in names if name.endswith((".py", ".mjs"))):
                    path = os.path.join(where, name)
                    with open(path, encoding="utf-8") as f:
                        source = f.read()
                    named = os.path.relpath(path, ROOT)
                    if STARTS_SERVE.search(source) and updates.SETTING not in source and named not in NO_SERVE:
                        online.append(named)
        self.assertEqual(sorted(online), [])


if __name__ == "__main__":
    unittest.main()
