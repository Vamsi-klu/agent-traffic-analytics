"""The environment layer: the rule table agentcake/data/env_rules.json and its evaluator,
agentcake/detect/env_rules.py.

    python3 -I -m unittest discover -s tests -v      (from the AgentCake folder)

Every rule has hit and miss cases (tests/fixtures/env_rules/cases.json). The checks on the lab's recorded sessions
(case T6's environment part) are kept with those recordings, outside the published repository.
"""
import copy, itertools, json, os, re, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from agentcake.detect import env_rules  # noqa: E402
from agentcake.detect.env_rules import EnvRulesError, evaluate, load_rules, parse_rules  # noqa: E402
sys.path.insert(0, os.path.join(ROOT, "tests"))
from verdict_cases import botscent_reasons, hit_fields  # noqa: E402

FIXTURES = os.path.join(ROOT, "tests", "fixtures", "env_rules")
DELETE = "$delete"  # in a case: remove this key, i.e. the input was not recorded
DEFAULT_OFF = {"env.auto.main-world-eval-stack", "env.ext.extension-probe"}  # the brief: these two are off by default
LAB_TRUTHS = {"pw-direct-headless", "pw-humanlike-headless", "pw-direct-headed", "pw-humanlike-headed",
              "claude-chrome", "claude-chrome-bg"}  # the 26 answered sessions of the 2026-11-11 lab


def merge(base, override):
    out = copy.deepcopy(base)
    for key, value in override.items():
        if value == DELETE:
            out.pop(key, None)
        elif isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load_cases():
    with open(os.path.join(FIXTURES, "cases.json"), encoding="utf-8") as handle:
        return json.load(handle)


def raw_table():
    with open(env_rules.RULES_FILE, encoding="utf-8") as handle:
        return json.load(handle)


class TableTest(unittest.TestCase):
    def setUp(self):
        self.table = load_rules()

    def test_every_rule_carries_what_the_brief_asks_for(self):
        for rule in self.table.rules:
            with self.subTest(rule=rule.id):
                self.assertTrue(rule.id.startswith("env."))
                self.assertEqual(rule.layer, "env")
                self.assertIn(rule.half, self.table.legend["halves"])
                self.assertTrue(rule.sources and rule.collisions and rule.evidence and rule.title)
                self.assertRegex(rule.date, r"^\d{4}-\d{2}-\d{2}$")
                self.assertIsInstance(rule.enabled, bool)

    def test_hooking_the_site_and_probing_extensions_are_off_by_default(self):
        self.assertEqual({rule.id for rule in self.table.rules if not rule.enabled}, DEFAULT_OFF)

    def test_every_botscent_page_reason_is_covered_by_a_rule(self):
        covered = {reason for rule in self.table.rules for reason in rule.botscent}
        self.assertEqual(covered, set(self.table.botscent["page_reasons"]))

    def test_every_header_a_rule_reads_is_kept_by_the_adapter(self):
        text = json.dumps([rule.match for rule in self.table.rules] + [list(rule.report) for rule in self.table.rules])
        read = set(re.findall(r"(?:nav\.headers|collect\.headers)\.([a-z-]+)", text))
        self.assertTrue(read)
        self.assertLessEqual(read, set(self.table.signals["network_headers"]))

    def test_every_rule_has_a_hit_case_and_a_miss_case(self):
        cases = load_cases()["cases"]
        ids = {rule.id for rule in self.table.rules}
        self.assertEqual(set(cases), ids)
        for rule_id, case in cases.items():
            with self.subTest(rule=rule_id):
                self.assertTrue(case.get("hit") and case.get("miss"))

    def test_a_malformed_table_is_rejected_when_loaded(self):
        good = raw_table()
        first = good["rules"][0]
        broken = {
            "two operators": {"path": "env.webdriver", "eq": True, "ne": False},
            "unknown operator": {"path": "env.webdriver", "equals": True},
            "bad regex": {"path": "env.userAgent", "regex": "("},
            "some without where": {"some": "dom_add"},
        }
        for name, match in broken.items():
            with self.subTest(name), self.assertRaises(EnvRulesError):
                parse_rules(merge(good, {"rules": [dict(first, match=match)]}))
        for name, change in {"unknown kind": {"kind": "magic"}, "unknown field": {"weight": 3},
                             "stray botscent reason": {"botscent": ["no.such.reason"]},
                             "enabled not a bool": {"enabled": "yes"}}.items():
            with self.subTest(name), self.assertRaises(EnvRulesError):
                parse_rules(merge(good, {"rules": [dict(first, **change)]}))
        for name, change in {"a setting cake.js does not record": {"enabled": False, "setting": "no_such_setting"},
                             "a setting on a rule that is on anyway": {"enabled": True, "setting": "hook_dom"}}.items():
            with self.subTest(name), self.assertRaisesRegex(EnvRulesError, "setting is for a rule that is off"):
                parse_rules(merge(good, {"rules": [dict(first, **change)]}))
        with self.assertRaises(EnvRulesError):
            parse_rules(merge(good, {"rules": [first, first]}))


class RuleCaseTest(unittest.TestCase):
    """Each rule on its own cases, with every rule switched on so the default-off ones are tested too."""

    def setUp(self):
        self.table = load_rules()
        self.cases = load_cases()
        self.all_on = {rule.id: True for rule in self.table.rules}

    def signals(self, rule, override):
        if rule.scope == "session":
            return merge(self.cases["session"], override)
        return {"pages": [merge(self.cases["page"], override)]}

    def test_an_ordinary_human_page_and_session_trigger_no_rule(self):
        signals = merge(self.cases["session"], {"pages": [self.cases["page"]]})
        result = evaluate(signals, self.table, self.all_on)
        self.assertEqual([hit.rule for hit in result.hits], [])
        self.assertEqual(list(result.unknown), [])

    def test_each_hit_case_hits_its_rule(self):
        for rule in self.table.rules:
            for index, override in enumerate(self.cases["cases"][rule.id]["hit"]):
                with self.subTest(rule=rule.id, case=index):
                    result = evaluate(self.signals(rule, override), self.table, self.all_on)
                    self.assertIn(rule.id, [hit.rule for hit in result.hits])

    def test_each_miss_case_is_checked_and_misses(self):
        for rule in self.table.rules:
            for index, override in enumerate(self.cases["cases"][rule.id]["miss"]):
                with self.subTest(rule=rule.id, case=index):
                    result = evaluate(self.signals(rule, override), self.table, self.all_on)
                    self.assertNotIn(rule.id, [hit.rule for hit in result.hits])
                    self.assertNotIn(rule.id, result.unknown)


class EvaluateTest(unittest.TestCase):
    def setUp(self):
        self.table = load_rules()
        self.page = load_cases()["page"]

    def test_default_off_rules_are_skipped_unless_the_config_turns_them_on(self):
        page = merge(self.page, {"auto": {"hookHits": [{"fn": "querySelector", "utilityScript": True}]}})
        off = evaluate({"pages": [page]}, self.table)
        self.assertNotIn("env.auto.main-world-eval-stack", [hit.rule for hit in off.hits])
        self.assertEqual(set(off.off), DEFAULT_OFF)
        on = evaluate({"pages": [page]}, self.table, {"env.auto.main-world-eval-stack": True})
        self.assertIn("env.auto.main-world-eval-stack", [hit.rule for hit in on.hits])
        silenced = evaluate({"pages": [merge(self.page, {"env": {"webdriver": True}})]}, self.table,
                            {"env.auto.webdriver": False})
        self.assertNotIn("env.auto.webdriver", [hit.rule for hit in silenced.hits])
        self.assertIn("env.auto.webdriver", silenced.off)

    def test_the_dom_watch_rule_runs_on_visits_recorded_with_hook_dom_on(self):
        rule = "env.auto.main-world-eval-stack"
        self.assertEqual(self.table.rule(rule).setting, "hook_dom")
        page = merge(self.page, {"auto": {"hookHits": [{"fn": "querySelector", "pptr": True}]}})
        recorded_on = {"pages": [page], "script_settings": {"hook_dom": True}}
        result = evaluate(recorded_on, self.table)
        self.assertIn(rule, [hit.rule for hit in result.hits])
        self.assertIn("env.ext.extension-probe", result.off)  # waits for no setting: stays off
        self.assertIn(rule, evaluate({"pages": [page], "script_settings": {"hook_dom": False}}, self.table).off)
        self.assertIn(rule, evaluate(recorded_on, self.table, {rule: False}).off)  # the config's switch wins

    def test_a_page_rule_lists_every_page_it_held_on(self):
        flagged = merge(self.page, {"env": {"webdriver": True}})
        pages = [self.page, flagged, flagged]
        hit = next(h for h in evaluate({"pages": pages}, self.table).hits if h.rule == "env.auto.webdriver")
        self.assertEqual(hit.pages, (1, 2))
        self.assertIs(hit.value, True)
        self.assertEqual((hit.layer, hit.kind, hit.half, hit.strength, hit.grade),
                         ("env", "automation", "page", "hard", "measured"))

    def test_a_landing_rule_reads_only_the_first_page(self):
        cross = merge(self.page, {"nav": {"headers": {"sec-fetch-site": "cross-site", "sec-fetch-user": None}}})
        first = evaluate({"pages": [cross, self.page]}, self.table)
        later = evaluate({"pages": [self.page, cross]}, self.table)
        self.assertIn("env.ext.cross-site-landing", [hit.rule for hit in first.hits])
        self.assertNotIn("env.ext.cross-site-landing", [hit.rule for hit in later.hits])

    def test_a_rule_is_unknown_only_when_no_page_recorded_its_inputs(self):
        bare = {"path": "/"}
        self.assertIn("env.ext.closed-shadow-host", evaluate({"pages": [bare, bare]}, self.table).unknown)
        self.assertNotIn("env.ext.closed-shadow-host", evaluate({"pages": [bare, self.page]}, self.table).unknown)
        self.assertIn("env.auto.collect-no-accept-language", evaluate({"pages": [self.page]}, self.table).unknown)

    def test_no_accept_language_is_a_hard_trace_only_on_requests_that_arrived_as_the_browser_sent_them(self):
        """chrome-headless-shell sends no Accept-Language, keeps its User-Agent and sends Sec-Fetch-Mode: the hard
        rule. A front door that drops the header for every visitor (CloudFront's defaults replace the User-Agent; its
        UserAgentRefererHeaders policy keeps it but drops the Sec-Fetch headers) only adds a reason."""
        hard, weak = "env.auto.collect-no-accept-language", "env.auto.collect-no-accept-language-proxy"
        session = load_cases()["session"]
        no_language = {"collect": {"headers": {"accept-language": {"present": 0, "values": []}}}}
        no_fetch_metadata = {"collect": {"headers": {"sec-fetch-mode": {"present": 0, "values": []}}}}
        cases = {"as sent": ({}, {hard}),
                 "user agent replaced": ({"collect": {"ua_as_page": False}}, {weak}),
                 "fetch metadata dropped": (no_fetch_metadata, {weak}),
                 "page user agent unknown": ({"collect": {"ua_as_page": DELETE}}, set())}
        for name, (change, expected) in cases.items():
            with self.subTest(name):
                signals = merge(merge(session, no_language), change)
                found = {hit.rule for hit in evaluate(signals, self.table).hits} & {hard, weak}
                self.assertEqual(found, expected)
        weak_hit = next(h for h in evaluate(merge(merge(session, no_language), cases["user agent replaced"][0]),
                                            self.table).hits if h.rule == weak)
        self.assertEqual((weak_hit.strength, weak_hit.half), ("weak", "collector"))

    def test_hits_serialise_to_json_with_their_reason_fields(self):
        host = {"tag": "DIV", "nattr": 0, "attrs": [], "open_shadow": 0, "disp": "contents", "parent": "body",
                "how": "added"}
        page = merge(self.page, {"env": {"window": {"iw": 1280, "ih": 720}}, "dom_add": [host]})
        hits = [hit_fields(found) for found in evaluate({"pages": [page]}, self.table).hits]
        json.dumps(hits)
        viewport = next(h for h in hits if h["rule"] == "env.auto.default-viewport")
        self.assertEqual(viewport["value"], {"env.window.iw": 1280, "env.window.ih": 720})
        host = next(h for h in hits if h["rule"] == "env.ext.closed-shadow-host")
        self.assertEqual((host["suggests"], host["pages"]), ("claude-chrome", [0]))
        self.assertEqual(host["value"][0]["disp"], "contents")

    def test_the_viewport_rule_is_not_read_on_a_phone_or_tablet_and_holds_on_a_computer_as_before(self):
        """A phone browser's address bar hides and shows as the page scrolls, which changes the viewport as Chrome's
        debugging bar does on a computer. The browser's own word decides (touch_device.claimed, what stops the
        behaviour model too); a computer's hit keeps its value."""
        rule, change = "env.ext.viewport-shrink", {"page": 0, "dw": 0, "dh": -56, "doh": 0, "w": 412, "h": 803}

        def held(*envs):
            signals = {"pages": [merge(self.page, {"env": env}) for env in envs], "viewport_changes": [change]}
            result = evaluate(signals, self.table)
            self.assertNotIn(rule, result.unknown)
            return [hit.value for hit in result.hits if hit.rule == rule]
        phones = ({"uaData": {"mobile": True}}, {"uaData": None, "anyPointer": ["coarse"]})
        computers = ({}, {"anyPointer": ["fine"]}, {"anyPointer": ["fine", "coarse"], "maxTouchPoints": 10})
        for env in phones:
            with self.subTest(env=env):
                self.assertEqual(held(env), [])
                self.assertEqual(held({}, env), [], "a phone on any page of the session")
        for env in computers:
            with self.subTest(env=env):
                self.assertEqual(held(env), [[change]])
        self.assertEqual([hit.value for hit in evaluate({"viewport_changes": [change]}, self.table).hits
                          if hit.rule == rule], [[change]], "signals without pages: read as before")

    def test_the_signals_a_caller_gives_are_left_as_they_are(self):
        signals = {"pages": [merge(self.page, {"env": {"uaData": {"mobile": True}}})]}
        before = json.dumps(signals, sort_keys=True)
        evaluate(signals, self.table)
        self.assertEqual(json.dumps(signals, sort_keys=True), before)

    def test_botscent_reasons_maps_hits_to_botscent_ids(self):
        page = merge(self.page, {"env": {"webdriver": True},
                                 "botscent": {"reasons": ["muse.cloud-browser.password-manager"]}})
        hits = evaluate({"pages": [page]}, self.table).hits
        self.assertEqual(sorted(botscent_reasons(hits, self.table)),
                         ["browser.webdriver-flag", "muse.cloud-browser.password-manager"])


class PhoneOrTabletTest(unittest.TestCase):
    """The rules for a computer passing as a phone or tablet (family phone_or_tablet): they read only what cake.js
    already records, and hold only on a page whose user agent names a phone or tablet, so no desktop page changes."""

    COMPUTER_AGENTS = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 "
        "Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 "
        "Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; CrOS x86_64 16181.61.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 "
        "Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 "
        "Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:146.0) Gecko/20100101 Firefox/146.0")
    PLATFORMS = ("MacIntel", "Win32", "Linux x86_64", "iPhone", "iPad", "Linux armv81")
    VENDORS = ("Google Inc.", "Apple Computer, Inc.", "")
    UA_DATA = (None, {"brands": [], "platform": "iOS", "mobile": True},
               {"brands": [{"brand": "Google Chrome", "version": "157"}], "platform": "Android", "mobile": True})
    GPUS = ({"vendor": "Google Inc. (Apple)", "renderer": "ANGLE (Apple, ANGLE Metal Renderer: Apple M2, Unspecified "
                                                          "Version)"},
            {"vendor": "Apple Inc.", "renderer": "Apple GPU"}, {"vendor": "Qualcomm", "renderer": "Adreno (TM) 740"})
    POINTERS = (["fine"], ["coarse"], ["fine", "coarse"])
    PIXEL_ON_A_MAC = {"env": {"userAgent": "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like "
                                           "Gecko) Chrome/157.0.0.0 Mobile Safari/537.36",
                              "uaData": {"brands": [], "platform": "Android", "mobile": True}}}

    def setUp(self):
        self.table = load_rules()
        self.page = load_cases()["page"]

    def family(self):
        return [rule for rule in self.table.rules if rule.family == "phone_or_tablet"]

    def test_the_family_holds_three_soft_page_rules_of_one_kind(self):
        self.assertEqual(sorted(rule.id for rule in self.family()),
                         ["env.spoof.android-ua-apple-gpu", "env.spoof.ios-ua-chromium-engine",
                          "env.spoof.phone-ua-desktop-platform"])
        for rule in self.family():
            with self.subTest(rule=rule.id):
                self.assertEqual((rule.strength, rule.kind, rule.scope, rule.half, rule.enabled),
                                 ("soft", "spoofing", "page", "page", True))
        self.assertEqual({rule.family for rule in self.table.rules} - {None}, set(self.table.legend["families"]))

    def test_no_family_rule_holds_on_a_page_whose_user_agent_names_a_computer(self):
        family = {rule.id for rule in self.family()}
        for agent, platform, vendor, ua_data, gpu, pointer in itertools.product(
                self.COMPUTER_AGENTS, self.PLATFORMS, self.VENDORS, self.UA_DATA, self.GPUS, self.POINTERS):
            page = merge(self.page, {"env": {"userAgent": agent, "platform": platform, "vendor": vendor,
                                             "uaData": ua_data, "webgl": gpu, "anyPointer": pointer,
                                             "maxTouchPoints": 5 if "coarse" in pointer else 0}})
            held = family & {found.rule for found in evaluate({"pages": [page]}, self.table).hits}
            if held:
                self.fail(f"{sorted(held)} held on {agent} with platform {platform}, vendor {vendor!r}")

    def test_hits_carry_their_rule_family(self):
        page = merge(self.page, merge(self.PIXEL_ON_A_MAC, {"env": {"windowChrome": "undefined"}}))
        families = {found.rule: found.family for found in evaluate({"pages": [page]}, self.table).hits}
        self.assertEqual(families, {"env.spoof.phone-ua-desktop-platform": "phone_or_tablet",
                                    "env.spoof.android-ua-apple-gpu": "phone_or_tablet",
                                    "env.auto.chrome-object-missing": None})

    def test_a_family_the_legend_does_not_name_is_rejected(self):
        good = raw_table()
        with self.assertRaisesRegex(EnvRulesError, "family"):
            parse_rules(merge(good, {"rules": [dict(good["rules"][0], family="no_such_family")]}))

    def test_an_ipad_in_desktop_mode_is_no_worker_mismatch(self):
        ipad = merge(self.page, {"env": {"userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                                      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 "
                                                      "Safari/605.1.15",
                                         "uaData": None, "maxTouchPoints": 5, "anyPointer": ["coarse"]},
                                 "auto": {"workerConsistency": {"differs": ["platform"],
                                                                "worker": {"platform": "iPad"}}}})
        self.assertNotIn("env.spoof.worker-mismatch", {found.rule for found in evaluate({"pages": [ipad]}).hits})
        a_mac = merge(ipad, {"env": {"maxTouchPoints": 0}})
        self.assertIn("env.spoof.worker-mismatch", {found.rule for found in evaluate({"pages": [a_mac]}).hits})


if __name__ == "__main__":
    unittest.main()
