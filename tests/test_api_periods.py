"""agentcake/api/periods.py: the date ranges and the wall-clock words, in AgentCake's timezone.

    python3 -I -m unittest discover -s tests -p test_api_periods.py -v      (from the AgentCake folder)

Every function takes the timezone: None follows this computer (the C library's clock), a ZoneInfo is the one set in
the settings. Periods runs with this computer in America/Los_Angeles, which changes for daylight saving on 2026-03-08
and on 2026-11-01; InATimezone runs with this computer on UTC and a timezone set, which then decides the days, hours
and words. Each test fixes the clock.
"""
import datetime
import os
import sys
import time
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from agentcake.api import periods  # noqa: E402

HOUR = 3_600_000
MINUTE = 60_000
# 2026-11-12 21:13 in Los Angeles (PST, UTC-8), a Thursday: Friday 13:13 in Shanghai, Friday 10:43 in Kolkata
NOW = 1_794_546_780_000
MACHINE = None  # follow this computer's timezone
LOS_ANGELES, SHANGHAI, KOLKATA = ZoneInfo("America/Los_Angeles"), ZoneInfo("Asia/Shanghai"), ZoneInfo("Asia/Kolkata")


def at(zone, *fields):
    """The moment a clock in zone shows fields (year, month, day[, hour, minute]), in ms."""
    return int(datetime.datetime(*fields, tzinfo=zone).timestamp() * 1000)


def in_timezone(case, name):
    """This computer's timezone is name for the rest of the test."""
    zone = mock.patch.dict(os.environ, {"TZ": name})
    zone.start()
    case.addCleanup(zone.stop)
    case.addCleanup(time.tzset)
    time.tzset()


class Periods(unittest.TestCase):
    """Following this computer's timezone, America/Los_Angeles."""

    def setUp(self):
        in_timezone(self, "America/Los_Angeles")

    def local(self, *fields):
        return int(time.mktime(fields + (0, 0, -1)) * 1000)

    def labels(self, interval, start, now):
        return [label for _, label in periods.buckets(interval, start, now, MACHINE)]

    def test_the_ranges_in_menu_order_and_today_is_none_of_them(self):
        self.assertEqual(periods.range_keys(), ("24h", "7d", "30d", periods.ALL_TIME))

    def test_the_last_24_hours_start_at_the_start_of_the_hour_24_hours_ago(self):
        self.assertEqual(periods.window("24h", NOW, MACHINE), (self.local(2026, 11, 11, 21, 0, 0), None))
        on_the_hour = self.local(2026, 11, 12, 21, 0, 0)
        self.assertEqual(periods.window("24h", on_the_hour, MACHINE), (on_the_hour - 24 * HOUR, None))

    def test_the_last_24_hours_start_on_a_local_hour_whatever_the_timezone(self):
        for zone in ("UTC", "Asia/Kolkata", "Asia/Kathmandu", "Pacific/Chatham"):
            with mock.patch.dict(os.environ, {"TZ": zone}):
                time.tzset()
                start, _ = periods.window("24h", NOW, MACHINE)
                self.assertEqual((time.localtime(start / 1000)[4:6], NOW - start - 24 * HOUR < HOUR),
                                 ((0, 0), True), f"{zone}: the start of a local hour, at most an hour before")
                self.assertLessEqual(start, NOW - 24 * HOUR, zone)
        time.tzset()

    def test_the_last_24_hours_go_back_24_real_hours_across_a_change_of_daylight_saving(self):
        autumn = self.local(2026, 11, 1, 12, 30, 0)  # 01:00 came twice that night: the clock shows 23 hours back
        self.assertEqual(periods.window("24h", autumn, MACHINE)[0], autumn - 24 * HOUR - 30 * MINUTE)
        self.assertEqual(periods.window("24h", autumn, MACHINE)[0], self.local(2026, 10, 31, 13, 0, 0))
        spring = self.local(2026, 3, 8, 12, 30, 0)  # 02:00 never came that night: the clock shows 25 hours back
        self.assertEqual(periods.window("24h", spring, MACHINE)[0], spring - 24 * HOUR - 30 * MINUTE)
        self.assertEqual(periods.window("24h", spring, MACHINE)[0], self.local(2026, 3, 7, 11, 0, 0))

    def test_days_start_at_local_midnight_7_and_30_days_ago_as_posthogs_do(self):
        self.assertEqual(periods.window("7d", NOW, MACHINE), (self.local(2026, 11, 5, 0, 0, 0), None), "8 days")
        self.assertEqual(periods.window("30d", NOW, MACHINE), (self.local(2026, 10, 13, 0, 0, 0), None), "31 days")
        self.assertEqual(periods.window(None, NOW, MACHINE), (None, None))
        self.assertEqual(periods.window(periods.ALL_TIME, NOW, MACHINE), (None, None), "all time: every session")

    def test_thirty_days_back_crosses_the_change_of_daylight_saving_at_midnight(self):
        start, _ = periods.window("30d", NOW, MACHINE)
        self.assertEqual(time.localtime(start / 1000)[3:6], (0, 0, 0))

    def test_the_last_24_hours_compare_with_the_25_hours_before_their_first_hour(self):
        start, _ = periods.window("24h", NOW, MACHINE)
        self.assertEqual(periods.earlier("24h", NOW, MACHINE), (start - 25 * HOUR, start),
                         "PostHog's previous period: the range is 25 hours long, to the end of the current one")

    def test_days_compare_with_the_as_many_days_before_and_all_time_with_nothing(self):
        self.assertEqual(periods.earlier("7d", NOW, MACHINE), (self.local(2026, 10, 28, 0, 0, 0),
                                                               self.local(2026, 11, 5, 0, 0, 0)), "8 days")
        self.assertEqual(periods.earlier("30d", NOW, MACHINE), (self.local(2026, 9, 12, 0, 0, 0),
                                                                self.local(2026, 10, 13, 0, 0, 0)), "31 days")
        self.assertIsNone(periods.earlier(periods.ALL_TIME, NOW, MACHINE))
        self.assertIsNone(periods.earlier(None, NOW, MACHINE))

    def test_a_previous_period_across_a_change_of_daylight_saving_is_whole_days(self):
        after = self.local(2026, 11, 9, 12, 0, 0)  # its previous 8 days hold 2026-11-01, 25 hours long
        self.assertEqual(periods.earlier("7d", after, MACHINE), (self.local(2026, 10, 25, 0, 0, 0),
                                                                 self.local(2026, 11, 2, 0, 0, 0)))

    def test_days_are_dated_and_a_week_or_less_by_weekday(self):
        week = periods.days(periods.window("7d", NOW, MACHINE)[0], NOW, MACHINE)
        self.assertEqual([label for _, label in week], [f"Nov {day}" for day in range(5, 13)],
                         "8 days: the weekday of the first and the last is the same")
        self.assertEqual(week[-1][0], "2026-11-12")
        month = periods.days(periods.window("30d", NOW, MACHINE)[0], NOW, MACHINE)
        self.assertEqual((len(month), month[0][1], month[-1][1]), (31, "Oct 13", "Nov 12"))
        days = periods.days(self.local(2026, 11, 6, 9, 0, 0), NOW, MACHINE)
        self.assertEqual([label for _, label in days], ["Fri", "Sat", "Sun", "Mon", "Tue", "Wed", "Thu"])

    def test_when_in_words(self):
        self.assertEqual(periods.when(self.local(2026, 11, 12, 9, 5, 0), NOW, MACHINE), "Today 09:05")
        self.assertEqual(periods.when(self.local(2026, 11, 11, 22, 4, 0), NOW, MACHINE), "Yesterday 22:04")
        self.assertEqual(periods.when(self.local(2026, 11, 9, 14, 0, 0), NOW, MACHINE), "Mon 14:00")
        self.assertEqual(periods.when(self.local(2026, 11, 3, 8, 30, 0), NOW, MACHINE), "Nov 3, 08:30")
        self.assertEqual(periods.when(self.local(2025, 12, 24, 8, 30, 0), NOW, MACHINE), "Dec 24, 2025")

    def test_the_last_24_hours_by_hour_from_the_hour_24_hours_ago_to_the_current_one(self):
        hours = periods.buckets("hour", periods.window("24h", NOW, MACHINE)[0], NOW, MACHINE)
        self.assertEqual(len(hours), 25, "Nov 11, 21:00, a whole hour, to Nov 12, 21:00, the current one")
        self.assertEqual((hours[0], hours[1], hours[-1]), (("2026-11-11 21", "Nov 11, 21:00"),
                                                            ("2026-11-11 22", "Nov 11, 22:00"),
                                                            ("2026-11-12 21", "Nov 12, 21:00")))
        self.assertEqual([label for _, label in hours[3:5]], ["Nov 12, 00:00", "Nov 12, 01:00"])
        self.assertEqual(periods.interval_key("hour", self.local(2026, 11, 12, 21, 59, 0), MACHINE), hours[-1][0])

    def test_the_last_24_hours_by_hour_across_a_month_and_a_year(self):
        for now, first, last in ((self.local(2026, 12, 1, 0, 20, 0), ("2026-11-30 00", "Nov 30, 00:00"),
                                  ("2026-12-01 00", "Dec 1, 00:00")),
                                 (self.local(2027, 1, 1, 9, 45, 0), ("2026-12-31 09", "Dec 31, 09:00"),
                                  ("2027-01-01 09", "Jan 1, 09:00"))):
            hours = periods.buckets("hour", periods.window("24h", now, MACHINE)[0], now, MACHINE)
            self.assertEqual((len(hours), hours[0], hours[-1]), (25, first, last))

    def test_the_last_24_hours_by_hour_across_a_change_of_daylight_saving(self):
        autumn = self.local(2026, 11, 1, 12, 30, 0)
        self.assertEqual(self.labels("hour", periods.window("24h", autumn, MACHINE)[0], autumn),
                         [f"Oct 31, {h:02d}:00" for h in range(13, 24)] + [f"Nov 1, {h:02d}:00" for h in range(13)],
                         "the hour 01:00 that came twice is one")
        spring = self.local(2026, 3, 8, 12, 30, 0)
        self.assertEqual(self.labels("hour", periods.window("24h", spring, MACHINE)[0], spring),
                         [f"Mar 7, {h:02d}:00" for h in range(11, 24)] +
                         [f"Mar 8, {h:02d}:00" for h in range(13) if h != 2], "no 02:00, which never came")

    def test_the_hour_daylight_saving_repeats_is_one(self):
        end = self.local(2026, 11, 1, 23, 30, 0)  # 2026-11-01 has 25 hours in Los Angeles: 01:00 comes twice
        self.assertEqual(self.labels("hour", periods.midnight(end, MACHINE), end),
                         [f"Nov 1, {h:02d}:00" for h in range(24)])

    def test_the_current_hour_after_a_half_hour_change_of_daylight_saving_is_a_bucket(self):
        # Lord Howe Island moves its clocks half an hour (2026-10-04, 02:00 to 02:30): whole hours from midnight then
        # fall on half past, and the step after 02:30 is 03:30, past the clock
        with mock.patch.dict(os.environ, {"TZ": "Australia/Lord_Howe"}):
            time.tzset()
            now = self.local(2026, 10, 4, 3, 10, 0)
            hours = periods.buckets("hour", periods.midnight(now, MACHINE), now, MACHINE)
            current = periods.interval_key("hour", now, MACHINE)
        time.tzset()
        self.assertEqual(([label for _, label in hours], hours[-1][0]),
                         (["Oct 4, 00:00", "Oct 4, 01:00", "Oct 4, 02:00", "Oct 4, 03:00"], current))

    def test_days_across_years_name_the_year(self):
        days = periods.days(self.local(2025, 12, 30, 23, 0, 0), NOW, MACHINE)
        self.assertEqual((len(days), days[0], days[2], days[-1]),
                         (318, ("2025-12-30", "Dec 30, 2025"), ("2026-01-01", "Jan 1, 2026"), ("2026-11-12", "Nov 12, 2026")))
        long_ago = periods.days(self.local(2025, 10, 1, 9, 0, 0), NOW, MACHINE)
        self.assertEqual(len({label for _, label in long_ago}), len(long_ago), "over a year, every label once")

    def test_only_hours_and_days(self):
        self.assertEqual(set(periods.INTERVAL_KEYS), {"hour", "day"})

    def test_days_are_the_days_buckets(self):
        start = periods.window("7d", NOW, MACHINE)[0]
        self.assertEqual(periods.buckets("day", start, NOW, MACHINE), periods.days(start, NOW, MACHINE))

    def test_a_day_key_is_the_local_date(self):
        self.assertEqual(periods.interval_key("day", self.local(2026, 11, 12, 0, 30, 0), MACHINE), "2026-11-12")


class InATimezone(unittest.TestCase):
    """The days, hours and words of the timezone set, with this computer on UTC."""

    def setUp(self):
        in_timezone(self, "UTC")

    def labels(self, interval, range_key, now, zone):
        return [label for _, label in periods.buckets(interval, periods.window(range_key, now, zone)[0], now, zone)]

    def test_days_start_at_the_timezones_midnight(self):
        self.assertEqual(periods.window("7d", NOW, LOS_ANGELES), (at(LOS_ANGELES, 2026, 11, 5), None))
        self.assertEqual(periods.window("7d", NOW, SHANGHAI), (at(SHANGHAI, 2026, 11, 6), None))
        self.assertEqual(periods.window("30d", NOW, SHANGHAI), (at(SHANGHAI, 2026, 10, 14), None))
        self.assertEqual(self.labels("day", "7d", NOW, LOS_ANGELES), [f"Nov {day}" for day in range(5, 13)])
        self.assertEqual(self.labels("day", "7d", NOW, SHANGHAI), [f"Nov {day}" for day in range(6, 14)])

    def test_following_this_computer_days_are_its_own(self):
        self.assertEqual(periods.window("7d", NOW, MACHINE), (at(datetime.timezone.utc, 2026, 11, 6), None))

    def test_hours_are_labelled_by_the_timezones_clock(self):
        self.assertEqual(self.labels("hour", "24h", NOW, LOS_ANGELES)[::24], ["Nov 11, 21:00", "Nov 12, 21:00"])
        self.assertEqual(self.labels("hour", "24h", NOW, SHANGHAI)[::24], ["Nov 12, 13:00", "Nov 13, 13:00"])
        self.assertEqual(periods.window("24h", NOW, LOS_ANGELES), periods.window("24h", NOW, SHANGHAI),
                         "two timezones a whole number of hours apart: the same moment")
        self.assertEqual(periods.interval_key("hour", at(SHANGHAI, 2026, 11, 13, 9, 59), SHANGHAI), "2026-11-13 09")

    def test_a_half_hour_timezone_starts_the_24_hours_on_its_own_hour(self):
        self.assertEqual(periods.window("24h", NOW, KOLKATA), (at(KOLKATA, 2026, 11, 12, 10, 0), None))
        self.assertEqual(self.labels("hour", "24h", NOW, KOLKATA)[::24], ["Nov 12, 10:00", "Nov 13, 10:00"])

    def test_words_in_the_timezone(self):
        ten_in_los_angeles = at(LOS_ANGELES, 2026, 11, 12, 10, 0)  # Friday 02:00 in Shanghai
        seven_in_los_angeles = at(LOS_ANGELES, 2026, 11, 12, 7, 0)  # Thursday 23:00 in Shanghai
        self.assertEqual(periods.when(ten_in_los_angeles, NOW, LOS_ANGELES), "Today 10:00")
        self.assertEqual(periods.when(ten_in_los_angeles, NOW, SHANGHAI), "Today 02:00")
        self.assertEqual(periods.when(seven_in_los_angeles, NOW, LOS_ANGELES), "Today 07:00")
        self.assertEqual(periods.when(seven_in_los_angeles, NOW, SHANGHAI), "Yesterday 23:00")
        self.assertEqual(periods.when(seven_in_los_angeles, NOW, MACHINE), "Yesterday 15:00", "this computer's: UTC")

    def test_a_change_of_daylight_saving_of_the_timezone_set(self):
        autumn = at(LOS_ANGELES, 2026, 11, 1, 12, 30)
        self.assertEqual(periods.window("24h", autumn, LOS_ANGELES)[0], autumn - 24 * HOUR - 30 * MINUTE)
        self.assertEqual(self.labels("hour", "24h", autumn, LOS_ANGELES),
                         [f"Oct 31, {h:02d}:00" for h in range(13, 24)] + [f"Nov 1, {h:02d}:00" for h in range(13)])
        week_after = at(LOS_ANGELES, 2026, 11, 3, 12, 0)
        self.assertEqual(periods.window("7d", week_after, LOS_ANGELES)[0], at(LOS_ANGELES, 2026, 10, 27))
        self.assertEqual(len(self.labels("day", "7d", week_after, LOS_ANGELES)), 8)
        spring = at(LOS_ANGELES, 2026, 3, 8, 12, 30)
        self.assertNotIn("Mar 8, 02:00", self.labels("hour", "24h", spring, LOS_ANGELES))

    def test_new_year_is_the_timezones(self):
        new_year_in_shanghai = at(SHANGHAI, 2026, 1, 1, 3, 0)  # still 2025 in UTC and in Los Angeles
        self.assertEqual(periods.interval_key("day", new_year_in_shanghai, SHANGHAI), "2026-01-01")
        self.assertEqual(periods.interval_key("day", new_year_in_shanghai, LOS_ANGELES), "2025-12-31")


if __name__ == "__main__":
    unittest.main()
