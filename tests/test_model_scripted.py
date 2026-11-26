"""agentcake/detect/model.py and verdict.py: events a script dispatched, the page's own or an agent's.

    python3 -I -m unittest discover -s tests -v

A page's own script presses its buttons too: a carousel that turns itself every few seconds with element.click()
(tests/autoplay.py, as three browsers were measured sending it). Its clicks look like an agent's script clicks, so they
are no evidence either way, and a person who clicked around and then read the page while the carousel turned is a human,
not Human + agent at 99% (0.6.1). A script that imitates a device, a key, a button or the pointer, is still hard
evidence: pages do not fake their visitors' input.
"""
import os
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]

import autoplay  # noqa: E402  (written from measured browser events: no recording)
import verdict_cases  # noqa: E402
from agentcake.detect import model, verdict  # noqa: E402
from test_model import ev, hand_clicks  # noqa: E402

AGENTISH = (verdict.AGENT, verdict.MIXED)


def judged(events):
    """(the behaviour model's verdict, the session's class) for raw events on this computer's AgentCake."""
    return (model.judge_session(events)["verdict"],
            verdict.judge(verdict_cases.evidence(mode="local"), raw=events)["class"])


class PageScriptTest(unittest.TestCase):
    """The page's own scripted clicks while a person is there, or nobody."""

    def test_a_person_who_sits_still_while_the_carousel_turns_is_a_human(self):
        for how in (autoplay.CLICK, autoplay.DISPATCH):
            self.assertEqual(judged(autoplay.still(how)), ("human", verdict.HUMAN), how)

    def test_the_carousel_turning_while_the_person_clicks_is_no_agent(self):
        for how in (autoplay.CLICK, autoplay.DISPATCH):
            self.assertEqual(judged(autoplay.interleaved(how)), ("human", verdict.HUMAN), how)

    def test_the_carousel_in_a_window_without_focus_is_no_agent(self):
        # the person reads in another window while the page's script goes on clicking
        self.assertEqual(judged(autoplay.still(hf=0)), ("human", verdict.HUMAN))

    def test_a_scripted_click_with_a_detail_and_a_place_shows_no_hand(self):
        # dispatchEvent(new MouseEvent("click", {detail: 1, clientX, clientY})) on the button's centre: no approach,
        # an aim at the centre and a screen position that jumped, were a hand behind it
        box = autoplay.NEXT["r"]
        centre = {"d": 1, "cx": box[0] + box[2] // 2, "cy": box[1] + box[3] // 2, "sx": 0, "sy": 0}
        self.assertEqual(judged(autoplay.still(autoplay.DISPATCH, **centre)), ("human", verdict.HUMAN))

    def test_a_page_nobody_touches_is_no_agent(self):
        behaviour, cls = judged(autoplay.nobody())
        self.assertNotIn(cls, AGENTISH)
        self.assertNotEqual(behaviour, "agent")

    def test_the_scripted_clicks_fire_no_rule(self):
        hits = model.judge_session(autoplay.still(hf=0))["evidence"]["rule_hits"]
        self.assertEqual(set(hits), {"many_moves_before_click", "click_off_centre"})  # the person's hand only


class AgentScriptTest(unittest.TestCase):
    """A script that imitates the device stays hard evidence of automation."""

    def test_keys_a_script_dispatched_are_an_agent(self):
        # an agent typing through script: a keydown, the field's input and a keyup per key, none trusted
        words = [e for k in range(3) for t in range(6)
                 for e in (ev(2000 + 9000 * k + 150 * t, "keydown", tr=0, kc="letter"),
                           ev(2001 + 9000 * k + 150 * t, "input", tr=0, it="insertText", len=t + 1),
                           ev(2002 + 9000 * k + 150 * t, "keyup", tr=0, kc="letter"))]
        result = model.judge_session(words)
        self.assertEqual(result["verdict"], "agent")
        self.assertEqual(result["evidence"]["rule_hits"]["untrusted"], 3)

    def test_a_press_a_script_dispatched_beside_a_hand_is_still_hard_evidence(self):
        # Selenium's script click, driven over MCP: a mouseup and a click it dispatched, among a hand's clicks
        pressed = [e for k in range(3) for e in (ev(30000 + 4000 * k, "mouseup", tr=0, cx=0, cy=0, d=1),
                                                 ev(30001 + 4000 * k, "click", tr=0, cx=0, cy=0, d=1))]
        result = model.judge_session(hand_clicks(3) + pressed)
        self.assertEqual(result["evidence"]["rule_hits"].get("untrusted"), 3)
        self.assertEqual(result["verdict"], "agent")


if __name__ == "__main__":
    unittest.main()
