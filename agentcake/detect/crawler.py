"""Crawler-like patterns of a session: weak signals for the reasons, never a class.

Only a certain name makes a Bot; what is guessed (a datacenter address, visits at fixed intervals, many pages in
a row) is written into the reasons as "looks like a crawler: ...", and the session stays what the four layers made it
(a script on a cloud server is an Agent in the Automated browser row).

    patterns(page_times, network=None, visits=(), settings=None) -> {"datacenter", "fixed_interval", "every_s",
                                                                      "every_of", "many_pages", "pages"}
    looks_like_crawler(found, settings=None) -> True when at least min_signals of the three hold
    reason(found, settings=None) -> the "crawler.like" reason, or None

page_times: when each page view of the session began (ms). network: lists.match_ip()'s answer for the visitor's
address (None when no address was seen): a cloud range that is not a relay counts as a datacenter. visits: when the
same network's earlier sessions began (ms), from the collect endpoint's salted network hash, when known; with this
session's start they show a script that comes back at fixed intervals (every_of "visits"), which is said before page
loads at fixed intervals within the session (every_of "pages").
Thresholds: agentcake/data/verdict.json "crawler".
"""
import statistics

from agentcake import datafiles
from agentcake.detect.verdict_text import reason as make_reason
from agentcake.units import MS_PER_S

SETTINGS_FILE = "data/verdict.json"
PATTERNS = ("datacenter", "fixed_interval", "many_pages")


def _gaps(times):
    ordered = sorted(times)
    return [later - earlier for earlier, later in zip(ordered, ordered[1:])]


def _fixed_every_s(times, rule):
    """The median gap in seconds when there are at least min_gaps gaps between the times with a coefficient of
    variation of at most max_cv, else None."""
    gaps = _gaps(times)
    if len(gaps) < rule["min_gaps"] or statistics.fmean(gaps) <= 0:
        return None
    if statistics.pstdev(gaps) / statistics.fmean(gaps) > rule["max_cv"]:
        return None
    return statistics.median(gaps) / MS_PER_S


def patterns(page_times, network=None, visits=(), settings=None):
    """Which crawler-like patterns the session shows (see the module docstring)."""
    rule = (settings or datafiles.load(SETTINGS_FILE))["crawler"]
    times = [t for t in page_times if t is not None]
    gaps = _gaps(times)
    many = rule["many_pages"]
    comes_back = _fixed_every_s(list(visits) + times[:1], rule["fixed_interval"])
    every_s, every_of = (comes_back, "visits") if comes_back is not None else (
        _fixed_every_s(times, rule["fixed_interval"]), "pages")
    return {"datacenter": bool(network and network.get("cloud") and not network.get("relay")),
            "fixed_interval": every_s is not None, "every_s": every_s,
            "every_of": every_of if every_s is not None else None,
            "many_pages": (len(times) >= many["min_pages"]
                           and statistics.median(gaps) / MS_PER_S <= many["max_median_gap_s"]),
            "pages": len(times)}


def looks_like_crawler(found, settings=None):
    rule = (settings or datafiles.load(SETTINGS_FILE))["crawler"]
    return sum(bool(found[name]) for name in PATTERNS) >= rule["min_signals"]


def reason(found, settings=None):
    """The weak reason "looks like a crawler: ..." naming the patterns found, or None when too few hold."""
    if not looks_like_crawler(found, settings):
        return None
    held = [name for name in PATTERNS if found[name]]
    keys = [f"{name}_{found['every_of']}" if name == "fixed_interval" else name for name in held]
    return make_reason("crawler.like", "collector", held, signals=keys, pages=found["pages"], every_s=found["every_s"])

