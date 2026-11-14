"""The date ranges of the dashboard and the session list, and wall-clock times in words (S5.1).

A session's wall-clock time is sessions.start_ms: when cake received its first upload, on this computer's clock,
shown in this computer's timezone (the owner's). A range is today, the last 7 or the last 30 days, each from local
midnight (data/api.json range_days); no range is every session. The words are api.en.json's "when" (English only, D21:
no locale is read).

    now_ms()                          this computer's clock (the tests replace it)
    window(range_key, now)            (first ms, None): sessions from then on; (None, None) for no range
    earlier(start, now, days)         the same range `days` earlier: (first ms, end ms)
    days(start, now)                  [(day key, label)] of each local day from start's day to today
    day_key(ms)                       the local day of a time, as SQLite's date(ms / 1000, 'unixepoch', 'localtime')
    when(ms, now)                     "Today 09:12", "Yesterday 22:04", "Thu 14:05", "Nov 3, 14:05", "Nov 3, 2025"
"""
import datetime
import time

from agentcake.datafiles import load
from agentcake.units import MS_PER_DAY, MS_PER_S

DAY_KEY = "%Y-%m-%d"  # protocol: SQLite's date() format


def now_ms():
    return int(time.time() * MS_PER_S)


def _numbers():
    return load("data/api.json")


def _words():
    return load("data/api.en.json")["when"]


def midnight(ms, days_back=0):
    """Local midnight of the day `days_back` days before the day of ms (mktime takes care of month ends and DST)."""
    t = time.localtime(ms / MS_PER_S)
    return int(time.mktime((t.tm_year, t.tm_mon, t.tm_mday - days_back, 0, 0, 0, 0, 0, -1)) * MS_PER_S)


def window(range_key, now):
    if range_key is None:
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
