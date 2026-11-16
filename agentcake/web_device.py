"""A session's browser, operating system and device type, named as PostHog's web analytics names them.

    describe(user_agent, env=None) -> Device(browser, os, device_type)

The rules are posthog-js's (packages/core/src/utils/user-agent-utils.ts: detectBrowser, detectOS, detectDevice and
detectDeviceType, MIT), transcribed into data/devices.json, which says how a rule matches. Only what cake already
records is read: the User-Agent of the session's uploads, and from the page's environment record (env, optional) the
vendor, the platform of the client hints, the touch points, the screen and the pixel ratio, which PostHog reads to tell
an Android tablet from a phone when the User-Agent names no device. A value no rule names is "" (the tables show it as
not set, as PostHog does).
"""
import functools
import re
from collections import namedtuple

from agentcake.datafiles import load

Device = namedtuple("Device", "browser os device_type")
RULES = "data/devices.json"


@functools.lru_cache(maxsize=None)
def _pattern(text):
    return re.compile(text)


def _matches(rule, user_agent, vendor):
    found = bool(rule.get("match")) and bool(_pattern(rule["match"]).search(user_agent))
    found = found or bool(rule.get("or_vendor") and vendor and rule["or_vendor"] in vendor)
    return found and not (rule.get("unless") and _pattern(rule["unless"]).search(user_agent))


def first_name(rules, user_agent, vendor=""):
    """The name the first matching rule gives (its then rules first), or "" when none matches."""
    for rule in rules:
        if _matches(rule, user_agent, vendor):
            return first_name(rule.get("then", ()), user_agent, vendor) or rule["name"]
    return ""


def device_type(user_agent, env=None):
    """Tablet, Console, Wearable, Mobile or Desktop (detectDeviceType)."""
    data = load(RULES)
    device = first_name(data["devices"], user_agent)
    for kind, devices in data["device_types"].items():
        if device in devices:
            return kind
    if device:
        return data["any_device_type"]
    env = env or {}
    platform = (env.get("uaData") or {}).get("platform")
    if platform == data["android_platform"] and (env.get("maxTouchPoints") or 0) > 0:
        screen = env.get("screen") or {}
        short_side = min(screen.get("w") or 0, screen.get("h") or 0) / (env.get("dpr") or 1)
        return data["tablet_type"] if short_side >= data["tablet_short_side_dp"] else data["any_device_type"]
    return data["no_device_type"]


@functools.lru_cache(maxsize=None)
def _from_user_agent(user_agent, vendor):
    data = load(RULES)
    return first_name(data["browsers"], user_agent, vendor), first_name(data["systems"], user_agent)


def describe(user_agent, env=None):
    """The Device of a session (see the module docstring); every field "" without a User-Agent."""
    if not user_agent:
        return Device("", "", "")
    env = env or {}
    browser, system = _from_user_agent(user_agent, env.get("vendor") or "")
    return Device(browser, system, device_type(user_agent, env))
