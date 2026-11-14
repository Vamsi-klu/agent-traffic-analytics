"""The tables and measurements of `agentcake eval` (plan step S3.9): each one on data whose answer is known.

    python3 -I -m unittest discover -s tests -p test_eval_tables.py -v

Real data of this repository (the lab's 26 sessions with their signals, the lab's 57 signal recordings, two real
cake.js uploads, GOAL A7's ten User-Agents) and made-up sessions (tests/verdict_cases.py) for what has no real data
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
from agentcake.evaluation import (bots, datasets, evidence as evidence_builder, humans, measures, sessions, sources,
                                  takeovers)

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
        return takeovers.session_row(built, lambda t: self.TRUTH[int((t - vc.T0) / vc.S)], [vc.T0 + 5 * vc.S], 3)

    def test_a_mixed_session_shows_what_the_timeline_found(self):
        row = self.row(vc.AGENT_RUN, vc.HUMAN_RUN)
        self.assertEqual(row["class"], "mixed")
        for view in ("model", "verdict"):
            self.assertEqual((row[view]["accuracy_decided"], row[view]["handoff_errors_s"]), (1.0, [0.0]), view)

    def test_an_agent_session_gives_every_action_to_the_agent_and_has_no_hand_off(self):
        row = self.row(vc.AGENT_RUN)
        self.assertEqual(row["class"], "agent")
        self.assertEqual(row["model"]["accuracy_decided"], 1.0)
        self.assertEqual((row["verdict"]["accuracy_decided"], row["verdict"]["handoff_errors_s"]), (0.5, [None]))
        self.assertEqual(row["verdict"]["share_error_pp"], 50.0)

    def test_a_missed_hand_off_leaves_the_largest_error_unknown(self):
        rows = [{"class": "human", "model": None, "verdict": {"n": 4, "accuracy_decided": 1.0, "share_error_pp": 0.0,
                                                             "handoff_errors_s": [1.0, None], "handoffs_extra": 0}}]
        summary = takeovers.summary(rows, "verdict", 3)
        self.assertEqual((summary["handoffs_missed"], summary["largest_handoff_error_s"]), (1, None))
        a5 = [m for m in measures._takeover("x", rows, 3) if m["threshold"] == "A5"][0]
        self.assertEqual((a5["value"], a5["n"], a5["details"]["missed"]), (None, 2, 1))

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
