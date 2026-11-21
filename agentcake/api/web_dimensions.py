"""The dimensions of the dashboard's Sources, Devices and Geography tables, as PostHog's web
analytics breaks them down (products/web_analytics/backend/hogql_queries/stats_table.py), over a session's
session_web row (web_props.py), aliased `w`:

    sources    channel (PostHog's default channel type), referring_domain, utm_source, utm_medium, utm_campaign
    devices    device_type, browser, os
    geography  country, region, city (the city database's, on a server: geoip.py), timezone, language

Left out of PostHog's own lists: the dimensions cake has nothing for (Viewport, Screen name, In-app browser) and the
combined UTM source / medium / campaign. Each dimension is one SQL expression, so the tables (web.py) and the session
list's filter (sessions.py) read the same value: its key, or NULL for a session without one (PostHog's "not set";
an empty referring domain is a visit without a referrer, PostHog's $direct). As PostHog's do (stats_table.py breaks
regions and cities down by country first), a region and a city are counted with their country: the key is the
country, PLACE_SEPARATOR and the name ("US:California", "US:Mountain View"), a session whose country is known but not
its region or city is that country's own Not set ("DE:"), and a session without a country is in neither table. The
place is computed when the tables are asked for, from what each session kept: a region kept before AgentCake looked
places up itself (0.5 read a load balancer's CLDR subdivision id, such as USCA) is named in English from Unicode
CLDR's list (data/subdivisions.en.json); nothing stored is changed. A time zone is its offset from UTC (PostHog groups
by $timezone_offset), a language is navigator.language's primary subtag ("en" for en-US).

    TABLES                         {table: (dimension, ...)}, in the order the dashboard shows them
    EXPRESSIONS                    {dimension: SQL expression over w}
    PLACE                          the dimensions of a place (geoip.py): no Not set row where there is no source
    PER_COUNTRY                    the place dimensions counted with their country, Not set by country
    label(dimension, key) -> dict  {"value", "country"}: what a row shows for a key (a value of None: Not set)
    where(scope, dimension, key)   the scope narrowed to the sessions whose dimension has that key (None: not set)
"""
import functools

from agentcake.datafiles import load

TABLES = {"sources": ("channel", "referring_domain", "utm_source", "utm_medium", "utm_campaign"),
          "devices": ("device_type", "browser", "os"),
          "geography": ("country", "region", "city", "timezone", "language")}
PLACE_SEPARATOR = ":"  # between a region's or a city's country and its name in its key
LANGUAGE_SEPARATOR = "-"  # protocol: BCP 47 separates a language's subtags with hyphens


def _per_country(column):
    """The key of a region or a city: its country, the separator and its name, or nothing after the separator for
    the country's Not set; NULL for a session without a country."""
    return f"CASE WHEN w.country IS NOT NULL THEN w.country || '{PLACE_SEPARATOR}' || COALESCE({column}, '') END"


EXPRESSIONS = {
    "channel": "w.channel",
    "referring_domain": "w.referring_domain",
    "utm_source": "w.utm_source",
    "utm_medium": "w.utm_medium",
    "utm_campaign": "w.utm_campaign",
    "device_type": "NULLIF(w.device_type, '')",
    "browser": "NULLIF(w.browser, '')",
    "os": "NULLIF(w.os, '')",
    "country": "w.country",
    "region": _per_country("w.subdivision"),
    "city": _per_country("w.city"),
    "timezone": "CAST(w.tz_offset AS TEXT)",
    "language": (f"lower(CASE WHEN instr(w.language, '{LANGUAGE_SEPARATOR}') > 0 THEN substr(w.language, 1, "
                 f"instr(w.language, '{LANGUAGE_SEPARATOR}') - 1) ELSE w.language END)"),
}
PLACE = ("country", "region", "city")
PER_COUNTRY = ("region", "city")
COUNTRY_CODE_LETTERS = 2  # protocol: an ISO 3166-1 alpha-2 country code, which starts a CLDR subdivision id
MINUTES_PER_HOUR = 60  # protocol: minutes in an hour
UTC_OFFSET = "UTC{sign}{hours:02d}:{minutes:02d}"  # protocol: how an offset from UTC is written (ISO 8601)


def label(dimension, key):
    """What a row shows for a key: its value (None: Not set), and the country it is in for a region or a city (None
    otherwise)."""
    if key is None:
        return {"value": None, "country": None}
    if dimension in PER_COUNTRY:
        country, _, name = key.partition(PLACE_SEPARATOR)
        if dimension == "region":
            name = _region_name(country, name)
        return {"value": name or None, "country": country or None}
    if dimension == "timezone":
        return {"value": utc_offset(int(key)), "country": None}
    return {"value": key, "country": None}


def _region_name(country, name):
    """A region's name as kept: a CLDR subdivision id a load balancer gave (USCA, upper case and starting with its
    country's code) by its English name, or by the part after the country's code when CLDR has none; any other name
    as it is (the city database's)."""
    if name.isupper() and name[:COUNTRY_CODE_LETTERS] == country:
        return _subdivisions().get(name.lower()) or name[COUNTRY_CODE_LETTERS:] or name
    return name


@functools.lru_cache(maxsize=1)
def _subdivisions():
    """{lower-case CLDR subdivision id: English name} (Unicode CLDR, data/subdivisions.en.json)."""
    return load("data/subdivisions.en.json")["names"]


def utc_offset(minutes_behind):
    """UTC+08:00 for Date.getTimezoneOffset()'s -480 (the minutes UTC is ahead of local time)."""
    ahead = -minutes_behind
    hours, minutes = divmod(abs(ahead), MINUTES_PER_HOUR)
    return UTC_OFFSET.format(sign="-" if ahead < 0 else "+", hours=hours, minutes=minutes)


def where(scope, dimension, key):
    """The scope narrowed to the sessions whose dimension has this key; key None: those without one."""
    expression = EXPRESSIONS[dimension]
    if key is None:
        return scope.where(f"s.id NOT IN (SELECT w.session_id FROM session_web w WHERE {expression} IS NOT NULL)")
    return scope.where(f"s.id IN (SELECT w.session_id FROM session_web w WHERE {expression} = ?)", key)
