"""`agentcake migrate`: a cake 0.3.4 database into the new storage, keeping everything 0.3.4 had.

cake 0.3.4 kept every rrweb event of a replay as an uncompressed row of the events table. migrate():

1. stops when cake is running on this data folder (it writes the same files), when there is nothing to copy, or when
   the disk cannot hold a backup (backup_free_space_factor times the database);
2. backs cake.db up with SQLite's backup API to backups/cake-<UTC time>Z.db and checks the copy (integrity_check,
   the same row counts) before anything changes;
3. opens the database the new way (store.db(): WAL mode, the new tables);
4. copies each session's replay rows its rrweb chunks do not hold yet, oldest first (rows of the same millisecond in
   the order they were written), into rrweb chunks (streams.append, then seal), and checks them: a session that had
   no chunks reads back as its rows byte for byte; one that had (a visit that went on after the upgrade, which the
   new collect wrote into chunks; or rows 0.3.4 added after an earlier migrate) holds every row once more
   than before, and no chunk is deleted. A row and its copy are the same time and the same JSON text
   (session_replay.py). A session that fails is rolled back and reported, the others go on; a session whose rows
   are all in its chunks is skipped;
5. records what it did in the settings table (key "migration").

The 0.3.4 rows stay, for a cake 0.3.4 the person may go back to: session_replay.py gives each of them once next to
its copy (to judging and the replay page), space.py counts them in the disk budget, and streams.drop_replay() removes
both together. dry_run says what would be done and changes nothing. Returns the exit code: 0 when everything was
copied or nothing was to do, 1 otherwise.
"""
import os
import shutil
import sqlite3
from itertools import zip_longest

from agentcake import daemon, paths, store, streams
from agentcake.session_replay import OLD_ROWS, STREAM, stream_keys, take
from agentcake.storage_config import SETTINGS, now_ms as clock_ms, when

CHECKED_TABLES = ("sessions", "events", "srv")
_MISSING = object()  # what zip_longest gives when the rows and their copy end apart; it equals nothing else


class BackupFailed(RuntimeError):
    """The backup copy does not match the database: nothing was changed."""


def migrate(dry_run=False, now_ms=None, cfg=SETTINGS):
    now_ms = clock_ms() if now_ms is None else now_ms
    db = paths.db_file()
    if not os.path.exists(db):
        print(f"no database at {paths.tilde(db)}: nothing to migrate")
        return 0
    if daemon.running_here():
        print(f"cake is running on this data folder; stop it first ({paths.launcher()} stop), then migrate")
        return 1
    todo = _sessions_to_copy(db)
    if not todo:
        print("nothing to migrate: every replay is already in chunks")
        return 0
    events = sum(n for _, n in todo)
    if dry_run:
        print(f"would back up {paths.tilde(db)}, then copy {len(todo)} sessions, {events} replay events into chunks")
        return 0
    need, free = _database_bytes(db) * cfg["backup_free_space_factor"], shutil.disk_usage(paths.home()).free
    if free < need:
        print(f"not enough free disk for the backup: {free:,} bytes free, {int(need):,} needed; nothing was changed")
        return 1
    try:
        backup, counts = _backup(db, now_ms, cfg)
    except BackupFailed as e:
        print(f"{e}; nothing was changed")
        return 1
    print(f"backup: {paths.tilde(os.path.join(paths.home(), backup))} (checked: "
          + ", ".join(f"{n} {table} rows" for table, n in counts.items()) + ")")
    return _copy_all(todo, backup, now_ms, cfg)


def _copy_all(todo, backup, now_ms, cfg):
    con = store.db()
    try:
        copied, failed = [], []
        for sid, _ in todo:
            try:
                copied.append((sid, _copy_session(con, sid, now_ms, cfg)))
                con.commit()
            except ValueError as e:  # a row that is not one line of JSON, or a copy that reads back differently
                con.rollback()
                failed.append(f"{sid}: {e}")
        ids = [sid for sid, _ in copied]
        rows_bytes, chunk_bytes, chunks = _sizes(con, ids)
        events = sum(n for _, n in copied)
        store.set_setting(con, "migration", {"from": "0.3.4", "at_ms": now_ms, "backup": backup,
                                             "sessions": len(copied), "events": events, "row_bytes": rows_bytes,
                                             "chunk_bytes": chunk_bytes, "failed": failed}, now_ms)
        con.commit()
    finally:
        con.close()
    print(f"copied {len(copied)} sessions, {events} replay events into {chunks} chunks: {rows_bytes:,} bytes of rows "
          f"-> {chunk_bytes:,} bytes of chunks in {paths.tilde(os.path.join(paths.home(), cfg['replay_dir']))}")
    print("the 0.3.4 replay rows stay in cake.db; cake 0.3.4's pages still read them")
    for line in failed:
        print(f"not copied (left as it was): {line}")
    return 1 if failed else 0


def _copy_session(con, sid, now_ms, cfg):
    """Copy the rows of one session its chunks do not hold yet next to those chunks, and check; returns how many."""
    fresh = streams.event_count(con, sid, STREAM) == 0
    have = None if fresh else stream_keys(con, sid)
    cursor, n = con.cursor().execute(OLD_ROWS, (sid,)), 0
    while True:
        rows = cursor.fetchmany(cfg["migrate_batch_rows"])
        if not rows:
            break
        todo = [(ts or 0, body) for ts, body in rows if fresh or not take(have, ts or 0, body)]
        streams.append(con, sid, STREAM, todo, now_ms, cfg)
        n += len(todo)
    streams.seal(con, now_ms, force=True, session_id=sid, cfg=cfg)
    if fresh:
        _check_same(con, sid, cfg)
    else:
        _check_held(con, sid)
    return n


def _check_same(con, sid, cfg):
    """A session that had no chunks: they read back as its rows, byte for byte and in order."""
    bodies = (body for _, body in con.cursor().execute(OLD_ROWS, (sid,)))
    copies = (text for _, _, text in streams.read_events(con, sid, [STREAM], cfg=cfg))
    for index, (body, text) in enumerate(zip_longest(bodies, copies, fillvalue=_MISSING)):
        if body is _MISSING or text is _MISSING or body != text:
            raise ValueError(f"the copy differs from the rows at event {index}")


def _check_held(con, sid):
    """A session that had chunks: they now hold each of its rows (with the events they held before)."""
    have = stream_keys(con, sid)
    for index, (ts, body) in enumerate(con.cursor().execute(OLD_ROWS, (sid,))):
        if not take(have, ts or 0, body):
            raise ValueError(f"row {index} is not in the chunks after copying")


def _sessions_to_copy(db):
    """(session id, rows to copy) of each session whose rows are not all in its chunks yet. Reads only: a
    database 0.3.4 made has no chunks table, and every row is to copy."""
    con = sqlite3.connect(db)
    try:
        have_chunks = con.execute("SELECT 1 FROM sqlite_master WHERE name='chunks'").fetchone() is not None
        todo = []
        for sid, n in con.execute(f"SELECT session_id, COUNT(*) FROM events WHERE {streams.OLD_REPLAY_ROW} "
                                  "GROUP BY session_id ORDER BY MIN(ts)").fetchall():
            if have_chunks and streams.event_count(con, sid, STREAM):
                have = stream_keys(con, sid)
                n = sum(1 for ts, body in con.execute(OLD_ROWS, (sid,)) if not take(have, ts or 0, body))
            if n:
                todo.append((sid, n))
        return todo
    finally:
        con.close()


def _backup(db, now_ms, cfg):
    """Copy the database with SQLite's backup API and check the copy; returns (path under home, row counts)."""
    folder = os.path.join(paths.home(), cfg["backup_dir"])
    os.makedirs(folder, exist_ok=True)
    stamp = when(now_ms).strftime("cake-%Y%m%d-%H%M%SZ")
    name, n = f"{stamp}.db", 1
    while os.path.exists(os.path.join(folder, name)):
        n += 1
        name = f"{stamp}-{n}.db"
    path = os.path.join(folder, name)
    source, copy = sqlite3.connect(db), sqlite3.connect(path)
    try:
        source.backup(copy)
        counts = {t: source.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in CHECKED_TABLES}
        copied = {t: copy.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in CHECKED_TABLES}
        healthy = copy.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        copy.close()
        source.close()
    if not healthy or copied != counts:
        raise BackupFailed(f"the backup {paths.tilde(path)} does not match the database")
    return f"{cfg['backup_dir']}/{name}", counts


def _sizes(con, ids):
    """(bytes of the copied sessions' rows, bytes of their rrweb chunks, number of chunks)."""
    if not ids:
        return 0, 0, 0
    marks = ",".join("?" * len(ids))
    rows = con.execute(f"SELECT COALESCE(SUM(LENGTH(CAST(body AS BLOB))), 0) FROM events WHERE session_id IN ({marks}) "
                       f"AND {streams.OLD_REPLAY_ROW}", ids).fetchone()[0]
    size, count = con.execute(f"SELECT COALESCE(SUM(byte_length), 0), COUNT(*) FROM chunks WHERE stream=? "
                              f"AND session_id IN ({marks})", [STREAM, *ids]).fetchone()
    return rows, size, count


def _database_bytes(db):
    return sum(os.path.getsize(p) for p in (db, db + "-wal") if os.path.exists(p))
