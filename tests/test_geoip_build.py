"""Downloading and converting the city database: agentcake/geoip_build.py, without the internet.

    python3 -I -m unittest discover -s tests -p test_geoip_build.py -v      (from the AgentCake folder)

DB-IP's CSV becomes fixed-length records: neighbouring ranges of one place make one record, a gap or what lies after
the last range has no place, and a file out of order or not DB-IP's stops the conversion. A download takes this
month's file, or last month's until this month's is published, and swaps the new database in whole; when anything
fails the database in use stays. `agentcake lists update` downloads it only on an AgentCake that sees visitor
addresses. The real download (urllib) is tried against a server on this computer; the rest gets its files from a
function the tests pass in.
"""
import contextlib
import datetime
import gzip
import hashlib
import http.server
import io
import ipaddress
import json
import os
import shutil
import tempfile
import threading
import unittest
from unittest import mock

import geo_fixtures
from agentcake import cli, config, geoip, geoip_build, wording
from agentcake.detect import lists, lists_build

BELOW_TEST_NET_1 = str(ipaddress.ip_address("192.0.2.0") - 1)  # computed, so no public address is written here

SERVER = {"public_listen": "127.0.0.1:8080", "trust_lb": True}


class Fetcher:
    """fetch(url, path) as http_fetch gives it: {month: gzipped body} written to path, False for a month not in it."""

    def __init__(self, bodies):
        self.bodies, self.asked = bodies, []

    def __call__(self, url, path):
        self.asked.append(url)
        month = next((m for m in self.bodies if m in url), None)
        if month is None:
            return False
        with open(path, "wb") as f:
            f.write(self.bodies[month])
        return True


def any_month(body):
    """fetch() that answers every month with body: for what runs on today's clock."""
    def fetch(url, path):
        with open(path, "wb") as f:
            f.write(body)
        return True
    return fetch


def unreachable(url, path):
    raise geoip_build.BuildError(f"{url}: network is down")


class BuildCase(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="cake-geo-build-test-")
        self.addCleanup(shutil.rmtree, self.home, True)
        environment = mock.patch.dict(os.environ, {"CAKE_HOME": self.home})
        environment.start()
        self.addCleanup(environment.stop)
        self.root = geoip.user_folder()

    def convert(self, rows):
        return geo_fixtures.install(self.root, rows)


class Convert(BuildCase):
    def test_neighbouring_ranges_of_one_place_make_one_record(self):
        about = self.convert(geo_fixtures.ROWS)
        self.assertEqual(about["records"], {"ipv4": 9, "ipv6": 4}, "the two Paris rows are one record")
        self.assertEqual((about["rows"], about["places"]), (len(geo_fixtures.ROWS), 7))

    def test_the_csvs_sha1_is_kept_to_compare_with_db_ips(self):
        about = self.convert(geo_fixtures.ROWS)
        published = gzip.decompress(geo_fixtures.csv_gz(geo_fixtures.ROWS))
        self.assertEqual(about["csv_sha1"], hashlib.sha1(published).hexdigest())

    def test_a_gap_and_the_addresses_after_the_last_range_have_no_place(self):
        self.convert([("192.0.2.0", "192.0.2.9", "NA", "US", "", ""), ("192.0.2.20", "192.0.2.29", "EU", "DE", "", "")])
        found = {address: (geoip.place(address) or {}).get("country") for address in
                 (BELOW_TEST_NET_1, "192.0.2.5", "192.0.2.15", "192.0.2.25", "192.0.2.30", "203.0.113.1")}
        self.assertEqual(found, {BELOW_TEST_NET_1: None, "192.0.2.5": "US", "192.0.2.15": None, "192.0.2.25": "DE",
                                 "192.0.2.30": None, "203.0.113.1": None})

    def test_a_long_region_name_is_kept_whole(self):
        self.convert(geo_fixtures.single("192.0.2.10", "FR", "Provence-Alpes-Côte d'Azur", "Marseille"))
        self.assertEqual(geoip.place("192.0.2.10")["subdivision"], "Provence-Alpes-Côte d'Azur")

    def test_the_notice_names_db_ip_the_licence_and_the_month(self):
        self.convert(geo_fixtures.ROWS)
        with open(os.path.join(self.root, geoip.FILES["notice"]), encoding="utf-8") as f:
            notice = f.read()
        for words in (geoip.SETTINGS["attribution"]["text"], geoip.SETTINGS["attribution"]["url"],
                      geoip.SETTINGS["license"]["url"], geo_fixtures.MONTH):
            self.assertIn(words, notice)

    def test_a_file_that_is_not_db_ips_stops_the_conversion(self):
        cases = {"out of order": [geo_fixtures.ROWS[2], geo_fixtures.ROWS[1]],
                 "overlapping": [("192.0.2.0", "192.0.2.9", "NA", "US", "", ""),
                                 ("192.0.2.5", "192.0.2.19", "NA", "US", "", "")],
                 "not an address": [("192.0.2", "192.0.2.9", "NA", "US", "", "")],
                 "ends before it starts": [("192.0.2.9", "192.0.2.0", "NA", "US", "", "")],
                 "not a country code": [("192.0.2.0", "192.0.2.9", "NA", "USA", "", "")],
                 "too few columns": [("192.0.2.0", "192.0.2.9")],
                 "no rows": []}
        for case, rows in cases.items():
            with self.subTest(case), self.assertRaises(geoip_build.BuildError):
                geo_fixtures.install(os.path.join(self.home, "x"), rows)

    def test_a_download_cut_short_stops_the_conversion(self):
        cut = os.path.join(self.home, "cut.csv.gz")
        with open(cut, "wb") as f:
            f.write(geo_fixtures.csv_gz(geo_fixtures.ROWS)[:-20])
        with self.assertRaises(geoip_build.BuildError):
            geoip_build.convert(cut, self.home, geo_fixtures.MONTH, "https://example.com/cut", geo_fixtures.NOW)


class Download(BuildCase):
    def test_this_months_file_is_used_once_it_is_published(self):
        fetch = Fetcher({"2026-11": geo_fixtures.csv_gz(geo_fixtures.ROWS)})
        self.assertEqual(geoip_build.download(self.root, fetch, geo_fixtures.NOW),
                         {"updated": self.root, "month": "2026-11"})
        self.assertEqual(fetch.asked, [geoip_build.SOURCE["url"].format(month="2026-11")])
        self.assertEqual(geoip.place("198.51.100.7")["country"], "JP")

    def test_last_months_file_is_used_until_this_months_is_published(self):
        fetch = Fetcher({"2026-10": geo_fixtures.csv_gz(geo_fixtures.ROWS)})
        early = datetime.datetime(2026, 11, 1, 3, tzinfo=datetime.timezone.utc)
        self.assertEqual(geoip_build.download(self.root, fetch, early)["month"], "2026-10")
        self.assertEqual(len(fetch.asked), 2)

    def test_last_months_file_of_january_is_decembers(self):
        self.assertEqual(geoip_build.months(datetime.datetime(2027, 1, 1, tzinfo=datetime.timezone.utc)),
                         ["2027-01", "2026-12"])

    def test_with_nothing_published_it_fails_and_the_database_in_use_stays(self):
        self.convert(geo_fixtures.single("192.0.2.10", "US"))
        with self.assertRaises(geoip_build.BuildError):
            geoip_build.download(self.root, Fetcher({}), geo_fixtures.NOW)
        self.assertEqual(geoip.place("192.0.2.10")["country"], "US")

    def test_a_download_that_cannot_be_read_leaves_the_database_in_use_and_no_leftovers(self):
        self.convert(geo_fixtures.single("192.0.2.10", "US"))
        with self.assertRaises(geoip_build.BuildError):
            geoip_build.download(self.root, Fetcher({"2026-11": b"not gzip"}), geo_fixtures.NOW)
        self.assertEqual(geoip.place("192.0.2.10")["country"], "US")
        self.assertEqual(sorted(os.listdir(self.home)), [os.path.basename(self.root)])

    def test_the_month_in_use_is_not_downloaded_again(self):
        fetch = Fetcher({"2026-11": geo_fixtures.csv_gz(geo_fixtures.ROWS)})
        self.assertEqual(geoip_build.download(self.root, fetch, geo_fixtures.NOW, have="2026-11"), {"current": "2026-11"})
        self.assertEqual(fetch.asked, [])

    def test_a_new_month_replaces_the_old_database_whole(self):
        self.convert(geo_fixtures.single("192.0.2.10", "US"))
        fetch = Fetcher({"2026-11": geo_fixtures.csv_gz(geo_fixtures.single("192.0.2.10", "NZ"))})
        geoip_build.download(self.root, fetch, geo_fixtures.NOW, have="2026-10")
        self.assertEqual(geoip.place("192.0.2.10")["country"], "NZ")
        self.assertEqual(sorted(os.listdir(self.home)), [os.path.basename(self.root)])
        self.assertNotIn(geoip.FILES["download"], os.listdir(self.root))

    def test_what_a_stopped_update_left_behind_is_removed(self):
        for prefix in (geoip_build.FOLDER["staging_prefix"], geoip_build.FOLDER["retired_prefix"]):
            os.makedirs(os.path.join(self.home, prefix + "stopped"))
        geoip_build.download(self.root, Fetcher({"2026-11": geo_fixtures.csv_gz(geo_fixtures.ROWS)}), geo_fixtures.NOW)
        self.assertEqual(sorted(os.listdir(self.home)), [os.path.basename(self.root)])

    def test_the_database_is_readable_by_others_as_the_umask_allows(self):
        """As everything else in the data folder, whose own mode keeps other users out: a database another user wrote
        (root running `agentcake lists update`) can still be read by AgentCake's own."""
        previous = os.umask(0o022)
        try:
            geoip_build.download(self.root, Fetcher({"2026-11": geo_fixtures.csv_gz(geo_fixtures.ROWS)}),
                                 geo_fixtures.NOW)
        finally:
            os.umask(previous)
        self.assertEqual(os.stat(self.root).st_mode & 0o777, 0o755)


class ListsUpdatePart(BuildCase):
    def test_on_this_computer_the_city_database_is_not_downloaded(self):
        fetch = Fetcher({"2026-11": geo_fixtures.csv_gz(geo_fixtures.ROWS)})
        self.assertEqual(geoip_build.update(fetch=fetch, now=geo_fixtures.NOW), {"skipped": "local"})
        self.assertEqual(fetch.asked, [])

    def test_on_a_server_it_is_downloaded_into_cake_home(self):
        config.save_user(**SERVER)
        fetch = Fetcher({"2026-11": geo_fixtures.csv_gz(geo_fixtures.ROWS)})
        self.assertEqual(geoip_build.update(fetch=fetch, now=geo_fixtures.NOW)["month"], "2026-11")
        self.assertEqual(geoip.status()["folder"], geoip.paths.tilde(geoip.user_folder()))

    def test_a_database_of_this_month_is_not_downloaded_again(self):
        config.save_user(**SERVER)
        geo_fixtures.install(geoip.user_folder())
        fetch = Fetcher({"2026-11": geo_fixtures.csv_gz(geo_fixtures.ROWS)})
        self.assertEqual(geoip_build.update(fetch=fetch, now=geo_fixtures.NOW), {"current": "2026-11"})
        self.assertEqual(fetch.asked, [])


class Commands(BuildCase):
    """`agentcake lists` and `agentcake lists update` (cli.py), in-process; the lists' own part is the release's, not
    fetched."""

    def command(self, function, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                mock.patch.object(lists_build, "update", return_value=os.path.join(self.home, "lists", "today")):
            code = function(list(argv))
        lists.reload()
        return code, out.getvalue(), err.getvalue()

    def test_lists_update_on_a_server_downloads_the_city_database_too(self):
        config.save_user(**SERVER)
        with mock.patch.object(geoip_build, "http_fetch", return_value=any_month(geo_fixtures.csv_gz(geo_fixtures.ROWS))):
            code, out, _ = self.command(cli.main, "lists", "update")
        self.assertEqual(code, 0)
        said = json.loads(out)
        self.assertEqual(said["places_update"]["month"], said["places"]["month"])
        self.assertEqual(said["places"]["folder"], geoip.paths.tilde(geoip.user_folder()))

    def test_a_city_database_that_cannot_be_fetched_fails_the_command_and_says_so(self):
        config.save_user(**SERVER)
        with mock.patch.object(geoip_build, "http_fetch", return_value=unreachable):
            code, out, err = self.command(cli.main, "lists", "update")
        self.assertEqual(code, 1)
        before_error = wording.text("places_not_updated", error="\x00", name="\x01").split("\x00")[0]
        self.assertIn(before_error, err)  # the sentence from copy.en.json, whatever its wording
        self.assertIn("updated", json.loads(out), "the lists were still updated")

    def test_lists_update_on_this_computer_skips_the_city_database(self):
        with mock.patch.object(geoip_build, "http_fetch", return_value=unreachable):
            code, out, _ = self.command(cli.main, "lists", "update")
        self.assertEqual((code, json.loads(out)["places_update"], json.loads(out)["places"]), (0, {"skipped": "local"}, None))

    def test_lists_names_the_city_database_in_use(self):
        geo_fixtures.install(self.root)
        code, out, _ = self.command(cli.main, "lists")
        self.assertEqual((code, json.loads(out)["places"]["month"]), (0, geo_fixtures.MONTH))


class Answers(http.server.BaseHTTPRequestHandler):
    """A server on this computer answering as DB-IP's would: /ok the file, /missing 404, /broken 500."""
    body, asked = geo_fixtures.csv_gz(geo_fixtures.ROWS), []

    def do_GET(self):
        Answers.asked.append(self.path)
        status = {"/ok": 200, "/missing": 404}.get(self.path, 500)
        self.send_response(status)
        self.send_header("Content-Length", str(len(self.body) if status == 200 else 0))
        self.end_headers()
        if status == 200:
            self.wfile.write(self.body)

    def log_message(self, *args):
        pass


class HttpFetch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Answers)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="cake-geo-fetch-")
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.path = os.path.join(self.folder, "download.csv.gz")
        Answers.asked.clear()

    def test_a_published_file_is_written_whole(self):
        self.assertTrue(geoip_build.http_fetch()(self.base + "/ok", self.path))
        with open(self.path, "rb") as f:
            self.assertEqual(f.read(), Answers.body)

    def test_a_month_not_published_yet_answers_false(self):
        self.assertFalse(geoip_build.http_fetch()(self.base + "/missing", self.path))

    def test_a_failing_server_is_asked_again_then_it_fails(self):
        with self.assertRaises(geoip_build.BuildError):
            geoip_build.http_fetch()(self.base + "/broken", self.path)
        self.assertEqual(len(Answers.asked), geoip_build.FETCH["retries"] + 1)

    def test_a_file_larger_than_the_limit_fails(self):
        with self.assertRaises(geoip_build.BuildError):
            geoip_build.http_fetch(dict(geoip_build.FETCH, max_bytes=len(Answers.body) - 1))(self.base + "/ok", self.path)


if __name__ == "__main__":
    unittest.main()
