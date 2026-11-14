"""agentcake/detect/model.py: the whole session's verdict, the main model's missing variant.

    python3 -I -m unittest discover -s tests -v

The small cases document the rules, the fallback, "too little data" and the interface the verdict reads. The cases on the
lab's 26 sessions and on PostHog replays are kept with that data, outside the published repository.
"""
import json
import math
import os
import socket
import sys
import unittest
from unittest import mock

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]

from agentcake.detect import features, model, timeline  # noqa: E402

NO_EVIDENCE = dict.fromkeys(features.FEATURES)


def ev(t, ty, **fields):
    return {"t": float(t), "ty": ty, "tr": 1, "hf": 1, "vs": 1, **fields}


def sigmoid(z):
    return 1 / (1 + math.exp(-z))


TARGET_STEP_PX = 120  # jump_clicks()' targets side by side, 100 px wide


def jump_clicks(n, gap_ms=5000, t0=1000):
    """Claude in Chrome: one move onto the target, a click a few ms later, centred on its box. Each click is on a
    target of its own: the same spot pressed again would repeat the click in place, which shows no approach."""
    out = []
    for k in range(n):
        t, x = t0 + k * gap_ms, 400 + TARGET_STEP_PX * k
        out += [ev(t - 5, "mousemove", cx=x, cy=300),
                ev(t, "click", cx=x, cy=300, d=1, pt="mouse", r=[x - 50, 280, 100, 40])]
    return out


def hand_clicks(n, gap_ms=5000, t0=1000):
    """A hand: 20 curved moves 50 ms apart before each click, off the centre of its box."""
    out = []
    for k in range(n):
        t = t0 + k * gap_ms
        out += [ev(t - (20 - j) * 50, "mousemove", cx=300 + 5 * j, cy=250 + (j * j) % 23) for j in range(20)]
        out.append(ev(t, "click", cx=395, cy=290, d=1, pt="mouse", r=[350, 280, 100, 40]))
    return out


def clicks_in_place(n, t0, gap_ms=800):
    """A person paging through pictures: n more clicks on the spot hand_clicks() pressed, the pointer at rest."""
    return [ev(t0 + k * gap_ms, "click", cx=395, cy=290, d=1, pt="mouse", r=[350, 280, 100, 40]) for k in range(n)]


def even_keys(t0, n=4, gap_ms=100):
    """A short word typed in one go, its keys evenly apart."""
    return [ev(t0 + k * gap_ms, "keydown", kc="letter") for k in range(n)]


def straight_glides_and_scrolls(n, t0=1000):
    """Mouse glides (10 straight moves 50 ms apart, no click) and wheel-less scrolls: no rule has anything to say."""
    out = []
    for k in range(n):
        t = t0 + k * 6000
        out += [ev(t + 50 * j, "mousemove", cx=100 + 10 * j, cy=100) for j in range(10)]
        out.append(ev(t + 3000, "scroll"))
    return out


KEY_GAPS_MS = (210, 340, 180, 290, 450, 230)  # a hand's typing: uneven gaps, none too short for a hand


def typing(t0):
    """A word typed by hand: keydown, input and keyup per key, the keydowns KEY_GAPS_MS apart."""
    out, t = [], t0
    for gap in KEY_GAPS_MS:
        t += gap
        out += [ev(t, "keydown", kc="letter"), ev(t + 5, "input", it="insertText", len=1),
                ev(t + 90, "keyup", kc="letter")]
    return out


def tap(t, pointer="touch", x=200, y=300):
    """A finger (or a pen) tapping a field: its pointer events, the touch events and the mousemove, mousedown, mouseup
    and click a browser adds after a tap for pages written for a mouse, all at the tapped spot (Chrome's click names
    the pointer that made it)."""
    return [ev(t, "pointerdown", cx=x, cy=y, pt=pointer), ev(t, "touchstart"),
            ev(t + 80, "pointerup", cx=x, cy=y, pt=pointer), ev(t + 80, "touchend"),
            ev(t + 85, "mousemove", cx=x, cy=y), ev(t + 85, "mousedown", cx=x, cy=y),
            ev(t + 86, "mouseup", cx=x, cy=y), ev(t + 87, "click", cx=x, cy=y, d=1, pt=pointer)]


def taps_and_typing(n, pointer="touch"):
    """A phone the environment layer did not flag: tap a field, type into it, n times."""
    out = []
    for k in range(n):
        t = 1000 + k * 8000
        out += tap(t, pointer) + typing(t + 500)
    return out


def scrolls_and_typing():
    """Experiment 2's reading of a touch capture (motion-attestation): typing and page scrolls, no mouse event at all
    (the capture's touch points have no cake event)."""
    return typing(1000) + [ev(9000, "scroll"), ev(9100, "scroll")] + typing(16000)


class RuleTest(unittest.TestCase):
    def test_a_segment_where_no_rule_fires_scores_one_half(self):
        self.assertEqual(model.rule_score(NO_EVIDENCE), (0.5, []))

    def test_rules_add_their_weights_and_name_themselves(self):
        p, fired = model.rule_score(dict(NO_EVIDENCE, moves_before_click=1, click_center_norm=0.01))
        self.assertAlmostEqual(p, sigmoid(1.6 + 1.4), places=12)
        self.assertEqual(fired, ["few_moves_before_click", "click_at_centre"])

    def test_human_evidence_pulls_the_score_down(self):
        p, fired = model.rule_score(dict(NO_EVIDENCE, moves_before_click=12, n_move=20, straightness=0.6))
        self.assertAlmostEqual(p, sigmoid(-1.6 - 1.2), places=12)
        self.assertEqual(fired, ["many_moves_before_click", "curved_moves"])

    def test_a_feature_with_no_data_never_fires_its_rule(self):
        self.assertEqual(model.rule_score(dict(NO_EVIDENCE, keys_n=5))[1], [])

    def test_a_missing_wheel_count_reads_as_zero_as_in_the_lab(self):
        self.assertEqual(model.rule_score(dict(NO_EVIDENCE, scroll_no_wheel=1.0))[1], ["scroll_without_wheel"])

    def test_even_typing_needs_nine_keys_unless_it_is_very_even(self):
        # the lab's spread (< 0.15) from 9 keys on (agent-detector's uniform typing: 8 gaps), and
        # under 9 keys only a spread below 0.08 (bot-signal's linear typing). The clean humans' typing segments this
        # fires on went from 9 to 5; every lab agent segment fires as before.
        def fired(keys, spread):
            return model.rule_score(dict(NO_EVIDENCE, keys_n=keys, key_iv_cv=spread))[1]
        self.assertEqual(fired(3, 0.10), [])
        self.assertEqual(fired(8, 0.10), [])
        self.assertEqual(fired(3, 0.05), ["metronome_typing_short"])
        self.assertEqual(fired(9, 0.10), ["metronome_typing"])
        self.assertEqual(fired(12, 0.05), ["metronome_typing"])  # the two never fire together

    def test_the_rules_come_from_the_data_file(self):
        params = json.loads(json.dumps(model.load_params()))
        for rule in params["rules"]["list"]:
            rule["weight"] = 0.0
        self.assertEqual(model.rule_score(dict(NO_EVIDENCE, moves_before_click=1), params)[0], 0.5)


class FallbackTest(unittest.TestCase):
    def test_the_active_move_rate_counts_time_inside_movement_bursts_only(self):
        moves = [ev(t, "mousemove", cx=t, cy=0) for t in (0, 10, 20, 1020, 1030)]
        self.assertEqual(model.active_move_rate(moves), 5 / 0.05)

    def test_fewer_than_two_moves_give_no_rate(self):
        self.assertIsNone(model.active_move_rate([ev(0, "mousemove", cx=0, cy=0)]))
        self.assertIsNone(model.active_move_rate([]))

    def test_moves_that_never_form_a_burst_give_a_rate_of_zero(self):
        moves = [ev(t, "mousemove", cx=t, cy=0) for t in (0, 500, 1000)]
        self.assertEqual(model.active_move_rate(moves), 0.0)

    def test_a_click_with_no_move_before_it_is_a_teleport(self):
        self.assertEqual(model.teleport_click_share([ev(0, "click", cx=5, cy=5)]), 1.0)

    def test_a_click_right_after_a_long_jump_is_a_teleport(self):
        events = [ev(0, "mousemove", cx=0, cy=0), ev(30, "mousemove", cx=500, cy=0), ev(80, "click", cx=500, cy=0)]
        self.assertEqual(model.teleport_click_share(events), 1.0)

    def test_a_click_after_a_steady_approach_is_no_teleport(self):
        events = [ev(10 * k, "mousemove", cx=5 * k, cy=0) for k in range(20)] + [ev(250, "click", cx=95, cy=0)]
        self.assertEqual(model.teleport_click_share(events), 0.0)

    def test_a_click_the_keyboard_made_is_no_teleport(self):
        # Enter or Space on a button clicks with detail 0, the pointer anywhere
        self.assertIsNone(model.teleport_click_share([ev(0, "click", cx=5, cy=5, d=0)]))

    def test_a_tapped_click_is_no_teleport(self):
        # a tap's first click has no move before it but the one the browser adds at the spot
        for pointer in ("touch", "pen"):
            self.assertIsNone(model.teleport_click_share(tap(0, pointer)), pointer)

    def test_a_click_again_in_place_is_no_teleport_of_its_own(self):
        # the jump before the first click is the only one: a label's click on its input and a second press on the
        # same spot came with no pointer movement
        jump = [ev(0, "mousemove", cx=0, cy=0), ev(30, "mousemove", cx=500, cy=0), ev(80, "click", cx=500, cy=0)]
        label = [ev(80, "click", cx=500, cy=0)]
        again = [ev(1080, "click", cx=501, cy=1)]
        self.assertEqual(model.teleport_clicks(jump + label + again), [80.0])
        self.assertEqual(model.teleport_click_share(jump + label + again), 1.0)

    def test_no_clicks_no_teleport_share(self):
        self.assertIsNone(model.teleport_click_share([ev(0, "mousemove", cx=0, cy=0)]))

    def test_a_pointer_event_of_type_mouse_or_a_mouse_event_shows_a_mouse(self):
        self.assertTrue(model.mouse_pointer([ev(0, "pointermove", cx=1, cy=1, pt="mouse")]))
        self.assertTrue(model.mouse_pointer([ev(0, "mousemove", cx=1, cy=1)]))  # rrweb-only: no pointer type
        self.assertTrue(model.mouse_pointer([ev(0, "click", cx=1, cy=1, pt="")]))  # element.click(): no pointer
        self.assertTrue(model.mouse_pointer(tap(0, "touch") + [ev(500, "pointermove", cx=1, cy=1, pt="mouse")]))

    def test_after_a_touch_or_a_pen_the_browsers_mouse_events_show_no_mouse(self):
        for pointer in ("touch", "pen"):
            self.assertFalse(model.mouse_pointer(tap(0, pointer)), pointer)

    def test_no_mouse_event_at_all_shows_no_mouse(self):
        self.assertFalse(model.mouse_pointer(scrolls_and_typing()))
        self.assertFalse(model.mouse_pointer([]))


class VerdictTest(unittest.TestCase):
    def test_a_touch_device_is_too_little_data_and_no_model_runs(self):
        result = model.judge_session(jump_clicks(6), touch=True)
        self.assertEqual((result["verdict"], result["segments"], result["timeline"]), ("too_little_data", [], None))

    def test_fewer_action_segments_than_the_minimum_are_too_little_data(self):
        result = model.judge_session(jump_clicks(2))
        self.assertEqual((result["verdict"], result["n_actions"]), ("too_little_data", 2))

    def test_the_minimum_comes_from_the_parameters(self):
        params = dict(model.load_params(), min_actions=2)
        self.assertEqual(model.judge_session(jump_clicks(2), params=params)["verdict"], "agent")

    def test_jumps_to_the_centre_of_each_target_are_an_agent(self):
        result = model.judge_session(jump_clicks(6))
        self.assertEqual((result["verdict"], result["confidence"]), ("agent", 1.0))
        self.assertIn("rules", result["basis"])

    def test_curved_approaches_off_centre_are_a_human(self):
        result = model.judge_session(hand_clicks(6))
        self.assertEqual((result["verdict"], result["confidence"], result["basis"]), ("human", 1.0, ["rules"]))

    def test_clicking_again_in_place_is_no_agent_evidence(self):
        # one approach, then the same spot pressed again and again: no approach to read, however many times; with
        # the even keys of one short word as a second kind of evidence, such people were judged agents
        events = hand_clicks(1) + clicks_in_place(10, t0=1800) + even_keys(12000)
        result = model.judge_session(events)
        self.assertEqual(result["verdict"], "human")
        self.assertNotIn("few_moves_before_click", result["evidence"]["rule_hits"])

    def test_no_evidence_either_way_is_unsure(self):
        result = model.judge_session(straight_glides_and_scrolls(4), raw_input=False)
        self.assertEqual((result["verdict"], result["basis"]), ("unsure", []))

    def test_a_pointer_that_never_glides_is_one_kind_of_evidence_and_not_enough_alone(self):
        events = straight_glides_and_scrolls(4)
        sparse = [dict(e, t=e["t"] + 100 * i) for i, e in enumerate(events)]  # moves now 150 ms apart
        result = model.judge_session(sparse, raw_input=False)
        self.assertEqual((result["verdict"], result["basis"]), ("unsure", []))
        self.assertEqual((result["evidence"]["active_move_rate"], result["evidence"]["one_kind"]), (0.0, "motion"))

    def test_a_touch_screen_the_environment_missed_is_no_agent_for_its_pointer_rate(self):
        # Experiment 2: motion-attestation's touch humans, judged as if no phone had been seen
        for pointer in ("touch", "pen"):
            result = model.judge_session(taps_and_typing(3, pointer))
            self.assertEqual((result["verdict"], result["basis"]), ("unsure", []), pointer)
            evidence = result["evidence"]
            self.assertEqual((evidence["active_move_rate"], evidence["mouse_pointer"]), (0.0, False))

    def test_a_session_without_any_mouse_event_is_no_agent_for_its_pointer_rate(self):
        result = model.judge_session(scrolls_and_typing())
        self.assertEqual((result["verdict"], result["basis"]), ("unsure", []))

    def test_a_mouse_that_barely_moved_is_no_agent_for_its_pointer_rate(self):
        # after agent-detector ("missing is not negative"): one move, then wheel and keys only,
        # leaves no movement to measure, which says nothing about who moved it
        result = model.judge_session([ev(500, "mousemove", cx=10, cy=10)] + scrolls_and_typing())
        self.assertIsNone(result["evidence"]["active_move_rate"])
        self.assertEqual((result["verdict"], result["basis"]), ("unsure", []))

    def test_raw_input_shows_what_rrweb_cannot(self):
        typing = [ev(1000 + 4000 * k, "input", it="insertText") for k in range(4)]
        events = hand_clicks(1, t0=500) + typing
        self.assertEqual(model.judge_session(events, raw_input=True)["segments"][1]["rules"],
                         ["input_without_keydown"])
        self.assertEqual(model.judge_session(events, raw_input=False)["segments"][1]["rules"], [])

    def test_confidence_is_the_share_of_segments_behind_the_verdict(self):
        result = model.judge_session(jump_clicks(3, t0=1000) + hand_clicks(3, t0=40000))
        self.assertEqual([seg["who"] for seg in result["segments"]], ["agent"] * 3 + ["human"] * 3)
        self.assertEqual((result["verdict"], result["confidence"]), ("agent", 0.5))

    def test_the_result_holds_what_s3_4_reads(self):
        result = model.judge_session(jump_clicks(3, t0=1000) + hand_clicks(3, t0=40000))
        self.assertEqual(set(result), {"verdict", "confidence", "basis", "evidence", "n_actions", "raw_input",
                                       "segments", "timeline"})
        self.assertEqual(set(result["timeline"]),
                         {"actions", "evidence", "runs", "shares", "handoffs", "marks", "checks"})
        self.assertEqual([(h["from"], h["to"]) for h in result["timeline"]["handoffs"]], [("agent", "human")])
        for seg in result["segments"]:
            self.assertEqual(set(seg), {"start", "end", "act_t", "kind", "p_rules", "p", "who", "rules"})

    def test_a_pointer_gliding_like_a_hand_is_human_evidence_on_the_timeline(self):
        result = model.judge_session(straight_glides_and_scrolls(4), raw_input=False)
        steps = result["timeline"]["evidence"]
        self.assertEqual([(s["kind"], s["rules"]) for s in steps], [("scroll", ["pointer_glides"])] * 4)
        self.assertAlmostEqual(steps[0]["score"], sigmoid(-1.6))

    def test_stretches_where_nothing_fires_stay_off_the_timeline(self):
        sparse = [dict(e, t=e["t"] + 100 * i) for i, e in enumerate(straight_glides_and_scrolls(4))]
        self.assertEqual(model.judge_session(sparse, raw_input=False)["timeline"]["evidence"], [])

    def test_movement_evidence_has_its_own_switch(self):
        params = json.loads(json.dumps(model.load_params()))
        params["timeline"]["movement_evidence"] = False
        self.assertEqual(model.judge_session(straight_glides_and_scrolls(4), raw_input=False,
                                             params=params)["timeline"]["evidence"], [])

    def test_with_both_switches_off_the_timeline_is_the_first_versions(self):
        events = jump_clicks(3, t0=1000) + straight_glides_and_scrolls(3, t0=20000) + hand_clicks(3, t0=40000)
        first_version = switches_off()
        result = model.judge_session(events, raw_input=False, params=first_version)
        expected = timeline.build(events, first_version)
        self.assertEqual((result["timeline"]["evidence"], result["timeline"]["shares"], result["timeline"]["handoffs"]),
                         ([], expected["shares"], expected["handoffs"]))
        self.assertEqual([a["p"] for a in result["timeline"]["actions"]], [a["p"] for a in expected["actions"]])

    def test_judging_makes_no_network_call(self):
        with mock.patch.object(socket, "socket", side_effect=AssertionError("network used")):
            self.assertEqual(model.judge_session(jump_clicks(4))["verdict"], "agent")


def switches_off():
    """The packaged parameters with both of the timeline's changes off: the first version (0.3.4's judge)."""
    params = json.loads(json.dumps(model.load_params()))
    params["timeline"]["no_pointer_no_evidence"] = False
    params["timeline"]["movement_evidence"] = False
    return params


if __name__ == "__main__":
    unittest.main()
