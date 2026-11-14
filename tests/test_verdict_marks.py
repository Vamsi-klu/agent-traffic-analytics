"""The reasons a verdict gives for an agent product's indicator (agentcake.detect.verdict_marks).

    python3 -I -m unittest discover -s tests -p test_verdict_marks.py -v

One reason per turn span the timeline was given: when the indicator was on and that the actions in that time are the
agent's, with the mark's evidence grade; when the timeline judged the span's tail on its own evidence (held_to) and a
step there did not turn out the agent's, until when the actions are the agent's.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentcake.detect import markers, verdict_marks  # noqa: E402

WORKING = "claude-chrome.working"
START = 4000


def span(start, end, **more):
    return {"marker": WORKING, "product": "claude-chrome", "kind": "indicator", "from": start, "to": end, **more}


def step(t, who, kind="click"):
    return {"kind": kind, "t": t, "who": who}


def said(marks, actions=(), evidence=()):
    return verdict_marks.reasons({"marks": marks, "actions": list(actions), "evidence": list(evidence)}, START)


class IndicatorReasons(unittest.TestCase):
    def test_a_span_says_when_it_was_on_and_that_its_actions_are_the_agents(self):
        (reason,) = said([span(20000, 40000)], [step(25000, "agent"), step(45000, "human")])
        self.assertEqual((reason["id"], reason["value"]), ("behavior.indicator", [20000, 40000]))
        self.assertEqual(reason["facts"], {"marker": WORKING, "from_ms": 16000, "to_ms": 36000})
        self.assertEqual(reason["grade"], markers.load_table().markers[WORKING]["grade"])

    def test_a_tail_where_every_step_stayed_the_agents_says_the_same(self):
        (reason,) = said([span(20000, 40000, held_to=35100)], [step(25000, "agent"), step(45000, "human")])
        self.assertEqual(reason["id"], "behavior.indicator")

    def test_a_tail_with_a_step_not_the_agents_says_until_when_the_actions_are(self):
        steps = [step(25000, "agent"), step(37000, "human"), step(45000, "human")]
        (reason,) = said([span(20000, 40000, held_to=35100)], steps)
        self.assertEqual((reason["id"], reason["value"]), ("behavior.indicator-tail", [20000, 40000, 35100]))
        self.assertEqual(reason["facts"]["until_ms"], 31100)
        self.assertEqual(reason["text"], "Claude in Chrome was working from 0:16 to 0:36, so the actions until 0:31 are "
                                         "the agent's.")
        self.assertEqual(reason["grade"], markers.load_table().markers[WORKING]["grade"])

    def test_an_unsure_step_or_evidence_in_the_tail_counts_too(self):
        (unsure,) = said([span(20000, 40000, held_to=35100)], [step(37000, "unsure")])
        (moved,) = said([span(20000, 40000, held_to=35100)], evidence=[step(38000, "human", "move")])
        self.assertEqual((unsure["id"], moved["id"]), ("behavior.indicator-tail", "behavior.indicator-tail"))

    def test_spans_without_a_timeline_mark_give_no_reason(self):
        self.assertEqual(said([]), [])


if __name__ == "__main__":
    unittest.main()
