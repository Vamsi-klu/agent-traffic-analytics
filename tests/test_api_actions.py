"""The "All actions" list of GET /api/session/<id> and each actor's share of it (agentcake/api/actions.py), on the
actions agentcake/data/actions.json defines for the whole of AgentCake (detect/visitor_actions.py).

    python3 -I -m unittest discover -s tests -p test_api_actions.py -v      (from the AgentCake folder)

Sessions are written into a scratch CAKE_HOME as collect leaves them (cake.js's raw records and its page record). Keys
and typing on one field are one action, keys with no typing on a target another; a wheel and the scrolling it causes
are one scroll; a scroll the page made by itself is none, nor a touch of its own; a double click is its two clicks.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_api_pages import Recorded, T0  # noqa: E402
from agentcake import streams  # noqa: E402

PV = "pv1"


def rec(t, ty, **fields):
    """A made-up raw record at t ms after T0 (cake.js's field names)."""
    return {"t": t, "ty": ty, **fields}


class EveryAction(Recorded):
    def raw(self, sid, records):
        """A session of one page view holding these raw records ({"t" from T0, "ty", ...}), judged a human's."""
        stamped = [dict(record, t=T0 + record["t"]) for record in records]
        last = max(record["t"] for record in stamped)
        streams.append(self.con, sid, "env", [(T0, rec(T0, "page", n=1), PV)], last)
        streams.append(self.con, sid, "raw", [(record["t"], record, PV) for record in stamped], last)
        self.record(sid, "human", runs=[(T0, last, "human")], last_ms=last)
        return [action["what"] for action in self.detail(sid)["actions"] if not action["what"].startswith("Open ")]

    def test_keys_and_typing_on_one_field_are_one_action(self):
        typed = []
        for k in range(5):
            typed += [rec(1000 + 150 * k, "keydown", kc="letter", s="#email"),
                      rec(1005 + 150 * k, "input", len=k + 1, s="#email")]
        self.assertEqual(self.raw("typed", typed), ["Type in #email"])

    def test_a_key_with_no_typing_is_an_action_of_its_own_that_names_no_key(self):
        records = [rec(1000, "keydown", kc="enter", s="#search"),
                   rec(4000, "keydown", kc="tab", s="#email"),
                   rec(4005, "keydown", kc="tab", s="#email")]
        self.assertEqual(self.raw("keys", records), ["Key press on #search", "Key press on #email"])

    def test_a_wheel_and_the_scrolling_it_causes_are_one_scroll(self):
        records = [rec(1000, "wheel", dy=120, s="#main"), rec(1040, "scroll", y=120),
                   rec(1100, "wheel", dy=120, s="#main"), rec(1150, "scroll", y=240),
                   rec(1300, "scroll", y=300)]
        self.assertEqual(self.raw("wheeled", records), ["Scroll"])

    def test_a_scroll_the_page_made_by_itself_is_no_action_and_no_share(self):
        records = [rec(1000, "click", s="#buy"), rec(5000, "scroll", y=0),
                   rec(5100, "scroll", y=300)]
        self.assertEqual(self.raw("restored", records), ["Click #buy"])
        self.assertEqual(self.detail("restored")["session"]["share"], {"human": 100, "agent": 0, "unsure": 0})

    def test_a_double_click_is_its_two_clicks_and_a_touch_no_action_of_its_own(self):
        records = [rec(1000, "click", s="#size"), rec(1150, "click", s="#size"),
                   rec(1160, "dblclick", s="#size"), rec(3000, "touchstart"),
                   rec(3080, "touchend")]
        self.assertEqual(self.raw("clicked", records), ["Click #size", "Click #size"])


if __name__ == "__main__":
    unittest.main()
