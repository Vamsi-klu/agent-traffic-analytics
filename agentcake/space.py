"""The disk rules (carried over from cake 0.3.4, the floor changed in 0.4.0): a budget for cake's data,
freeing space from human-only replays, and a floor of free space on the disk.

used_bytes(con) is what cake's data takes: the database's pages in use plus the live replay chunks, whose total
SQLite keeps on every write (the totals table in schema.sql), so collect can ask on every batch. space_status() gives
used, budget, share, the warning from budget_warn_ratio on, full, days until full at the pace of the last
budget_pace_days, the disk's total and free bytes against disk_min_free_mb, and why new replays are stopped, if they
are ("disk": below the floor with auto_free off; "disk_full_other": below the floor and other files fill the disk;
"budget"). /api/health and /api/settings return it.

room_for_replay() is collect's question before it stores a batch's rrweb replay events; raw input and environment
signals are stored either way, because verdicts are made from them.

The budget: when it is full and auto_free is on, free_space() removes the replays of the oldest human-only sessions
quiet for auto_free_quiet_ms (never a session an agent took part in or one cake is unsure about), down to
auto_free_target_ratio of the budget; with auto_free off, or nothing left to free, no new replay is stored.

The floor: while the disk holding the data folder has less than disk_min_free_mb free, new replays are still
stored as long as auto_free is on and room can be made. free_disk() removes the replays of the oldest human-only
sessions quiet for auto_free_quiet_ms, then those of the oldest other sessions quiet as long (an agent's, a mixed or
an unsure one), until the free space plus the dead bytes of the chunk files reaches the floor, at most
auto_free_batch_sessions per round. Counting the dead bytes, which the next reclaim gives back, keeps a round from
removing more replays while the bytes of the last ones are still on their way back. Collect asks at most once per
maintenance_tick_ms (the answer is kept in the settings table, DISK_ANSWER: listing the chunk files and finding the
oldest replays is too much for every batch), except right after a round that removed a full batch: then the next
batch goes on. With auto_free off new replays stop.

Before removing any, free_disk() checks that removing every replay it may would reach the floor: the free space,
the dead bytes and those replays' chunk bytes together (_replay_bytes_to_free). If not, other files fill the disk
and it removes none: new replays stop until there is room, then start again on their own. PostHog 1.0.0 has
no rule that deletes data for disk space and today's PostHog expires data by age; Elasticsearch at its flood-stage
watermark stops writing and deletes nothing; a deletion cannot be undone and would not free a disk others fill.

Dropping a replay deletes its rows at once (streams.drop_replay); reclaim_if_due(), which every maintenance round
runs, then gives the chunk files' bytes back (recompress.reclaim). After freeing for the floor (RECLAIM_ALL) it
rewrites every file with dead bytes, not only those compact_min_dead_share dead: a replay is about a quarter of what
a visit stores (measured on our lab's sessions), so a file whose replays were all dropped
would otherwise keep their bytes. The thresholds are settings (budget_*, auto_free_*, disk_min_free_mb: defaults.json);
the replay streams are storage.json's replay_streams.
"""
import shutil

from agentcake import paths, recompress, replay_chunks, store, streams
from agentcake.config import DEFAULTS
from agentcake.storage_config import SETTINGS, now_ms as clock_ms
from agentcake.units import BYTES_PER_MB, MS_PER_DAY, PERCENT

# A human-only session: judged after its last event, a Human by the four layers' verdict (no automation trace,
# no agent name, every action a human's), and no stretch or name of an agent or bot in the newer tables (segments,
# labels). A session cake 0.3.4's judge decided (no verdict_class yet) keeps 0.3.4's test until it is judged anew: a
# human all the way (no agent share), its source not an agent's (no self-declared name, no automation flag, no server
# verdict, no agent IP range: group H1/L?). Only these sessions' replays are removed to keep the budget, oldest first,
# once quiet for auto_free_quiet_ms; below the disk's floor theirs go first, then the oldest of the others.
HUMAN_ONLY = ("(verdict_class='human' OR (verdict_class IS NULL AND verdict='human' AND COALESCE(agent_pct,0)=0 "
              "AND group_id='H1/L?')) AND judged_ms>=end_ms AND replay_freed_ms IS NULL "
              "AND NOT EXISTS (SELECT 1 FROM segments g WHERE g.session_id=sessions.id "
              "AND g.actor NOT IN ('human','unsure')) "
              "AND NOT EXISTS (SELECT 1 FROM labels l WHERE l.session_id=sessions.id)")
DISK_ANSWER = "disk_room"  # settings key: {"ms": when collect last asked about a disk below its floor, "room"}
RECLAIM_ALL = "reclaim_all_dead_ms"  # settings key: the next reclaim rewrites every file with dead bytes


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
    """Remove the replays of the oldest human-only sessions until cake's data is at auto_free_target_ratio of its
    budget, checking after each one. Their raw input, environment signals, sessions rows (verdict, shares, timeline),
    segments and srv rows stay. Returns how many replays were removed; the caller commits."""
    now = clock_ms() if now is None else now
    target, freed = c["auto_free_target_ratio"] * budget_bytes(c), 0
    while used_bytes(con) > target:
        oldest = _freeable(con, c, now, c["auto_free_batch_sessions"])
        if not oldest:
            break
        for sid in oldest:
            _remove_replay(con, sid, now)
            freed += 1
            if used_bytes(con) <= target:
                break
    if freed:
        store.mark_reclaim_due(con, now)
    return freed


def free_disk(con, c, disk, now=None):
    """Make room on a disk below its floor (disk: disk_space()'s answer) if removing replays can: remove the
    replays of the oldest sessions quiet for auto_free_quiet_ms, human-only ones first, until the free space plus the
    chunk files' dead bytes reaches the floor, at most auto_free_batch_sessions of them, and have the next reclaim
    rewrite every file with dead bytes; none when even all of those replays would leave the disk short. What else a
    session holds stays, as with free_space(). Returns (room, removed): whether new replays may be stored (the floor
    is reached, or a full batch went and the next round can go on) and the sessions whose replay went, in that order.
    The caller commits."""
    now = clock_ms() if now is None else now
    dead_now, dead_later = dead_bytes(con, now)
    short, removed = disk["min_free"] - disk["free"] - dead_now - dead_later, []
    if 0 < short <= _replay_bytes_to_free(con, c, now):
        for sid in _oldest_replays(con, c, now, c["auto_free_batch_sessions"]):
            short -= _remove_replay(con, sid, now)
            removed.append(sid)
            if short <= 0:
                break
    if removed or dead_now:
        store.mark_reclaim_due(con, now)
        store.set_setting(con, RECLAIM_ALL, now, now)
    return short <= 0 or len(removed) == c["auto_free_batch_sessions"], removed


def disk_room(con, c, disk, now=None):
    """Whether new replays may be stored on a disk below its floor, changing nothing (space_status, doctor): auto_free
    is on, and the dead bytes make up for what is missing, alone or with the replays free_disk() may remove."""
    if not c["auto_free"]:
        return False
    now = clock_ms() if now is None else now
    short = disk["min_free"] - disk["free"] - sum(dead_bytes(con, now))
    return short <= 0 or short <= _replay_bytes_to_free(con, c, now)


def dead_bytes(con, now):
    """(in the files before the current hour's, in the current hour's file): the chunk files' bytes no live chunk
    holds (dropped, replaced or wiped chunks). A reclaim that rewrites every file with dead bytes gives the first
    back; the current hour's file is never rewritten while it grows, so its dead bytes come back after the hour."""
    current = replay_chunks.file_for(now)
    sizes = dict(recompress.chunk_files(replay_chunks.replay_dir()))
    growing = sizes.pop(current, 0)
    live_now = con.execute("SELECT COALESCE(SUM(byte_length), 0) FROM chunks WHERE file=?", (current,)).fetchone()[0]
    live = con.execute("SELECT value FROM totals WHERE name='chunk_bytes'").fetchone()[0]
    return max(0, sum(sizes.values()) - (live - live_now)), max(0, growing - live_now)


def room_for_replay(con, c, now=None, usage=None):
    """Whether a batch's rrweb replay events may be stored. On a disk below its floor only if room is made
    (_room_on_low_disk). A full budget is first freed if allowed; if still full, no. Either way the visit, its small
    events, raw input, environment signals and verdict are still recorded."""
    now = clock_ms() if now is None else now
    disk = disk_space(c, usage)
    if disk["low"] and not _room_on_low_disk(con, c, disk, now):
        return False
    budget = budget_bytes(c)
    if used_bytes(con) < budget:
        return True
    if c["auto_free"]:
        free_space(con, c, now)
    return used_bytes(con) < budget


def space_status(con, c, now=None, usage=None):
    """Used, budget, share, warning, full, days until full at the pace of the last budget_pace_days (None when nothing
    was added), replays freed so far, auto_free, the disk, and why new replays are stopped (None, "disk",
    "disk_full_other", "budget")."""
    now = clock_ms() if now is None else now
    used, budget, days_back = used_bytes(con), budget_bytes(c), c["budget_pace_days"]
    recent, total = _recorded_bytes(con, now - days_back * MS_PER_DAY)
    per_day = (recent * (used / total if total else 1)) / days_back if recent else 0
    days = max(0.0, (budget - used) / per_day) if per_day else None
    freed = con.execute("SELECT COUNT(*) FROM sessions WHERE replay_freed_ms IS NOT NULL").fetchone()[0]
    full, disk = used >= budget, disk_space(c, usage)
    disk_stop = "disk_full_other" if c["auto_free"] else "disk"  # with auto_free on, no room means other files
    stopped = (disk_stop if disk["low"] and not disk_room(con, c, disk, now) else
               "budget" if full and not (c["auto_free"] and _freeable(con, c, now, 1)) else None)
    return {"used": used, "budget": budget, "pct": round(PERCENT * used / budget, 1) if budget else 0,
            "days_left": days, "warn": used >= c["budget_warn_ratio"] * budget, "full": full, "freed": freed,
            "auto_free": bool(c["auto_free"]), "disk": disk, "replays_stopped": stopped}


def reclaim_if_due(con, now_ms, cfg=SETTINGS):
    """Give back the file space of the chunks dropped since the last reclaim (freeing space, a retention, a deletion):
    every maintenance round runs this, by day as well as at night, so the bytes do not wait for a quiet night. After
    freeing for the disk's floor (RECLAIM_ALL) every file with dead bytes is rewritten. Returns recompress.reclaim()'s
    result, or None when nothing was dropped. The caller holds store.LOCK and has committed."""
    if store.setting(con, store.RECLAIM_DUE) is None:
        return None
    result = recompress.reclaim(con, now_ms, cfg, every_dead=store.setting(con, RECLAIM_ALL) is not None)
    store.delete_setting(con, store.RECLAIM_DUE)
    store.delete_setting(con, RECLAIM_ALL)
    con.commit()
    return result


def _room_on_low_disk(con, c, disk, now):
    """Collect's answer for a disk below its floor: no with auto_free off, else free_disk()'s, asked at most once per
    maintenance_tick_ms, or at the next batch after a round that removed a full batch."""
    if not c["auto_free"]:
        return False
    answer = store.setting(con, DISK_ANSWER)
    if answer and 0 <= now - answer["ms"] < SETTINGS["maintenance_tick_ms"]:
        return answer["room"]
    room, removed = free_disk(con, c, disk, now)
    if len(removed) == c["auto_free_batch_sessions"]:
        store.delete_setting(con, DISK_ANSWER)
    else:
        store.set_setting(con, DISK_ANSWER, {"ms": now, "room": room}, now)
    return room


def _remove_replay(con, sid, now):
    """Drop one session's replay (streams.drop_replay) and note when; returns the bytes it took."""
    dropped = streams.drop_replay(con, sid)
    con.execute("UPDATE sessions SET replay_freed_ms=? WHERE id=?", (now, sid))
    return dropped


def _freeable(con, c, now, limit):
    """Up to `limit` human-only sessions quiet for auto_free_quiet_ms that still have a replay to free, oldest first
    (the budget)."""
    names = SETTINGS["replay_streams"]
    return [sid for (sid,) in con.execute(
        f"SELECT id FROM sessions WHERE {HUMAN_ONLY} AND end_ms < ? AND {_has_replay(names)} ORDER BY end_ms, id LIMIT ?",
        (now - c["auto_free_quiet_ms"], *names, *names, limit))]


def _oldest_replays(con, c, now, limit):
    """Up to `limit` sessions quiet for auto_free_quiet_ms that still have a replay, human-only ones first, each kind
    oldest first (the disk's floor deletes by the oldest session replay)."""
    names = SETTINGS["replay_streams"]
    return [sid for (sid,) in con.execute(
        f"SELECT id FROM sessions WHERE end_ms < ? AND {_has_replay(names)} "
        f"ORDER BY CASE WHEN {HUMAN_ONLY} THEN 0 ELSE 1 END, end_ms, id LIMIT ?",
        (now - c["auto_free_quiet_ms"], *names, *names, limit))]


def _replay_bytes_to_free(con, c, now):
    """The bytes the disk gets back, at the reclaim after, if free_disk() removes every replay it may: the sealed
    chunks of the replay streams of every session quiet for auto_free_quiet_ms (_oldest_replays' sessions). Their open
    windows and 0.3.4 replay rows are rows in cake.db, whose pages SQLite keeps for itself when they are deleted: the
    disk gets nothing back from them, so they do not count. CROSS JOIN keeps the sessions as SQLite's outer loop,
    so chunks_s reads only their replay chunks instead of scanning raw input and signals too (about half the time on
    two million chunks)."""
    names = SETTINGS["replay_streams"]
    marks = ",".join("?" * len(names))
    return con.execute(
        f"SELECT COALESCE(SUM(c.byte_length), 0) FROM sessions s CROSS JOIN chunks c "
        f"ON c.session_id = s.id AND c.stream IN ({marks}) WHERE s.end_ms < ?",
        (*names, now - c["auto_free_quiet_ms"])).fetchone()[0]


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
