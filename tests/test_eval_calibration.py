"""agentcake/evaluation/calibration.py: fitting the behaviour map and checking percents.

    python3 -I -m unittest discover -s tests -v
"""
import os
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]

from agentcake.evaluation import calibration  # noqa: E402

BINS = [[0.0, 0.5], [0.5, 1.0]]


class FitTest(unittest.TestCase):
    def test_blocks_rise_with_the_score(self):
        points = [(-3, False)] * 40 + [(-1, False)] * 5 + [(-1, True)] * 5 + [(2, True)] * 20
        blocks = calibration.fit(points, 0.5)
        chances = [chance for _, chance in blocks]
        self.assertEqual(chances, sorted(chances))
        self.assertEqual([upper for upper, _ in blocks], [-3, -1, 2])

    def test_each_class_weighs_alike(self):
        # one agent for every eight people at the same score reads as even odds when the classes are 10 and 80
        points = [(0, True)] * 10 + [(0, False)] * 80
        (only,) = calibration.fit(points, 0.0)
        self.assertAlmostEqual(only[1], 0.5)

    def test_shrinking_keeps_the_ends_away_from_zero_and_one(self):
        blocks = calibration.fit([(-1, False)] * 30 + [(1, True)] * 30, 0.5)
        self.assertTrue(0 < blocks[0][1] < 0.05 and 0.95 < blocks[-1][1] < 1)

    def test_a_tie_is_never_split_between_blocks(self):
        points = [(0.0, True)] * 6 + [(0.0, False)] * 3 + [(0.3, False)] * 10 + [(-2, False)] * 50 + [(3, True)] * 20
        uppers = [upper for upper, _ in calibration.fit(points, 0.5)]
        self.assertNotIn(0.0, uppers)  # the agents at 0.0 pooled with the people after them, not cut off before

    def test_one_class_alone_fits_nothing(self):
        self.assertEqual(calibration.fit([(1, True)] * 5, 0.5), [])


class AnsweredTest(unittest.TestCase):
    def test_real_products_count_and_the_automation_made_to_look_human_does_not(self):
        def row(source, label, cls="agent", weak=False):
            return {"source": source, "truth": {"class": cls, "label": label, **({"weak": True} if weak else {})}}
        rows = {"selfcollect": [row("selfcollect", "cc-playwright-mcp"), row("selfcollect", "fake-camoufox")],
                "posthog": [row("posthog", None, "human"), row("posthog", None, "human", weak=True),
                            row("posthog", None, "mixed")]}
        spec = {"sources": ["selfcollect", "posthog"], "left_out": {"selfcollect": ["fake-camoufox"]}}
        kept = [(r["source"], r["truth"]["label"], r["truth"]["class"]) for r in calibration.answered(rows, spec)]
        self.assertEqual(kept, [("selfcollect", "cc-playwright-mcp", "agent"), ("posthog", None, "human")])


class CheckTest(unittest.TestCase):
    def test_bins_compare_the_predicted_and_the_actual_share(self):
        pairs = [(0.1, False)] * 9 + [(0.1, True)] + [(0.9, True)] * 9 + [(0.9, False)]
        out = calibration.check(pairs, BINS)
        low, high = out["bins"]
        self.assertEqual((low["sessions"], low["agents"], high["agents"]), (10, 1, 9))
        self.assertAlmostEqual(low["actual"], 0.1)
        self.assertAlmostEqual(high["predicted"], 0.9)
        self.assertAlmostEqual(out["brier"], 0.09)

    def test_a_coin_scores_a_quarter_and_one_class_alone_is_not_checked(self):
        self.assertAlmostEqual(calibration.check([(0.5, True), (0.5, False)], BINS)["brier"], 0.25)
        self.assertIsNone(calibration.check([(0.5, True)], BINS)["brier"])


if __name__ == "__main__":
    unittest.main()
