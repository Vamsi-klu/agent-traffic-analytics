"""agentcake/evaluation/scoreboard.py and heldout.py: the behaviour layer reported the industry's way, and
thresholds set from data tested where they were not set.

    python3 -I -m unittest discover -s tests -v

Rows are made by hand in the shape of sessions.row(), so each count is visible in the test.
"""
import os
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]

from agentcake import datafiles  # noqa: E402
from agentcake.evaluation import heldout, report, scoreboard  # noqa: E402

SETTINGS = datafiles.load("data/eval.json")


def row(source, group, truth, behaviour, cls, site=None):
    return {"source": source, "group": group, "truth": {"class": truth}, "behaviour": behaviour, "class": cls,
            "site": site}


ROWS = {"lab": [row("lab", "claude-chrome", "agent", "agent", "agent"),
                row("lab", "claude-chrome-bg", "agent", "unsure", "not_sure"),
                row("lab", "pw-humanlike-headed", "agent", "human", "agent")],
        "recordings": [row("recordings", "clean-human", "human", "human", "human", "shop"),
                       row("recordings", "clean-human", "human", "agent", "agent", "lab")],
        "public_humans": [row("public_humans", "psai", "human", "too_little_data", "too_little_data", "psai/x")],
        "posthog": [row("posthog", "claude-chrome", "agent", "too_little_data", "too_little_data"),
                    row("posthog", "owner", "human", "human", "mixed"),
                    row("posthog", "unknown", None, "agent", "agent")]}


class ScoreboardTest(unittest.TestCase):
    def setUp(self):
        self.board = scoreboard.build(ROWS, {}, SETTINGS, 3)

    def cell(self, cells, **match):
        return next(c for c in cells if all(c[k] == v for k, v in match.items()))

    def test_agents_by_product_with_evaluable_share_and_both_recalls(self):
        cic = self.cell(self.board["agents"], source="lab", product="claude-chrome")
        self.assertEqual((cic["sessions"], cic["evaluable"]["k"], cic["recall"]["k"], cic["recall"]["n"]), (2, 2, 1, 2))
        humanlike = self.cell(self.board["agents"], product="playwright-humanlike")
        self.assertEqual((humanlike["recall"]["k"], humanlike["four_layers"]["k"]), (0, 1))
        unseen = self.cell(self.board["agents"], source="posthog", product="claude-chrome")
        self.assertEqual((unseen["evaluable"]["k"], unseen["recall"]["n"], unseen["recall_all"]["n"]), (0, 0, 1))

    def test_humans_count_the_behaviour_models_agents_on_evaluable_sessions(self):
        clean = self.cell(self.board["humans"], source="recordings")
        self.assertEqual((clean["false_positives"]["k"], clean["false_positives"]["n"]), (1, 2))
        self.assertAlmostEqual(clean["false_positives"]["high"], 0.9874, places=4)
        owner = self.cell(self.board["humans"], source="posthog", group="owner")
        self.assertEqual((owner["false_positives"]["k"], owner["four_layers"]["k"]), (0, 1))  # Mixed counts there

    def test_rows_without_an_answer_are_left_out(self):
        self.assertFalse([c for c in self.board["agents"] + self.board["humans"] if c["group" if "group" in c
                                                                                     else "product"] == "unknown"])

    def test_humans_pooled_per_recording_kind(self):
        raw = self.board["pooled_humans"]["raw"]
        self.assertEqual((raw["sessions"], raw["evaluable"]["k"], raw["false_positives"]["k"]), (3, 2, 1))
        self.assertEqual(self.board["pooled_humans"]["rrweb"]["sessions"], 1)

    def test_precision_pairs_a_product_with_the_humans_recorded_the_same_way(self):
        cic = self.cell(self.board["precision"], source="lab", product="claude-chrome")
        self.assertEqual((cic["humans"], cic["false_positive_rate"]), (2, 0.5))
        self.assertAlmostEqual(cic["at"]["0.01"]["measured"], 0.5 * 0.01 / (0.5 * 0.01 + 0.5 * 0.99))

    def test_counts_per_site(self):
        self.assertEqual(self.board["sites"]["lab"]["humans"]["false_positives"]["k"], 1)
        self.assertEqual(self.board["sites"]["lab"]["agents"]["sessions"], 3)
        self.assertIsNone(self.board["sites"]["shop"]["agents"])

    def test_the_report_prints_every_table(self):
        text = "\n".join(report._scoreboard(self.board, 3))
        for heading in ("agents: data set / product", "humans: data set / group", "precision at 1.0%",
                        "| site |", "Mixed sessions"):
            self.assertIn(heading, text)


def measured(source, group, site, truth, values, product=None):
    """A session heldout.build() has measured: segments carrying only the fitted feature."""
    return {"source": source, "group": group, "site": site, "truth": truth, "product": product or group,
            "segments": [{"features": {"score": v}} for v in values]}


class FitTest(unittest.TestCase):
    CANDIDATES = [0.3, 0.4, 0.5, 0.6]

    def test_the_largest_threshold_that_keeps_every_data_set_within_the_budget(self):
        people = [measured("a", "x", "s1", "human", [0.35, 0.9, 0.9, 0.9, 0.9]),
                  measured("b", "y", "s2", "human", [0.55, 0.8, 0.8, 0.8, 0.8])]
        self.assertEqual(heldout.fit(people, "score", "<", self.CANDIDATES, 0.2), 0.6)
        self.assertEqual(heldout.fit(people, "score", "<", self.CANDIDATES, 0.1), 0.3)

    def test_no_threshold_keeps_the_budget(self):
        people = [measured("a", "x", "s1", "human", [0.1, 0.1])]
        self.assertIsNone(heldout.fit(people, "score", "<", self.CANDIDATES, 0.0))

    def test_segments_without_data_do_not_count(self):
        people = [measured("a", "x", "s1", "human", [None, None, 0.9])]
        self.assertEqual(heldout.fit(people, "score", "<", self.CANDIDATES, 0.0), 0.6)

    def test_a_model_without_the_rule_has_nothing_to_fit(self):
        params = {"rules": {"list": []}, "min_actions": 3}
        self.assertEqual(heldout.build([], SETTINGS, params), [])

    def test_agents_are_never_used(self):
        people = [measured("a", "x", "s1", "human", [0.9] * 10)]
        agents = [measured("lab", "pw", "lab", "agent", [0.2] * 10)]
        self.assertEqual(heldout.fit(people, "score", "<", self.CANDIDATES, 0.0),
                         heldout.fit(people + agents, "score", "<", self.CANDIDATES, 0.0))


if __name__ == "__main__":
    unittest.main()
