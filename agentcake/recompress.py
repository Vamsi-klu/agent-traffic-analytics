"""Night work on the replay chunks: recompress old sessions, and give back the disk of dropped chunks.

run(now_ms) recompresses up to recompress_sessions_per_run sessions whose newest chunk is recompress_after_days old
and that have chunks not yet archived and no open window: each stream of the session becomes one chunk at the
codec's archive level (zstd-19, zlib-9). A whole session compresses much better than its 10-second pieces (measured on
recorded sessions: zstd-19 is 21-69% smaller than zstd-3, more again on whole sessions). The lines are copied as stored, style
references and page views included, so a read gives back exactly the same events. The slow compression runs without
store.LOCK; the lock is taken only to append the new chunk and swap the rows, and a session that changed meanwhile is
left for the next night.

reclaim(con, now_ms) gives the space of dropped or replaced chunks back: a file no chunk points into is deleted; a
file at least compact_min_dead_share dead has its live chunks copied, unchanged, into the current hour's file and is
deleted; then styles.gc_styles() drops stylesheets no chunk refers to. The current hour's file is never touched. The caller holds
store.LOCK and has committed; reclaim commits after moving each file's chunks, before deleting it. maintenance.py
runs both at night, and space.reclaim_if_due() runs reclaim() at its next round, by day too, once chunks were dropped
(space freed, a retention). chunk_files(root) lists the chunk files and their sizes.
"""
import os
from collections import namedtuple

from agentcake import codecs, replay_chunks, store, streams, styles
from agentcake.storage_config import SETTINGS, ms_from_days

# The chunks row fields an archive chunk is planned from; the SELECT lists these fields in this order.
_Chunk = namedtuple("_Chunk", "id t_start t_end n_events styles")


def due_sessions(con, now_ms, cfg=SETTINGS):
    cut = now_ms - ms_from_days(cfg["recompress_after_days"])
    return [sid for (sid,) in con.execute(
        """SELECT session_id FROM chunks WHERE session_id NOT IN (SELECT session_id FROM open_chunks)
           GROUP BY session_id HAVING MAX(created_ms) <= ? AND MIN(archived) = 0 ORDER BY MAX(created_ms) LIMIT ?""",
        (cut, cfg["recompress_sessions_per_run"]))]


def run(now_ms, cfg=SETTINGS):
    """Recompress the sessions that are due; returns how many were rewritten. Do not hold store.LOCK."""
    con = store.db()
    try:
        return sum(recompress_session(con, sid, now_ms, cfg) for sid in due_sessions(con, now_ms, cfg))
    finally:
        con.close()


def recompress_session(con, session_id, now_ms, cfg=SETTINGS):
    """Rewrite each stream of one session as a single archive chunk; returns 1 when done, 0 when it changed
    meanwhile."""
    codec = codecs.writer_codec(cfg)
    level = codecs.level_for(codec, "archive", cfg)
    plans = [_plan(con, session_id, stream, codec, level, cfg) for (stream,) in con.execute(
        "SELECT DISTINCT stream FROM chunks WHERE session_id=? ORDER BY stream", (session_id,)).fetchall()]
    with store.LOCK:
        if any(_chunk_ids(con, session_id, plan["meta"]["stream"]) != plan["ids"] for plan in plans):
            return 0
        for plan in plans:
            ref = replay_chunks.append_chunk(plan["blob"], plan["raw"], now_ms, cfg)
            con.executemany("DELETE FROM chunks WHERE id=?", [(i,) for i in plan["ids"]])
            streams.record_chunk(con, plan["meta"], ref, codec, level, plan["styles"], 1, now_ms)
        con.commit()
    return 1


def reclaim(con, now_ms, cfg=SETTINGS):
    """Delete or rewrite chunk files with dead space (at least compact_min_dead_share of the file); returns {deleted,
    compacted, freed_bytes, styles}."""
    if con.in_transaction:
        raise RuntimeError("commit the dropped chunks before reclaim(): their files are deleted from committed state")
    live = {f: size for f, size in con.execute("SELECT file, SUM(byte_length) FROM chunks GROUP BY file")}
    current, root = replay_chunks.file_for(now_ms), replay_chunks.replay_dir(cfg)
    share = cfg["compact_min_dead_share"]
    result = {"deleted": 0, "compacted": 0, "freed_bytes": 0}
    for rel, size in list(chunk_files(root)):  # listed first: moving chunks adds to the current hour's file
        if rel == current:
            continue
        dead = size - live.get(rel, 0)
        if rel not in live:
            result["deleted"] += 1
        elif dead > 0 and dead >= share * size:
            _move_chunks(con, rel, now_ms, cfg)
            result["compacted"] += 1
        else:
            continue
        os.remove(os.path.join(root, rel))
        result["freed_bytes"] += dead
    _remove_empty_folders(root)
    result["styles"] = styles.gc_styles(con)
    con.commit()
    return result


def _plan(con, session_id, stream, codec, level, cfg):
    """The archive chunk of one stream, built without the lock: its bytes, the rows it replaces, its styles."""
    chunks = [_Chunk._make(row) for row in con.execute(
        f"SELECT {', '.join(_Chunk._fields)} FROM chunks WHERE session_id=? AND stream=?", (session_id, stream))]
    meta = {"session": session_id, "stream": stream, "t0": min(chunk.t_start for chunk in chunks),
            "t1": max(chunk.t_end for chunk in chunks), "n": sum(chunk.n_events for chunk in chunks)}
    read = [0]

    def lines():
        for ts, text, refs, page in streams.stored_lines(con, session_id, stream, cfg, with_page=True):
            read[0] += 1
            yield replay_chunks.encode_line(ts, text, refs, page)

    blob, raw = replay_chunks.build_chunk(meta, lines(), codec, level)
    if read[0] != meta["n"]:
        raise replay_chunks.ChunkError(f"{session_id}/{stream}: read {read[0]} events, its chunks say {meta['n']}")
    used = {digest for chunk in chunks if chunk.styles for digest in chunk.styles.split()}
    return {"meta": meta, "ids": sorted(chunk.id for chunk in chunks), "styles": used, "blob": blob, "raw": raw}


def _chunk_ids(con, session_id, stream):
    return [i for (i,) in con.execute("SELECT id FROM chunks WHERE session_id=? AND stream=? ORDER BY id",
                                      (session_id, stream))]


def _move_chunks(con, rel, now_ms, cfg):
    """Copy a file's live chunks into the current hour's file and point their rows there (committed)."""
    for chunk_id, offset, length in con.execute("SELECT id, byte_offset, byte_length FROM chunks WHERE file=? "
                                                "ORDER BY byte_offset", (rel,)).fetchall():
        new_rel, new_offset = replay_chunks.copy_chunk(rel, offset, length, now_ms, cfg)
        con.execute("UPDATE chunks SET file=?, byte_offset=? WHERE id=?", (new_rel, new_offset, chunk_id))
    con.commit()


def chunk_files(root):
    """(path relative to root with / separators, size) of every chunk file."""
    for folder, _, names in os.walk(root):
        for name in sorted(names):
            if name.endswith(".bin"):
                path = os.path.join(folder, name)
                yield os.path.relpath(path, root).replace(os.sep, "/"), os.path.getsize(path)


def _remove_empty_folders(root):
    for folder, dirs, names in os.walk(root, topdown=False):
        if folder != root and not dirs and not names:
            os.rmdir(folder)
