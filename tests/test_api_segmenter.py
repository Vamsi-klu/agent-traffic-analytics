"""agentcake/api/segmenter.py: which tab a session's replay shows while it follows the visitor (PostHog's segmenter).

    python3 -I -m unittest discover -s tests -p test_api_segmenter.py -v      (from the AgentCake folder)

The rules are PostHog's createSegments (common/replay-shared/src/segmenter.ts at f7221a4a): a tab's active stretch
ends after follow_activity_ms without activity, an active moment of another tab starts that tab's segment, a gap goes
to the tab before it while that tab's recording spans the gap's first moment (offset by 1 ms), else to a tab whose
recording does, else to none; the schedule covers every moment once, keeps the tab before a stretch of no tab, and
never switches for a single moment.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from agentcake.api import answers, segmenter  # noqa: E402
from agentcake.api.segmenter import Event, Segment  # noqa: E402

QUIET = answers.numbers()["follow_activity_ms"]  # PostHog's ACTIVITY_THRESHOLD_MS


def active(tab, *times):
    return [Event(t, tab, True) for t in times]


def last(tab, t):
    """The last moment a tab's recording holds, no activity of its own."""
    return [Event(t, tab, False)]


class Segments(unittest.TestCase):
    def test_one_tab_acting_without_a_pause_is_one_active_segment(self):
        found = segmenter.segments(active("a", 0, 1000, 2000))
        self.assertEqual(found, [Segment("a", 0, 2000, True)])

    def test_a_pause_longer_than_the_threshold_starts_a_new_segment_and_the_gap_stays_on_the_tab(self):
        found = segmenter.segments(active("a", 0, 1000) + active("a", 1000 + QUIET + 1))
        self.assertEqual(found, [Segment("a", 0, 1000, True), Segment("a", 1000, 1000 + QUIET + 1, False),
                                 Segment("a", 1000 + QUIET + 1, 1000 + QUIET + 1, True)])

    def test_an_active_moment_of_another_tab_starts_its_segment(self):
        found = segmenter.segments(active("a", 0, 1000) + active("b", 1500, 2500) + last("a", 3000))
        self.assertEqual([(s.tab, s.start, s.end) for s in found if s.active], [("a", 0, 1000), ("b", 1500, 2500)])
        self.assertEqual(found[1], Segment("a", 1000, 1500, False))  # tab a's recording still spans the gap

    def test_a_quiet_moment_of_another_tab_does_not_switch_within_the_threshold(self):
        found = segmenter.segments(active("a", 0, 1000, 2000, 3000) + active("b", 500) + last("b", 1500)
                                   + last("b", 4000))
        self.assertIn(Segment("a", 1000, 3000, True), found)

    def test_the_moment_after_a_tabs_last_one_starts_a_new_segment(self):
        found = segmenter.segments(active("a", 0) + last("a", 400) + active("b", 0, 300, 600))
        self.assertEqual(found[-1], Segment("b", 600, 600, True))

    def test_a_gap_goes_to_the_tab_whose_recording_still_spans_it(self):
        # tab a closed at 1000, tab b opened at 5000 and stays open past the gap's first moment
        found = segmenter.segments(active("a", 0, 1000) + active("b", 900) + active("b", 5000, 6000))
        gap = next(s for s in found if s.start == 1000 and not s.active)
        self.assertEqual(gap.tab, "b")

    def test_a_gap_no_recording_spans_has_no_tab(self):
        found = segmenter.segments(active("a", 0, 1000) + active("b", 5000, 6000))
        self.assertEqual(found[1], Segment(None, 1000, 5000, False))

    def test_the_start_and_the_end_of_the_recording_are_stretches_of_no_tab(self):
        found = segmenter.segments(active("a", 1000, 2000), start=0, end=9000)
        self.assertEqual(found, [Segment(None, 0, 1000, False), Segment("a", 1000, 2000, True),
                                 Segment(None, 2001, 9000, False)])

    def test_events_in_any_order_are_put_in_time_order(self):
        self.assertEqual(segmenter.segments(list(reversed(active("a", 0, 1000, 2000)))),
                         segmenter.segments(active("a", 0, 1000, 2000)))


class Schedule(unittest.TestCase):
    def shown(self, events, start=None, end=None):
        return segmenter.schedule(segmenter.segments(events, start, end))

    def test_one_tab_is_shown_from_start_to_end(self):
        self.assertEqual(self.shown(active("a", 1000, 2000, 30_000), start=0, end=40_000), [("a", 0, 40_000)])

    def test_a_link_opened_in_a_new_tab_moves_the_replay_there_and_back_when_only_the_first_is_left(self):
        # the landing tab: a click at 6 s opens the demo in a new tab; the landing tab stays open until 727 s
        landing = active("landing", 0, 6000) + last("landing", 727_000)
        demo = active("demo", 7800, 120_000, 721_000)
        self.assertEqual(self.shown(landing + demo), [("landing", 0, 7800), ("demo", 7800, 721_000),
                                                      ("landing", 721_000, 727_000)])

    def test_two_tabs_acting_at_once_switch_at_each_active_moment_of_the_other(self):
        human = active("human", *range(0, 10_001, 1000))
        agent = active("agent", 2500, 6500)
        self.assertEqual(self.shown(human + agent), [("human", 0, 2500), ("agent", 2500, 3000),
                                                     ("human", 3000, 10_000)])

    def test_a_stretch_of_no_tab_keeps_the_tab_before_it(self):
        self.assertEqual(self.shown(active("a", 0, 1000) + active("b", 5000, 6000)),
                         [("a", 0, 5000), ("b", 5000, 6000)])

    def test_the_first_stretch_of_no_tab_takes_the_tab_after_it(self):
        self.assertEqual(self.shown(active("b", 1000, 2000), start=0, end=2000), [("b", 0, 2000)])

    def test_every_moment_is_covered_once(self):
        found = self.shown(active("a", 0, 3000, 9000) + active("b", 1000, 4000) + last("b", 20_000), start=0,
                           end=25_000)
        self.assertEqual(found[0][1], 0)
        self.assertEqual(found[-1][2], 25_000)
        for before, after in zip(found, found[1:]):
            self.assertEqual(before[2], after[1])
            self.assertNotEqual(before[0], after[0])
            self.assertLess(after[1], after[2])

    def test_no_events_and_no_range_is_no_schedule(self):
        self.assertEqual(self.shown([]), [])


if __name__ == "__main__":
    unittest.main()
