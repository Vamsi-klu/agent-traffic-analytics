"""The environment layer (S3.3): the rule table agentcake/data/env_rules.json and its evaluator,
agentcake/detect/env_rules.py.

    python3 -I -m unittest discover -s tests -v      (from the Agent Cake folder)

Every rule has hit and miss cases (tests/fixtures/env_rules/cases.json). The checks on the lab's recorded sessions
(GOAL T6's environment part) are kept with those recordings, outside the published repository.
"""
import copy, json, os, re, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from agentcake.detect import env_rules  # noqa: E402
from agentcake.detect.env_rules import EnvRulesError, evaluate, load_rules, parse_rules  # noqa: E402

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

    def test_hits_serialise_to_json_with_their_reason_fields(self):
        host = {"tag": "DIV", "nattr": 0, "attrs": [], "open_shadow": 0, "disp": "contents", "parent": "body",
                "how": "added"}
        page = merge(self.page, {"env": {"window": {"iw": 1280, "ih": 720}}, "dom_add": [host]})
        hits = [hit.as_dict() for hit in evaluate({"pages": [page]}, self.table).hits]
        json.dumps(hits)
        viewport = next(h for h in hits if h["rule"] == "env.auto.default-viewport")
        self.assertEqual(viewport["value"], {"env.window.iw": 1280, "env.window.ih": 720})
        host = next(h for h in hits if h["rule"] == "env.ext.closed-shadow-host")
        self.assertEqual((host["suggests"], host["pages"]), ("claude-chrome", [0]))
        self.assertEqual(host["value"][0]["disp"], "contents")

    def test_botscent_reasons_maps_hits_to_botscent_ids(self):
        page = merge(self.page, {"env": {"webdriver": True},
                                 "botscent": {"reasons": ["muse.cloud-browser.password-manager"]}})
        hits = evaluate({"pages": [page]}, self.table).hits
        self.assertEqual(sorted(env_rules.botscent_reasons(hits, self.table)),
                         ["browser.webdriver-flag", "muse.cloud-browser.password-manager"])


if __name__ == "__main__":
    unittest.main()
