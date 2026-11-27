"""Reference cohort counts on fabricated verdict rows with known answers."""
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from agentcake import datafiles  # noqa: E402
from agentcake.evaluation import recorded_cohorts  # noqa: E402

COHORTS = datafiles.load("data/eval.json")["recorded"]["mode_cohorts"]
LIMIT_S = 3
ANTIGRAVITY = "antigravity-browser"


def row(id_, label, truth, mode, verdict, name=None):
    return {"id": id_, "group": label, "truth": {"class": truth, "mode": mode}, "class": verdict, "name": name}


class RecordedCohorts(unittest.TestCase):
    def test_browser_success_needs_the_joint_verdict_and_name(self):
        outcomes = [("agent", ANTIGRAVITY), ("mixed", ANTIGRAVITY), ("agent", "other-agent"),
                    ("human", ANTIGRAVITY), ("too_little_data", ANTIGRAVITY)]
        rows = [row(i, "agy-browser", "agent", "in-app", verdict, name)
                for i, (verdict, name) in enumerate(outcomes)]
        cells = recorded_cohorts.build(rows, {}, COHORTS, LIMIT_S)
        self.assertEqual(cells, [{"label": "agy-browser", "mode": "in-app", "truth": "agent", "sessions": 5,
                                  "classes": {"agent": 2, "mixed": 1, "human": 1, "too_little_data": 1},
                                  "expected_name": ANTIGRAVITY, "named_agent_or_mixed": 2}])
        self.assertIn("| agy-browser | in-app | agent | 5 | 2 | 1 | 1 | 2/5 (`antigravity-browser`) | — |",
                      recorded_cohorts.markdown(cells, LIMIT_S))

    def test_computer_use_separates_surfaces_and_keeps_unknown_modes_visible(self):
        rows = [row(i, "agy-cu", "agent", mode, "agent")
                for i, mode in enumerate(("in-app", "own-chrome", None, "external-devtools"))]
        rows += [row("legacy", "agy", "agent", "in-app", "agent", ANTIGRAVITY),
                 row("manual", "agy-human", "human", "in-app", "mixed", ANTIGRAVITY)]
        cells = recorded_cohorts.build(rows, {}, COHORTS, LIMIT_S)
        self.assertEqual([(c["label"], c["mode"], c["sessions"]) for c in cells],
                         [("agy-cu", None, 2), ("agy-cu", "in-app", 1), ("agy-cu", "own-chrome", 1),
                          ("agy-human", "in-app", 1)])
        lines = recorded_cohorts.markdown(cells, LIMIT_S)
        self.assertIn("| agy-cu | unverified | agent | 2 | 2 | 0 | 0 | — | — |", lines)
        self.assertIn("| agy-human | in-app | human | 1 | 0 | 1 | 0 | — | — |", lines)

    def test_handoffs_count_misses_including_unscored_sessions(self):
        rows = [row(i, "agy-browser", "mixed", "in-app", verdict)
                for i, verdict in enumerate(("mixed", "mixed", "agent", "too_little_data"))]
        handoffs = {0: {"true_handoffs": 1, "verdict": {"handoff_errors_s": [2.0]}},
                    1: {"true_handoffs": 1, "verdict": {"handoff_errors_s": [5.0]}},
                    2: {"true_handoffs": 1, "verdict": {"handoff_errors_s": [None]}},
                    3: {"true_handoffs": 1, "verdict": None},
                    "legacy": {"true_handoffs": 1, "verdict": {"handoff_errors_s": [0.0]}}}
        cells = recorded_cohorts.build(rows, handoffs, COHORTS, LIMIT_S)
        result, = cells
        self.assertEqual(result["handoffs"], {"true": 4, "found": 2, "within_limit": 1})
        self.assertIn("| agy-browser | in-app | mixed | 4 | 1 | 2 | 1 | — | 2/4 (1) |",
                      recorded_cohorts.markdown(cells, LIMIT_S))


if __name__ == "__main__":
    unittest.main()
