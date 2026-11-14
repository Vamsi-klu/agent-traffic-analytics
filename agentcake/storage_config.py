"""The storage parameters: agentcake/data/storage.json, read once when the package is imported.

SETTINGS holds the chunk length, the compression codec and levels, the folder names, the night recompression rules
and the CSS de-duplication switch; the storage modules take every number from it. Functions whose behaviour a test
varies take a `cfg` argument that defaults to SETTINGS. ms_from_days() and when() turn days and epoch milliseconds
into the units the code needs without unit literals.
"""
import json
import os
from datetime import datetime, timedelta, timezone

from agentcake import paths

STORAGE_FILE = os.path.join(paths.PACKAGE_DIR, "data", "storage.json")
ONE_MS = timedelta(milliseconds=1)
EPOCH = datetime.fromtimestamp(0, timezone.utc)

with open(STORAGE_FILE, encoding="utf-8") as f:
    SETTINGS = json.load(f)


def ms_from_days(days):
    return timedelta(days=days) // ONE_MS


def now_ms():
    return (datetime.now(timezone.utc) - EPOCH) // ONE_MS


def when(ms):
    """The UTC datetime of an epoch-milliseconds time."""
    return EPOCH + timedelta(milliseconds=ms)
