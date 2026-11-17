"""The content-blocker check before a release (tools/blockers/): what it checks and how it decides, without the
internet. The check itself downloads the blockers' lists and runs them (tools/blockers/check.py, live.py).

    python3 -I -m unittest discover -s tests -v      (from the AgentCake folder)
"""
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from agentcake import config, routes  # noqa: E402
from agentcake.datafiles import load  # noqa: E402
from tools.blockers import check, targets  # noqa: E402

CONF = targets.settings()


def blocked(rule, lists=("EasyPrivacy",)):
    return {"blocked": True, "rule": rule, "exception": None,
            "lists": [{"list": name, "rule": rule, "exception": None} for name in lists]}


PASSES = {"blocked": False, "rule": None, "exception": None, "lists": []}


class Requests(unittest.TestCase):
    def setUp(self):
        self.reqs = targets.requests(CONF)
        self.urls = {r["url"] for r in self.reqs}

    def test_every_public_route_a_browser_asks_for_is_checked_on_the_site_and_on_this_computer(self):
        prefix = targets.documented_prefix()
        site = f"https://{CONF['site']['page_host']}{prefix}"
        local = config.base_url(config.DEFAULTS)
        for route in routes.PUBLIC:
            if route.path in CONF["not_from_browsers"]:
                continue
            self.assertIn(site + route.path, self.urls)
            self.assertIn(local + route.path, self.urls)

    def test_the_upload_is_checked_plain_and_gzipped(self):
        gzip = load("data/cakejs.json")["script"]["gzip_query"]
        uploads = {r["url"] for r in self.reqs if r["type"] == targets.UPLOAD}
        self.assertTrue(uploads)
        self.assertEqual({u for u in uploads if u.endswith(gzip)}, {u + gzip for u in uploads if "?" not in u})

    def test_server_only_routes_are_left_out(self):
        for path in CONF["not_from_browsers"]:
            self.assertFalse([u for u in self.urls if u.endswith(path)], path)

    def test_the_listed_names_are_routes_of_the_public_listener(self):
        public = {r.path for r in routes.PUBLIC}
        self.assertLessEqual(set(CONF["legacy"]) | set(CONF["not_from_browsers"]), public)

    def test_only_the_old_recorder_is_legacy(self):
        legacy = {r["url"].rsplit("/", 1)[1] for r in self.reqs if r["legacy"]}
        self.assertEqual(legacy, {p.lstrip("/") for p in CONF["legacy"]})

    def test_the_prefix_is_the_one_server_md_sets(self):
        folder = tempfile.mkdtemp(prefix="agentcake-blockers-")
        self.addCleanup(shutil.rmtree, folder, True)
        doc = os.path.join(folder, "SERVER.md")
        with open(doc, "w", encoding="utf-8") as f:
            f.write("```sh\nagentcake config set path_prefix /shop-ac/\n```\n")
        self.assertEqual(targets.documented_prefix(doc), "/shop-ac")

    def test_the_site_s_own_path_is_first_party_and_the_local_page_is_not(self):
        for r in self.reqs:
            self.assertEqual(targets.first_party(r["url"], r["page"]), r["label"].startswith("server"), r["label"])


class Lists(unittest.TestCase):
    def test_ubo_takes_its_filter_lists_that_are_not_off(self):
        catalog = {"easyprivacy": {"content": "filters", "title": "EasyPrivacy",
                                   "contentURL": ["https://lists.example/easyprivacy.txt", "assets/easyprivacy.txt"]},
                   "annoyances": {"content": "filters", "off": True, "contentURL": "https://lists.example/a.txt"},
                   "public_suffix_list.dat": {"content": "internal", "contentURL": "https://lists.example/psl"}}
        self.assertEqual(targets.lists_of("uBlock Origin", catalog, CONF),
                         [("EasyPrivacy", "https://lists.example/easyprivacy.txt", True)])

    def test_brave_takes_its_default_desktop_lists_and_knows_which_spare_first_party_requests(self):
        catalog = [{"title": "Privacy", "default_enabled": True, "first_party_protections": True,
                    "sources": [{"url": "https://lists.example/p1.txt"}, {"url": "https://lists.example/p2.txt"}]},
                   {"title": "First party", "default_enabled": True, "sources": [{"url": "https://lists.example/f.txt"}]},
                   {"title": "iOS", "default_enabled": True, "platforms": ["IOS"],
                    "sources": [{"url": "https://lists.example/ios.txt"}]},
                   {"title": "Optional", "sources": [{"url": "https://lists.example/o.txt"}]}]
        self.assertEqual(targets.lists_of("Brave", catalog, CONF),
                         [("Privacy (1)", "https://lists.example/p1.txt", False),
                          ("Privacy (2)", "https://lists.example/p2.txt", False),
                          ("First party (1)", "https://lists.example/f.txt", True)])

    def test_adguard_is_its_fixed_lists(self):
        self.assertEqual([url for _, url, _ in targets.lists_of("AdGuard", None, CONF)],
                         list(CONF["blockers"]["AdGuard"]["lists"].values()))

    def test_a_hosts_file_is_told_from_filter_syntax(self):
        self.assertTrue(targets.hosts_format("# hosts\n127.0.0.1 ads.example\n0.0.0.0 track.example\n"))
        self.assertFalse(targets.hosts_format("! EasyPrivacy\n/rrweb.min.js\n||track.example^\n"))

    def test_a_rule_s_line_is_found_as_the_list_writes_it(self):
        self.assertEqual(targets.line_of("/rrweb.min.js", "! title\n/rrweb.js\n/rrweb.min.js\n"), [3])


class Judge(unittest.TestCase):
    def setUp(self):
        folder = tempfile.mkdtemp(prefix="agentcake-blockers-")
        self.addCleanup(shutil.rmtree, folder, True)
        path = os.path.join(folder, "easyprivacy.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("! EasyPrivacy\n/beacon.js\n/rrweb-record.min.js\n/api/collect|\n")
        self.lists = [{"blocker": "uBlock Origin", "name": "EasyPrivacy", "path": path}]

    def request(self, path, legacy=False):
        return {"label": path, "url": "https://example.com/cake" + path, "legacy": legacy}

    def test_a_blocked_current_request_fails_and_says_where_the_rule_is(self):
        reqs = [self.request("/collect")]
        rows, failing = check.judge(reqs, [{"uBlock Origin": blocked("/api/collect|")}], self.lists)
        self.assertEqual(len(failing), 1)
        self.assertEqual(rows[0]["verdicts"]["uBlock Origin"]["written_at"], ["EasyPrivacy line 4"])

    def test_the_old_recorder_being_blocked_is_expected(self):
        reqs = [self.request("/rrweb-record.min.js", legacy=True), self.request("/cake.js")]
        rows, failing = check.judge(reqs, [{"uBlock Origin": blocked("/rrweb-record.min.js")},
                                           {"uBlock Origin": PASSES}], self.lists)
        self.assertEqual(failing, [])
        self.assertEqual(rows[0]["verdicts"]["uBlock Origin"]["written_at"], ["EasyPrivacy line 3"])

    def test_nothing_blocked_passes(self):
        rows, failing = check.judge([self.request("/cake.js")], [{"uBlock Origin": PASSES}], self.lists)
        self.assertEqual(failing, [])
        self.assertFalse(rows[0]["verdicts"]["uBlock Origin"]["blocked"])


class Settings(unittest.TestCase):
    def test_the_matcher_is_pinned_by_hash(self):
        pin = CONF["matcher"]
        self.assertRegex(pin["version"], r"^\d+\.\d+\.\d+$")
        self.assertTrue(pin["sha256"])
        for digest in pin["sha256"]:
            self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_every_list_and_catalog_is_fetched_over_https(self):
        for spec in CONF["blockers"].values():
            for url in [spec.get("catalog")] + list(spec.get("lists", {}).values()):
                if url:
                    self.assertTrue(url.startswith("https://"), url)


if __name__ == "__main__":
    unittest.main()
