"""The storage parameters: agentcake/data/storage.json, read once when the package is imported.

SETTINGS holds the chunk length, the compression codec and levels, the folder names, the night recompression rules
and the CSS de-duplication switch; the storage modules take every number from it. Functions whose behaviour a test
varies take a `cfg` argument that defaults to SETTINGS. ms_from_days() and when() turn days and epoch milliseconds
into the units the code needs without unit literals; now_ms() is this computer's clock in epoch milliseconds, the
one every module reads (each imports it under a name of its own, which a test replaces to fix the time).
"""
from datetime import datetime, timedelta, timezone

from agentcake.datafiles import load

SETTINGS = load("data/storage.json")
ONE_MS = timedelta(milliseconds=1)
EPOCH = datetime.fromtimestamp(0, timezone.utc)


def ms_from_days(days):
    return timedelta(days=days) // ONE_MS


def now_ms():
    return (datetime.now(timezone.utc) - EPOCH) // ONE_MS


def when(ms):
    """The UTC datetime of an epoch-milliseconds time."""
    return EPOCH + timedelta(milliseconds=ms)
