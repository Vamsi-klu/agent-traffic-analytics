"""The tables and measurements of `agentcake eval`: each one on data whose answer is known.

    python3 -I -m unittest discover -s tests -p test_eval_tables.py -v

Real data of this repository (the lab's 26 sessions with their signals, the lab's 57 signal recordings, two real
cake.js uploads, threshold A7's ten User-Agents) and made-up sessions (tests/verdict_cases.py) for what has no real data
here yet: T22's groups, take-overs with known hand-offs, the half and layer filters, PostHog's mixed replays.
"""
import os
import sys
import tempfile
import json
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.dirname(os.path.abspath(__file__))
for folder in (REPO, TESTS):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import verdict_cases as vc  # noqa: E402
from test_lists import A7  # noqa: E402
from agentcake import datafiles  # noqa: E402
from agentcake.evaluation import (bots, datasets, evidence as evidence_builder, gate, humans, measures, report,
                                  sessions, sources, takeovers)

FIXTURES = os.path.join(REPO, "tests", "fixtures")
SETTINGS = datafiles.load("data/eval.json")


class CakeJsAndNamed(unittest.TestCase):

    def test_the_a7_cases_are_the_ten_s3_1_tests(self):
        cases = datasets.named_user_agents(os.path.join(REPO, "eval", "named_user_agents.json"))
        self.assertEqual([(c["user_agent"], c["name"], c["class"], c["kind"]) for c in cases], [tuple(a) for a in A7])

    def test_the_ten_named_user_agents_are_right(self):
        cases = datasets.named_user_agents(os.path.join(REPO, "eval", "named_user_agents.json"))
        table = bots.named_table(sessions.named(cases))
        self.assertEqual((table["right"], table["n"]), (10, 10))


def store_row(name, group, truth, **case):
    return sessions.row(name, "store", group, dict(truth, case="T22", group=group), vc.evidence(**case))


class T22(unittest.TestCase):
    def rows(self, impersonated_right=True):
        out = []
        for k in range(3):
            out.append(store_row(f"g{k}", "googlebot-verified", {"class": "bot", "verification": "verified"},
                                 uas=vc.GOOGLEBOT, platform="Linux x86_64",
                                 address=vc.first_address("google-common-crawlers")))
            out.append(store_row(f"i{k}", "googlebot-impersonated",
                                 {"class": "agent" if impersonated_right else "bot", "row": "automated",
                                  "verification": "impersonation"},
                                 uas=vc.GOOGLEBOT, platform="Linux x86_64",
                                 behavior_result=vc.behavior("agent", vc.AGENT_RUN)))
            out.append(store_row(f"c{k}", "cloud-script", {"class": "agent", "row": "automated", "crawler": True},
                                 uas=vc.HEADLESS, hits=[vc.hit(r) for r in vc.AUTOMATION_HITS],
                                 address=vc.first_address("aws"), pages=vc.crawl_pages(12, 5),
                                 behavior_result=vc.too_little(n_actions=0)))
        return out

    def test_every_group_right_and_the_crawler_reason_counted(self):
        table = bots.t22_table(self.rows(), SETTINGS)
        self.assertEqual((table["right"], table["n"]), (9, 9))
        self.assertEqual(table["groups"]["cloud-script"]["crawler_reason"], 3)
        a9 = measures._a9(table)
        self.assertEqual((a9["value"], a9["groups"]["googlebot-verified"]), (1.0, {"n": 3, "right": 3}))

    def test_a_wrong_answer_shows_in_its_group(self):
        table = bots.t22_table(self.rows(impersonated_right=False), SETTINGS)
        self.assertEqual(table["groups"]["googlebot-impersonated"]["right"], 0)


class Takeovers(unittest.TestCase):
    TRUTH = ["agent"] * 5 + ["human"] * 5

    def row(self, *runs):
        """A behaviour-only session whose timeline gave ten actions, one a second, agent then human, with one
        hand-off at the sixth; the runs decide the class (both long: Mixed; the agent's alone: Agent)."""
        result = vc.behavior("agent", *runs)
        actions = [{"t": vc.T0 + i * vc.S, "who": who} for i, who in enumerate(self.TRUTH)]
        handoff = {"t": vc.T0 + 5 * vc.S, "from": "agent", "to": "human", "after": vc.T0 + 4 * vc.S}
        result["timeline"].update(actions=actions, handoffs=[handoff])
        built = dict(vc.evidence(mode="local", behavior_result=result), env=None)
        return takeovers.session_row(built, lambda t: self.TRUTH[int((t - vc.T0) / vc.S)],
                                     [(vc.T0 + 5 * vc.S, "agent", "human")], 3)

    def test_a_mixed_session_shows_what_the_timeline_found(self):
        row = self.row(vc.AGENT_RUN, vc.HUMAN_RUN)
        self.assertEqual(row["class"], "mixed")
        for view in ("model", "verdict"):
            self.assertEqual((row[view]["accuracy_decided"], row[view]["handoff_errors_s"]), (1.0, [0.0]), view)

    def test_a_hand_off_the_timeline_found_the_other_way_round_is_missed(self):
        result = vc.behavior("agent", vc.AGENT_RUN, vc.HUMAN_RUN)
        result["timeline"].update(actions=[{"t": vc.T0 + i * vc.S, "who": who} for i, who in enumerate(self.TRUTH)],
                                  handoffs=[{"t": vc.T0 + 5 * vc.S, "from": "human", "to": "agent",
                                             "after": vc.T0 + 4 * vc.S}])
        built = dict(vc.evidence(mode="local", behavior_result=result), env=None)
        row = takeovers.session_row(built, lambda t: self.TRUTH[int((t - vc.T0) / vc.S)],
                                    [(vc.T0 + 5 * vc.S, "agent", "human")], 3)
        self.assertEqual(row["model"]["handoff_errors_s"], [None], "right moment, wrong direction: not found")

    def test_an_agent_session_gives_every_action_to_the_agent_and_has_no_hand_off(self):
        row = self.row(vc.AGENT_RUN)
        self.assertEqual(row["class"], "agent")
        self.assertEqual(row["model"]["accuracy_decided"], 1.0)
        self.assertEqual((row["verdict"]["accuracy_decided"], row["verdict"]["handoff_errors_s"]), (0.5, [None]))
        self.assertEqual(row["verdict"]["share_error_pp"], 50.0)

    @staticmethod
    def judged(cls, errors, extra=0):
        """A scored session of the product view: its class and the errors of its true hand-offs (None: missed)."""
        return {"class": cls, "model": None, "verdict": {"n": 4, "accuracy_decided": 1.0, "share_error_pp": 0.0,
                                                         "handoff_errors_s": errors, "handoffs_extra": extra}}

    @staticmethod
    def a5(rows, source="x"):
        return next(m for m in measures._takeover(source, rows, 3) if m["threshold"] == "A5")

    @staticmethod
    def a5_verdict(rows):
        thresholds = gate.load(os.path.join(REPO, "eval", "thresholds.json"))
        verdicts = gate.judge(thresholds, measures._takeover("recording_splices", rows, 3))
        return next(v for v in verdicts if v["id"] == "A5"), "\n".join(report.markdown_gate(verdicts))

    def test_a_missed_hand_off_leaves_the_largest_error_unknown(self):
        summary = takeovers.summary([self.judged("human", [1.0, None])], "verdict", 3)
        self.assertEqual((summary["handoffs_missed"], summary["largest_handoff_error_s"]), (1, None))

    def test_the_sessions_judged_human_plus_agent_are_counted_with_their_own_hand_off_errors(self):
        rows = [self.judged("mixed", [1.0, 5.0]), self.judged("human", [None])]
        summary = takeovers.summary(rows, "verdict", 3)
        self.assertEqual(summary["mixed_found"], {"count": 1, "n": 2})
        in_mixed = summary["in_mixed"]
        self.assertEqual((in_mixed["handoffs_true"], in_mixed["handoffs_missed"], in_mixed["handoffs_within_limit"],
                          in_mixed["largest_handoff_error_s"], in_mixed["handoff_error_median_s"]),
                         (2, 0, 0.5, 5.0, 3.0))

    def test_a5_is_the_median_error_over_the_sessions_judged_human_plus_agent(self):
        a5 = self.a5([self.judged("mixed", [1.0, 5.0]), self.judged("human", [None])])
        self.assertEqual((a5["value"], a5["n"], a5["details"]["missed"]), (3.0, 2, 0),
                         "the session judged Human has no hand-off: it is left out of A5")
        self.assertEqual(a5["details"]["mixed_found"], {"count": 1, "n": 2})
        self.assertEqual(a5["details"]["every_handoff"],
                         {"true": 3, "missed": 1, "within_limit": 1 / 3, "largest_found": 5.0, "extra": 0})

    def test_a_missed_hand_off_counts_as_over_the_limit(self):
        self.assertEqual(self.a5([self.judged("mixed", [1.0, 2.0, None])])["value"], 2.0,
                         "the miss is the largest error, not left out (that would give 1.5)")
        self.assertIsNone(self.a5([self.judged("mixed", [1.0, None])])["value"],
                          "half missed: the median lies over any limit")

    def test_more_than_half_missed_in_the_sessions_judged_human_plus_agent_fails(self):
        rows = [self.judged("mixed", [0.0, None]), self.judged("mixed", [None]), self.judged("human", [None])]
        a5, text = self.a5_verdict(rows)
        self.assertEqual((a5["status"], a5["gated"][0]["value"], a5["gated"][0]["n"]), ("fail", None, 3))
        self.assertIn("recording_splices: over the limit (n=3; missed 2, within the limit 33.3%, largest found 0 s) "
                      "**FAIL**", text)

    def test_no_true_hand_off_in_the_sessions_judged_human_plus_agent_is_no_samples(self):
        a5, text = self.a5_verdict([self.judged("human", [None, None]), self.judged("agent", [None])])
        self.assertEqual((a5["status"], a5["gated"][0]["status"], a5["gated"][0]["n"]), ("no_data", "no_data", 0),
                         "no sample is not a pass")
        self.assertIn("| A5 | ≤ 3 seconds | no data | recording_splices: no samples;", text)
        self.assertIn("| A5 (reference) | — | not judged | recording_splices: found 0/3 (missed 3), within the limit "
                      "0.0%, largest found — s, extra 0 |", text)

    def test_the_gate_table_shows_every_true_hand_off_under_a5_without_judging_it(self):
        a5, text = self.a5_verdict([self.judged("mixed", [1.0, 5.0]), self.judged("human", [None])])
        self.assertEqual(a5["status"], "pass", "the median over the session judged Human + agent is 3 s")
        self.assertIn("| A5 | ≤ 3 seconds | pass | recording_splices: 3 (n=2; missed 0, within the limit 50.0%, "
                      "largest found 5 s) pass;", text)
        self.assertIn("| A5 (reference) | — | not judged | recording_splices: found 2/3 (missed 1), within the limit "
                      "33.3%, largest found 5 s, extra 0 | — |", text)
        self.assertIn("| A5 (reference) | — | not judged | recording_splices: 50.0% (1/2) | — |", text)

    def test_verdict_who(self):
        self.assertEqual([takeovers.verdict_who(w, "agent") for w in ("human", "unsure")], ["agent", "unsure"])
        self.assertEqual(takeovers.verdict_who("human", "mixed"), "human")


class Keep(unittest.TestCase):
    def test_keeping_the_page_half_drops_what_the_others_read(self):
        built = vc.evidence(uas=vc.HEADLESS, hits=[vc.hit(r) for r in vc.AUTOMATION_HITS], address=vc.NOWHERE,
                            pages=[{"t": vc.T0, "sp": "prefetch"}], visits=[vc.T0 - vc.S],
                            behavior_result=vc.behavior("agent", vc.AGENT_RUN))
        page = evidence_builder.keep(built, halves=["page"])
        self.assertEqual(set(page["user_agents"]), {"page"})
        self.assertEqual((page["network"], page["visits"], page["pages"]), (None, [], [{"t": vc.T0}]))
        self.assertEqual({h.half for h in page["env"].hits}, {"page"})
        self.assertIsNotNone(page["behavior"])
        collector = evidence_builder.keep(built, halves=["collector"])
        self.assertIsNone(collector["behavior"])
        self.assertEqual({h.half for h in collector["env"].hits}, {"collector"})

    def test_keeping_layers(self):
        built = vc.evidence(uas=vc.HEADLESS, hits=[vc.hit("env.auto.webdriver")],
                            behavior_result=vc.behavior("agent", vc.AGENT_RUN))
        behaviour = evidence_builder.keep(built, layers=["behavior"])
        self.assertEqual((behaviour["user_agents"], behaviour["env"].hits), ({}, ()))
        environment = evidence_builder.keep(built, layers=["environment"])
        self.assertIsNone(environment["behavior"])
        self.assertTrue(environment["env"].hits)


class Humans(unittest.TestCase):
    def test_weak_hits_are_listed_and_never_count(self):
        name, _, make, _ = next(c for c in vc.CONTROLS if c[0] == "weak-only")
        row = sessions.row(name, "recordings", "clean-human", {"class": "human"}, make())
        table = humans.table([row])
        self.assertEqual(table["summary"]["rules_held"]["weak"],
                         ["env.cloud.datacenter-ip", "env.ext.cross-site-landing", "env.ext.viewport-shrink"])
        self.assertEqual(table["summary"]["sessions_with_a_strong_hit"], 0)
        self.assertEqual(table["sessions"][0]["class"], "human")

    def test_a1_counts_only_whole_sessions_judged_agent(self):
        rows = [{"truth": {"class": "human"}, "class": c} for c in ("human", "mixed", "agent", "too_little_data")]
        a1 = measures._a1("recordings", rows)
        self.assertEqual((a1["count"], a1["n"], a1["details"]["mixed"], a1["details"]["not_judged"]), (1, 3, 1, 1))


class PhonesTabletsAndTooFewActions(unittest.TestCase):
    """Threshold A8: none is an Agent; a real phone or tablet is a Human, the rest too little data."""

    def row(self, touch_fits=False, judged=None, **fields):
        fields = dict({"uas": vc.IPHONE, "platform": "iPhone", "touch": True, "touch_fits": touch_fits,
                       "behavior_result": vc.too_little("touch", None)}, **fields)
        found = sessions.row("made-up", "store", "phone", {"class": "human"}, vc.evidence(**fields))
        return dict(found, **({"class": judged} if judged else {}))

    def test_a_real_phone_shown_as_a_human_and_the_rest_as_too_little_data_are_right(self):
        few = self.row(uas=vc.CHROME_MAC, platform="MacIntel", touch=False,
                       behavior_result=vc.too_little(n_actions=2))
        a8 = measures._a8("store", [self.row(touch_fits=True), self.row(), few])
        self.assertEqual((a8["count"], a8["n"]), (3, 3))
        self.assertEqual(a8["details"]["classes"], {"human": 1, "too_little_data": 2})

    def test_a_phone_whose_records_do_not_fit_shown_as_a_plain_human_is_wrong(self):
        a8 = measures._a8("store", [self.row(judged="human"), self.row(touch_fits=True)])
        self.assertEqual((a8["count"], a8["n"], a8["value"]), (1, 2, 0.5))

    def test_one_judged_an_agent_is_wrong_whatever_its_records(self):
        for touch_fits in (True, False):
            with self.subTest(touch_fits=touch_fits):
                a8 = measures._a8("store", [self.row(touch_fits=touch_fits, judged="agent")])
                self.assertEqual((a8["count"], a8["n"]), (0, 1))

    def test_the_published_threshold_says_what_is_measured(self):
        entry = gate.by_id(gate.load(os.path.join(REPO, "eval", "thresholds.json")))["A8"]
        for text in (entry["goal"], entry["measure"], entry["statistic"]):
            self.assertIn("real phone or tablet", text)
        self.assertEqual((entry["op"], entry["value"], entry["unit"]), (">=", 1.0, "share"))


class PostHogMixed(unittest.TestCase):
    def unit(self, session, label, group, times):
        return {"session": session, "label": label, "group": group, "start": times[0],
                "events": [{"t": float(t), "ty": "click", "cx": 1, "cy": 1} for t in times]}

    def test_an_owner_session_with_agent_and_human_actions_is_a_mixed_replay(self):
        units = [self.unit("s1", "agent", None, [0, 1000, 2000]), self.unit("s1", "probably-human", "owner",
                                                                            [9000, 10000, 11000]),
                 self.unit("s2", "agent", None, [0, 1000, 2000]), self.unit("s2", "probably-human", "visitor",
                                                                            [9000, 10000, 11000])]
        (mixed,) = datasets.mixed_replays(units, SETTINGS)
        self.assertEqual((mixed["h"], mixed["agent_at"](1000.0), mixed["agent_at"](10000.0)), ("s1", True, False))


class Sources(unittest.TestCase):
    def test_the_command_line_wins_then_the_sources_file_then_the_checkout(self):
        folder = tempfile.mkdtemp(prefix="cake-eval-")
        path = os.path.join(folder, "sources.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"out_dir": os.path.join(folder, "ph"), "recordings": os.path.join(folder, "rec"),
                       "_about": "ignored"}, f)
        where = sources.locate({"sources": path, "recordings": os.path.join(folder, "mine")}, SETTINGS)
        self.assertEqual(where["recordings"], os.path.join(folder, "mine"))
        self.assertEqual(where["posthog"], os.path.join(folder, "ph"))
        self.assertTrue(where["thresholds"].endswith(os.path.join("eval", "thresholds.json")))

    def test_short_hashes_follow_eval_readme(self):
        self.assertRegex(datasets.short_hash(SETTINGS["short_hash"]["goal"], "abc", SETTINGS), r"^[0-9a-f]{12}$")


if __name__ == "__main__":
    unittest.main()
