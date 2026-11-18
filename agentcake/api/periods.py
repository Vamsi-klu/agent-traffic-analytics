"""The date ranges of the dashboard and the session list, and wall-clock times in words, in AgentCake's timezone.

A session's wall-clock time is sessions.start_ms: when cake received its first upload, on this computer's clock. Its
days, hours and words are those of AgentCake's timezone, the zone every function here takes (timezone.py): the
settings' timezone (a ZoneInfo), or None, this computer's own, the C library's clock (time.localtime and mktime),
which the Trends chart's note names from the same clock. A range is PostHog's: the last 24 hours, from the start of
the hour 24 hours ago (-24h; data/api.json range_hours: a full day's sessions on any timezone), the last 7 or the last
30 days, from midnight 7 or 30 days ago (-7d, -30d; range_days: 8 and 31 days, today's included), or all time
(ALL_TIME): every session, from the first, as no range is. The Trends chart counts the last 24 hours by the hour and
every other range by the day. The words are api.en.json's "when"
(English only: no locale is read).

    now_ms()                              this computer's clock (the tests replace it)
    range_keys()                          the ranges a page may ask for, in menu order: range_hours, range_days, ALL_TIME
    window(range_key, now, zone)          (first ms, None): sessions from then on; (None, None) for all time or no range
    earlier(range_key, now, zone)         the range's previous period, PostHog's: (first ms, end ms), the end left out;
                                          None for all time or no range, which have no earlier range
    midnight(ms, zone, days_back=0)       the start of the day days_back days before the day of ms
    hour_start(ms, zone)                  the start of the hour of a time
    days(start, now, zone)                [(day key, label)] of each day from start's day to today
    buckets(interval, start, now, zone)   [(key, label)] of each hour or day from start's to the current one
    interval_key(interval, ms, zone)      the hour or day of a time, as buckets() keys it
    when(ms, now, zone)                   "Today 09:12", "Yesterday 22:04", "Thu 14:05", "Nov 3, 14:05", "Nov 3, 2025"
"""
import datetime
import time

from agentcake.datafiles import load
from agentcake.storage_config import now_ms  # the API's clock: the views call periods.now_ms(), tests replace it
from agentcake.units import MS_PER_S, S_PER_HOUR, S_PER_MIN

DAY_KEY = "%Y-%m-%d"  # protocol: SQLite's date() format
INTERVAL_KEYS = {"hour": "%Y-%m-%d %H", "day": DAY_KEY}  # protocol: the zone's wall clock
MS_PER_HOUR = S_PER_HOUR * MS_PER_S
ALL_TIME = "all"  # the range of every session: no earlier range to compare with


def _numbers():
    return load("data/api.json")


def _words():
    return load("data/api.en.json")["when"]


def _clock(ms, zone):
    """What a clock in zone (None: this computer's) shows at ms, as a naive datetime."""
    return datetime.datetime.fromtimestamp(ms / MS_PER_S, zone).replace(tzinfo=None)


def _moment(clock, zone):
    """The ms when a clock in zone (None: this computer's) shows clock, a naive datetime: of a time a change of daylight
    saving repeats, the first; of one it skips, when the clock passed it (mktime and zoneinfo agree on both)."""
    if zone is None:
        return int(time.mktime(clock.timetuple()) * MS_PER_S)
    return int(clock.replace(tzinfo=zone).timestamp() * MS_PER_S)


def midnight(ms, zone, days_back=0):
    """The start of the day days_back days before the day of ms (date arithmetic: month ends and DST included)."""
    day = _clock(ms, zone).date() - datetime.timedelta(days=days_back)
    return _moment(datetime.datetime.combine(day, datetime.time()), zone)


def range_keys():
    numbers = _numbers()
    return tuple(numbers["range_hours"]) + tuple(numbers["range_days"]) + (ALL_TIME,)


def window(range_key, now, zone):
    """A range of hours (Last 24 hours) starts where PostHog's -24h does when it is drawn by the hour: 24 real hours
    back, then back to the start of that hour, so the first hour on the Trends chart is a whole one (PostHog counts the
    hours off the clock's face, so on a day daylight saving changes its range is an hour longer or shorter). A range of
    days starts at midnight that many days ago, as PostHog's -7d does, so today is one more of its days."""
    if range_key in (None, ALL_TIME):
        return None, None
    numbers = _numbers()
    if range_key in numbers["range_hours"]:
        return hour_start(now - numbers["range_hours"][range_key] * MS_PER_HOUR, zone), None
    return midnight(now, zone, numbers["range_days"][range_key]), None


def earlier(range_key, now, zone):
    """The previous period, PostHog's (QueryDateRange.previous_period_date_from = date_from - (date_to - date_from)):
    as long as the range runs to the end of its current hour or day, and right before it. Last 24 hours: the 25 hours
    before its first hour; the last 7 and 30 days: the 8 and 31 days before its first day, whole days on the zone's
    calendar (a day daylight saving changes is 23 or 25 hours long). The range itself runs only to now, so its
    current hour or day is counted so far against a whole one."""
    if range_key in (None, ALL_TIME):
        return None
    numbers, start = _numbers(), window(range_key, now, zone)[0]
    if range_key in numbers["range_hours"]:
        return start - (numbers["range_hours"][range_key] + 1) * MS_PER_HOUR, start
    return midnight(start, zone, numbers["range_days"][range_key] + 1), start


def hour_start(ms, zone):
    """ms less the minutes and seconds past the hour on zone's clock (of the two hours a change of daylight saving
    repeats, the start of the one ms is in; in a zone half an hour off UTC, on the half hour)."""
    clock = _clock(ms, zone)
    return ms - ms % MS_PER_S - (clock.minute * S_PER_MIN + clock.second) * MS_PER_S


def days(start, now, zone):
    """Each day from the day of start to today: (day key, label). A short span is labelled by weekday, a longer one by
    date, and one that crosses a new year by date and year, so that no label comes twice (All time can span years)."""
    first, last = _clock(start, zone).date(), _clock(now, zone).date()
    count, words = (last - first).days + 1, _words()
    template = (words["day_short"] if count <= _numbers()["weekday_label_days"] else
                words["day_long"] if first.year == last.year else words["day_year"])
    out = []
    for offset in range(count):
        day = first + datetime.timedelta(days=offset)
        out.append((day.strftime(DAY_KEY), _fill(template, day)))
    return out


def when(ms, now, zone):
    words, moment, today = _words(), _clock(ms, zone), _clock(now, zone).date()
    ago = (today - moment.date()).days
    clock = words["time"].format(hour=moment.hour, minute=moment.minute)
    if ago == 0:
        return words["today"].format(time=clock)
    if ago == 1:
        return words["yesterday"].format(time=clock)
    if 0 < ago < _numbers()["weekday_label_days"]:
        return _fill(words["week"], moment, time=clock)
    if moment.year == today.year:
        return _fill(words["year"], moment, time=clock)
    return _fill(words["older"], moment)


def _fill(template, day, **values):
    words = _words()
    return template.format(weekday=words["weekdays"][day.weekday()], month=words["months"][day.month - 1],
                           day=day.day, year=day.year, **values)


def interval_key(interval, ms, zone):
    return _clock(ms, zone).strftime(INTERVAL_KEYS[interval])


def buckets(interval, start, now, zone):
    """Each hour or day (days()) from the one of start to the current one: (key, label). An hour is labelled by its
    date and the clock ("Nov 15, 23:00": the last 24 hours have the same hour on two days; an hour a change of daylight
    saving repeats is one; after a change by half an hour, as Lord Howe Island's, the steps fall on half past, so the
    current hour is found by now itself)."""
    if interval == "day":
        return days(start, now, zone)
    words, hours = _words(), {}
    for ms in [*range(hour_start(start, zone), now + 1, MS_PER_HOUR), now]:
        clock = _clock(ms, zone)
        hours.setdefault(interval_key(interval, ms, zone),
                         _fill(words["hour"], clock, time=words["time"].format(hour=clock.hour, minute=0)))
    return list(hours.items())
