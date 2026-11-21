"""The monthly update of the lists and the city database: agentcake/updates.py, without the internet.

    python3 -I -m unittest discover -s tests -p test_updates.py -v      (from the AgentCake folder)

A fake clock and fake downloads stand in for the date and the network: the lists' sources answer from
test_lists_build's small world, the city database from geo_fixtures; a guard notes every connection that would leave
this computer. Checks: on by default, on a computer and on a server; what is due (the lists a month after their last
success, counted from the day they were built, so a new release's lists are fresh; on a server the city database at
once while there is none, else a month after it was downloaded or last found current; nothing while the setting is
off; a part that failed waits about a day, restarts included); a run keeps what is in use when it fails, records when
and how it went and counts the failed runs in a row; two updates never run at once; the daily loop waits a random
moment first, then a day between checks, and a check that raises doesn't end it. Off, a check opens no connection;
on, the downloads ask only the addresses in sources.json and geo.json, through fake downloads and through the real
ones (refused by the guard); `agentcake lists update` records its run the same way.
"""
import contextlib
import datetime
import io
import json
import os
import random
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.request
from unittest import mock
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import geo_fixtures  # noqa: E402
from receiver import OutsideGuard  # noqa: E402
from test_lists_build import fetcher, recipe, world  # noqa: E402
from agentcake import cli, config, geoip, geoip_build, server, updates  # noqa: E402
from agentcake.detect import lists, lists_build  # noqa: E402

UTC = datetime.timezone.utc
DAY = datetime.timedelta(days=1)
AUTO = updates.settings()
EVERY = datetime.timedelta(days=AUTO["every_days"])
RETRY = datetime.timedelta(seconds=AUTO["retry_after_s"])
SERVER = {"public_listen": "127.0.0.1:8080", "trust_lb": True}  # protocol: server mode on the loopback address
BUNDLED_BUILT = datetime.datetime.combine(datetime.date.fromisoformat(lists.Lists.load(lists.BUNDLED_DIR).built),
                                          datetime.time(), tzinfo=UTC)


class Recorder:
    """A fetch() that notes every address it is asked for before the fake one answers."""

    def __init__(self, inner):
        self.inner, self.urls = inner, []

    def __call__(self, url, *args, **kwargs):
        self.urls.append(url)
        return self.inner(url, *args, **kwargs)


def city_database(url, path):
    """The city database's download, answered for any month with geo_fixtures' small database."""
    with open(path, "wb") as f:
        f.write(geo_fixtures.csv_gz(geo_fixtures.ROWS))
    return True


def not_published(url, path):
    """The city database's download while no newer month is out: DB-IP answers 404 (geoip_build.http_fetch)."""
    return False


def check_here(c, now, fetchers=None):
    """What the daily check has run, in this process: the parts due now (child() runs them in its own)."""
    parts = updates.due(c, now)
    return updates.run(updates.AUTO, c, now, parts, fetchers) if parts else None


def unreachable_lists(url, accept=None):
    raise lists_build.BuildError(f"{url}: unreachable")


def unreachable_places(url, path):
    raise geoip_build.BuildError(f"{url}: unreachable")


class ScratchHome(unittest.TestCase):
    """A CAKE_HOME of its own, the lists read again for it, and the small world's recipe in place of sources.json."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="cake-test-")
        self.addCleanup(shutil.rmtree, self.home, True)
        environment = mock.patch.dict(os.environ, {"CAKE_HOME": self.home})
        environment.start()
        self.addCleanup(environment.stop)
        lists.reload()
        self.addCleanup(lists.reload)
        self.sources = recipe()
        recipe_patch = mock.patch.object(lists_build, "read_recipe",
                                         return_value=(self.sources, lists_build.read_recipe()[1]))
        recipe_patch.start()
        self.addCleanup(recipe_patch.stop)

    def cfg(self, **values):
        config.save_user(**values)
        return config.load_cfg()

    def fetchers(self, lists_fetch=None, places_fetch=None):
        return {updates.LISTS: lists_fetch or fetcher(world(self.sources)), updates.PLACES: places_fetch or city_database}


class Setting(unittest.TestCase):
    def test_automatic_updates_are_on_by_default_on_a_computer_and_on_a_server(self):
        self.assertIs(config.DEFAULTS[updates.SETTING], True)
        with mock.patch.dict(os.environ, {"CAKE_HOME": tempfile.mkdtemp(prefix="cake-test-")}):
            config.save_user(**SERVER)
            self.assertIs(config.load_cfg()[updates.SETTING], True)

    def test_the_lists_are_updated_before_they_pass_their_age_limit(self):
        self.assertLessEqual(AUTO["every_days"], lists.update_settings()["max_age_days"])

    def test_after_a_failure_the_next_daily_check_is_not_skipped(self):
        self.assertLess(AUTO["retry_after_s"], AUTO["check_every_s"])


class Due(ScratchHome):
    def test_lists_younger_than_a_month_are_not_due(self):
        self.assertEqual(updates.due(self.cfg(), BUNDLED_BUILT + EVERY - DAY), [])

    def test_lists_are_due_a_month_after_the_day_they_were_built(self):
        self.assertEqual(updates.due(self.cfg(), BUNDLED_BUILT + EVERY), [updates.LISTS])

    def test_nothing_is_due_while_the_setting_is_off(self):
        later = BUNDLED_BUILT + 3 * EVERY
        self.assertEqual(updates.due(self.cfg(**SERVER, lists_auto_update=False), later), [])

    def test_on_this_computer_the_city_database_is_never_due(self):
        self.assertNotIn(updates.PLACES, updates.due(self.cfg(), BUNDLED_BUILT + 3 * EVERY))

    def test_on_a_server_without_a_city_database_it_is_due_at_once(self):
        self.assertEqual(updates.due(self.cfg(**SERVER), BUNDLED_BUILT + DAY), [updates.PLACES])

    def test_a_city_database_is_due_a_month_after_it_was_downloaded(self):
        geo_fixtures.install(geoip.user_folder())  # downloaded at geo_fixtures.NOW
        c = self.cfg(**SERVER)
        self.assertNotIn(updates.PLACES, updates.due(c, geo_fixtures.NOW + EVERY - DAY))
        self.assertIn(updates.PLACES, updates.due(c, geo_fixtures.NOW + EVERY))

    def test_a_city_database_found_current_counts_as_a_success(self):
        geo_fixtures.install(geoip.user_folder())  # this month's, downloaded at geo_fixtures.NOW
        c, checked = self.cfg(**SERVER), geo_fixtures.NOW + 10 * DAY
        record = updates.run(updates.AUTO, c, checked, [updates.PLACES], self.fetchers())
        self.assertEqual(record["parts"], {updates.PLACES: "current"})
        self.assertNotIn(updates.PLACES, updates.due(c, geo_fixtures.NOW + EVERY))
        self.assertIn(updates.PLACES, updates.due(c, checked + EVERY))

    def test_a_part_that_failed_waits_before_it_is_tried_again_restarts_included(self):
        c, failed = self.cfg(), BUNDLED_BUILT + EVERY
        updates.run(updates.AUTO, c, failed, [updates.LISTS], self.fetchers(lists_fetch=unreachable_lists))
        self.assertEqual(updates.due(c, failed + RETRY - DAY / 24), [])
        self.assertEqual(updates.due(c, failed + RETRY), [updates.LISTS])

    def test_a_city_database_that_failed_waits_while_the_lists_are_still_due(self):
        c, failed = self.cfg(**SERVER), BUNDLED_BUILT + EVERY
        updates.run(updates.AUTO, c, failed, [updates.PLACES], self.fetchers(places_fetch=unreachable_places))
        self.assertEqual(updates.due(c, failed + DAY / 24), [updates.LISTS])


class Run(ScratchHome):
    def test_a_successful_run_is_used_at_once_and_recorded(self):
        at = BUNDLED_BUILT + EVERY
        record = updates.run(updates.AUTO, self.cfg(), at, [updates.LISTS], self.fetchers())
        self.assertEqual((record["ok"], record["how"], record["parts"]), (True, updates.AUTO, {updates.LISTS: "updated"}))
        self.assertEqual(lists.current().built, at.date().isoformat())
        status = updates.status(self.cfg())
        self.assertEqual((status["last"]["at"], status["failures"], status["failing"]), (at.isoformat(), 0, False))

    def test_a_failed_run_keeps_the_lists_in_use_and_says_why(self):
        record = updates.run(updates.AUTO, self.cfg(), BUNDLED_BUILT + EVERY, [updates.LISTS],
                             self.fetchers(lists_fetch=unreachable_lists))
        self.assertEqual((record["ok"], record["parts"]), (False, {updates.LISTS: "failed"}))
        self.assertIn("unreachable", record["error"])
        self.assertEqual(lists.current().location, "bundled")
        self.assertEqual(updates.status(self.cfg())["failures"], 1)

    def test_failed_runs_in_a_row_warn_and_a_success_clears_them(self):
        c, at = self.cfg(), BUNDLED_BUILT + EVERY
        for _ in range(AUTO["warn_after_failures"]):
            updates.run(updates.AUTO, c, at, [updates.LISTS], self.fetchers(lists_fetch=unreachable_lists))
            at += DAY
        self.assertEqual(updates.status(c)["failures"], AUTO["warn_after_failures"])
        self.assertTrue(updates.status(c)["failing"])
        updates.run(updates.AUTO, c, at, [updates.LISTS], self.fetchers())
        self.assertEqual((updates.status(c)["failures"], updates.status(c)["failing"]), (0, False))

    def test_a_city_database_that_fails_fails_the_run_while_the_lists_are_updated(self):
        record = updates.run(updates.AUTO, self.cfg(**SERVER), BUNDLED_BUILT + EVERY, list(updates.PARTS),
                             self.fetchers(places_fetch=unreachable_places))
        self.assertEqual(record["parts"], {updates.LISTS: "updated", updates.PLACES: "failed"})
        self.assertFalse(record["ok"])
        self.assertIsNone(geoip.database())

    def test_on_this_computer_the_city_database_is_skipped_and_the_run_succeeds(self):
        record = updates.run(updates.MANUAL, self.cfg(), BUNDLED_BUILT + EVERY, list(updates.PARTS), self.fetchers())
        self.assertEqual(record["parts"], {updates.LISTS: "updated", updates.PLACES: "skipped"})
        self.assertTrue(record["ok"])

    def test_the_error_kept_is_cut_to_its_length(self):
        def long_error(url, accept=None):
            raise lists_build.BuildError(url + "x" * (2 * AUTO["error_chars"]))

        record = updates.run(updates.AUTO, self.cfg(), BUNDLED_BUILT + EVERY, [updates.LISTS],
                             self.fetchers(lists_fetch=long_error))
        self.assertEqual(len(record["error"]), AUTO["error_chars"])
        self.assertEqual(updates.status(self.cfg())["last"]["error"], record["error"])

    def test_a_background_update_skips_its_turn_while_another_one_runs(self):
        with updates.exclusive(wait=True):
            self.assertIsNone(updates.run(updates.AUTO, self.cfg(), BUNDLED_BUILT + EVERY, [updates.LISTS],
                                          self.fetchers()))
        self.assertIsNone(updates.status(self.cfg())["last"])

    def test_a_check_hands_the_child_only_the_parts_that_are_due(self):
        geo_fixtures.install(geoip.user_folder())  # November's, downloaded at geo_fixtures.NOW
        c, handed = self.cfg(**SERVER), []

        def child(parts):  # stands in for child_command(): notes the parts, and a process that does nothing
            handed.append(parts)
            return [sys.executable, "-I", "-c", "pass"]

        self.assertIsNone(updates.check(c, BUNDLED_BUILT + DAY, child))  # the release's lists, a new database
        updates.run(updates.AUTO, c, BUNDLED_BUILT + EVERY - 5 * DAY, [updates.PLACES],
                    self.fetchers(places_fetch=not_published))  # found current five days before the lists are due
        self.assertIsNone(updates.check(c, BUNDLED_BUILT + EVERY, child))
        self.assertEqual(handed, [[updates.LISTS]])


class Loop(unittest.TestCase):
    class Stop:
        """threading.Event as the loop uses it: each wait is noted, and the loop is told to stop after `rounds`."""

        def __init__(self, rounds):
            self.rounds, self.waits = rounds, []

        def wait(self, timeout):
            self.waits.append(timeout)
            return len(self.waits) > self.rounds

    def test_the_first_check_waits_a_random_moment_then_one_day_between_checks(self):
        stop, checks = self.Stop(rounds=3), []
        updates.loop(stop, 123.0, AUTO["check_every_s"], lambda: checks.append(True))
        self.assertEqual(stop.waits, [123.0] + [AUTO["check_every_s"]] * 3)
        self.assertEqual(len(checks), 3)

    def test_the_first_moment_is_random_within_its_window(self):
        low, high = AUTO["first_check_s"]
        moments = [updates.first_wait(random.Random(seed)) for seed in range(20)]
        self.assertTrue(all(low <= moment <= high for moment in moments))
        self.assertGreater(len(set(moments)), 1)

    def test_a_check_that_raises_does_not_end_the_loop(self):
        stop, calls = self.Stop(rounds=2), []

        def check():
            calls.append(True)
            if len(calls) == 1:
                raise RuntimeError("a bug in one check")

        with contextlib.redirect_stderr(io.StringIO()) as err:
            updates.loop(stop, 1.0, AUTO["check_every_s"], check)
        self.assertEqual(len(calls), 2)
        self.assertIn("a bug in one check", err.getvalue())


class Serve(unittest.TestCase):
    """`agentcake serve` starts the daily checks with its other threads, and ends them when it stops."""

    class Listener:
        """A local listener whose loop returns at once, as after a SIGTERM."""

        def serve_forever(self):
            pass

        def server_close(self):
            pass

    def test_serve_starts_the_checks_and_ends_them_when_it_stops(self):
        checks, upkeep = threading.Event(), threading.Event()
        with mock.patch.dict(os.environ, {"CAKE_HOME": tempfile.mkdtemp(prefix="cake-test-")}), \
                mock.patch.object(server, "make_listeners", return_value=(self.Listener(), None)), \
                mock.patch.object(server, "stop_on_signals"), \
                mock.patch.object(server.maintenance, "start", return_value=upkeep), \
                mock.patch.object(updates, "start", return_value=checks) as started, \
                contextlib.redirect_stdout(io.StringIO()):
            server.serve()
        started.assert_called_once_with()
        self.assertTrue(checks.is_set() and upkeep.is_set())


def hosts(urls):
    return {urlsplit(url).hostname for url in urls}


class Network(ScratchHome):
    """What goes online: nothing while the setting is off; only the addresses in sources.json and geo.json while on."""

    def allowed_hosts(self, sources, signer_hosts):
        """The hosts sources.json and geo.json name: GitHub's two, each published range's, each signer's (its
        directory address with the host filled in) and DB-IP's."""
        github = [sources["github"]["commit_api"], sources["github"]["raw"]]
        ranges = [url for spec in sources["ip_ranges"]["ranges"] for url in spec["urls"]]
        signers = [sources["signers"]["directory"].format(host=host) for host in signer_hosts]
        return hosts(github + ranges + signers + [geoip.SETTINGS["source"]["url"]])

    def test_off_a_check_opens_no_connection(self):
        c = self.cfg(**SERVER, lists_auto_update=False)  # no city database, lists three months old: all would be due
        with OutsideGuard() as guard:
            self.assertIsNone(updates.check(c, BUNDLED_BUILT + 3 * EVERY))
        self.assertEqual((guard.outside, guard.local), ([], []))
        self.assertIsNone(updates.status(c)["last"])

    def test_on_the_downloads_ask_only_the_addresses_in_sources_and_geo(self):
        c = self.cfg(**SERVER)
        lists_fetch, places_fetch = Recorder(fetcher(world(self.sources))), Recorder(city_database)
        with OutsideGuard() as guard:
            record = check_here(c, BUNDLED_BUILT + EVERY, self.fetchers(lists_fetch, places_fetch))
        self.assertEqual(record["parts"], {updates.LISTS: "updated", updates.PLACES: "updated"})
        self.assertEqual(guard.outside, [])
        asked = lists_fetch.urls + places_fetch.urls
        self.assertTrue(lists_fetch.urls and places_fetch.urls)
        self.assertEqual({urlsplit(url).scheme for url in asked}, {"https"})
        # the signers are botscent's registry (fetched from GitHub, as sources.json says) and sources.json's own
        self.assertLessEqual(hosts(asked), self.allowed_hosts(self.sources, lists.current().signer_hosts()))

    def test_on_the_real_downloads_reach_only_the_hosts_sources_and_geo_name(self):
        if any(urllib.request.getproxies().get(scheme) for scheme in ("http", "https")):
            self.skipTest("a proxy is set: the downloads would connect to it")
        c = self.cfg(**SERVER)
        with mock.patch.object(lists_build, "read_recipe", _real_recipe), OutsideGuard() as guard:
            record = check_here(c, BUNDLED_BUILT + EVERY)  # the real downloads, here: every connection is refused
        self.assertEqual(record["parts"], {updates.LISTS: "failed", updates.PLACES: "failed"})
        self.assertEqual(guard.local, [])
        refused = {where if isinstance(where, str) else where[0] for where in guard.outside}
        self.assertTrue(refused)
        signer_hosts = lists.Lists.load(lists.BUNDLED_DIR).signer_hosts()
        self.assertLessEqual(refused, self.allowed_hosts(_real_recipe()[0], signer_hosts))
        self.assertEqual(lists.current().location, "bundled")
        self.assertIsNone(geoip.database())


def _real_recipe():
    """sources.json and kinds.json as the package has them (ScratchHome puts the small world's recipe in place)."""
    with open(lists.SOURCES_FILE, encoding="utf-8") as f:
        sources = json.load(f)
    with open(lists.KINDS_FILE, encoding="utf-8") as f:
        kinds = json.load(f)["kinds"]
    return sources, kinds


class ListsCommand(ScratchHome):
    """`agentcake lists update` runs every part and records its run as the background update does."""

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_a_manual_update_is_recorded(self):
        with mock.patch.object(lists_build, "http_fetch", return_value=fetcher(world(self.sources))):
            code, out, _ = self.run_cli("lists", "update")
        self.assertEqual(code, 0)
        last = updates.status(config.load_cfg())["last"]
        self.assertEqual((last["how"], last["ok"], last["parts"]),
                         (updates.MANUAL, True, {updates.LISTS: "updated", updates.PLACES: "skipped"}))
        self.assertTrue(json.loads(out)["location"].startswith(lists.user_root()))

    def test_a_manual_update_that_fails_is_recorded_and_exits_1(self):
        with mock.patch.object(lists_build, "http_fetch", return_value=unreachable_lists):
            code, _, err = self.run_cli("lists", "update")
        self.assertEqual(code, 1)
        self.assertIn("lists not updated", err)
        last = updates.status(config.load_cfg())["last"]
        self.assertEqual((last["how"], last["ok"]), (updates.MANUAL, False))


if __name__ == "__main__":
    unittest.main()
