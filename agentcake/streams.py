"""A session's recorded streams: rrweb replay, raw input and environment signals, kept as 10-second chunks.

cake.js sends a session's events in batches every few seconds, several streams at once. Every stream is kept
the same way, whatever its fields: events are grouped into windows of chunk_ms of their own time; a window stays
uncompressed in the open_chunks table while it can still grow, then it is sealed: sorted by time, its stylesheets
taken out (styles.py, rrweb only), compressed (zstd-3, or zlib without compression.zstd) and appended to the hour's
chunk file (replay_chunks.py); the chunks table keeps where. A window is sealed once the stream has events
seal_lag_ms past its end (cake.js has moved on), or after seal_idle_ms without new events (seal(), run by the
maintenance thread). Nothing is lost if cake stops: open windows are in the database, and every read includes them.

Raw input is a stream of chunks rather than a row per event: a minute of mouse and keyboard timing is about 1,300
events (lab session pwhhd-1), which as rows would cost more than the compressed replay (measured: 626 bytes per SQLite
row), and the behaviour features read it in time order next to the rrweb events, which is what a chunk gives. The events table keeps
only the small events a dashboard counts.

Each event can carry the page view it was recorded on (cake.js's `pv`; two tabs of one visit send events of
the same times), kept in its chunk line and given back by the reads with with_page=True.

Interfaces (writers hold store.LOCK and commit):
    append(con, session_id, stream, items, now_ms)       collect_store.py: one stream of a batch, items are
                                                         (ts_ms, event) or (ts_ms, event, page view)
    seal(con, now_ms, force=False, session_id=None)      maintenance.py: seal the windows that went quiet;
                                                         migrate.py: all of one session's, at once
    read_events(con, session_id, streams, t_from, t_to)  visit_batches.py, session_replay.py, migrate.py: (ts, stream,
                                                         JSON text), oldest first, read one chunk at a time; each
                                                         event byte for byte as written; with_page=True: (ts, stream,
                                                         JSON text, page view)
    event_count(con, session_id, stream)                 collect_store.py, migrate.py: how many events a session's
                                                         stream holds
    stored_lines(con, session_id, stream)                recompress.py: (ts, text, style refs) as stored, and the
                                                         page view with with_page=True
    record_chunk(con, ...)                               sealing, recompress.py: the chunks row of a chunk written
    replay_bytes(con, session_id=None, streams=None)     bytes a session's replay (or all replays) takes
    drop_replay(con, session_id, streams=None)           space.py: delete a session's replay (chunks, open
                                                         windows and 0.3.4 replay rows); its raw input and
                                                         environment signals, session, segments, srv, labels and
                                                         small events stay; recompress.reclaim() frees the files
    OLD_REPLAY_ROW                                       the SQL condition of a cake 0.3.4 replay row in events
The replay is the streams in replay_streams (rrweb): what freeing space removes. The raw input and
environment streams are what verdicts are made from, so they stay unless a caller names them in `streams`.
"""
import heapq
import json
import os
from collections import namedtuple
from operator import itemgetter

from agentcake import codecs, replay_chunks, styles
from agentcake.storage_config import SETTINGS, now_ms as clock_ms

# A 0.3.4 replay row in events: an rrweb event, so its body has no "kind" (small events always have one).
OLD_REPLAY_ROW = "(json_valid(body) = 0 OR json_extract(body, '$.kind') IS NULL)"

# The rows a read takes from the chunks and open_chunks tables; the SELECT lists these fields in this order.
_Chunk = namedtuple("_Chunk", "stream t_start t_end id file byte_offset byte_length styles")
_OpenWindow = namedtuple("_OpenWindow", "stream t_start t_end window_ms lines")


def append(con, session_id, stream, items, now_ms=None, cfg=SETTINGS):
    """Add one stream's events of a batch. items: (ts_ms, event) or (ts_ms, event, page view); an event is a str of
    one-line JSON text (stored byte for byte) or anything json can write (stored as compact JSON). Returns how many
    were added."""
    if stream not in cfg["streams"]:
        raise ValueError(f"unknown stream {stream!r}; cake keeps {', '.join(cfg['streams'])}")
    now_ms = clock_ms() if now_ms is None else now_ms
    size, windows, newest = cfg["chunk_ms"], {}, None  # windows: window start -> [(ts, line)], in arrival order
    for ts, event, *page in items:
        ts = int(ts)
        text = event if isinstance(event, str) else json.dumps(event, separators=(",", ":"), ensure_ascii=False)
        line = replay_chunks.encode_line(ts, text, page=page[0] if page else None)
        windows.setdefault(ts - ts % size, []).append((ts, line + replay_chunks.NEWLINE))
        newest = ts if newest is None else max(newest, ts)
    for start, events in windows.items():
        stamps = [ts for ts, _ in events]
        con.execute("""INSERT INTO open_chunks(session_id, stream, window_ms, t_start, t_end, n_events, lines,
                       updated_ms) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(session_id, stream, window_ms) DO UPDATE SET
                       t_start=MIN(t_start, excluded.t_start), t_end=MAX(t_end, excluded.t_end),
                       n_events=n_events+excluded.n_events, lines=lines||excluded.lines,
                       updated_ms=excluded.updated_ms""",
                    (session_id, stream, start, min(stamps), max(stamps), len(events),
                     "".join(line for _, line in events), now_ms))
    if newest is not None:  # the stream has moved this far: earlier windows are complete
        _seal_where(con, "session_id=? AND stream=? AND window_ms<=?",
                    (session_id, stream, newest - size - cfg["seal_lag_ms"]), now_ms, cfg)
    return sum(len(events) for events in windows.values())


def seal(con, now_ms=None, force=False, session_id=None, cfg=SETTINGS):
    """Seal the windows without new events for seal_idle_ms (all of them with force); returns how many."""
    now_ms = clock_ms() if now_ms is None else now_ms
    where, args = ("1", []) if force else ("updated_ms<=?", [now_ms - cfg["seal_idle_ms"]])
    if session_id is not None:
        where, args = where + " AND session_id=?", args + [session_id]
    return _seal_where(con, where, args, now_ms, cfg)


def read_events(con, session_id, streams=None, t_from=None, t_to=None, cfg=SETTINGS, with_page=False):
    """(ts, stream, JSON text) of a session's events, oldest first, streams merged by time (ties: the streams'
    order, then the order the events arrived in); with_page adds each event's page view (None when it has none).
    Lazy: a chunk is read when its events are reached."""
    names = tuple(streams or cfg["streams"])
    snap = _Snapshot(con, session_id, names, t_from, t_to, cfg)
    try:
        lookup = styles.Lookup(snap.styles, cfg)
        merged = heapq.merge(*(_stream_events(snap, name, cfg) for name in names), key=itemgetter(0))
        for ts, name, text, refs, page in merged:
            if (t_from is None or ts >= t_from) and (t_to is None or ts <= t_to):
                event = styles.restore(text, refs, lookup)
                yield (ts, name, event, page) if with_page else (ts, name, event)
    finally:
        snap.close()


def event_count(con, session_id, stream):
    """How many events a session's stream holds, sealed and open."""
    return con.execute("SELECT COALESCE(SUM(n), 0) FROM (SELECT SUM(n_events) AS n FROM chunks WHERE session_id=? AND "
                       "stream=? UNION ALL SELECT SUM(n_events) FROM open_chunks WHERE session_id=? AND stream=?)",
                       (session_id, stream, session_id, stream)).fetchone()[0]


def stored_lines(con, session_id, stream, cfg=SETTINGS, with_page=False):
    """(ts, text, style refs) of one stream as stored (stylesheets still out), oldest first; with_page adds the page
    view."""
    snap = _Snapshot(con, session_id, (stream,), None, None, cfg)
    try:
        for ts, _, text, refs, page in _stream_events(snap, stream, cfg):
            yield (ts, text, refs, page) if with_page else (ts, text, refs)
    finally:
        snap.close()


def record_chunk(con, meta, ref, codec, level, style_hashes, archived, now_ms):
    """The chunks row of a chunk written with replay_chunks.write_chunk (meta: session, stream, t0, t1, n)."""
    con.execute("""INSERT INTO chunks(session_id, stream, t_start, t_end, n_events, file, byte_offset, byte_length,
                   raw_bytes, codec, level, styles, archived, created_ms) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (meta["session"], meta["stream"], meta["t0"], meta["t1"], meta["n"], ref.file, ref.offset, ref.length,
                 ref.raw_bytes, codec, level, " ".join(sorted(style_hashes)) or None, archived, now_ms))


def replay_bytes(con, session_id=None, streams=None, cfg=SETTINGS):
    """Bytes in chunk files plus open windows of the replay streams (or of `streams`), for one session or (None) for
    all."""
    where, args = _streams_where(streams, cfg)
    if session_id is not None:
        where, args = where + " AND session_id=?", args + [session_id]
    sealed = con.execute(f"SELECT COALESCE(SUM(byte_length), 0) FROM chunks WHERE {where}", args).fetchone()[0]
    opened = con.execute(f"SELECT COALESCE(SUM(LENGTH(CAST(lines AS BLOB))), 0) FROM open_chunks WHERE {where}",
                         args).fetchone()[0]
    return sealed + opened


def drop_replay(con, session_id, streams=None, cfg=SETTINGS):
    """Delete a session's replay: the chunks rows and open windows of the replay streams (or of `streams`) and, with
    the replay, its 0.3.4 replay rows. Returns the bytes they took. The chunk files keep the bytes until
    recompress.reclaim() rewrites or deletes them."""
    where, names = _streams_where(streams, cfg)
    replay = any(name in cfg["replay_streams"] for name in names)
    old = con.execute("SELECT COALESCE(SUM(LENGTH(CAST(body AS BLOB))), 0) FROM events "
                      f"WHERE session_id=? AND {OLD_REPLAY_ROW}", (session_id,)).fetchone()[0] if replay else 0
    freed = replay_bytes(con, session_id, names, cfg) + old
    con.execute(f"DELETE FROM chunks WHERE session_id=? AND {where}", [session_id, *names])
    con.execute(f"DELETE FROM open_chunks WHERE session_id=? AND {where}", [session_id, *names])
    if replay:
        con.execute(f"DELETE FROM events WHERE session_id=? AND {OLD_REPLAY_ROW}", (session_id,))
    return freed


def _streams_where(streams, cfg):
    """The SQL condition and its arguments for rows of these streams (default: the replay streams)."""
    names = list(streams or cfg["replay_streams"])
    return f"stream IN ({','.join('?' * len(names))})", names


def _seal_where(con, where, args, now_ms, cfg):
    keys = con.execute(f"SELECT session_id, stream, window_ms FROM open_chunks WHERE {where} "
                       "ORDER BY session_id, stream, window_ms", args).fetchall()
    for key in keys:
        _seal(con, key, now_ms, cfg)
    return len(keys)


def _seal(con, key, now_ms, cfg):
    session_id, stream, _ = key
    t0, t1, n, text = con.execute("SELECT t_start, t_end, n_events, lines FROM open_chunks "
                                  "WHERE session_id=? AND stream=? AND window_ms=?", key).fetchone()
    events = _open_lines(text)
    dedup = cfg["css_dedup"] and stream in cfg["css_dedup_streams"]
    lines, used = [], set()
    for ts, event, _, page in events:  # an open window's lines have no style references yet
        event, refs = styles.cut_styles(con, event, now_ms, cfg) if dedup else (event, [])
        used.update(digest for _, digest in refs)
        lines.append(replay_chunks.encode_line(ts, event, refs, page))
    codec = codecs.writer_codec(cfg)
    level = codecs.level_for(codec, "live", cfg)
    meta = {"session": session_id, "stream": stream, "t0": t0, "t1": t1, "n": n}
    ref = replay_chunks.write_chunk(meta, lines, codec, level, now_ms, cfg)
    record_chunk(con, meta, ref, codec, level, used, 0, now_ms)
    con.execute("DELETE FROM open_chunks WHERE session_id=? AND stream=? AND window_ms=?", key)


def _open_lines(text):
    """The decoded lines of an open window, in time order: they are kept in the order their batches arrived."""
    return sorted(map(replay_chunks.decode_line, text.split(replay_chunks.NEWLINE)[:-1]), key=itemgetter(0))


class _Snapshot:
    """What a read sees, taken in one read transaction: the chunks and open windows of a session's streams that
    touch [t_from, t_to], the stylesheets they refer to, and their files, opened at once so that a file the night
    reclaim deletes afterwards can still be read. A file deleted before it was opened means the chunks moved: the
    snapshot is taken again (up to read_snapshot_tries times)."""

    def __init__(self, con, session_id, names, t_from, t_to, cfg):
        self.session_id, self.files = session_id, {}
        for attempt in range(cfg["read_snapshot_tries"]):
            self._take(con, session_id, names, t_from, t_to, cfg)
            try:
                for rel in {chunk.file for chunk in self.chunks}:
                    self.files[rel] = open(os.path.join(replay_chunks.replay_dir(cfg), rel), "rb")
                return
            except FileNotFoundError:
                self.close()
                if attempt == cfg["read_snapshot_tries"] - 1:
                    raise

    def _take(self, con, session_id, names, t_from, t_to, cfg):
        marks = ",".join("?" * len(names))
        cond, args = f"session_id=? AND stream IN ({marks})", [session_id, *names]
        if t_from is not None:
            cond, args = cond + " AND t_end>=?", args + [t_from]
        if t_to is not None:
            cond, args = cond + " AND t_start<=?", args + [t_to]
        own = not con.in_transaction
        if own:
            con.execute("BEGIN")
        try:
            self.chunks = _rows(con, _Chunk, f"FROM chunks WHERE {cond} ORDER BY t_start, id", args)
            self.opened = _rows(con, _OpenWindow, f"FROM open_chunks WHERE {cond} ORDER BY t_start, window_ms", args)
            used = {digest for chunk in self.chunks if chunk.styles for digest in chunk.styles.split()}
            self.styles = styles.fetch(con, used)
        finally:
            if own:
                con.commit()

    def close(self):
        for f in self.files.values():
            f.close()
        self.files = {}


def _rows(con, row_type, rest, args):
    """The rows of "SELECT <row_type's fields> <rest>" as row_type tuples."""
    return [row_type._make(row) for row in con.execute(f"SELECT {', '.join(row_type._fields)} {rest}", args)]


def _stream_events(snap, name, cfg):
    """(ts, stream, text, refs, page) of one stream in time order. Sources (chunks, then open windows) are read in
    order of their first event; only sources whose time ranges overlap are merged, so one chunk at a time is in
    memory."""
    sources = sorted([chunk for chunk in snap.chunks if chunk.stream == name] +
                     [window for window in snap.opened if window.stream == name], key=_source_order)
    group, group_end = [], None
    for source in sources:
        if group and source.t_start > group_end:
            yield from _merge(group, snap, name, cfg)
            group = []
        group_end = source.t_end if not group else max(group_end, source.t_end)
        group.append(source)
    if group:
        yield from _merge(group, snap, name, cfg)


def _source_order(source):
    """By first event; at the same time, chunks (by id) come before open windows (by window)."""
    if isinstance(source, _OpenWindow):
        return source.t_start, True, source.window_ms
    return source.t_start, False, source.id


def _merge(group, snap, name, cfg):
    parts = [_source_lines(source, snap, name, cfg) for source in group]
    for ts, text, refs, page in (parts[0] if len(parts) == 1 else heapq.merge(*parts, key=itemgetter(0))):
        yield ts, name, text, refs, page


def _source_lines(source, snap, name, cfg):
    if isinstance(source, _OpenWindow):
        yield from _open_lines(source.lines)
        return
    rel, offset = source.file, source.byte_offset
    header, lines = replay_chunks.read_chunk(rel, offset, source.byte_length, cfg, fileobj=snap.files[rel])
    if header.get("session") != snap.session_id or header.get("stream") != name:
        raise replay_chunks.ChunkError(f"{rel}@{offset} holds another session's chunk")
    yield from (replay_chunks.decode_line(line) for line in lines)
