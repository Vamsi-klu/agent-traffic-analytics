"""agentcake/detect/rrweb_events.py: rrweb recordings turned into the raw-event format of the features.

    python3 -I -m unittest discover -s tests -v

The small cases document the mapping. The lab case converts the rrweb half of the 26 lab sessions and compares the
event counts with our PostHog study's (rr_vs_raw.json), which used the same conversion.
"""
import os
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]

import posthog_fixtures as ph  # noqa: E402
from agentcake.detect import rrweb_events  # noqa: E402

FULL_SNAPSHOT, INCREMENTAL, META = 2, 3, 4
MUTATION, MOUSE_MOVE, MOUSE_INTERACTION, SCROLL, VIEWPORT, INPUT, TOUCH_MOVE, DRAG = 0, 1, 2, 3, 4, 5, 6, 12
MOUSE_UP, MOUSE_DOWN, CLICK, CONTEXT_MENU, DBL_CLICK, FOCUS, BLUR, TOUCH_START, TOUCH_END = 0, 1, 2, 3, 4, 5, 6, 7, 9


def incremental(timestamp, source, **data):
    return {"type": INCREMENTAL, "timestamp": timestamp, "data": {"source": source, **data}}


def interaction(timestamp, kind, x=10, y=20, pointer=0):
    return incremental(timestamp, MOUSE_INTERACTION, type=kind, id=7, x=x, y=y, pointerType=pointer)


def convert(*events):
    return rrweb_events.events_from_rrweb(list(events))


class ConversionTest(unittest.TestCase):
    def test_mouse_positions_become_mousemoves_at_their_own_times(self):
        out = convert(incremental(1000, MOUSE_MOVE, positions=[{"x": 10.4, "y": 20.6, "id": 1, "timeOffset": -40},
                                                               {"x": 12, "y": 22, "id": 1, "timeOffset": 0}]))
        self.assertEqual([(e["ty"], e["t"], e["cx"], e["cy"]) for e in out],
                         [("mousemove", 960.0, 10, 21), ("mousemove", 1000.0, 12, 22)])

    def test_drags_are_mouse_moves_and_touch_moves_are_pointer_moves(self):
        pos = [{"x": 1, "y": 2, "id": 1, "timeOffset": 0}]
        out = convert(incremental(0, DRAG, positions=pos), incremental(5, TOUCH_MOVE, positions=pos))
        self.assertEqual([e["ty"] for e in out], ["mousemove", "pointermove"])

    def test_mouse_interactions_become_dom_events(self):
        kinds = [MOUSE_DOWN, MOUSE_UP, CLICK, DBL_CLICK, CONTEXT_MENU, TOUCH_START, TOUCH_END, FOCUS, BLUR]
        out = convert(*[interaction(i, kind) for i, kind in enumerate(kinds)])
        self.assertEqual([e["ty"] for e in out],
                         ["mousedown", "mouseup", "click", "dblclick", "contextmenu", "touchstart", "touchend"])

    def test_a_click_is_a_mouse_click_where_it_happened(self):
        (c,) = convert(interaction(0, CLICK, x=15.6, y=25))
        self.assertEqual((c["cx"], c["cy"], c["d"], c["pt"]), (16, 25, 1, "mouse"))

    def test_a_press_keeps_the_pointer_type_rrweb_names(self):
        pen, touch = 1, 2  # rrweb PointerTypes
        out = convert(interaction(0, MOUSE_DOWN, pointer=pen), interaction(1, CLICK, pointer=pen),
                      interaction(2, CLICK, pointer=touch))
        self.assertEqual([(e["ty"], e["pt"]) for e in out],
                         [("mousedown", "pen"), ("click", "pen"), ("click", "touch")])

    def test_a_click_rrweb_names_no_pointer_for_is_a_mouses(self):
        (c,) = convert(incremental(0, MOUSE_INTERACTION, type=CLICK, id=7, x=1, y=2))
        self.assertEqual(c["pt"], "mouse")

    def test_a_click_without_coordinates_gets_minus_one(self):
        (c,) = convert(incremental(0, MOUSE_INTERACTION, type=CLICK, id=7))
        self.assertEqual((c["cx"], c["cy"]), (-1, -1))

    def test_scrolls_and_inputs_keep_only_what_the_features_read(self):
        out = convert(incremental(0, SCROLL, id=1, x=0, y=300),
                      incremental(10, INPUT, id=2, text="*****", isChecked=False))
        self.assertEqual([(e["ty"], e.get("it"), e.get("len")) for e in out],
                         [("scroll", None, None), ("input", "insertText", 5)])

    def test_page_content_and_viewport_changes_are_not_input(self):
        out = convert({"type": FULL_SNAPSHOT, "timestamp": 0, "data": {"node": {}}}, incremental(1, MUTATION, adds=[]),
                      incremental(2, VIEWPORT, width=800, height=600),
                      {"type": META, "timestamp": 3,
                       "data": {"href": "https://example.test/", "width": 800, "height": 600}})
        self.assertEqual(out, [])

    def test_rrweb_cannot_see_trust_focus_visibility_or_movement(self):
        (m,) = convert(incremental(0, MOUSE_MOVE, positions=[{"x": 1, "y": 2, "id": 1, "timeOffset": 0}]))
        self.assertEqual((m["tr"], m["hf"], m["vs"], m["mx"], m["my"]), (1, 1, 1, None, None))

    def test_events_come_out_in_time_order(self):
        out = convert(interaction(1000, CLICK),
                      incremental(1010, MOUSE_MOVE, positions=[{"x": 1, "y": 1, "id": 1, "timeOffset": -50}]))
        self.assertEqual([(e["ty"], e["t"]) for e in out], [("mousemove", 960.0), ("click", 1000.0)])

    def test_rows_can_count_time_from_any_start(self):
        rows = rrweb_events.interaction_rows([interaction(1500, CLICK)], t0=1000)
        self.assertEqual(rows[0][:2], [500, "c"])


class RowsTest(unittest.TestCase):
    """Rows are also the layout of the PostHog study's downloads, where each row names its browser window
    (tests/posthog_fixtures.py makes them)."""

    def test_each_event_gets_the_page_of_its_window(self):
        rows = [[0, "M", "/pricing", None, "w1", 1280, 800, "example.test"], [10, "m", 5, 5, "w1"],
                [20, "c", CLICK, 5, 5, "w1", 0], [30, "M", "/docs", None, "w2", 1280, 800, "example.test"],
                [40, "m", 6, 6, "w2"], [50, "s", 0, 100, "w1", 3], [60, "i", 4, None, "w2", True]]
        out = rrweb_events.events_from_rows(rows)
        self.assertEqual([(e["ty"], e["pg"]) for e in out],
                         [("mousemove", "/pricing"), ("click", "/pricing"), ("mousemove", "/docs"),
                          ("scroll", "/pricing"), ("input", "/docs")])

    def test_posthog_moves_have_no_movement_values_and_count_as_trusted(self):
        (event,) = rrweb_events.events_from_rows([ph.page(0), ph.move(10, 5, 6)])
        self.assertEqual((event["ty"], event["cx"], event["cy"], event["mx"], event["my"]),
                         ("mousemove", 5, 6, None, None))
        self.assertEqual((event["tr"], event["hf"], event["vs"]), (1, 1, 1))

    def test_a_click_row_is_a_mouse_click_and_focus_is_dropped(self):
        rows = [ph.page(0), ph.click(5, kind=CLICK), ph.click(6, kind=FOCUS), ph.click(7, kind=MOUSE_DOWN)]
        events = rrweb_events.events_from_rows(rows)
        self.assertEqual([e["ty"] for e in events], ["click", "mousedown"])
        self.assertEqual((events[0]["d"], events[0]["pt"]), (1, "mouse"))

    def test_scroll_input_and_touch_rows(self):
        events = rrweb_events.events_from_rows([ph.page(0), ph.scroll(5), ph.typed(6, length=4), ph.touch_move(7)])
        self.assertEqual([e["ty"] for e in events], ["scroll", "input", "pointermove"])
        self.assertEqual((events[1]["it"], events[1]["len"]), ("insertText", 4))

    def test_snapshot_custom_and_viewport_rows_are_not_events(self):
        rows = [ph.page(0), [1, "F", None, None, "w1"], [2, "C", "$pageview", None, "w1"], [3, "v", 800, 600, "w1"]]
        self.assertEqual(rrweb_events.events_from_rows(rows), [])


if __name__ == "__main__":
    unittest.main()
