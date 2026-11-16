"""Signals for the environment rules: agentcake/detect/env_signals.py turns recordings into one dict.

    python3 -I -m unittest discover -s tests -v      (from the Agent Cake folder)

cake.js's upload format version 1 (docs/collect-format.md): batches built from the document's tables become the same
signals as the lab's reports, and the rules read them. The research lab's format: small hand-written reports pin down
each step (pairing env.js's and raw.js's reports into page views, merging reports, botscent's markers, the
hidden-input counts, the request headers, the viewport changes).
"""
import copy, os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from agentcake.detect import env_signals  # noqa: E402
from agentcake.detect.env_rules import evaluate, load_rules  # noqa: E402

FIXTURES = os.path.join(ROOT, "tests", "fixtures", "env_rules")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 "
      "Safari/537.36")


def env_report(kind, page, env=None, auto=None, botd=None):
    return {"kind": kind, "page": page, "snap": {"env": env or {}, "auto": auto or {}, "botd": botd}}


def raw_report(kind, page, items=()):
    return {"kind": kind, "page": page, "items": list(items)}


def dom_div(display):
    return {"t": 1, "ty": "dom_add", "how": "added", "tag": "DIV", "nattr": 0, "attrs": [], "open_shadow": 0,
            "disp": display, "parent": "body"}


class PageViewTest(unittest.TestCase):
    def test_reports_pair_into_page_views_in_load_order_even_when_a_path_repeats(self):
        payloads = [
            raw_report("meta", "/"),  # raw.js often reports before env.js
            env_report("load", "/", env={"webdriver": False}),
            raw_report("raw", "/", [dom_div("contents")]),
            env_report("load", "/pricing"),
            raw_report("meta", "/pricing"),
            env_report("load", "/", env={"webdriver": True}),
            raw_report("meta", "/"),
            raw_report("raw", "/", [dom_div("block")]),
        ]
        pages = env_signals.from_lab(payloads)["pages"]
        self.assertEqual([page["path"] for page in pages], ["/", "/pricing", "/"])
        self.assertEqual((pages[0]["env"]["webdriver"], pages[0]["dom_add"][0]["disp"]), (False, "contents"))
        self.assertEqual((pages[2]["env"]["webdriver"], pages[2]["dom_add"][0]["disp"]), (True, "block"))

    def test_env_reports_merge_into_the_most_complete_values(self):
        payloads = [
            env_report("load", "/", env={"webdriver": True}, auto={
                "runtimeEnableLeak": {"rounds": 2, "prepareStackTraceCount": 2},
                "globalsAtLoad": {"playwright_globals": [], "selenium_cdc": []}}),
            env_report("probes", "/", auto={"permissions": {"mismatch": True}}, botd={"result": {"bot": True}}),
            env_report("summary", "/", auto={
                "runtimeEnableLeak": {"rounds": 40, "prepareStackTraceCount": 40},
                "globalsAtEnd": {"playwright_globals": ["__pwInitScripts"], "botdprop_selenium": ["_selenium"]},
                "hookHits": [{"fn": "querySelector", "arg": "#buy", "pptr": False, "utilityScript": True,
                              "puppeteerEval": False, "stack": "at eval (eval at evaluate)"}]}),
        ]
        page = env_signals.from_lab(payloads)["pages"][0]
        auto = page["auto"]
        self.assertEqual(auto["runtimeEnableLeak"]["rounds"], 40)
        self.assertEqual(auto["globals"]["playwright_globals"], ["__pwInitScripts"])
        self.assertEqual(auto["globals"]["selenium_cdc"], [])
        self.assertEqual(auto["globals"]["botd_props"], ["selenium"])
        self.assertTrue(auto["permissions"]["mismatch"])
        self.assertEqual(auto["hookHits"], [{"fn": "querySelector", "pptr": False, "utilityScript": True,
                                             "puppeteerEval": False}])
        self.assertEqual(page["botd"], {"result": {"bot": True}})
        self.assertEqual(page["env"], {"webdriver": True})

    def test_botscent_markers_add_up_per_page(self):
        marker = {"t": 1, "ty": "lab_botscent", "ver": "1.2.0"}
        payloads = [raw_report("meta", "/"), raw_report("raw", "/", [
            dict(marker, why="t3s", type="human", agent=None, reasons=[]),
            dict(marker, why="pagehide", type="agent", agent=None, reasons=["browser.webdriver-flag"])])]
        botscent = env_signals.from_lab(payloads)["pages"][0]["botscent"]
        self.assertEqual(botscent, {"reasons": ["browser.webdriver-flag"], "type": "agent", "agent_name": None,
                                    "version": "1.2.0"})

    def test_hidden_input_counts_only_trusted_input_while_hidden(self):
        events = [
            {"ty": "pointerdown", "tr": 1, "vs": 0, "hf": 0},
            {"ty": "keydown", "tr": 1, "vs": 0, "hf": 1},
            {"ty": "pointerdown", "tr": 0, "vs": 0, "hf": 0},  # synthetic: not trusted
            {"ty": "click", "tr": 1, "vs": 0, "hf": 0},  # not one of botscent's input types
            {"ty": "pointerdown", "tr": 1, "vs": 1, "hf": 1},  # visible
        ]
        page = env_signals.from_lab([raw_report("meta", "/"), raw_report("raw", "/", events)])["pages"][0]
        self.assertEqual(page["hidden_input"], {"trusted_hidden": 2, "trusted_pointerdown": 1, "trusted_focused": 1})

    def test_what_a_page_did_not_record_stays_out(self):
        only_env = env_signals.from_lab([env_report("load", "/")])["pages"][0]
        self.assertEqual(set(only_env), {"path", "env", "auto"})
        no_dom_watch = env_signals.from_lab([raw_report("meta", "/"), raw_report("raw", "/", [])])["pages"][0]
        self.assertNotIn("dom_add", no_dom_watch)
        self.assertEqual(no_dom_watch["hidden_input"]["trusted_hidden"], 0)


class RequestTest(unittest.TestCase):
    def test_a_page_request_keeps_only_the_rule_headers_and_marks_absent_ones_null(self):
        get = {"method": "GET", "path": "/", "headers": [["Host", "127.0.0.1:8098"], ["Cookie", "labid=abc"],
                                                         ["User-Agent", UA], ["Sec-Fetch-Site", "cross-site"],
                                                         ["Sec-Fetch-Mode", "navigate"]]}
        headers = env_signals.from_lab([env_report("load", "/")], [get])["pages"][0]["nav"]["headers"]
        self.assertEqual(set(headers), set(load_rules().signals["network_headers"]))
        self.assertEqual((headers["user-agent"], headers["sec-fetch-site"]), (UA, "cross-site"))
        self.assertIsNone(headers["sec-fetch-user"])
        self.assertNotIn("cookie", headers)

    def test_page_requests_match_page_views_by_path_and_order(self):
        gets = [{"method": "GET", "path": "/", "headers": [["Sec-Fetch-Site", "none"]]},
                {"method": "GET", "path": "/static/env.js", "headers": []},
                {"method": "GET", "path": "/", "headers": [["Sec-Fetch-Site", "same-origin"]]}]
        pages = env_signals.from_lab([env_report("load", "/"), env_report("load", "/")], gets)["pages"]
        self.assertEqual([p["nav"]["headers"]["sec-fetch-site"] for p in pages], ["none", "same-origin"])

    def test_collect_requests_are_counted_per_header(self):
        def post(*headers):
            return {"method": "POST", "path": "/collect", "headers": [["User-Agent", UA], *headers]}
        requests = [post(["Accept-Language", "en-US"]), post(["Accept-Language", "en-US"]), post()]
        collect = env_signals.from_lab([env_report("load", "/")], requests)["collect"]
        self.assertEqual(collect["requests"], 3)
        self.assertEqual(collect["headers"]["accept-language"], {"present": 2, "values": ["en-US"]})
        self.assertEqual(collect["headers"]["user-agent"], {"present": 3, "values": [UA]})
        self.assertEqual(collect["headers"]["sec-fetch-user"], {"present": 0, "values": []})
        self.assertNotIn("collect", env_signals.from_lab([env_report("load", "/")], []))


class ViewportTest(unittest.TestCase):
    def test_changes_follow_load_sizes_resizes_and_window_samples(self):
        window = {"iw": 1920, "ih": 958, "ow": 1920, "oh": 958}
        resize = {"type": 3, "timestamp": 50, "data": {"source": 4, "width": 1920, "height": 902}}
        payloads = [
            env_report("load", "/", env={"window": window}), raw_report("meta", "/"),
            raw_report("rrweb", "/", [{"type": 4, "timestamp": 10, "data": {"width": 1920, "height": 958}}, resize]),
            env_report("load", "/docs", env={"window": dict(window, ih=902)}), raw_report("meta", "/docs"),
            raw_report("raw", "/docs", [{"t": 90, "ty": "geo", "why": "resize", "g": [1600, 800, 1600, 880, 0, 0, 2]}]),
        ]
        changes = env_signals.from_lab(payloads)["viewport_changes"]
        self.assertEqual(changes, [{"page": 0, "dw": 0, "dh": -56, "w": 1920, "h": 902},
                                   {"page": 1, "dw": -320, "dh": -102, "doh": -78, "w": 1600, "h": 800}])

    def test_no_sizes_means_no_viewport_changes_key(self):
        self.assertNotIn("viewport_changes", env_signals.from_lab([env_report("load", "/")]))


VISIT = "5b0e6c2f0d8a4a61b7f4c0b1e2d3a4f5"
HEADLESS = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
            "HeadlessChrome/149.0.7827.55 Safari/537.36")


def batch(pv, seq, t, x=(), r=(), e=(), url="https://shop.example.com/demo"):
    return {"v": 1, "k": "site", "s": VISIT, "pv": pv, "seq": seq, "t": t, "u": url, "ua": HEADLESS, "wd": True,
            "why": "timer", "e": list(e), "r": list(r), "x": list(x)}


def automated_visit():
    """Two page views of headless Playwright, as cake.js reports them: every record type of the format's table."""
    env = {"webdriver": True, "webdriver_getter_native": True, "webdriver_on_proto": True, "webdriver_own_prop": False,
           "userAgent": HEADLESS, "platform": "MacIntel", "plugins": 0, "windowChrome": "undefined",
           "uaData": {"brands": [{"brand": "HeadlessChrome", "version": "149"}], "platform": "macOS", "mobile": False},
           "window": {"iw": 1280, "ih": 720, "ow": 1280, "oh": 720}, "hasFocus": True,
           "visibilityState": "visible"}
    leak = {"rounds": 1, "prepareStackTraceCount": 1, "nameGetterCount": 2, "stackLookupCount": 0, "firstHitRound": 1}
    detections = {"detectWebDriver": {"bot": True, "botKind": "headless_chrome"}}
    first = [
        batch("pv-a", 0, 1000.5, x=[{"t": 1000.1, "ty": "page", "n": 1, "hook_dom": False}],
              e=[{"type": 4, "data": {"href": "https://shop.example.com/demo", "width": 1280, "height": 720},
                  "timestamp": 1000}],
              r=[{"t": 1000.2, "ty": "geo", "hf": 1, "vs": 1, "why": "load", "g": [1280, 720, 1280, 720, 0, 0, 1]}]),
        batch("pv-a", 1, 1500.5, x=[
            {"t": 1400, "ty": "env", "env": env},
            {"t": 1401, "ty": "auto", "globalsAtLoad": {"playwright_globals": [], "selenium_cdc": []},
             "errorStack": "TypeError: x", "docInterception": {"nextHopProtocol": "h2", "intercepted": False}},
            {"t": 1450, "ty": "cdp", "runtimeEnableLeak": leak},
            {"t": 1460, "ty": "frames", "iframeSharesRealm": False,
             "ipcFlooding": {"applied": 300, "error": None, "all300": True}},
            {"t": 1470, "ty": "probes",
             "permissions": {"notificationPermission": "denied", "permissionsQuery": "prompt", "mismatch": True},
             "workerConsistency": {"differs": []}, "nativeTampering": {"tampered": {}}},
            {"t": 1480, "ty": "botd", "result": {"bot": True, "botKind": "headless_chrome"}, "detections": detections},
            {"t": 1490, "ty": "botscent", "why": "start", "type": "agent", "agent": None,
             "reasons": ["browser.webdriver-flag"], "ver": "1.2.0"}],
            r=[{"t": 1420, "ty": "pointerdown", "tr": 1, "vs": 1, "hf": 1},
               {"t": 1430, "ty": "dom_add", "how": "scan", "tag": "P", "nattr": 0, "attrs": [], "open_shadow": 0,
                "disp": "block", "parent": "body"}]),
        batch("pv-a", 2, 1900.5, x=[{"t": 1900, "ty": "globals", "globalsAtEnd": {"playwright_globals": []}}]),
    ]
    second = [batch("pv-b", 0, 2000.5, url="https://shop.example.com/demo?page=2", x=[
        {"t": 2000, "ty": "page", "n": 2, "hook_dom": False},
        {"t": 2100, "ty": "env", "env": dict(env, window={"iw": 1280, "ih": 720, "ow": 1280, "oh": 720})},
        {"t": 2150, "ty": "cdp", "runtimeEnableLeak": leak},
        {"t": 2160, "ty": "botscent", "why": "start", "type": "agent", "agent": None,
         "reasons": ["browser.webdriver-flag"], "ver": "1.2.0"}], r=[{"t": 2120, "ty": "keydown", "tr": 1, "vs": 1}])]
    return second + first + [copy.deepcopy(first[1])]  # out of order, and one batch sent twice


class CakeFormatTest(unittest.TestCase):
    def test_the_documents_example_batch(self):
        example = {"v": 1, "k": "9f3c", "s": VISIT, "pv": "c2a8", "seq": 0, "t": 1794518371369.5,
                   "u": "https://shop.example.com/demo", "why": "snapshot", "st": "c1.e30.x", "ua": UA, "wd": False,
                   "e": [{"type": 4, "data": {"href": "https://shop.example.com/demo", "width": 1280, "height": 900},
                          "timestamp": 1794518371301},
                         {"type": 2, "data": {"node": {}, "initialOffset": {"left": 0, "top": 0}},
                          "timestamp": 1794518371304}],
                   "r": [{"t": 1794518371302.4, "ty": "geo", "hf": 1, "vs": 1, "why": "load",
                          "g": [1280, 900, 1280, 987, 0, 25, 2, 1512, 982]}],
                   "x": [{"t": 1794518371300.1, "ty": "page", "n": 1, "build": "3f9a", "ref": "", "nav": "navigate",
                          "t0": 1794518371012.3, "ran": 288.1, "prerendering": False, "vis": "visible", "hf": True,
                          "hist": 1, "hook_dom": False}]}
        signals = env_signals.from_cake([example])
        no_input = {"trusted_hidden": 0, "trusted_pointerdown": 0, "trusted_focused": 0}
        # cake.js always watches the DOM: raw records and no dom_add record mean nothing was added (known)
        self.assertEqual(signals["pages"], [{"path": "/demo", "dom_add": [], "hidden_input": no_input}])
        self.assertEqual(signals["viewport_changes"], [])
        self.assertNotIn("collect", signals)
        result = evaluate(signals)
        self.assertNotIn("env.ext.closed-shadow-host", result.unknown)
        self.assertNotIn("env.ext.closed-shadow-host", [hit.rule for hit in result.hits])

    def test_records_join_into_the_labs_layout_per_page_view(self):
        opened = {"pv-a": {"headers": {"Sec-Fetch-Site": "none"}}}
        signals = env_signals.from_cake(automated_visit(), page_requests=opened)
        first, second = signals["pages"]
        self.assertEqual((first["path"], second["path"]), ("/demo", "/demo"))
        self.assertEqual(first["auto"]["ipcFlooding"]["all300"], True)
        self.assertEqual(second["auto"]["ipcFlooding"]["all300"], True)  # frames: once per visit, for all of it
        self.assertEqual(first["auto"]["nativeTampering"], {"tampered": {}, "iframeSharesRealm": False})
        self.assertEqual(first["auto"]["runtimeEnableLeak"]["nameGetterCount"], 2)
        self.assertEqual(first["auto"]["globals"]["botd_props"], [])
        self.assertNotIn("hookHits", first["auto"])  # hook_dom off: unknown, not "no hits"
        self.assertEqual(first["botd"]["result"], {"bot": True, "botKind": "headless_chrome"})
        self.assertEqual(set(first["botd"]), {"result", "detections"})
        self.assertEqual(first["botscent"]["reasons"], ["browser.webdriver-flag"])
        self.assertEqual(first["hidden_input"]["trusted_hidden"], 0)
        self.assertEqual(len(first["dom_add"]), 1)  # the batch sent twice counts once
        self.assertEqual(first["nav"]["headers"]["sec-fetch-site"], "none")
        self.assertNotIn("nav", second)

    def test_the_rules_read_cake_js_data_unchanged(self):
        requests = [{"headers": {"User-Agent": HEADLESS}, "ip_class": "cloud"}] * 3
        hits = {hit.rule for hit in evaluate(env_signals.from_cake(automated_visit(), requests)).hits}
        for rule in ("env.auto.webdriver", "env.auto.headless-ua", "env.auto.headless-ua-collector",
                     "env.auto.collect-no-accept-language", "env.auto.cdp-runtime-leak", "env.auto.ipc-flooding-off",
                     "env.auto.notification-permission-mismatch", "env.auto.chrome-object-missing",
                     "env.auto.default-viewport", "env.cloud.datacenter-ip"):
            self.assertIn(rule, hits)

    def test_upload_requests_count_headers_and_network_classes(self):
        requests = [{"headers": [["Accept-Language", "en"], ["User-Agent", UA]], "ip_class": "residential"},
                    {"headers": {"accept-language": "en", "user-agent": UA}, "ip_class": "cdn"}]
        collect = env_signals.from_cake(automated_visit(), requests)["collect"]
        self.assertEqual((collect["requests"], collect["headers"]["accept-language"]["present"]), (2, 2))
        self.assertEqual(collect["ip_classes"], ["cdn", "residential"])
        self.assertNotIn("ip_classes", env_signals.from_cake(automated_visit(), [{"headers": {}}])["collect"])

    def test_a_page_view_that_sent_only_its_page_record_stays_unknown(self):
        page_only = batch("pv-z", 0, 10.5, x=[{"t": 10, "ty": "page", "n": 1}])
        self.assertEqual(env_signals.from_cake([page_only])["pages"], [{"path": "/demo"}])

    def test_dom_lookups_are_kept_when_the_site_turned_the_watch_on(self):
        hooked = batch("pv-h", 0, 10.5, x=[{"t": 10, "ty": "auto", "globalsAtLoad": {}},
                                          {"t": 20, "ty": "globals", "globalsAtEnd": {}, "lookups": {"total": 4},
                                           "hookHits": [{"fn": "querySelector", "arg": "#buy", "t": 15, "pptr": False,
                                                         "utilityScript": True, "puppeteerEval": False,
                                                         "stack": "UtilityScript.evaluate"}]}])
        auto = env_signals.from_cake([hooked])["pages"][0]["auto"]
        self.assertEqual(auto["hookHits"], [{"fn": "querySelector", "pptr": False, "utilityScript": True,
                                             "puppeteerEval": False}])

    def test_the_page_records_say_how_the_site_owner_had_set_the_page_script(self):
        def page_view(pv, n, **page):
            return batch(pv, 0, 10.5 + n, x=[{"t": 10 + n, "ty": "page", "n": n, **page}])

        off, on = page_view("pv-1", 1, hook_dom=False), page_view("pv-2", 2, hook_dom=True)
        self.assertEqual(env_signals.from_cake([off, on])["script_settings"], {"hook_dom": True})  # on for one view
        self.assertEqual(env_signals.from_cake([off])["script_settings"], {"hook_dom": False})
        self.assertNotIn("script_settings", env_signals.from_cake([page_view("pv-3", 1)]))  # not said: unknown
        lab = env_report("load", "/", auto={"hookHits": []})  # the lab's own script always watched, unasked
        self.assertNotIn("script_settings", env_signals.from_lab([lab]))


if __name__ == "__main__":
    unittest.main()
