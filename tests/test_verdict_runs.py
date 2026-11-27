"""agentcake/detect/verdict_runs.py: which behaviour runs count as one side of a Human + agent session.

    python3 -I -m unittest discover -s tests -p test_verdict_runs.py -v

Made-up runs, timed in seconds: a human's run counts with enough steps over enough time, an agent's with enough clicks
or inputs of its own however fast, and its scrolling and pointer movement alone never; the reasons name each run of
the other side that does not count, with what it was counted in. With agent evidence, a long enough human run makes a
session Human + agent; where the name it rests on drives its own cloud browser (verdict.json "mixed" "handoff_only",
each one a cloud agent of the lists), only with the agent's part and a hand-off too, else it is the agent's, and a
reason says why. The whole verdict is in test_verdict.py (Muse and Grok Bot: test_verdict_browsers.py).
"""
import os
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]

from verdict_cases import run  # noqa: E402
from agentcake import datafiles  # noqa: E402
from agentcake.detect import timeline, verdict, verdict_runs  # noqa: E402

RULE = verdict.load_settings()["mixed"]
MUSE = {"id": "muse", "name": "Muse"}  # the list entries with_agent() reads: the name the class rests on
MANUS = {"id": "manus", "name": "Manus"}  # a cloud agent's name not in "handoff_only"
HUMAN = run("human", 61, 120, 15, 0.08)
ACTED = run("agent", 0, 60, 20, 0.97)  # 20 clicks or inputs of its own
ONE_CLICK = run("agent", 0, 60, 20, 0.97, acts=1)


class LongRuns(unittest.TestCase):
    def test_a_humans_run_needs_its_steps_over_its_time(self):
        counted = run("human", 0, 30, 3, 0.1)
        typed_too_fast = run("human", 0, 0.66, 12, 0.2)  # the lab's cic-03: Claude in Chrome typing
        too_few = run("human", 0, 30, 2, 0.1)
        self.assertEqual(verdict_runs.long_runs([counted, typed_too_fast, too_few], "human", RULE), [counted])

    def test_an_agents_run_needs_its_own_clicks_or_inputs_however_fast(self):
        fast = run("agent", 0, 1, 3, 0.9)
        scrolled_and_moved = run("agent", 0, 200, 12, 0.9, acts=0)
        two_clicks = run("agent", 0, 60, 6, 0.9, acts=2)
        found = verdict_runs.long_runs([fast, scrolled_and_moved, two_clicks], "agent", RULE)
        self.assertEqual(found, [fast])

    def test_the_minimum_comes_from_the_settings(self):
        two_clicks = run("agent", 0, 60, 6, 0.9, acts=2)
        self.assertEqual(verdict_runs.long_runs([two_clicks], "agent", dict(RULE, min_actions=2)), [two_clicks])


class ShortReasons(unittest.TestCase):
    def test_each_run_of_the_other_side_that_does_not_count_says_what_it_held(self):
        runs = [run("human", 0, 30, 6, 0.1), run("agent", 31, 90, 9, 0.9, acts=1), run("human", 91, 92, 1, 0.2)]
        said = verdict_runs.short_reasons(runs, "human", RULE)
        self.assertEqual([(r["id"], r["value"]) for r in said], [("behavior.short-run", 1)])
        self.assertIn("included 1 actions", said[0]["detail"])
        self.assertEqual(verdict_runs.short_reasons(runs, "agent", RULE)[0]["value"], 1, "the human's short run")


class BothSides(unittest.TestCase):
    def test_a_long_human_run_and_an_agents_part_by_its_runs_or_the_models_verdict(self):
        self.assertTrue(verdict_runs.both_sides([ACTED, HUMAN], False, RULE))
        self.assertTrue(verdict_runs.both_sides([HUMAN], True, RULE), "the model judged an agent")
        self.assertFalse(verdict_runs.both_sides([ONE_CLICK, HUMAN], False, RULE), "one click is no agent's part")
        self.assertFalse(verdict_runs.both_sides([ACTED, run("human", 61, 62, 15, 0.08)], True, RULE),
                         "a human's run too fast for a hand")


class WithAgent(unittest.TestCase):
    """The class of a session with agent evidence: with_agent(runs, handoffs, says_agent, named, rule, reasons)."""

    def judged(self, runs, named, says_agent=False):
        reasons = []
        return verdict_runs.with_agent(runs, timeline.handoffs(runs), says_agent, named, RULE, reasons), reasons

    def test_a_name_not_listed_with_a_human_run_alone_is_human_plus_agent(self):
        for named in (None, MANUS):
            with self.subTest(named=named):
                self.assertEqual(self.judged([HUMAN], named), ("mixed", []))
        self.assertEqual(self.judged([ACTED], MANUS), ("agent", []), "no human run long enough")

    def test_a_listed_name_with_a_human_run_and_no_hand_off_is_the_agents_with_one_reason(self):
        for says_agent in (False, True):
            with self.subTest(says_agent=says_agent):
                cls, reasons = self.judged([HUMAN], MUSE, says_agent)
                self.assertEqual((cls, [(r["id"], r["value"]) for r in reasons]),
                                 ("agent", [("behavior.humanlike-cloud-agent", "muse")]))
                self.assertIn("Muse", reasons[0]["text"])

    def test_a_listed_name_whose_agent_part_is_one_click_is_the_agents_despite_a_hand_off(self):
        runs = [ONE_CLICK, HUMAN]
        self.assertTrue(timeline.handoffs(runs))
        cls, reasons = self.judged(runs, MUSE)
        self.assertEqual((cls, len(reasons)), ("agent", 1))

    def test_a_listed_name_with_both_sides_and_a_hand_off_is_human_plus_agent(self):
        self.assertEqual(self.judged([ACTED, HUMAN], MUSE), ("mixed", []))
        self.assertEqual(self.judged([ONE_CLICK, HUMAN], MUSE, says_agent=True), ("mixed", []), "the model said agent")


class HandoffOnlyNames(unittest.TestCase):
    def test_every_name_listed_is_a_cloud_agent_of_the_lists_with_why(self):
        entries = {entry["id"]: entry for entry in datafiles.load("data/lists/names.json")["names"]}
        listed = RULE["handoff_only"]
        self.assertLessEqual({"muse", "grok-bot"}, set(listed))
        for list_id, why in listed.items():
            with self.subTest(list_id):
                self.assertIn(list_id, entries)
                self.assertEqual(entries[list_id]["kind"], "cloud-agent")
                self.assertTrue(why.strip())


if __name__ == "__main__":
    unittest.main()
