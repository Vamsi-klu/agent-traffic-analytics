"""A phone or tablet the behaviour model did not run on, in the verdict (agentcake/detect/verdict_touch.py).

    python3 -I -m unittest discover -s tests -p test_verdict_touch.py -v      (from the repository root)

Such a visit is a Human, with no limited-evidence mark, when everything holds: its browser says it is a phone or
tablet (so the model did not run), its environment records fit a real one (the evidence's touch_fits:
tests/test_touch_device.py), and the name, verification and environment layers found nothing but weak hits. One test
per condition shows that a visit failing it stays as it was, a Human on limited evidence (Too little data, or Not sure
with soft traces alone), and that an Agent or a Bot on a phone keeps its class. A computer's visit with too few actions
keeps the mark whatever its records say. The percent the verdict keeps is computed as before (the session page shows
none for these visits: tests/test_api_session.py).

A visit that stays a Human on limited evidence because its records do not fit a real phone or tablet says which check
they failed (the evidence's touch_failed: touch_device.failed_checks()), one reason per check after the one that says
the model was not used, worded with its facts. Nothing else changes, and no other visit gets them: a real phone or
tablet, an Agent or a Bot on one, a computer, nor a phone whose records fit but which another layer's own reason keeps
on limited evidence.
"""
import os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from verdict_cases import (ANTIGRAVITY, GOOGLEBOT, IPHONE, MANUS, T0, S, behavior, evidence,  # noqa: E402
                           first_address, hit, run, too_little)
from agentcake.api import visits  # noqa: E402
from agentcake.datafiles import load  # noqa: E402
from agentcake.detect import touch_device, verdict, verdict_text  # noqa: E402
from agentcake.units import PERCENT  # noqa: E402

HEADLESS_IPHONE = IPHONE.replace("Version/19.0", "HeadlessChrome/149.0.7827.55")  # a headless Chrome passing as one
PADDED_IPHONE = IPHONE + " "  # a User-Agent with a space after it: one of the lists' shapes of a forged one
THIN_CLASSES = ("too_little_data", "not_sure")
BOUNDARY = load("data/devices.json")["tablet_short_side_dp"]
# One failed check of each kind, with the facts touch_device.failed_checks() gives it (tests/test_touch_device.py)
FAILED = {"not-claimed": {"check": "not-claimed"},
          "no-touch-points": {"check": "no-touch-points", "points": 0},
          "no-screen": {"check": "no-screen"},
          "other-device": {"check": "other-device", "device": "Desktop"},
          "screen-too-large": {"check": "screen-too-large", "device": "Mobile", "w": 673, "h": 841, "min": BOUNDARY},
          "screen-too-small": {"check": "screen-too-small", "device": "Tablet", "w": 390, "h": 844, "min": BOUNDARY},
          "no-worker": {"check": "no-worker", "platform": "MacIntel", "points": 5}}
TOUCH_REASONS = {check: "behavior.touch-" + check for check in FAILED}  # their ids in reasons.json


def phone(touch_fits=True, **changes):
    """A visit from a phone whose browser says so: the behaviour model did not run, however many actions it has."""
    fields = dict({"uas": IPHONE, "platform": "iPhone", "touch": True, "touch_fits": touch_fits,
                   "behavior_result": too_little("touch", n_actions=None)}, **changes)
    return evidence(**fields)


def ids(result):
    return [r["id"] for r in result["reasons"]]


def limited(result):
    """Whether the lists mark the session as limited evidence (api/visits.py: evidence "thin")."""
    return visits.evidence_of(result["class"], None) == "thin"


class RealPhoneOrTablet(unittest.TestCase):
    def test_a_phone_whose_records_fit_and_no_layer_found_anything_on_is_a_human_without_the_mark(self):
        result = verdict.decide(phone())
        self.assertEqual((result["class"], result["judging"], result["row"], result["name"]),
                         ("human", "human", None, None))
        self.assertFalse(limited(result))

    def test_its_reasons_still_say_the_behaviour_model_was_not_used(self):
        result = verdict.decide(phone())
        self.assertIn("behavior.touch", ids(result))
        self.assertEqual(result["layers"]["behavior"], {"state": "unsure", "why": "touch", "leans": None,
                                                        "percent": None})
        self.assertEqual((result["segments"], result["confidence"]), ([], "unsure"), "the model judged no action")

    def test_weak_hits_only_inform_and_change_nothing(self):
        weak = [hit("env.ext.cross-site-landing"), hit("env.ext.viewport-shrink"), hit("env.cloud.datacenter-ip")]
        result = verdict.decide(phone(hits=weak, address=first_address("aws")))
        self.assertEqual((result["class"], limited(result)), ("human", False))
        self.assertIn("env.ext.cross-site-landing", ids(result))

    def test_on_this_computer_the_verification_layer_is_off_and_says_nothing(self):
        result = verdict.decide(phone(mode="local"))
        self.assertEqual((result["class"], result["layers"]["verify"]["state"]), ("human", "off"))

    def test_the_verdict_keeps_the_percent_it_computed_before(self):
        self.assertEqual(verdict.decide(phone())["percent"], verdict.decide(phone(touch_fits=False))["percent"])
        self.assertEqual(verdict.decide(phone())["percent"], PERCENT // 2, "no layer leans either way")


class EachConditionHasToHold(unittest.TestCase):
    """Failing one condition, and no Agent or Bot: the visit stays a Human on limited evidence, as before."""

    def assert_limited(self, case, cls):
        result = verdict.decide(case)
        self.assertEqual((result["class"], limited(result)), (cls, True))
        self.assertIn(cls, THIN_CLASSES)
        return result

    def test_the_browser_has_to_say_it_is_a_phone_or_tablet(self):
        """Too few actions on a computer is why the model judged nothing there: its records change nothing."""
        self.assert_limited(evidence(touch_fits=True, behavior_result=too_little(n_actions=2)), "too_little_data")
        self.assert_limited(evidence(touch_fits=True, behavior_result=None), "too_little_data")

    def test_its_environment_records_have_to_fit_a_real_one(self):
        result = self.assert_limited(phone(touch_fits=False), "too_little_data")
        self.assertIn("behavior.touch", ids(result))
        without_the_key = {key: value for key, value in phone().items() if key != "touch_fits"}
        self.assert_limited(without_the_key, "too_little_data")

    def test_no_check_for_a_computer_passing_as_a_phone_may_hold(self):
        for rule_id in ("env.spoof.phone-ua-desktop-platform", "env.spoof.ios-ua-chromium-engine",
                        "env.spoof.android-ua-apple-gpu"):
            with self.subTest(rule_id):
                result = self.assert_limited(phone(hits=[hit(rule_id)]), "not_sure")
                self.assertIn(rule_id, ids(result))

    def test_the_name_layer_may_have_found_nothing(self):
        for about, user_agent, reason_id in (("an AI app's own browser", ANTIGRAVITY, "name.ua-browser"),
                                             ("the shape of a forged User-Agent", PADDED_IPHONE, "name.ua-hint")):
            with self.subTest(about):
                result = self.assert_limited(phone(uas=user_agent), "too_little_data")
                self.assertIn(reason_id, ids(result))

    def test_the_verification_layer_may_have_found_nothing(self):
        result = self.assert_limited(phone(address=first_address("google-common-crawlers")), "too_little_data")
        self.assertIn("verify.ip-bot-range", ids(result))

    def test_the_environment_layer_may_have_found_no_soft_trace(self):
        result = self.assert_limited(phone(hits=[hit("env.auto.cdp-runtime-leak")]), "not_sure")
        self.assertIn("env.soft-alone", ids(result))

    def test_the_environment_layer_may_have_named_no_browser(self):
        result = self.assert_limited(phone(hits=[hit("env.product.codex-browser")]), "too_little_data")
        self.assertIn("env.product.codex-browser", ids(result))

    def test_no_agent_products_indicator_may_have_shown(self):
        span = {"marker": "comet.overlay", "from": T0 + S, "to": T0 + 30 * S}
        self.assert_limited(dict(phone(), marks=[span]), "too_little_data")


class AgentsAndBotsKeepTheirClass(unittest.TestCase):
    def test_hard_automation_on_a_phone_is_still_an_agent(self):
        result = verdict.decide(phone(uas=HEADLESS_IPHONE, hits=[hit("env.auto.headless-ua")]))
        self.assertEqual((result["class"], result["row"]), ("agent", "automated"))
        self.assertIn("behavior.touch", ids(result))

    def test_soft_traces_that_count_together_are_still_an_agent(self):
        result = verdict.decide(phone(hits=[hit("env.auto.chrome-object-missing"), hit("env.auto.plugins-empty")]))
        self.assertEqual((result["class"], result["row"]), ("agent", "automated"))

    def test_a_named_agent_and_a_listed_bot_on_a_phone_keep_their_class(self):
        named = verdict.decide(phone(uas=MANUS))
        self.assertEqual((named["class"], named["name"]), ("agent", "manus"))
        listed = verdict.decide(phone(uas=GOOGLEBOT, address=None, behavior_result=None))
        self.assertEqual((listed["class"], listed["name"]), ("bot", "googlebot"))


class ComputersAreJudgedAsBefore(unittest.TestCase):
    def test_too_few_actions_and_a_model_that_cannot_tell_keep_the_limited_evidence_mark(self):
        few = verdict.decide(evidence(behavior_result=too_little(n_actions=2)))
        unsure = verdict.decide(evidence(behavior_result=behavior("unsure", run("unsure", 0, 9, 4, 0.5))))
        soft = verdict.decide(evidence(hits=[hit("env.auto.cdp-runtime-leak")],
                                       behavior_result=too_little(n_actions=2)))
        self.assertEqual([(found["class"], limited(found)) for found in (few, unsure, soft)],
                         [("too_little_data", True), ("not_sure", True), ("not_sure", True)])


def unconfirmed(*checks, **changes):
    """A phone whose records failed these checks (FAILED's keys), nothing else found on it."""
    return phone(touch_fits=False, touch_failed=[FAILED[check] for check in checks], **changes)


def check_reasons(result):
    """The reasons that name a failed check, in the order the verdict lists them."""
    return [r for r in result["reasons"] if r["id"] in TOUCH_REASONS.values()]


def without_reasons(result):
    return {key: value for key, value in result.items() if key != "reasons"}


class AnUnconfirmedPhoneSaysWhichCheckFailed(unittest.TestCase):
    def test_every_check_has_its_own_reason(self):
        from agentcake.detect import verdict_touch
        self.assertEqual(set(FAILED), set(touch_device.CHECKS))
        self.assertEqual(verdict_touch.FAILED_CHECK_REASONS, TOUCH_REASONS)
        known = verdict_text.reasons()["reasons"]
        self.assertEqual([reason_id for reason_id in TOUCH_REASONS.values() if reason_id not in known], [])

    def test_each_failed_check_is_said_right_after_the_model_was_not_used(self):
        for check in FAILED:
            with self.subTest(check):
                result = verdict.decide(unconfirmed(check))
                self.assertEqual((result["class"], limited(result)), ("too_little_data", True))
                found = ids(result)
                self.assertEqual(found[found.index("behavior.touch") + 1], TOUCH_REASONS[check])
                said = check_reasons(result)
                self.assertEqual([(r["layer"], r["source"], r["tone"]) for r in said], [("behavior", "page", "none")])

    def test_its_words_carry_the_facts_of_the_check(self):
        """No fact is left unknown, and the numbers and names the check read are said (the boundary is
        devices.json's)."""
        for check, facts in FAILED.items():
            with self.subTest(check):
                said = check_reasons(verdict.decide(unconfirmed(check)))[0]
                self.assertEqual(said["facts"], {name: value for name, value in facts.items() if name != "check"})
                worded = " ".join(filter(None, (said["text"], said["detail"])))
                self.assertNotIn(verdict_text.reasons()["$missing"], worded)
                for name, value in said["facts"].items():
                    self.assertIn(str(value), worded, name)

    def test_touch_points_that_were_not_recorded_are_said_to_be_unknown(self):
        case = phone(touch_fits=False, touch_failed=[{"check": "no-touch-points", "points": None}])
        said = check_reasons(verdict.decide(case))[0]
        self.assertIn(verdict_text.reasons()["$missing"], said["detail"])

    def test_several_failed_checks_are_listed_in_the_order_given(self):
        result = verdict.decide(unconfirmed("no-touch-points", "no-screen"))
        found = ids(result)
        start = found.index("behavior.touch")
        self.assertEqual(found[start:start + 3], ["behavior.touch", TOUCH_REASONS["no-touch-points"],
                                                  TOUCH_REASONS["no-screen"]])

    def test_the_conclusion_and_the_percents_stay_as_they_were(self):
        before = verdict.decide(phone(touch_fits=False))
        for checks in (("no-screen",), ("no-touch-points", "no-screen"), tuple(FAILED)):
            with self.subTest(checks=checks):
                after = verdict.decide(unconfirmed(*checks))
                self.assertEqual(without_reasons(after), without_reasons(before))
                self.assertEqual([r for r in after["reasons"] if r not in check_reasons(after)], before["reasons"])

    def test_beside_a_soft_trace_alone_both_are_said(self):
        result = verdict.decide(unconfirmed("no-screen", hits=[hit("env.spoof.phone-ua-desktop-platform")]))
        self.assertEqual((result["class"], limited(result)), ("not_sure", True))
        self.assertIn("env.spoof.phone-ua-desktop-platform", ids(result))
        self.assertEqual([r["id"] for r in check_reasons(result)], [TOUCH_REASONS["no-screen"]])

    def test_beside_another_layers_finding_both_are_said(self):
        result = verdict.decide(unconfirmed("screen-too-large", uas=PADDED_IPHONE))
        self.assertEqual(result["class"], "too_little_data")
        self.assertIn("name.ua-hint", ids(result))
        self.assertEqual([r["id"] for r in check_reasons(result)], [TOUCH_REASONS["screen-too-large"]])


class NoOtherVisitSaysWhichCheckFailed(unittest.TestCase):
    def test_a_real_phone_or_tablet(self):
        result = verdict.decide(phone())
        self.assertEqual((result["class"], check_reasons(result)), ("human", []))

    def test_a_phone_that_fits_but_another_layers_own_reason_keeps_on_limited_evidence(self):
        cases = {"a soft trace": phone(hits=[hit("env.spoof.ios-ua-chromium-engine")]),
                 "the name layer": phone(uas=PADDED_IPHONE),
                 "the verification layer": phone(address=first_address("google-common-crawlers")),
                 "a browser's own product rule": phone(hits=[hit("env.product.codex-browser")]),
                 "an indicator": dict(phone(), marks=[{"marker": "comet.overlay", "from": T0 + S, "to": T0 + 30 * S}])}
        for about, case in cases.items():
            with self.subTest(about):
                result = verdict.decide(case)
                self.assertEqual((limited(result), check_reasons(result)), (True, []))

    def test_an_agent_on_a_phone(self):
        cases = {"hard automation": unconfirmed(*FAILED, uas=HEADLESS_IPHONE, hits=[hit("env.auto.headless-ua")]),
                 "soft traces together": unconfirmed(*FAILED, hits=[hit("env.auto.chrome-object-missing"),
                                                                    hit("env.auto.plugins-empty")]),
                 "a named agent": unconfirmed(*FAILED, uas=MANUS)}
        for about, case in cases.items():
            with self.subTest(about):
                result = verdict.decide(case)
                self.assertEqual((result["class"], check_reasons(result)), ("agent", []))

    def test_a_bot_on_a_phone(self):
        result = verdict.decide(unconfirmed(*FAILED, uas=GOOGLEBOT, address=None, behavior_result=None))
        self.assertEqual((result["class"], check_reasons(result)), ("bot", []))

    def test_a_computer(self):
        for behavior_result in (too_little(n_actions=2), None, behavior("unsure", run("unsure", 0, 9, 4, 0.5))):
            with self.subTest(behavior=(behavior_result or {}).get("verdict")):
                case = evidence(touch_failed=list(FAILED.values()), behavior_result=behavior_result)
                self.assertEqual(check_reasons(verdict.decide(case)), [])

    def test_a_phone_whose_evidence_names_no_check(self):
        """The evaluation's recordings of events alone (PostHog's, the public data sets'): a phone by the data set's
        label, without an environment record or its checks."""
        case = {key: value for key, value in phone().items() if key not in ("touch_fits", "touch_failed")}
        result = verdict.decide(case)
        self.assertEqual((result["class"], check_reasons(result)), ("too_little_data", []))


if __name__ == "__main__":
    unittest.main()
