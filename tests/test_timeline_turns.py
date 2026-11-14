"""The behaviour timeline and an agent product's indicator (plan step S3.7; GOAL A5): timeline.build(..., turns=...).

    python3 -I -m unittest discover -s tests -p test_timeline_turns.py -v

While an indicator said the agent was working (markers.turn_spans), every action is the agent's, whatever the model
makes of it; the actions outside are the model's, smoothed apart in the stretches between the spans, so that once the
indicator goes off what follows is judged on its own evidence; the hand-offs stay at the new side's first action and
carry the indicator's moment beside them. With no turns the timeline is what it was. Through the verdict: a person,
then Claude in Chrome with its indicator lit, then the person again is Mixed, named, with both hand-offs and the
indicator's span in the reasons; without the indicator the same session is Human, since the extension's
closed-shadow host alone is a soft trace that needs company. The stretches of the behaviour model's session-level checks
(timeline.build(..., checks=...)) go to the agent the same way, but they are no indicator: no marks, no lit or off
moment, and no step of their own where they hold input but no action.
"""
import os
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]

from agentcake.detect import markers, timeline, verdict  # noqa: E402
from agentcake.evaluation import evidence as evidence_builder  # noqa: E402
from test_timeline import ev, hand_click, jump_click  # noqa: E402

WORKING = "claude-chrome.working"
HMM = timeline.load_params()["timeline"]["hmm"]


def turn(start, end, marker=WORKING):
    return {"marker": marker, "product": "claude-chrome", "kind": "indicator", "from": start, "to": end}


def clicks(maker, *times):
    return [e for t in times for e in maker(t)]


class Turns(unittest.TestCase):
    def test_without_turns_the_timeline_is_what_it_was(self):
        events = clicks(jump_click, 6000, 12000, 18000) + clicks(hand_click, 24000, 30000)
        self.assertEqual(timeline.build(events, turns=()), timeline.build(events))
        self.assertEqual(timeline.build(events)["marks"], [])

    def test_actions_while_the_indicator_is_lit_are_the_agents_whatever_the_model_says(self):
        events = clicks(hand_click, 5000, 10000, 15000, 20000)  # a hand's clicks: the model says human
        result = timeline.build(events, turns=[turn(9000, 16000)])
        self.assertEqual([a["who"] for a in result["actions"]], ["human", "agent", "agent", "human"])
        lit = [a for a in result["actions"] if a["who"] == "agent"]
        self.assertEqual({(a["p"], a["marker"]) for a in lit}, {(1.0, WORKING)})
        self.assertNotIn("marker", result["actions"][0])

    def test_once_the_indicator_is_off_what_follows_is_judged_on_its_own_evidence(self):
        events = clicks(jump_click, 5000, 10000, 15000) + clicks(hand_click, 25000, 30000, 35000)
        result = timeline.build(events, turns=[turn(4000, 16000)])
        after = [a for a in result["actions"] if a["t"] > 16000]
        self.assertEqual([a["p"] for a in after], timeline.smooth([a["score"] for a in after], HMM))
        unlit = timeline.build(events)  # without the indicator, the agent's clicks pull the next ones its way
        self.assertNotEqual([a["p"] for a in unlit["actions"] if a["t"] > 16000], [a["p"] for a in after])

    def test_a_lit_span_with_no_action_still_separates_what_comes_before_and_after(self):
        events = clicks(hand_click, 5000, 10000, 30000, 35000)
        result = timeline.build(events, turns=[turn(15000, 25000)])
        before = [a for a in result["actions"] if a["t"] < 15000]
        after = [a for a in result["actions"] if a["t"] > 25000]
        self.assertEqual([a["p"] for a in before], timeline.smooth([a["score"] for a in before], HMM))
        self.assertEqual([a["p"] for a in after], timeline.smooth([a["score"] for a in after], HMM))

    def test_hand_offs_stay_at_the_new_sides_first_input_with_the_indicators_moment_beside_them(self):
        events = clicks(hand_click, 5000, 10000) + clicks(jump_click, 15000, 20000, 25000) + \
            clicks(hand_click, 32000, 37000)
        result = timeline.build(events, turns=[turn(12000, 26000)])
        self.assertEqual([(r["who"], r["n"]) for r in result["runs"]], [("human", 2), ("agent", 3), ("human", 2)])
        to_agent, to_human = result["handoffs"]
        # the agent's first input once lit: the jump onto its first target, 5 ms before the click
        self.assertEqual((to_agent["t"], to_agent["marker"]), (14995, {"id": WORKING, "t": 12000}))
        human_start = next(r["start"] for r in result["runs"][2:])
        self.assertEqual((to_human["t"], to_human["marker"]), (human_start, {"id": WORKING, "t": 26000}))
        self.assertEqual(result["marks"], [turn(12000, 26000)])

    def test_an_agent_that_scrolls_before_its_first_click_takes_over_at_its_first_scroll(self):
        scrolls = [ev(13000 + 500 * k, "wheel", dy=120) for k in range(6)]
        events = clicks(hand_click, 5000, 10000) + scrolls + clicks(jump_click, 20000, 25000, 30000)
        result = timeline.build(events, turns=[turn(12000, 31000)])
        self.assertEqual([(h["from"], h["to"], h["t"]) for h in result["handoffs"]], [("human", "agent", 13000)])
        before_lit = timeline.build(events + [ev(11000, "wheel", dy=120)], turns=[turn(12000, 31000)])
        self.assertEqual(before_lit["handoffs"][0]["t"], 13000, "an input before the indicator lit is not the agent's")

    def test_a_lit_span_with_input_but_no_action_is_one_step_of_the_agents(self):
        moves = [ev(21000 + 40 * k, "mousemove", cx=300 + k, cy=200) for k in range(3)]
        events = clicks(hand_click, 5000, 10000, 15000) + moves + clicks(hand_click, 30000, 35000, 40000)
        result = timeline.build(events, turns=[turn(20000, 22000)])
        (step,) = [e for e in result["evidence"] if e["kind"] == "turn"]
        self.assertEqual((step["t"], step["who"], step["marker"]), (21000, "agent", WORKING))
        self.assertEqual([(r["who"], r["n"]) for r in result["runs"]], [("human", 3), ("agent", 1), ("human", 3)])
        self.assertEqual([(h["from"], h["to"]) for h in result["handoffs"]], [("human", "agent"), ("agent", "human")])
        self.assertEqual(result["shares"]["agent"], 0.0, "a step, not an action: the shares count actions")

    def test_a_lit_span_with_no_input_at_all_adds_nothing(self):
        events = clicks(hand_click, 5000, 10000, 30000, 35000)
        result = timeline.build(events, turns=[turn(15000, 25000)])
        self.assertEqual([e for e in result["evidence"] if e["kind"] == "turn"], [])

    def test_a_hand_off_the_indicator_did_not_see_has_no_moment(self):
        events = clicks(jump_click, 5000, 10000, 15000) + clicks(hand_click, 25000, 30000, 35000)
        result = timeline.build(events, turns=[turn(40000, 50000)])  # lit after everything happened
        self.assertEqual([(h["from"], h["to"]) for h in result["handoffs"]], [("agent", "human")])
        self.assertNotIn("marker", result["handoffs"][0])

    def test_runs_and_actions_keep_what_they_held(self):
        events = clicks(hand_click, 5000) + clicks(jump_click, 15000, 20000)
        result = timeline.build(events, turns=[turn(12000, 22000)])
        agent_run = result["runs"][1]
        self.assertEqual((agent_run["start"], agent_run["end"], agent_run["n"], agent_run["p"]), (14995, 20000, 2, 1.0))
        self.assertEqual(result["shares"], {"human": 1 / 3, "agent": 2 / 3, "unsure": 0.0})

    def test_events_inside_a_span_that_are_not_actions_go_with_it(self):
        events = clicks(jump_click, 5000, 10000) + [ev(12000, "scroll")]
        stretch = {"kind": "scroll", "t": 12000, "first": 12000, "start": 11500, "score": 0.02}
        result = timeline.build(events, evidence=[stretch], turns=[turn(4000, 13000)])
        self.assertEqual([(e["who"], e["marker"]) for e in result["evidence"]], [("agent", WORKING)])


HOST = {"tag": "DIV", "nattr": 0, "attrs": [], "open_shadow": 0, "disp": "contents", "parent": "body", "how": "added"}


def hand_off_session(indicator=True):
    """A person clicks three times, Claude in Chrome three times (its indicator lit from 20 s to 37 s), the person
    three times again; the extension's host is on the page throughout."""
    events = clicks(hand_click, 5000, 10000, 15000) + clicks(jump_click, 25000, 30000, 35000) + \
        clicks(hand_click, 45000, 50000, 55000)
    page = {"path": "/demo", "dom_add": [HOST]}
    if indicator:
        page["markers"] = {"list": "2026-11-13", "from": 2000, "until": 60000, "hidden": [],
                           "spans": [turn(20000, 37000)]}
    return evidence_builder.from_signals({"pages": [page]}, raw=events), events


class ThroughTheVerdict(unittest.TestCase):
    def test_a_lit_indicator_between_a_persons_turns_is_mixed_with_both_hand_offs(self):
        evidence, events = hand_off_session()
        result = verdict.judge(evidence, raw=events)
        self.assertEqual((result["class"], result["name"]), ("mixed", "claude-chrome"))
        self.assertEqual([(h["from"], h["to"], h["marker"]["t"]) for h in result["handoffs"]],
                         [("human", "agent", 20000), ("agent", "human", 37000)])
        reasons = {r["id"]: r for r in result["reasons"]}
        self.assertIn("env.product.claude-chrome-indicator", reasons)
        said = reasons["behavior.indicator"]
        self.assertEqual(said["text"], "Claude in Chrome was working from 0:16 to 0:33, so the actions in that time "
                                       "are the agent's.")
        self.assertEqual(said["grade"], markers.load_table().markers[WORKING]["grade"])

    def test_without_the_indicator_the_host_alone_needs_company(self):
        evidence, events = hand_off_session(indicator=False)
        result = verdict.judge(evidence, raw=events)
        self.assertEqual((result["class"], result["handoffs"]), ("human", []))
        self.assertIn("env.soft-alone", [r["id"] for r in result["reasons"]])


def check(start, end, name="typing_cadence"):
    return {"check": name, "from": start, "to": end}


class Checks(unittest.TestCase):
    def test_actions_inside_a_checks_stretch_are_the_agents_and_it_makes_no_mark(self):
        events = clicks(hand_click, 5000, 10000, 15000, 20000)  # a hand's clicks: the model says human
        result = timeline.build(events, checks=[check(9000, 16000)])
        self.assertEqual([a["who"] for a in result["actions"]], ["human", "agent", "agent", "human"])
        self.assertEqual({(a["p"], a["check"]) for a in result["actions"] if a["who"] == "agent"},
                         {(1.0, "typing_cadence")})
        self.assertEqual((result["marks"], result["checks"]), ([], [check(9000, 16000)]))
        self.assertFalse([run for run in result["runs"] if "lit" in run or "off" in run])
        self.assertEqual([(h["from"], h["to"]) for h in result["handoffs"]], [("human", "agent"), ("agent", "human")])

    def test_a_stretch_with_input_but_no_action_adds_no_step(self):
        moves = [ev(21000 + 40 * k, "mousemove", cx=300 + k, cy=200) for k in range(3)]
        events = clicks(hand_click, 5000, 10000, 15000) + moves + clicks(hand_click, 30000, 35000, 40000)
        result = timeline.build(events, checks=[check(20000, 22000, "active_move_rate")])
        self.assertEqual([e for e in result["evidence"] if e["kind"] == "turn"], [])


if __name__ == "__main__":
    unittest.main()
