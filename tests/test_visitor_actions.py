"""agentcake/detect/visitor_actions.py: the visitor's own actions among a session's raw events, one definition for the
All actions list, the hand-offs and the evaluation's splices (agentcake/data/actions.json).

    python3 -I -m unittest discover -s tests -p test_visitor_actions.py -v

A click, a key, typed input and a wheel are actions; a scroll event is one only when the visitor's own input came at
most a second before it (a page that scrolls itself, or a script, makes none); a double click is its two clicks; a
touch, pointer movement and page events are none.
"""
import json
import os
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]

from agentcake.detect import visitor_actions  # noqa: E402


def ev(t, ty, **fields):
    return {"t": float(t), "ty": ty, **fields}


class VisitorActions(unittest.TestCase):
    def kinds(self, events, definition=None):
        return [(event["t"], kind) for event, kind in visitor_actions.found(events, definition)]

    def test_a_click_a_key_typing_and_a_wheel_are_actions_of_their_kind(self):
        events = [ev(1000, "click", s="#buy"), ev(2000, "keydown", kc="letter"), ev(2005, "input", len=1),
                  ev(3000, "change"), ev(4000, "contextmenu"), ev(5000, "wheel", dy=120)]
        self.assertEqual(self.kinds(events), [(1000, "click"), (2000, "key"), (2005, "type"), (3000, "type"),
                                              (4000, "click"), (5000, "scroll")])

    def test_a_scroll_is_an_action_only_when_the_visitors_own_input_caused_it(self):
        events = [ev(1000, "wheel", dy=120), ev(1050, "scroll", y=120), ev(5000, "scroll", y=0),
                  ev(9000, "keydown", kc="arrow"), ev(9300, "scroll", y=40), ev(15000, "touchstart"),
                  ev(15400, "scroll", y=300), ev(20000, "pointerdown"), ev(20900, "scroll", y=500)]
        scrolls = [t for t, kind in self.kinds(events) if kind == "scroll"]
        self.assertEqual(scrolls, [1000, 1050, 9300, 15400, 20900], "5000: the page scrolled itself back")

    def test_a_scroll_more_than_a_second_after_the_input_is_the_pages(self):
        events = [ev(1000, "wheel", dy=120), ev(2001, "scroll", y=120)]
        self.assertEqual(self.kinds(events), [(1000, "scroll")])

    def test_a_double_click_is_its_two_clicks_and_a_touch_is_no_action_of_its_own(self):
        events = [ev(1000, "click"), ev(1150, "click"), ev(1160, "dblclick"), ev(3000, "touchstart"),
                  ev(3080, "touchend"), ev(3100, "click")]
        self.assertEqual(self.kinds(events), [(1000, "click"), (1150, "click"), (3100, "click")])

    def test_pointer_movement_focus_and_page_events_are_none(self):
        events = [ev(1000, "mousemove", cx=1, cy=1), ev(1100, "pointermove"), ev(1200, "focus"), ev(1300, "keyup"),
                  ev(1400, "dom_add"), ev(1500, "visibility"), ev(1600, "mousedown"), ev(1700, "mouseup")]
        self.assertEqual(self.kinds(events), [])

    def test_the_events_come_back_in_time_order_and_their_times_with_them(self):
        events = [ev(3000, "click"), ev(1000, "keydown"), ev(2000, "input")]
        self.assertEqual(visitor_actions.times(events), [1000.0, 2000.0, 3000.0])

    def test_the_definition_comes_from_the_data_file(self):
        definition = json.loads(json.dumps(visitor_actions.load()))
        events = [ev(1000, "wheel", dy=120), ev(1500, "scroll", y=120)]
        self.assertEqual(len(self.kinds(events)), 2)
        definition["cause_ms"] = 100
        self.assertEqual(self.kinds(events, definition), [(1000, "scroll")])
        self.assertEqual(sorted(set(visitor_actions.load()["kinds"].values())), ["click", "key", "scroll", "type"])


if __name__ == "__main__":
    unittest.main()
