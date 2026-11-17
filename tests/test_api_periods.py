"""agentcake/api/periods.py: the date ranges and the wall-clock words, in this computer's timezone.

    python3 -I -m unittest discover -s tests -p test_api_periods.py -v      (from the AgentCake folder)

Each test fixes the timezone (America/Los_Angeles, which changes for daylight saving on 2026-11-01) and the clock.
"""
import os
import sys
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from agentcake.api import periods  # noqa: E402

HOUR = 3_600_000
# 2026-11-12 21:13 in Los Angeles (PST, UTC-8)
NOW = 1_794_546_780_000


class Periods(unittest.TestCase):
    def setUp(self):
        zone = mock.patch.dict(os.environ, {"TZ": "America/Los_Angeles"})
        zone.start()
        self.addCleanup(zone.stop)
        self.addCleanup(time.tzset)
        time.tzset()

    def local(self, *fields):
        return int(time.mktime(fields + (0, 0, -1)) * 1000)

    def test_a_range_starts_at_local_midnight(self):
        self.assertEqual(periods.window("today", NOW), (self.local(2026, 11, 12, 0, 0, 0), None))
        self.assertEqual(periods.window("7d", NOW), (self.local(2026, 11, 6, 0, 0, 0), None))
        self.assertEqual(periods.window("30d", NOW), (self.local(2026, 10, 14, 0, 0, 0), None))
        self.assertEqual(periods.window(None, NOW), (None, None))
        self.assertEqual(periods.window(periods.ALL_TIME, NOW), (None, None), "all time: every session")
        self.assertIn(periods.ALL_TIME, periods.range_keys())

    def test_thirty_days_back_crosses_the_change_of_daylight_saving_at_midnight(self):
        start, _ = periods.window("30d", NOW)
        self.assertEqual(time.localtime(start / 1000)[3:6], (0, 0, 0))

    def test_the_same_range_a_week_earlier(self):
        start, _ = periods.window("7d", NOW)
        self.assertEqual(periods.earlier(start, NOW, 7), (start - 7 * 24 * HOUR, NOW - 7 * 24 * HOUR))
        self.assertEqual(periods.earlier(None, NOW, 7), (None, NOW - 7 * 24 * HOUR))

    def test_days_are_weekdays_for_a_week_and_dates_beyond(self):
        week = periods.days(periods.window("7d", NOW)[0], NOW)
        self.assertEqual([label for _, label in week], ["Fri", "Sat", "Sun", "Mon", "Tue", "Wed", "Thu"])
        self.assertEqual(week[-1][0], "2026-11-12")
        month = periods.days(periods.window("30d", NOW)[0], NOW)
        self.assertEqual((len(month), month[0][1], month[-1][1]), (30, "Oct 14", "Nov 12"))

    def test_when_in_words(self):
        self.assertEqual(periods.when(self.local(2026, 11, 12, 9, 5, 0), NOW), "Today 09:05")
        self.assertEqual(periods.when(self.local(2026, 11, 11, 22, 4, 0), NOW), "Yesterday 22:04")
        self.assertEqual(periods.when(self.local(2026, 11, 9, 14, 0, 0), NOW), "Mon 14:00")
        self.assertEqual(periods.when(self.local(2026, 11, 3, 8, 30, 0), NOW), "Nov 3, 08:30")
        self.assertEqual(periods.when(self.local(2025, 12, 24, 8, 30, 0), NOW), "Dec 24, 2025")

    def test_today_by_hour_to_the_current_one(self):
        hours = periods.buckets("hour", periods.window("today", NOW)[0], NOW)
        self.assertEqual(len(hours), 22, "00:00 to 21:00")
        self.assertEqual((hours[0], hours[-1]), (("2026-11-12 00", "00:00"), ("2026-11-12 21", "21:00")))
        self.assertEqual(periods.interval_key("hour", self.local(2026, 11, 12, 21, 59, 0)), hours[-1][0])

    def test_the_hour_daylight_saving_repeats_is_one(self):
        end = self.local(2026, 11, 1, 23, 30, 0)  # 2026-11-01 has 25 hours in Los Angeles: 01:00 comes twice
        hours = periods.buckets("hour", periods.window("today", end)[0], end)
        self.assertEqual([label for _, label in hours], [f"{h:02d}:00" for h in range(24)])

    def test_the_current_hour_after_a_half_hour_change_of_daylight_saving_is_a_bucket(self):
        # Lord Howe Island moves its clocks half an hour (2026-10-04, 02:00 to 02:30): whole hours from midnight then
        # fall on half past, and the step after 02:30 is 03:30, past the clock
        with mock.patch.dict(os.environ, {"TZ": "Australia/Lord_Howe"}):
            time.tzset()
            now = self.local(2026, 10, 4, 3, 10, 0)
            hours = periods.buckets("hour", periods.window("today", now)[0], now)
            current = periods.interval_key("hour", now)
        time.tzset()
        self.assertEqual(([label for _, label in hours], hours[-1][0]), (["00:00", "01:00", "02:00", "03:00"], current))

    def test_all_time_by_month_from_the_first_ones(self):
        months = periods.buckets("month", self.local(2025, 12, 30, 23, 0, 0), NOW)
        names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov"]
        self.assertEqual(months, [("2025-12", "Dec 2025")] + [(f"2026-{m:02d}", f"{name} 2026")
                                                              for m, name in enumerate(names, 1)])
        self.assertEqual(periods.interval_key("month", self.local(2026, 11, 30, 23, 59, 0)), "2026-11")

    def test_days_are_the_days_buckets(self):
        start = periods.window("7d", NOW)[0]
        self.assertEqual(periods.buckets("day", start, NOW), periods.days(start, NOW))

    def test_a_day_key_is_sqlites_local_date(self):
        self.assertEqual(periods.day_key(self.local(2026, 11, 12, 0, 30, 0)), "2026-11-12")


if __name__ == "__main__":
    unittest.main()
