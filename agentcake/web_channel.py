"""The channel a session came through (Direct, Organic Search, Paid Social, Referral …), by PostHog's default channel
rules.

    channel(entry) -> str     entry: the session's entry source (web_props.Entry)

PostHog's rules (PostHog/posthog posthog/hogql/database/schema/channel_type.py, _initial_default_channel_rules_expr,
at commit 2a7c8be6e0a359d6e4f2143079a3972a90862383; MIT, THIRD_PARTY.md), which follow GA4's default channel group:
a cross-network campaign; else a paid visit (a paid medium, an ad click id gclid, or gad_source) by its source, a
shopping campaign, its medium, its referring domain, then gad_source, a video campaign or a Facebook click; else Direct
(no referrer, no medium, no source but a direct one, no Facebook click); else the same lookups for an organic visit,
then a video campaign, a push medium, a Facebook click, no referrer (Direct), else a referrer (Referral). The
lookups read PostHog's channel definitions (data/channels.json): a value is looked up as it is, then, for a domain, as
each shorter domain of two labels or more ("news.google.co.uk", "google.co.uk", "co.uk"). PostHog's ClickHouse
dictionary looks up the value, then its "first significant subdomain" (cutToFirstSignificantSubdomain, which needs
the public suffix list); walking the shorter domains finds the same entry for every domain the list names, without
that list. Source, medium and campaign are compared in lower case, and an empty value or "null" is no value, as
PostHog's wrap_with_null_if_empty and wrap_with_lower make them.
"""
import functools
import re

from agentcake.datafiles import load

DIRECT = "$direct"  # protocol: PostHog's referring domain of a visit without a referrer
NO_VALUE = ("", "null")  # protocol: what PostHog's wrap_with_null_if_empty turns into no value
# protocol: PostHog's default channel rules (channel_type.py), word for word
PAID_MEDIUMS = ("cpc", "cpm", "cpv", "cpa", "ppc", "retargeting")
PAID_MEDIUM_PREFIX = "paid"
DIRECT_SOURCES = ("(direct)", "direct", DIRECT)
CROSS_NETWORK = re.compile("cross-network")
SHOPPING = re.compile("^(.*(([^a-df-z]|^)shop|shopping).*)$")
VIDEO = re.compile("^(.*video.*)$")
PUSH = re.compile("push$")
GOOGLE_SEARCH_AD = "1"  # gad_source=1: a Google search ad
DOMAIN_SEPARATOR = "."
SHORTEST_DOMAIN_LABELS = 2  # protocol: a domain has two labels or more (one alone is a top-level domain)
PAID, ORGANIC = 0, 1  # the two columns of data/channels.json
CHANNELS = {"cross_network": "Cross Network", "paid_shopping": "Paid Shopping", "paid_search": "Paid Search",
            "paid_video": "Paid Video", "paid_social": "Paid Social", "paid_unknown": "Paid Unknown",
            "direct": "Direct", "organic_shopping": "Organic Shopping", "organic_video": "Organic Video",
            "push": "Push", "organic_social": "Organic Social", "referral": "Referral"}


@functools.lru_cache(maxsize=1)
def _definitions():
    return load("data/channels.json")


def _value(text, lower=True):
    if text is None or text in NO_VALUE:
        return None
    return text.lower() if lower else text


def _candidates(value):
    """The value itself, then each shorter domain of at least two labels."""
    labels = value.split(DOMAIN_SEPARATOR)
    yield value
    for start in range(1, len(labels) - SHORTEST_DOMAIN_LABELS + 1):
        yield DOMAIN_SEPARATOR.join(labels[start:])


def _lookup(kind, value, column):
    if value is None:
        return None
    table = _definitions()[kind]
    for candidate in _candidates(value) if kind == "source" else (value,):
        if candidate in table and table[candidate][column]:
            return table[candidate][column]
    return None


def _found(pattern, value):
    return value is not None and bool(pattern.search(value))


def channel(entry):
    """The channel of a session whose entry source is `entry` (see the module docstring)."""
    source, medium, campaign = _value(entry.utm_source), _value(entry.utm_medium), _value(entry.utm_campaign)
    gad_source, domain = _value(entry.gad_source, lower=False), entry.referring_domain or DIRECT
    if _found(CROSS_NETWORK, campaign):
        return CHANNELS["cross_network"]
    paid = (medium in PAID_MEDIUMS or (medium or "").startswith(PAID_MEDIUM_PREFIX) or entry.has_gclid
            or gad_source is not None)
    if paid:
        return (_lookup("source", source, PAID) or (CHANNELS["paid_shopping"] if _found(SHOPPING, campaign) else None)
                or _lookup("medium", medium, PAID) or _lookup("source", domain, PAID)
                or _paid_fallback(gad_source, campaign, entry.has_fbclid))
    if domain == DIRECT and medium is None and source in (None,) + DIRECT_SOURCES and not entry.has_fbclid:
        return CHANNELS["direct"]
    return (_lookup("source", source, ORGANIC) or (CHANNELS["organic_shopping"] if _found(SHOPPING, campaign) else None)
            or _lookup("medium", medium, ORGANIC) or _lookup("source", domain, ORGANIC)
            or _organic_fallback(campaign, medium, domain, entry.has_fbclid))


def _paid_fallback(gad_source, campaign, has_fbclid):
    if gad_source == GOOGLE_SEARCH_AD:
        return CHANNELS["paid_search"]
    if _found(VIDEO, campaign):
        return CHANNELS["paid_video"]
    return CHANNELS["paid_social"] if has_fbclid else CHANNELS["paid_unknown"]


def _organic_fallback(campaign, medium, domain, has_fbclid):
    if _found(VIDEO, campaign):
        return CHANNELS["organic_video"]
    if _found(PUSH, medium):
        return CHANNELS["push"]
    if has_fbclid:
        return CHANNELS["organic_social"]
    return CHANNELS["direct"] if domain == DIRECT else CHANNELS["referral"]
