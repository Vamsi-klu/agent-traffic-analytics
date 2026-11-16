"""The disk rules: a budget for cake's data, freeing room by deleting the oldest session replays, and a floor of free
space on the disk.

used_bytes(con) is what cake's data takes: the database's pages in use plus the live replay chunks, whose total
SQLite keeps on every write (the totals table in schema.sql), so collect can ask on every batch. space_status() gives
used, budget, share, the warning from budget_warn_ratio on, full, days until full at the pace of the last
budget_pace_days, the disk's total and free bytes against disk_min_free_mb, and why new replays are stopped, if they
are ("disk": the disk is below its floor; "budget": the budget is full and nothing is left to free). /api/health and
/api/settings return it.

room_for_replay() is collect's question before it stores a batch's rrweb replay events; raw input and environment
signals are stored either way, because verdicts are made from them.

The budget, one rule: once cake's data reaches auto_free_target_ratio of it (less than the rest of the budget is left)
and auto_free is on, free_space() deletes session replays, the oldest first, of every kind of session alike, until the
data is under auto_free_target_ratio again. A replay still being recorded (its session active in the last
auto_free_quiet_ms) waits until it is quiet: deleting it would cut the replay being written; this favours no kind of
session. So does one whose verdict is older than its data (judged_ms < end_ms: judging failed or is behind): a freed
replay is never judged again (judging.rejudge), so its verdict waits for the replay it is made from. A session's raw
input, environment signals, verdict, shares, timeline and server half always stay. With
auto_free off, or nothing left to delete, no new replay is stored once the budget is full.

The floor: while the disk holding the data folder has less than disk_min_free_mb free, no new replay is stored and no
replay is deleted for it; new replays start again on their own once there is room. PostHog 1.0.0 has no rule that
deletes data for disk space and today's PostHog expires data by age; Elasticsearch at its flood-stage watermark stops
writing and deletes nothing; a deletion cannot be undone and would not free a disk other files fill.

Dropping a replay deletes its rows at once (streams.drop_replay); reclaim_if_due(), which every maintenance round
runs, then gives the chunk files' bytes back (recompress.reclaim). The thresholds are settings (budget_*, auto_free_*,
disk_min_free_mb: defaults.json); the replay streams are storage.json's replay_streams.
"""
import shutil

from agentcake import paths, recompress, replay_chunks, store, streams
from agentcake.config import DEFAULTS
from agentcake.storage_config import SETTINGS, now_ms as clock_ms
from agentcake.units import BYTES_PER_MB, MS_PER_DAY, PERCENT


def used_bytes(con):
    """Bytes cake's data takes: the database's pages minus the free ones (SQLite reuses freed pages; the file does not
    shrink), plus the live chunks (what a dropped chunk leaves in its file comes back at the next reclaim)."""
    pages = con.execute("PRAGMA page_count").fetchone()[0] - con.execute("PRAGMA freelist_count").fetchone()[0]
    chunks = con.execute("SELECT value FROM totals WHERE name='chunk_bytes'").fetchone()[0]
    return pages * con.execute("PRAGMA page_size").fetchone()[0] + chunks


def budget_bytes(c):
    # float: a budget of a fraction of a MB (the tests' tiny databases) is kept, not rounded down to whole MB
    return int(float(c.get("budget_mb", DEFAULTS["budget_mb"])) * BYTES_PER_MB)


def disk_space(c, usage=None):
    """The disk new chunks are written to: total and free bytes, the floor (disk_min_free_mb) and whether free space
    is below it. Before the data folder exists (doctor before the first start, or after the folder was deleted) it is
    the disk of the nearest folder above it that exists, where it will be made. usage stands in for
    shutil.disk_usage (the tests' nearly full disks)."""
    total, _, free = (usage or shutil.disk_usage)(paths.nearest_existing(replay_chunks.replay_dir()))
    floor = int(float(c["disk_min_free_mb"]) * BYTES_PER_MB)
    return {"total": total, "free": free, "min_free": floor, "low": free < floor}


def free_space(con, c, now=None):
    """Delete session replays, the oldest first whatever the kind of session, until cake's data is under
    auto_free_target_ratio of its budget, checking after each one; a replay still being recorded waits (_freeable).
    Their raw input, environment signals, sessions rows (verdict, shares, timeline), segments and srv rows stay.
    Returns how many replays were deleted; the caller commits."""
    now = clock_ms() if now is None else now
    target, freed = c["auto_free_target_ratio"] * budget_bytes(c), 0
    while used_bytes(con) >= target:
        oldest = _freeable(con, c, now, c["auto_free_batch_sessions"])
        if not oldest:
            break
        for sid in oldest:
            _remove_replay(con, sid, now)
            freed += 1
            if used_bytes(con) < target:
                break
    if freed:
        store.mark_reclaim_due(con, now)
    return freed


def room_for_replay(con, c, now=None, usage=None):
    """Whether a batch's rrweb replay events may be stored: not while the disk is below its floor (no replay is deleted
    for it); from auto_free_target_ratio of the budget on, the oldest replays are deleted first when auto_free allows;
    then yes while the budget isn't full. Either way the visit, its small events, raw input, environment signals and
    verdict are still recorded."""
    now = clock_ms() if now is None else now
    if disk_space(c, usage)["low"]:
        return False
    budget = budget_bytes(c)
    if c["auto_free"] and used_bytes(con) >= c["auto_free_target_ratio"] * budget:
        free_space(con, c, now)
    return used_bytes(con) < budget


def space_status(con, c, now=None, usage=None):
    """Used, budget, share, warning, full, days until full at the pace of the last budget_pace_days (None when nothing
    was added), replays freed so far, auto_free, the disk, and why new replays are stopped (None, "disk", "budget")."""
    now = clock_ms() if now is None else now
    used, budget, days_back = used_bytes(con), budget_bytes(c), c["budget_pace_days"]
    recent, total = _recorded_bytes(con, now - days_back * MS_PER_DAY)
    per_day = (recent * (used / total if total else 1)) / days_back if recent else 0
    days = max(0.0, (budget - used) / per_day) if per_day else None
    freed = con.execute("SELECT COUNT(*) FROM sessions WHERE replay_freed_ms IS NOT NULL").fetchone()[0]
    full, disk = used >= budget, disk_space(c, usage)
    stopped = ("disk" if disk["low"] else
               "budget" if full and not (c["auto_free"] and _freeable(con, c, now, 1)) else None)
    return {"used": used, "budget": budget, "pct": round(PERCENT * used / budget, 1) if budget else 0,
            "days_left": days, "warn": used >= c["budget_warn_ratio"] * budget, "full": full, "freed": freed,
            "auto_free": bool(c["auto_free"]), "disk": disk, "replays_stopped": stopped}


def reclaim_if_due(con, now_ms, cfg=SETTINGS):
    """Give back the file space of the chunks dropped since the last reclaim (freeing space, a retention, a deletion):
    every maintenance round runs this, by day as well as at night, so the bytes do not wait for a quiet night. Returns
    recompress.reclaim()'s result, or None when nothing was dropped. The caller holds store.LOCK and has committed."""
    if store.setting(con, store.RECLAIM_DUE) is None:
        return None
    result = recompress.reclaim(con, now_ms, cfg)
    store.delete_setting(con, store.RECLAIM_DUE)
    con.commit()
    return result


def _remove_replay(con, sid, now):
    """Drop one session's replay (streams.drop_replay) and note when; returns the bytes it took."""
    dropped = streams.drop_replay(con, sid)
    con.execute("UPDATE sessions SET replay_freed_ms=? WHERE id=?", (now, sid))
    return dropped


def _freeable(con, c, now, limit):
    """Up to `limit` sessions that still have a replay to delete, the oldest first whatever their kind, but none active
    in the last auto_free_quiet_ms (a replay still being recorded is never cut) and none whose verdict is older than its
    data (see the module docstring)."""
    names = SETTINGS["replay_streams"]
    return [sid for (sid,) in con.execute(
        f"SELECT id FROM sessions WHERE end_ms < ? AND judged_ms >= end_ms AND {_has_replay(names)} "
        "ORDER BY end_ms, id LIMIT ?",
        (now - c["auto_free_quiet_ms"], *names, *names, limit))]


def _has_replay(names):
    """The SQL condition, with `names` twice as its arguments, of a session that still has a replay to free: chunks
    or an open window of these streams, or 0.3.4 replay rows."""
    marks = ",".join("?" * len(names))
    return (f"(EXISTS (SELECT 1 FROM chunks c WHERE c.session_id=sessions.id AND c.stream IN ({marks})) "
            f"OR EXISTS (SELECT 1 FROM open_chunks o WHERE o.session_id=sessions.id AND o.stream IN ({marks})) "
            f"OR EXISTS (SELECT 1 FROM events e WHERE e.session_id=sessions.id AND {streams.OLD_REPLAY_ROW}))")


def _recorded_bytes(con, since):
    """(bytes recorded since `since`, all bytes): sealed chunks of every stream by the time of their last event (a
    session the night recompression rewrote keeps its times), open windows, and the events table's rows (small events
    and 0.3.4 replay rows, by their time, as 0.3.4 counted them)."""
    parts = (("byte_length", "t_end", "chunks"), ("LENGTH(CAST(lines AS BLOB))", "t_end", "open_chunks"),
             ("LENGTH(CAST(body AS BLOB))", "ts", "events"))
    recent = total = 0
    for size, at, table in parts:
        since_then, everything = con.execute(f"SELECT COALESCE(SUM(CASE WHEN {at} >= ? THEN {size} END), 0), "
                                             f"COALESCE(SUM({size}), 0) FROM {table}", (since,)).fetchone()
        recent, total = recent + since_then, total + everything
    return recent, total
