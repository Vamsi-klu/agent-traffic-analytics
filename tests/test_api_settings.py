"""GET and POST /api/settings (agentcake/api/settings.py).

    python3 -I -m unittest discover -s tests -p test_api_settings.py -v      (from the AgentCake folder)

GET answers the contract from the settings in use: the website's domain and site key and the line to add (with that
key), where visits come from and when each source last sent something, which headers the server half's recent page
requests arrived without and how the last log import went, how old the lists are against their age limit, how often the page asks
again, retention and the disk (with the share of the budget freeing space stops at, which the page's description
of auto_free states, from auto_free_target_ratio), the page script's two settings (hook_dom, hide_selectors) and the
four layers, which are not settings. A POST of only the fields to change saves retention_days, budget_mb, auto_free, site_domain,
hook_dom and hide_selectors to config.json under those names, checked as `agentcake config set` checks them, and answers
the whole Settings; a bad value, an unknown field or a budget off the list is a 400 that saves nothing. Only this
computer's own pages can post (403), only JSON (415).
"""
import datetime
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from collections import namedtuple
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from api_client import Client, contract_problems  # noqa: E402
from cake_server import AGENTCAKE  # noqa: E402
from agentcake import config, log_report, store, updates, wording  # noqa: E402
from agentcake.api import periods, visits  # noqa: E402
from agentcake.detect import lists, lists_build  # noqa: E402
from agentcake.units import BYTES_PER_MB, MS_PER_DAY, MS_PER_S, PERCENT  # noqa: E402

DiskUsage = namedtuple("DiskUsage", "total used free")  # what shutil.disk_usage returns
FETCH = {"s": "same-origin", "m": "navigate", "d": "document", "u": "?1"}  # a browser's Sec-Fetch-* in a token


class SettingsCase(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="cake-test-")
        os.environ["CAKE_HOME"] = self.home
        os.environ.pop("CAKE_PORT", None)
        config.save_user(site_key="ck_settings", disk_min_free_mb=0)
        self.client = Client()

    def settings(self):
        answer = self.client.get("/api/settings")
        self.assertEqual(answer.status, 200, answer.body)
        self.assertEqual(contract_problems(answer.body, "settings"), [])
        return answer.body

    def saved(self):
        with open(os.path.join(self.home, "config.json")) as f:
            return json.load(f)

    def refused(self, body, status=400, **kwargs):
        before = self.saved()
        answer = self.client.post("/api/settings", body, **kwargs)
        self.assertEqual(answer.status, status, answer.body)
        self.assertEqual(contract_problems(answer.body, "error"), [])
        self.assertEqual(self.saved(), before, "nothing saved")
        return answer.body["error"]

    def visit(self, sid, origin, end_ms, token=None):
        """A session that last sent something at end_ms; token: the body of a server-half token it brought."""
        con = visits.connect()
        try:
            con.execute("INSERT INTO sessions(id, start_ms, end_ms, origin, is_test) VALUES(?, ?, ?, ?, 0)",
                        (sid, end_ms, end_ms, origin))
            if token is not None:
                con.execute("INSERT INTO srv(id, session_id, recv_ms, page_ms, path, body) VALUES(?, ?, ?, ?, '/', ?)",
                            ("t-" + sid, sid, end_ms, end_ms, json.dumps(token)))
            con.commit()
        finally:
            con.close()


class Settings(SettingsCase):
    def test_get_answers_the_settings_in_use(self):
        body = self.settings()
        self.assertEqual((body["retention_days"], body["budget_mb"], body["auto_free"]), (0, 10240, True))
        self.assertIn(body["budget_mb"], body["budget_choices_mb"])
        self.assertEqual((body["site_domain"], body["site_key"]), ("", "ck_settings"))
        self.assertIn('data-site="ck_settings"', body["script_tag"], "the line to add carries the real site key")
        self.assertEqual((body["hook_dom"], body["hide_selectors"]), (False, ""))
        self.assertEqual(body["database"]["sessions"], 0)
        self.assertNotIn("layers", body, "where each layer works is the page's words, the same on any install")
        self.assertLessEqual(body["refresh_ms"], 10_000, "connected shows within 10 s while the page is open")

    def test_storage_says_how_much_of_the_disk_is_free_and_why_new_replays_stop(self):
        # the settings page explains a disk below its floor with the floor and the free space in bytes
        config.save_user(disk_min_free_mb=2000)
        nearly_full = DiskUsage(1000 * 1000 * BYTES_PER_MB, 0, 1500 * BYTES_PER_MB)
        with mock.patch("shutil.disk_usage", return_value=nearly_full):
            storage = self.settings()["storage"]
        self.assertEqual(storage["disk"], {"total": 1000 * 1000 * BYTES_PER_MB, "free": 1500 * BYTES_PER_MB,
                                           "min_free": 2000 * BYTES_PER_MB, "low": True})
        self.assertEqual(storage["replays_stopped"], "disk", "below the floor no replay is deleted, new ones stop")
        config.save_user(auto_free=False)
        with mock.patch("shutil.disk_usage", return_value=nearly_full):
            self.assertEqual(self.settings()["storage"]["replays_stopped"], "disk", "auto_free changes nothing here")
        with mock.patch("shutil.disk_usage", return_value=nearly_full._replace(free=2000 * BYTES_PER_MB)):
            self.assertIsNone(self.settings()["storage"]["replays_stopped"], "at the floor")

    def test_the_share_freeing_space_stops_at_follows_the_config(self):
        # The page's description of auto_free states this number, so it may never be written into the page's words
        default = config.SCHEMA["auto_free_target_ratio"]["default"]
        self.assertEqual(self.settings()["storage"]["free_to_pct"], round(default * PERCENT))
        config.save_user(auto_free_target_ratio=0.75)
        self.assertEqual(self.settings()["storage"]["free_to_pct"], 75)

    def test_a_budget_set_elsewhere_is_among_the_choices(self):
        config.save_user(budget_mb=3000)
        body = self.settings()
        self.assertEqual(body["budget_mb"], 3000)
        self.assertIn(3000, body["budget_choices_mb"])

    def test_the_lists_say_their_date_and_warn_after_i4(self):
        status = lists.current().status()
        lists_answer = self.settings()["lists"]
        self.assertEqual((lists_answer["built"], lists_answer["max_age_days"]), (status["built"], status["max_age_days"]))
        self.assertTrue(lists_answer["update_command"].endswith("lists update"))
        built = datetime.date.fromisoformat(status["built"])
        late = built + datetime.timedelta(days=status["max_age_days"] + 1)
        with mock.patch.object(lists.Lists, "status", lambda snapshot, max_age_days=None, today=None:
                               dict(status, age_days=(late - built).days, stale=True)):
            self.assertTrue(self.settings()["lists"]["stale"])

    def test_automatic_updates_are_on_by_default(self):
        self.assertIs(self.settings()["lists_auto_update"], True)

    def test_the_update_takes_in_the_city_database_only_where_it_downloads_it(self):
        """On a server that reads the visitor's address (public_listen and trust_lb), as updates.due() and doctor say;
        a public listener without trust_lb never looks up a place, so its update leaves the database out."""
        for values, downloads in (({}, False), ({"public_listen": "127.0.0.1:8080"}, False),
                                  ({"public_listen": "127.0.0.1:8080", "trust_lb": True}, True)):
            config.save_user(**values)
            self.assertIs(self.settings()["lists"]["city_database"], downloads, values)

    def test_before_any_update_there_is_no_last_update(self):
        self.assertEqual({key: self.settings()["lists"][key] for key in ("last_update", "failures", "failing")},
                         {"last_update": None, "failures": 0, "failing": False})

    def test_the_last_update_says_when_it_ran_and_why_it_failed(self):
        def unreachable(url, accept=None):
            raise lists_build.BuildError(f"{url}: unreachable")

        updates.run(updates.AUTO, parts=[updates.LISTS], fetchers={updates.LISTS: unreachable})
        ran_ms = datetime.datetime.fromisoformat(updates.status()["last"]["at"]).timestamp() * MS_PER_S
        answer = self.settings()["lists"]
        self.assertEqual(answer["last_update"]["when"], periods.when(ran_ms, periods.now_ms(), None))
        self.assertIs(answer["last_update"]["ok"], False)
        self.assertIn("unreachable", answer["last_update"]["error"])
        self.assertEqual((answer["failures"], answer["failing"]), (1, False))
        for _ in range(updates.settings()["warn_after_failures"] - 1):
            updates.run(updates.AUTO, parts=[updates.LISTS], fetchers={updates.LISTS: unreachable})
        self.assertIs(self.settings()["lists"]["failing"], True)


class Changes(SettingsCase):
    def test_a_post_turns_automatic_updates_off_and_back_on(self):
        answer = self.client.post("/api/settings", {"lists_auto_update": False})
        self.assertEqual(answer.status, 200, answer.body)
        self.assertEqual(contract_problems(answer.body, "settings"), [])
        self.assertIs(answer.body["lists_auto_update"], False)
        self.assertIs(self.saved()["lists_auto_update"], False)
        self.assertEqual(updates.due(config.load_cfg(), datetime.datetime.now(datetime.timezone.utc)
                                     + datetime.timedelta(days=updates.settings()["every_days"] * 3)), [])
        self.assertIs(self.client.post("/api/settings", {"lists_auto_update": True}).body["lists_auto_update"], True)
        self.assertEqual(self.refused({"lists_auto_update": "off"}), "lists_auto_update must be true or false.")

    def test_a_post_saves_only_what_it_names_and_config_get_reads_the_same(self):
        changes = {"retention_days": 90, "budget_mb": 20480, "auto_free": False, "site_domain": "https://Shop.example/",
                   "hook_dom": True, "hide_selectors": ".account-email, #address"}
        answer = self.client.post("/api/settings", changes)
        self.assertEqual(answer.status, 200, answer.body)
        self.assertEqual(contract_problems(answer.body, "settings"), [])
        tidied = dict(changes, site_domain="Shop.example")  # as `config set` tidies it: no scheme, no slash
        self.assertEqual({key: answer.body[key] for key in changes}, tidied)
        saved = self.saved()
        self.assertEqual({key: saved[key] for key in changes}, tidied)
        self.assertEqual(saved["site_key"], "ck_settings")
        printed = subprocess.run(AGENTCAKE + ["config", "get"], capture_output=True, text=True, check=True).stdout
        for key, value in tidied.items():
            line = next(line for line in printed.splitlines() if line.split()[:1] == [key])
            self.assertIn(json.dumps(value), line, key)

    def test_cake_js_carries_the_page_script_settings(self):
        self.client.post("/api/settings", {"hook_dom": True, "hide_selectors": "#address"})
        served = self.client.get("/cake.js").body
        self.assertIn('"hide_selectors":"#address","hook_dom":true', served)

    def test_bad_values_are_refused_and_nothing_is_saved(self):
        self.assertEqual(self.refused({"retention_days": 45}), wording.raw("invalid_setting")["retention_days"])
        self.assertIn("budget_mb must be one of", self.refused({"budget_mb": 7000}))
        self.assertEqual(self.refused({"auto_free": "yes"}), "auto_free must be true or false.")
        self.assertEqual(self.refused({"retention_days": True}), "retention_days must be a whole number.")
        self.assertEqual(self.refused({"hook_dom": 1}), "hook_dom must be true or false.")
        self.assertIn("site_domain", self.refused({"site_domain": "shop example.com"}))
        self.assertIn("hide_selectors", self.refused({"hide_selectors": "#a {color: red}"}))
        self.assertIn("hide_selectors", self.refused({"hide_selectors": "#a\n#b"}))
        self.assertIn("can't be changed on the Settings page", self.refused({"port": 9999}))
        self.assertIn("can't be changed on the Settings page", self.refused({"layers": {"behavior": False}}), "the layers are not settings")
        self.assertIn("can't be changed on the Settings page", self.refused({"signals": {"page_methods": True}}))
        self.assertIn("must be", self.refused({"retention_days": 90, "auto_free": 1}), "one bad field: none saved")

    def test_an_empty_site_domain_or_selector_list_is_allowed(self):
        config.save_user(site_domain="shop.example", hide_selectors="#address")
        answer = self.client.post("/api/settings", {"site_domain": "", "hide_selectors": ""})
        self.assertEqual((answer.status, answer.body["site_domain"], answer.body["hide_selectors"]), (200, "", ""))

    def test_only_this_computers_pages_may_post_and_only_json(self):
        self.refused({"auto_free": False}, 403, headers={"Origin": "https://evil.example"})
        self.refused(b"auto_free=false", 415, content_type="application/x-www-form-urlencoded")


class Sources(SettingsCase):
    def test_each_source_says_whether_it_sends_and_when_it_last_did(self):
        body = self.settings()
        self.assertEqual(body["sources"], {"site": "not_connected", "server_half": "not_connected"})
        self.assertEqual(body["last_seen"], {"site": None, "server_half": None})
        self.assertEqual(body["route"], "this_computer")
        now = int(time.time() * 1000)
        config.save_user(site_domain="shop.example")
        self.visit("demo1", "demo", now)  # the demo shop of an earlier AgentCake: not a source any more
        self.visit("old1", "site", now - 30 * MS_PER_DAY)
        body = self.settings()
        self.assertEqual(body["sources"], {"site": "waiting", "server_half": "not_connected"})
        self.assertIsNotNone(body["last_seen"]["site"], "an old visit still says when it came")
        self.assertNotRegex(body["last_seen"]["site"], r"^Today ", "the demo shop's visit is not the site's")

    def test_a_first_visit_shows_connected_at_once(self):
        self.visit("site1", "site", int(time.time() * 1000))
        self.assertEqual(self.settings()["sources"]["site"], "receiving", "the very next answer")

    def test_in_server_mode_the_website_arrives_through_the_server(self):
        config.save_user(public_listen="127.0.0.1:9", path_prefix="/cake")
        body = self.settings()
        self.assertEqual(body["route"], "server")
        self.assertIn('src="/cake/cake.js"', body["script_tag"], "the path on the site's own domain")

    def test_with_public_url_the_line_loads_from_the_subdomain(self):
        config.save_user(public_listen="127.0.0.1:9", path_prefix="/cake", public_url="https://cake.example.com")
        body = self.settings()
        self.assertEqual(body["script_tag"],
                         '<script src="https://cake.example.com/cake/cake.js" data-site="ck_settings" defer></script>')

    def test_the_server_half_says_which_headers_never_arrived(self):
        now = int(time.time() * 1000)
        self.visit("s1", "site", now, {"sf": {"s": None, "m": None, "d": None, "u": None}, "ua": "Mozilla/5.0"})
        self.visit("s2", "site", now, {"sf": {"s": None, "m": None, "d": None, "u": None}, "ua": "Mozilla/5.0"})
        body = self.settings()
        self.assertEqual(body["sources"]["server_half"], "receiving")
        self.assertRegex(body["last_seen"]["server_half"], r"^Today ")
        self.assertEqual(body["server_half"]["missing"], ["Sec-Fetch-Site", "Sec-Fetch-Mode", "Sec-Fetch-Dest"])
        self.visit("s3", "site", now, {"sf": FETCH, "ua": "Mozilla/5.0"})
        self.assertEqual(self.settings()["server_half"]["missing"], [], "one page request had them: none removed")

    def test_the_last_log_import_says_when_and_what_its_log_lacks(self):
        self.assertIsNone(self.settings()["server_half"]["logs"])
        now = int(time.time() * 1000)
        con = store.db()
        try:
            store.set_setting(con, log_report.SETTING, {"run": "r1", "format": "nginx", "missing": ["sec-fetch-user"],
                                                       "empty": ["accept-language"], "first_ms": now, "last_ms": now,
                                                       "records": 12, "matched": 10}, now)
            con.commit()
        finally:
            con.close()
        body = self.settings()
        self.assertEqual({key: body["server_half"]["logs"][key] for key in ("format", "missing", "empty")},
                         {"format": "nginx", "missing": ["Sec-Fetch-User"], "empty": ["Accept-Language"]})
        self.assertRegex(body["server_half"]["logs"]["last"], r"^Today ")
        self.assertEqual(body["sources"]["server_half"], "receiving", "a log import is the server half too")


if __name__ == "__main__":
    unittest.main()
