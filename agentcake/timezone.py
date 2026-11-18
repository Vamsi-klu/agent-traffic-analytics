"""AgentCake's timezone: the one its pages and its command line write days and times in, as PostHog's project time
zone (Team.timezone) is for PostHog's.

The setting `timezone` (defaults.json) names an IANA zone the timezone database knows (zoneinfo); empty, the default,
AgentCake follows this computer: its days and times are the C library's own (time.localtime: $TZ, else
/etc/localtime), and so is what the pages call them, so that what they count and what they say come from one place.

    known(name)            whether the timezone database knows an IANA name: what `timezone` may be set to
    chosen(c)              the ZoneInfo the settings c name; None to follow this computer (also when the name set by
                           hand names no zone)
    machine_name()         this computer's IANA name: $TZ, the zone /etc/localtime links to, /etc/timezone; None when
                           none names one (a $TZ rule as JST-9, a copied /etc/localtime): never a guess
    short(zone, ms)        what the pages call zone (None: this computer's) at ms: its abbreviation ("PST", "PDT",
                           "JST", "UTC"), or, when the timezone database has none, its offset ("UTC+05:45")
    listed(ms)             [{"name", "label"}] the settings page lists: UTC, then IANA's zone.tab zones
                           (data/timezones.json) the timezone database knows, each with its offset at ms, as PostHog's
                           time zone setting labels them (frontend/src/lib/utils/timezones.ts timeZoneLabel, MIT):
                           "America / Los Angeles (UTC-08:00)"
"""
import datetime
import functools
import os
import time
import zoneinfo

from agentcake.datafiles import load
from agentcake.units import MS_PER_S, S_PER_HOUR, S_PER_MIN

UTC = "UTC"  # protocol: the timezone database's name of UTC, listed first as PostHog's TimezoneSelect lists it
LOCALTIME = "/etc/localtime"  # protocol: where the C library reads this computer's zone when $TZ is unset
TIMEZONE_FILE = "/etc/timezone"  # protocol: Debian's file that names it
ZONEINFO = "/zoneinfo/"  # protocol: the folder of the timezone database that /etc/localtime links into
TZ_FILE_MARK = ":"  # protocol: $TZ=:<name> names a zone file, as $TZ=<name> does


def _words():
    return load("data/api.en.json")["when"]


@functools.cache
def _names():
    return frozenset(zoneinfo.available_timezones())


def known(name):
    return isinstance(name, str) and name in _names()


def chosen(c):
    name = c.get("timezone") or ""
    return zoneinfo.ZoneInfo(name) if known(name) else None


def machine_name():
    if "TZ" in os.environ:
        return _named(os.environ["TZ"].removeprefix(TZ_FILE_MARK) or UTC)  # an empty $TZ is UTC to the C library
    linked = _named(os.path.realpath(LOCALTIME))
    if linked:
        return linked
    try:
        with open(TIMEZONE_FILE) as f:
            return _named(f.read().strip())
    except OSError:
        return None


def _named(text):
    """text when it names a zone, or the zone a path into the timezone database's folder names; else None."""
    if known(text):
        return text
    _, inside, name = text.rpartition(ZONEINFO)
    return name if inside and known(name) else None


def short(zone, ms):
    if zone is None:
        clock = time.localtime(ms / MS_PER_S)
        name, offset_s = clock.tm_zone, clock.tm_gmtoff
    else:
        moment = datetime.datetime.fromtimestamp(ms / MS_PER_S, zone)
        name, offset_s = moment.tzname(), int(moment.utcoffset().total_seconds())
    return name if name and name.isalpha() else offset(offset_s)


def offset(seconds):
    """"UTC+05:45": an offset from UTC in hours and minutes, as the pages write it."""
    hours, minutes = divmod(abs(seconds) // S_PER_MIN, S_PER_HOUR // S_PER_MIN)
    return _words()["offset"].format(sign="-" if seconds < 0 else "+", hours=hours, minutes=minutes)


def listed(ms):
    zones = sorted(name for name in load("data/timezones.json")["zones"] if known(name) and name != UTC)
    moment = datetime.datetime.fromtimestamp(ms / MS_PER_S, datetime.timezone.utc)
    template = _words()["zone_label"]
    return [{"name": name, "label": template.format(name=name.replace("/", " / ").replace("_", " "),
                                                    offset=offset(_offset_s(moment, name)))}
            for name in [UTC, *zones]]


def _offset_s(moment, name):
    """The offset from UTC of the zone name at moment (an aware datetime), in seconds."""
    return int(moment.astimezone(zoneinfo.ZoneInfo(name)).utcoffset().total_seconds())
