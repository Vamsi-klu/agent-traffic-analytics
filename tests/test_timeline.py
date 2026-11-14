"""agentcake/detect/timeline.py: who did each action, the shares by action and the hand-offs.

    python3 -I -m unittest discover -s tests -v

The timeline is cake 0.3.4's per-action judge (kept as tests/judge_0_3_4.py), read from the raw-event format instead
of rrweb. The small cases document it; one case checks it against judge_0_3_4.judge on the same input, and the cases after it
pin what 0.4.0 changed. The cases on the lab's sessions and on PostHog replays are kept with that data, outside the published repository.
"""
import json
import math
import os
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]

import judge_0_3_4  # noqa: E402
from agentcake.detect import timeline  # noqa: E402

RRWEB_INCREMENTAL, MOUSE_MOVE, MOUSE_INTERACTION, INPUT, CLICK = 3, 1, 2, 5, 2


def ev(t, ty, **fields):
    return {"t": float(t), "ty": ty, "tr": 1, "hf": 1, "vs": 1, **fields}


MS_PER_TARGET_PX = 100  # jump_click()'s default target moves 1 px to the right per 100 ms of t


def jump_click(t, x=None, y=300):
    """How Claude in Chrome clicks: the pointer appears on the target and clicks a few ms later. By default each
    click's target is its own, further right the later the click: the same spot pressed again would repeat the
    click in place, which shows no approach."""
    x = 400 + int(t) // MS_PER_TARGET_PX if x is None else x
    return [ev(t - 5, "mousemove", cx=x, cy=y), ev(t, "click", cx=x, cy=y)]


def hand_click(t, x=400, y=300, moves=20, step_ms=50):
    """A hand on a mouse: a curved approach of `moves` moves, then the click."""
    out = [ev(t - (moves - k) * step_ms, "mousemove", cx=x - 3 * (moves - k), cy=y - (moves - k) ** 2 % 17)
           for k in range(moves)]
    return out + [ev(t, "click", cx=x, cy=y)]


def to_rrweb(events):
    """Raw events -> the minimal rrweb that 0.3.4's judge reads (one position per move, time offsets 0)."""
    out = []
    for e in events:
        if e["ty"] == "mousemove":
            data = {"source": MOUSE_MOVE, "positions": [{"x": e["cx"], "y": e["cy"], "timeOffset": 0}]}
        elif e["ty"] == "click":
            data = {"source": MOUSE_INTERACTION, "type": CLICK, "x": e["cx"], "y": e["cy"]}
        elif e["ty"] == "input":
            data = {"source": INPUT, "text": "*"}
        else:
            continue
        out.append({"type": RRWEB_INCREMENTAL, "timestamp": e["t"], "data": data})
    return out


def as_0_3_4():
    """The packaged parameters with 0.3.4's scoring: a click without any pointer position still reads as a jump."""
    params = json.loads(json.dumps(timeline.load_params()))
    params["timeline"]["no_pointer_no_evidence"] = False
    return params


def majority(shares):
    """0.3.4's session verdict from the shares: the largest rounded percentage, human before agent before unsure."""
    pct = {who: round(100 * share) for who, share in shares.items()}
    return max(("human", "agent", "unsure"), key=lambda who: pct[who])


def agent_then_human(agent_clicks=5, human_clicks=5, gap_ms=6000):
    """The agent's jump clicks, then a hand's clicks; the hand-off is the person's first click (their first
    action), a second after their pointer began to move towards it."""
    events, t = [], 1000
    for _ in range(agent_clicks):
        t += gap_ms
        events += jump_click(t)
    handoff = t + gap_ms
    for _ in range(human_clicks):
        t += gap_ms
        events += hand_click(t)
    return events, handoff



class ActionTest(unittest.TestCase):
    def test_clicks_and_inputs_are_actions_and_nothing_else_is(self):
        events = [ev(0, "mousemove", cx=1, cy=1), ev(100, "scroll"), ev(200, "wheel"), ev(300, "keydown"),
                  ev(400, "click", cx=1, cy=1), ev(500, "dblclick", cx=1, cy=1), ev(4000, "input", it="insertText")]
        self.assertEqual([(a["kind"], a["t"]) for a in timeline.actions(events)], [("click", 400), ("input", 4000)])

    def test_inputs_closer_than_the_merge_gap_are_one_action_timed_at_the_last_one(self):
        events = [ev(t, "input") for t in (0, 500, 1400, 3000)]
        self.assertEqual([a["t"] for a in timeline.actions(events)], [1400, 3000])

    def test_the_pause_after_merged_inputs_counts_from_the_first_of_them_as_in_0_3_4(self):
        events = [ev(t, "input") for t in (0, 500, 1400, 3000)]
        self.assertEqual(timeline.actions(events)[1]["features"]["pause_s"], 3.0)

    def test_the_first_pause_counts_from_the_session_start(self):
        (action,) = timeline.actions(jump_click(5000), session_start=2000)
        self.assertEqual(action["features"]["pause_s"], 3.0)

    def test_without_a_session_start_the_first_event_starts_the_session(self):
        (action,) = timeline.actions([ev(1000, "focus")] + jump_click(5000))
        self.assertEqual(action["features"]["pause_s"], 4.0)

    def test_only_mousemoves_are_pointer_moves(self):
        events = [ev(4000 + k, "pointermove", cx=k, cy=k) for k in range(10)] + [ev(4100, "click", cx=1, cy=1)]
        self.assertEqual(timeline.actions(events)[0]["features"]["moves_before_act"], 0)

    def test_a_jump_to_the_target_scores_as_an_agent(self):
        (action,) = timeline.actions(jump_click(5000), session_start=0)
        self.assertGreater(timeline.p_agent(action["features"]), 0.9)

    def test_a_curved_approach_scores_as_a_human(self):
        (action,) = timeline.actions(hand_click(5000), session_start=0)
        self.assertLess(timeline.p_agent(action["features"]), 0.1)

    def test_features_are_capped(self):
        events = [ev(k * 10, "mousemove", cx=k * 7 % 50, cy=k * 3 % 40) for k in range(200)] + \
                 [ev(1995, "click", cx=1, cy=1)]
        features = timeline.actions(events, session_start=0)[0]["features"]
        self.assertEqual((features["moves_per_s"], features["moves_before_act"]), (20, 30))

    def test_an_action_starts_where_the_activity_leading_up_to_it_starts(self):
        events = [ev(0, "click", cx=1, cy=1), ev(5000, "scroll"), ev(6500, "mousemove", cx=5, cy=5),
                  ev(7000, "click", cx=5, cy=5)]
        self.assertEqual(timeline.actions(events)[1]["start"], 5000)

    def test_a_pause_longer_than_the_approach_pause_ends_the_approach(self):
        events = [ev(0, "click", cx=1, cy=1), ev(2000, "mousemove", cx=2, cy=2), ev(4500, "mousemove", cx=5, cy=5),
                  ev(5000, "click", cx=5, cy=5)]
        self.assertEqual(timeline.actions(events)[1]["start"], 4500)

    def test_an_action_with_nothing_leading_up_to_it_starts_at_its_first_own_event(self):
        events = [ev(t, "input") for t in (1000, 1500, 2000)]
        (action,) = timeline.actions(events)
        self.assertEqual((action["start"], action["first"], action["t"]), (1000, 1000, 2000))


class NoPointerTest(unittest.TestCase):
    """An action with no pointer position before it gets no pointer evidence (the missing-data variant)."""

    WITHOUT_POINTER = {"moves_per_s": 0.0, "moves_before_act": 0, "straight": 1.0, "pause_s": 4.0, "no_move_act": 1.0}

    def test_no_position_takes_the_jump_and_the_straight_path_out(self):
        expected = timeline.p_agent(dict(self.WITHOUT_POINTER, straight=0.0, no_move_act=0.0), as_0_3_4())
        self.assertEqual(timeline.p_agent(self.WITHOUT_POINTER), expected)

    def test_one_position_where_the_click_lands_is_still_a_jump(self):
        jumped = dict(self.WITHOUT_POINTER, moves_before_act=1, moves_per_s=0.25)
        self.assertEqual(timeline.p_agent(jumped), timeline.p_agent(jumped, as_0_3_4()))

    def test_a_click_no_mouse_made_has_no_pointer_evidence(self):
        # the move just before a click the keyboard, a finger or a pen made says nothing about it
        by_mouse = timeline.actions(jump_click(1000))[0]
        for made_by in ({"d": 0}, {"d": 1, "pt": "touch"}, {"d": 1, "pt": "pen"}):
            act = timeline.actions([ev(995, "mousemove", cx=400, cy=300),
                                    ev(1000, "click", cx=400, cy=300, **made_by)])[0]
            self.assertEqual((act["features"]["by_mouse"], by_mouse["features"]["by_mouse"]), (0.0, 1.0))
            self.assertLess(timeline.p_agent(act["features"]), timeline.p_agent(by_mouse["features"]))

    def test_a_click_again_in_place_has_no_pointer_evidence(self):
        # the pointer rested on the spot it had clicked: its one jittered move is no jump onto a target
        def second(x):
            return timeline.actions(hand_click(1000) + [ev(3700, "mousemove", cx=x, cy=301),
                                                        ev(4000, "click", cx=x, cy=300)])[1]
        again, jumped = second(401), second(480)
        self.assertEqual((again["features"]["in_place"], jumped["features"]["in_place"]), (1.0, 0.0))
        self.assertEqual(timeline.p_agent(again["features"]),
                         timeline.p_agent(dict(again["features"], no_move_act=0.0, straight=0.0)))
        self.assertLess(timeline.p_agent(again["features"]), timeline.p_agent(jumped["features"]))

    def test_0_3_4_read_no_position_as_a_jump(self):
        self.assertGreater(timeline.p_agent(self.WITHOUT_POINTER, as_0_3_4()),
                           timeline.p_agent(self.WITHOUT_POINTER) + 0.1)


class SmoothTest(unittest.TestCase):
    HMM = {"switch": 0.05, "prior": 0.5, "temper": 0.7, "clamp": 0}

    def test_a_lone_doubtful_action_follows_its_neighbours(self):
        smoothed = timeline.smooth([0.9, 0.9, 0.5, 0.9, 0.9], self.HMM)
        self.assertGreater(smoothed[2], 0.65)

    def test_no_scores_give_no_posteriors(self):
        self.assertEqual(timeline.smooth([], self.HMM), [])

    def test_a_clamp_keeps_certain_scores_finite(self):
        smoothed = timeline.smooth([1.0, 0.0], dict(self.HMM, clamp=1e-4))
        self.assertTrue(all(0 < p < 1 for p in smoothed))


class BuildTest(unittest.TestCase):
    def test_agent_then_human_gives_two_runs_and_one_handoff_at_the_humans_first_click(self):
        events, handoff = agent_then_human()
        result = timeline.build(events)
        self.assertEqual([(r["who"], r["n"]) for r in result["runs"]], [("agent", 5), ("human", 5)])
        self.assertEqual([(h["from"], h["to"], h["t"]) for h in result["handoffs"]], [("agent", "human", handoff)])
        human_run = result["runs"][1]
        self.assertEqual(human_run["start"], handoff - 20 * 50, "the run still begins where the hand began to move")

    def test_shares_are_by_action(self):
        events, _ = agent_then_human(agent_clicks=3, human_clicks=1)
        shares = timeline.build(events)["shares"]
        self.assertEqual(shares, {"human": 0.25, "agent": 0.75, "unsure": 0.0})

    def test_no_actions_is_all_unsure_with_no_handoff(self):
        result = timeline.build([ev(0, "scroll"), ev(100, "scroll")])
        self.assertEqual((result["shares"], result["runs"], result["handoffs"]),
                         ({"human": 0.0, "agent": 0.0, "unsure": 1.0}, [], []))

    def test_a_handoff_to_an_agent_starts_at_its_first_action_not_at_the_human_s_last_activity(self):
        events = []
        for t in (5000, 10000, 15000):
            events += hand_click(t)
        events += [ev(15500 + 250 * k, "scroll") for k in range(15)]  # the human reads on until 19000
        for t in (20500, 26000, 31000):
            events += jump_click(t)
        result = timeline.build(events)
        self.assertEqual([(r["who"], r["n"]) for r in result["runs"]], [("human", 3), ("agent", 3)])
        self.assertEqual([(h["from"], h["to"], h["t"]) for h in result["handoffs"]], [("human", "agent", 20500)])

    def test_evidence_shapes_the_runs_but_not_the_shares_and_movement_alone_hands_nothing_over(self):
        events, _ = agent_then_human(agent_clicks=3, human_clicks=0)
        glide = {"kind": "move", "t": 30000, "first": 30000, "start": 29000, "score": 0.02}
        result = timeline.build(events, evidence=[glide, dict(glide, t=32000, first=32000, start=31000)])
        self.assertEqual(result["shares"], {"human": 0.0, "agent": 1.0, "unsure": 0.0})
        self.assertEqual([(r["who"], r["n"]) for r in result["runs"]], [("agent", 3), ("human", 2)])
        self.assertEqual(result["handoffs"], [], "a hand that only moved the pointer took no action")
        self.assertEqual([e["who"] for e in result["evidence"]], ["human", "human"])
        scroll = {"kind": "scroll", "t": 30000, "first": 30000, "start": 29500, "score": 0.02}
        wheeled = timeline.build(events + [ev(30000, "wheel", dy=120)], evidence=[scroll, dict(scroll, t=32000)])
        self.assertEqual([(h["from"], h["to"], h["t"]) for h in wheeled["handoffs"]], [("agent", "human", 30000)])

    def test_an_unsure_run_between_two_actors_does_not_hide_the_handoff(self):
        runs = [{"who": "agent", "start": 0, "end": 10}, {"who": "unsure", "start": 20, "end": 30},
                {"who": "human", "start": 40, "end": 50}]
        self.assertEqual([(h["from"], h["to"], h["t"], h["after"]) for h in timeline.handoffs(runs)],
                         [("agent", "human", 40, 10)])

    def test_an_unsure_run_inside_one_actor_is_no_handoff(self):
        runs = [{"who": "agent", "start": 0, "end": 10}, {"who": "unsure", "start": 20, "end": 30},
                {"who": "agent", "start": 40, "end": 50}]
        self.assertEqual(timeline.handoffs(runs), [])

    def test_a_scroll_hands_over_only_when_the_visitors_own_input_caused_it(self):
        events = [e for t in (6000, 12000, 18000) for e in jump_click(t)] + \
            [e for t in (24000, 30000, 36000) for e in hand_click(t)]
        page_made = timeline.build(sorted(events + [ev(23500, "scroll", y=200)], key=lambda e: e["t"]))
        self.assertEqual([h["t"] for h in page_made["handoffs"]], [24000], "the page scrolled itself: the click")
        caused = events + [ev(23400, "pointerdown", pt="mouse"), ev(23500, "scroll", y=200)]
        dragged = timeline.build(sorted(caused, key=lambda e: e["t"]))
        self.assertEqual([h["t"] for h in dragged["handoffs"]], [23500], "the person's pointer moved the page")

    def test_the_parameters_come_from_the_data_file(self):
        params = timeline.load_params()
        events, _ = agent_then_human()
        everyone_unsure = json.loads(json.dumps(params))
        everyone_unsure["timeline"]["labels"] = {"human_max": 0.0, "agent_min": 1.0}
        self.assertEqual(timeline.build(events, everyone_unsure)["shares"]["unsure"], 1.0)
        self.assertEqual(timeline.build(events)["shares"]["unsure"], 0.0)

    def test_the_scores_are_0_3_4_judges_on_the_same_input(self):
        events, _ = agent_then_human(agent_clicks=4, human_clicks=4, gap_ms=3000)
        events += [ev(40000 + 300 * k, "input") for k in range(6)] + jump_click(52000) + hand_click(60000)
        rrweb = to_rrweb(sorted(events, key=lambda e: e["t"]))
        old_actions = judge_0_3_4.rr_actions(rrweb)
        new_actions = timeline.actions(events, as_0_3_4(), session_start=rrweb[0]["timestamp"])
        self.assertEqual([(a["kind"], a["t"]) for a in new_actions], [(a["kind"], a["t"]) for a in old_actions])
        for new, old in zip(new_actions, old_actions):
            for name, value in old["f"].items():
                self.assertTrue(math.isclose(new["features"][name], value, abs_tol=1e-12), name)
        _, _, verdict, pct, _ = judge_0_3_4.judge("", rrweb)
        result = timeline.build(events, as_0_3_4(), session_start=rrweb[0]["timestamp"])
        self.assertEqual({k: round(100 * v) for k, v in result["shares"].items()}, pct)
        self.assertEqual(majority(result["shares"]), verdict)


if __name__ == "__main__":
    unittest.main()
