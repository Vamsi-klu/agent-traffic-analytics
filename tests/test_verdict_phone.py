"""Visits that say they come from a phone or tablet, in the verdict (agentcake/detect/verdict_soft.py).

    python3 -I -m unittest discover -s tests -p test_verdict_phone.py -v      (from the repository root)

The behaviour model does not run on a phone or tablet. The environment rules for a computer passing as one
(env_rules.json family phone_or_tablet: a phone's user agent with a computer's platform, an iPhone's with Chrome's
engine, an Android phone's with an Apple GPU) are one kind of evidence together. Alone, or with a trace that a
developer tool's device emulation or a user-agent switcher also leaves (another spoofing rule, the DevTools-protocol
leak), the visit stays Human with limited evidence; with a trace of another kind (automation, a cloud host, an
extension) it is an Agent. The other rules count with each other as before. An iPad in desktop mode, whose worker
reports the iPad while the page reports a Mac, shows no worker mismatch.
"""
import json, os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from test_env_rules import load_cases, merge  # noqa: E402
from verdict_cases import evidence, hit, too_little  # noqa: E402
from agentcake.detect import env_rules, verdict  # noqa: E402

PIXEL = ("Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 "
         "Mobile Safari/537.36")
IPAD_DESKTOP_MODE = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
                     "Version/18.0 Safari/605.1.15")
FAMILY = ("env.spoof.phone-ua-desktop-platform", "env.spoof.ios-ua-chromium-engine", "env.spoof.android-ua-apple-gpu")
EMULATION_TOO = ("env.auto.cdp-runtime-leak", "env.spoof.worker-mismatch", "env.spoof.system-font-names",
                 "env.spoof.request-os-mismatch", "env.spoof.ua-platform-mismatch")
OTHER_KINDS = ("env.auto.chrome-object-missing", "env.cloud.linux-swiftshader", "env.ext.closed-shadow-host")
AGENT_CLASSES = ("agent", "mixed")


def phone(*rule_ids):
    """A visit with a phone's user agent from a desktop browser (Playwright's Pixel 7 on a Mac), judged on these
    hits."""
    return verdict.decide(evidence(uas=PIXEL, platform="MacIntel", touch=True, hits=[hit(r) for r in rule_ids],
                                   behavior_result=too_little("touch", n_actions=4)))


def ids(result):
    return [r["id"] for r in result["reasons"]]


class OneKindOfEvidence(unittest.TestCase):
    def test_one_check_alone_leaves_a_human_with_limited_evidence(self):
        for rule_id in FAMILY:
            with self.subTest(rule_id):
                result = phone(rule_id)
                self.assertEqual(result["class"], "not_sure")
                self.assertIn(rule_id, ids(result))
                self.assertIn("env.soft-alone", ids(result))
                self.assertEqual(result["layers"]["environment"]["state"], "unsure")

    def test_all_three_checks_together_are_still_one_kind(self):
        self.assertEqual(phone(*FAMILY)["class"], "not_sure")

    def test_with_a_trace_device_emulation_also_leaves_it_stays_human(self):
        for other in EMULATION_TOO:
            with self.subTest(other):
                self.assertNotIn(phone(*FAMILY, other)["class"], AGENT_CLASSES)

    def test_with_a_trace_of_another_kind_it_is_an_agent(self):
        for other in OTHER_KINDS:
            with self.subTest(other):
                result = phone(FAMILY[0], other)
                self.assertEqual(result["class"], "agent")
                self.assertIn(FAMILY[0], ids(result))

    def test_the_other_rules_count_with_each_other_as_before(self):
        pair = ("env.auto.cdp-runtime-leak", "env.spoof.worker-mismatch")
        self.assertEqual(phone(*pair)["class"], "agent")
        self.assertEqual(phone(*pair, *FAMILY)["class"], "agent")
        self.assertEqual(phone(pair[0])["class"], "not_sure")

    def test_without_a_check_a_phone_is_too_little_data_as_before(self):
        result = phone()
        self.assertEqual(result["class"], "too_little_data")
        self.assertIn("behavior.touch", ids(result))


class FamilySettings(unittest.TestCase):
    def test_every_family_of_the_rule_table_says_what_it_cannot_count_with(self):
        table = env_rules.load_rules()
        families = verdict.load_settings()["families"]
        self.assertEqual(set(families), set(table.legend["families"]))
        known = {rule.id for rule in table.rules}
        for name, alike in families.items():
            with self.subTest(name):
                self.assertLessEqual(set(alike["kinds"]), set(table.legend["kinds"]))
                self.assertLessEqual(set(alike["rules"]), known)


class IPadInDesktopMode(unittest.TestCase):
    """fpscanner's benign split: iPadOS shows the desktop site by default, and then the page reports MacIntel while a
    worker still reports the iPad."""

    def test_a_soft_trace_more_leaves_the_ipad_human(self):
        cases = load_cases()
        page = merge(cases["page"], {
            "env": {"userAgent": IPAD_DESKTOP_MODE, "uaData": None, "vendor": "Apple Computer, Inc.",
                    "maxTouchPoints": 5, "anyPointer": ["coarse"],
                    "webgl": {"vendor": "Apple Inc.", "renderer": "Apple GPU"}},
            "auto": {"workerConsistency": {"differs": ["platform"], "worker": {"platform": "iPad"}},
                     "runtimeEnableLeak": {"rounds": 1, "stackLookupCount": 1, "prepareStackTraceCount": 0,
                                           "nameGetterCount": 2}}})
        case = dict(evidence(uas=IPAD_DESKTOP_MODE, platform="MacIntel", touch=True,
                             behavior_result=too_little("touch", n_actions=6)),
                    env=env_rules.evaluate({"pages": [page]}))
        result = verdict.decide(case)
        self.assertNotIn(result["class"], AGENT_CLASSES, json.dumps(ids(result)))
        self.assertNotIn("env.spoof.worker-mismatch", ids(result))


if __name__ == "__main__":
    unittest.main()
