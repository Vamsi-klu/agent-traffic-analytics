"""agentcake/evaluation/stats.py: exact binomial bounds and precision at a prevalence (plan step S3.7, D36).

    python3 -I -m unittest discover -s tests -v

The Clopper–Pearson values are the published ones (two-sided 95%): 0 of 11 allows up to 28.5% (research note 21's
clean humans), 21 of 23 lies in 72.0%–98.9% (note 21's Claude in Chrome on PostHog), 2 of 10 in 2.5%–55.6% (the
textbook example). Precision at 1% is note 21's worked example: recall 90%, false positives 5% → 15.4%.
"""
import os
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]

from agentcake.evaluation import stats  # noqa: E402

CONFIDENCE = 0.95


def rounded(interval, places=4):
    return tuple(round(x, places) for x in interval)


class ClopperPearsonTest(unittest.TestCase):
    def test_none_of_eleven(self):
        low, high = stats.clopper_pearson(0, 11, CONFIDENCE)
        self.assertEqual(low, 0.0)
        self.assertAlmostEqual(high, 1 - 0.025 ** (1 / 11), places=9)  # the closed form for k = 0

    def test_published_values(self):
        self.assertEqual(rounded(stats.clopper_pearson(21, 23, CONFIDENCE)), (0.7196, 0.9893))
        self.assertEqual(rounded(stats.clopper_pearson(2, 10, CONFIDENCE)), (0.0252, 0.5561))

    def test_all_successes_reach_one(self):
        low, high = stats.clopper_pearson(11, 11, CONFIDENCE)
        self.assertEqual((round(low, 4), high), (0.7151, 1.0))

    def test_no_trials_no_interval(self):
        self.assertEqual(stats.clopper_pearson(0, 0, CONFIDENCE), (None, None))

    def test_k_outside_the_trials_is_an_error(self):
        with self.assertRaises(ValueError):
            stats.clopper_pearson(3, 2, CONFIDENCE)

    def test_the_binomial_tail_sums_to_one(self):
        self.assertAlmostEqual(stats.binomial_cdf(30, 30, 0.3), 1.0)
        self.assertAlmostEqual(stats.binomial_cdf(0, 3, 0.5), 0.125)


class PrecisionTest(unittest.TestCase):
    def test_note_21s_example(self):
        self.assertAlmostEqual(stats.precision_at(0.9, 0.05, 0.01), 0.1538, places=4)
        self.assertAlmostEqual(stats.precision_at(0.9, 0.001, 0.01), 0.9009, places=4)

    def test_no_false_positives_is_all_agents(self):
        self.assertEqual(stats.precision_at(0.4, 0.0, 0.01), 1.0)

    def test_nothing_called_agent_or_an_unknown_rate_has_no_precision(self):
        self.assertIsNone(stats.precision_at(0.0, 0.0, 0.01))
        self.assertIsNone(stats.precision_at(None, 0.01, 0.01))


if __name__ == "__main__":
    unittest.main()
