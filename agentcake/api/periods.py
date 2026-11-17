"""The date ranges of the dashboard and the session list, and wall-clock times in words.

A session's wall-clock time is sessions.start_ms: when cake received its first upload, on this computer's clock,
shown in this computer's timezone (the owner's). A range is today, the last 7 or the last 30 days, each from local
midnight (data/api.json range_days), or all time (ALL_TIME): every session, from the first, as no range is. The words
are api.en.json's "when" (English only: no locale is read).

    now_ms()                          this computer's clock (the tests replace it)
    range_keys()                      the ranges a page may ask for: data/api.json range_days and ALL_TIME
    window(range_key, now)            (first ms, None): sessions from then on; (None, None) for all time or no range
    earlier(start, now, days)         the same range `days` earlier: (first ms, end ms)
    days(start, now)                  [(day key, label)] of each local day from start's day to today
    day_key(ms)                       the local day of a time, as SQLite's date(ms / 1000, 'unixepoch', 'localtime')
    buckets(interval, start, now)     [(key, label)] of each local hour, day or month from start's to the current one
    interval_key(interval, ms)        the local hour, day or month of a time, as buckets() keys it
    when(ms, now)                     "Today 09:12", "Yesterday 22:04", "Thu 14:05", "Nov 3, 14:05", "Nov 3, 2025"
"""
import calendar
import datetime
import time

from agentcake.datafiles import load
from agentcake.storage_config import now_ms  # the API's clock: the views call periods.now_ms(), tests replace it
from agentcake.units import MS_PER_DAY, MS_PER_S, S_PER_HOUR

DAY_KEY = "%Y-%m-%d"  # protocol: SQLite's date() format
INTERVAL_KEYS = {"hour": "%Y-%m-%d %H", "day": DAY_KEY, "month": "%Y-%m"}  # protocol: local time, as day_key
MS_PER_HOUR = S_PER_HOUR * MS_PER_S
ALL_TIME = "all"  # the range of every session: no earlier range to compare with


def _numbers():
    return load("data/api.json")


def _words():
    return load("data/api.en.json")["when"]


def midnight(ms, days_back=0):
    """Local midnight of the day `days_back` days before the day of ms (mktime takes care of month ends and DST)."""
    t = time.localtime(ms / MS_PER_S)
    return int(time.mktime((t.tm_year, t.tm_mon, t.tm_mday - days_back, 0, 0, 0, 0, 0, -1)) * MS_PER_S)


def range_keys():
    return tuple(_numbers()["range_days"]) + (ALL_TIME,)


def window(range_key, now):
    if range_key in (None, ALL_TIME):
        return None, None
    return midnight(now, _numbers()["range_days"][range_key] - 1), None


def earlier(start, now, days):
    shift = days * MS_PER_DAY
    return (None if start is None else start - shift), now - shift


def day_key(ms):
    return time.strftime(DAY_KEY, time.localtime(ms / MS_PER_S))


def days(start, now):
    """Each local day from the day of start to today: (day key, label). A short span is labelled by weekday."""
    first, last = _date(start), _date(now)
    count = (last - first).days + 1
    template = _words()["day_short"] if count <= _numbers()["weekday_label_days"] else _words()["day_long"]
    out = []
    for offset in range(count):
        day = first + datetime.timedelta(days=offset)
        out.append((day.strftime(DAY_KEY), _fill(template, day)))
    return out


def when(ms, now):
    words, moment = _words(), datetime.datetime.fromtimestamp(ms / MS_PER_S)
    ago = (_date(now) - moment.date()).days
    clock = words["time"].format(hour=moment.hour, minute=moment.minute)
    if ago == 0:
        return words["today"].format(time=clock)
    if ago == 1:
        return words["yesterday"].format(time=clock)
    if 0 < ago < _numbers()["weekday_label_days"]:
        return _fill(words["week"], moment, time=clock)
    if moment.year == _date(now).year:
        return _fill(words["year"], moment, time=clock)
    return _fill(words["older"], moment)


def _date(ms):
    return datetime.date.fromtimestamp(ms / MS_PER_S)


def _fill(template, day, **values):
    words = _words()
    return template.format(weekday=words["weekdays"][day.weekday()], month=words["months"][day.month - 1],
                           day=day.day, year=day.year, **values)


def interval_key(interval, ms):
    return time.strftime(INTERVAL_KEYS[interval], time.localtime(ms / MS_PER_S))


def buckets(interval, start, now):
    """Each local hour, day (days()) or month from the one of start to the current one: (key, label). An hour is
    labelled by the clock ("13:00"; an hour a change of daylight saving repeats is one; after a change by half an hour,
    as Lord Howe Island's, the steps fall on half past, so the current hour is found by now itself), a month by month
    and year."""
    if interval == "day":
        return days(start, now)
    words = _words()
    if interval == "hour":
        t = time.localtime(start / MS_PER_S)
        first = int(time.mktime((t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, 0, 0, 0, 0, -1)) * MS_PER_S)
        hours = {}
        for ms in [*range(first, now + 1, MS_PER_HOUR), now]:
            hours.setdefault(interval_key(interval, ms), words["time"].format(hour=time.localtime(ms / MS_PER_S).tm_hour,
                                                                              minute=0))
        return list(hours.items())
    month, last = _date(start).replace(day=1), _date(now)
    out = []
    while month <= last:
        out.append((month.strftime(INTERVAL_KEYS[interval]), _fill(words["month_long"], month)))
        _, length = calendar.monthrange(month.year, month.month)
        month += datetime.timedelta(days=length)
    return out
