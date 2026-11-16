"""The behaviour timeline and an agent product's indicator (threshold A5): timeline.build(..., turns=...).

    python3 -I -m unittest discover -s tests -p test_timeline_turns.py -v

While an indicator said the agent was working (markers.turn_spans), every action is the agent's, whatever the model
makes of it; the actions outside are the model's, smoothed apart in the stretches between the spans, so that once the
indicator goes off what follows is judged on its own evidence; the hand-offs stay at the new side's first action (a
click, a key or typed input, a wheel) and carry the indicator's moment beside them. With no turns the timeline is what
it was. Through the verdict: a person, then Claude in Chrome with its indicator lit, then the person again is Mixed,
named, with both hand-offs and the indicator's span in the reasons; without the indicator the same session is Human,
since the extension's closed-shadow host alone is a soft trace that needs company. The stretches of the behaviour
model's session-level checks (timeline.build(..., checks=...)) go to the agent the same way, but they are no indicator:
no marks, no lit or off moment, and no step of their own where they hold input but no action.
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

    def test_hand_offs_stay_at_the_new_sides_first_action_with_the_indicators_moment_beside_them(self):
        events = clicks(hand_click, 5000, 10000) + clicks(jump_click, 15000, 20000, 25000) + \
            clicks(hand_click, 32000, 37000)
        result = timeline.build(events, turns=[turn(12000, 26000)])
        self.assertEqual([(r["who"], r["n"]) for r in result["runs"]], [("human", 2), ("agent", 3), ("human", 2)])
        to_agent, to_human = result["handoffs"]
        # the agent's first action once lit is its first click; the jump onto the target 5 ms before is no action
        self.assertEqual((to_agent["t"], to_agent["marker"]), (15000, {"id": WORKING, "t": 12000}))
        self.assertEqual(result["runs"][1]["start"], 14995, "the agent's run still begins at its first input")
        self.assertEqual((to_human["t"], to_human["marker"]), (32000, {"id": WORKING, "t": 26000}))
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
        self.assertEqual(result["handoffs"], [], "the agent only moved the pointer: no action, so no hand-off")
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


TAIL_MS = timeline.load_params()["timeline"]["indicator_tail"]["ms"]["claude-chrome"]


def went_off(start, end, marker=WORKING):
    """A span that ended with its mark going away while the page view went on (markers.turn_spans' went_off)."""
    return dict(turn(start, end, marker), went_off=True)


class IndicatorTail(unittest.TestCase):
    """The indicator stays lit for a while after the agent's last action (Claude in Chrome checks its work and writes
    its answer first): its last seconds say nothing about who acted, once the visitor acted after it went off."""

    def test_the_tail_is_seconds_the_agent_never_acted_in(self):
        self.assertGreater(TAIL_MS, 0)
        self.assertLess(TAIL_MS, 10000, "Claude in Chrome's shortest measured gap is 4.9 s")

    def test_a_product_whose_tail_was_never_measured_keeps_its_whole_span(self):
        events = clicks(jump_click, 10000, 15000) + clicks(hand_click, 27000, 29000) + clicks(hand_click, 35000, 40000)
        comet = dict(went_off(5000, 30000, "comet.overlay"), product="comet")
        result = timeline.build(events, turns=[comet])
        self.assertEqual([a["who"] for a in result["actions"]][:4], ["agent"] * 4)
        self.assertNotIn("held_to", result["marks"][0])

    def test_actions_in_the_tail_are_judged_with_what_follows_the_indicator(self):
        off = 30000
        human = (off - TAIL_MS + 1000, off - 1000)  # a hand's clicks under the lit indicator's last seconds
        events = clicks(jump_click, 10000, 15000, 20000) + clicks(hand_click, *human) + \
            clicks(hand_click, 35000, 40000)
        result = timeline.build(events, turns=[went_off(5000, off)])
        self.assertEqual([(a["t"], a["who"]) for a in result["actions"]],
                         [(10000, "agent"), (15000, "agent"), (20000, "agent"), (human[0], "human"),
                          (human[1], "human"), (35000, "human"), (40000, "human")])
        released = [a for a in result["actions"] if a["t"] in human]
        self.assertFalse([a for a in released if "marker" in a], "the indicator did not decide them")
        (to_human,) = result["handoffs"]
        self.assertEqual((to_human["from"], to_human["to"], to_human["t"]), ("agent", "human", human[0]))
        self.assertEqual(to_human["marker"], {"id": WORKING, "t": off}, "the indicator's own off stays beside it")
        self.assertEqual(result["marks"], [dict(went_off(5000, off), held_to=off - TAIL_MS)],
                         "the reasons still say when it was lit, and until when it decided")

    def test_the_agents_actions_before_the_tail_stay_the_agents(self):
        events = clicks(hand_click, 10000, 15000, 20000) + clicks(hand_click, 35000, 40000)
        result = timeline.build(events, turns=[went_off(5000, 30000)])
        self.assertEqual([a["who"] for a in result["actions"]][:3], ["agent"] * 3, "outside the tail: lit, the agent's")

    def test_with_nothing_done_after_the_indicator_its_tail_stays_the_agents(self):
        events = clicks(jump_click, 10000, 15000, 20000) + clicks(hand_click, 27000)
        result = timeline.build(events, turns=[went_off(5000, 30000)])
        self.assertEqual([a["who"] for a in result["actions"]], ["agent"] * 4, "no one took over after it")

    def test_leaving_the_page_is_no_end_of_the_turn(self):
        # the agent clicks a link: its marks go off as the page unloads and light again on the next page before it acts
        events = clicks(jump_click, 10000, 15000, 29000) + clicks(hand_click, 36000, 41000)
        result = timeline.build(events, turns=[went_off(5000, 29500), turn(31000, 45000)])
        self.assertEqual({a["who"] for a in result["actions"]}, {"agent"})

    def test_a_span_closed_by_the_page_view_or_cut_where_it_was_hidden_keeps_its_tail(self):
        events = clicks(jump_click, 10000, 15000) + clicks(hand_click, 27000, 29000) + clicks(hand_click, 35000, 40000)
        result = timeline.build(events, turns=[dict(turn(5000, 30000), went_off=False)])
        self.assertEqual([a["who"] for a in result["actions"]][:4], ["agent"] * 4)

    def test_a_span_shorter_than_the_tail_decides_nothing(self):
        moves = [ev(28000 + 40 * k, "mousemove", cx=300 + k, cy=200) for k in range(3)]
        events = clicks(hand_click, 10000, 15000, 20000) + moves + clicks(hand_click, 35000, 40000)
        result = timeline.build(events, turns=[went_off(27000, 30000)])
        self.assertEqual({a["who"] for a in result["actions"]}, {"human"})
        self.assertEqual([e for e in result["evidence"] if e["kind"] == "turn"], [], "no lit step of the agent's")


HOST = {"tag": "DIV", "nattr": 0, "attrs": [], "open_shadow": 0, "disp": "contents", "parent": "body", "how": "added"}
INDICATOR_TAIL_TEXT = "Claude in Chrome was active {span}. Actions up to {until} are counted as the agent's actions."
INDICATOR_TAIL_DETAIL = ("Claude in Chrome's “working” indicator appears on the screen {span}. The indicator stays on for a few "
                         "seconds after the agent stops. Actions after that point are classified by the behavior model.")


def hand_off_session(indicator=True):
    """A person clicks three times, Claude in Chrome three times (its indicator lit from 20 s to 37 s, going off 6 s
    after its last click, as it does: never sooner than its tail), the person three times again; the extension's host
    is on the page throughout."""
    events = clicks(hand_click, 5000, 10000, 15000) + clicks(jump_click, 25000, 28000, 31000) + \
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
        self.assertEqual(said["text"], "Claude in Chrome was active from 0:16 to 0:33. All actions during this time "
                                       "count as agent actions.")
        self.assertEqual(said["grade"], markers.load_table().markers[WORKING]["grade"])

    def test_without_the_indicator_the_host_alone_needs_company(self):
        evidence, events = hand_off_session(indicator=False)
        result = verdict.judge(evidence, raw=events)
        self.assertEqual((result["class"], result["handoffs"]), ("human", []))
        self.assertIn("env.soft-alone", [r["id"] for r in result["reasons"]])

    def test_a_human_who_took_over_before_the_indicator_went_off_is_told_apart_in_the_reasons(self):
        # the person clicks under the lit indicator's last seconds, then goes on after it went off at 40 s
        events = clicks(hand_click, 5000, 10000, 15000) + clicks(jump_click, 25000, 30000) + \
            clicks(hand_click, 37000, 39000, 45000, 50000)
        page = {"path": "/demo", "dom_add": [HOST],
                "markers": {"list": "2026-11-13", "from": 2000, "until": 60000, "hidden": [],
                            "spans": [turn(20000, 40000)]}}
        result = verdict.judge(evidence_builder.from_signals({"pages": [page]}, raw=events), raw=events)
        self.assertEqual(result["class"], "mixed")
        self.assertEqual([(h["from"], h["to"], h["t"]) for h in result["handoffs"]],
                         [("human", "agent", 25000), ("agent", "human", 37000)])
        reasons = {r["id"]: r for r in result["reasons"]}
        self.assertNotIn("behavior.indicator", reasons, "not every action while it was lit is the agent's")
        said = reasons["behavior.indicator-tail"]
        self.assertEqual(said["value"], [20000, 40000, 40000 - TAIL_MS])
        self.assertEqual(said["text"], INDICATOR_TAIL_TEXT.format(span="from 0:16 to 0:36", until="0:31"))
        self.assertEqual(said["detail"], INDICATOR_TAIL_DETAIL.format(span="from 0:16 to 0:36"))
        self.assertEqual(said["grade"], markers.load_table().markers[WORKING]["grade"])


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
