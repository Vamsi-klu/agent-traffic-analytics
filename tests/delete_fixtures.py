"""What the delete tests share: two made-up visits in every table, in chunk files of three hours and
open windows, with a stylesheet of their own and one they share, in a migrate backup and in cake.log, each with a
canary string of its own; and readers that look for them without trusting Agent Cake's own code: a database file's raw
bytes, every cell of every table, every chunk found by its magic and decompressed (zstd and zlib).

tests/test_delete.py (agentcake/delete.py) and tests/test_delete_command.py (`agentcake delete`, POST /api/delete) use
it. Every value is made up: random ids and canaries, example.com-style shop addresses.
"""
import contextlib
import io
import json
import os
import secrets
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
import urllib.request
import zlib
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from agentcake import cli, codecs, paths, replay_chunks, store, streams  # noqa: E402
from agentcake.storage_config import SETTINGS  # noqa: E402
from cake_server import POLL_S, START_TIMEOUT_S  # noqa: E402

HOUR = 3600_000
NOW = 1794520800000 + 40 * 60_000  # 40 minutes into an hour (UTC), so the two hours before have files of their own
CSS_SHARED = "body{margin:0;font:16px system-ui}" * 30


def made_up_id():
    return secrets.token_hex(16)  # cake.js's visit ids: 32 hex digits


def own_css(canary):
    return f"main::after{{content:'{canary}'}}" * 20


def snapshot(ts, canary, css):
    return json.dumps({"type": 2, "timestamp": ts, "data": {"node": {"type": 0, "childNodes": [
        {"type": 2, "tagName": "style", "attributes": {"_cssText": css}, "childNodes": []},
        {"type": 3, "textContent": f"Hello {canary}"}]}}}, separators=(",", ":"))


def plant(con, sid, canary, sealed_at, padding):
    """One visit in every table, its replay sealed into the chunk files of the hours in sealed_at, plus an open window
    of raw input; `padding` makes its chunks bigger, so a file it shares can be mostly its own."""
    t0 = NOW - 10 * 60_000
    con.execute("INSERT INTO sessions(id, start_ms, end_ms, url, ua, verdict, segs, judged_ms) VALUES(?,?,?,?,?,?,?,?)",
                (sid, t0, NOW, f"https://shop.example/?q={canary}", f"Mozilla/5.0 {canary}", "human", "[]", NOW))
    con.execute("INSERT INTO events(session_id, ts, body) VALUES(?,?,?)",
                (sid, t0, json.dumps({"kind": "pageview", "url": f"/{canary}"})))
    con.execute("INSERT INTO events(session_id, ts, body) VALUES(?,?,?)",
                (sid, t0, json.dumps({"type": 3, "data": {"text": canary}})))
    con.execute("INSERT INTO srv(id, session_id, recv_ms, page_ms, path, body, net_match) VALUES(?,?,?,?,?,?,?)",
                (f"tok-{sid}", sid, t0, t0, f"/{canary}", json.dumps({"p": canary}), 1))
    con.execute("INSERT INTO batches(session_id, pv, seq, recv_ms, t, url, why, n_rrweb, n_raw, n_env, token_id) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)", (sid, "pv1", 0, t0, t0, f"https://shop.example/{canary}", "start", 1, 1, 1,
                                                  f"tok-{sid}"))
    con.execute("INSERT INTO segments(session_id, t_start, t_end, actor, share, n_actions, model, reasons) "
                "VALUES(?,?,?,?,?,?,?,?)", (sid, t0, NOW, "human", 0.0, 3, "m1", json.dumps([canary])))
    con.execute("INSERT INTO labels(session_id, name, layer, method, certainty, evidence, judged_ms) VALUES(?,?,?,?,?,?,?)",
                (sid, "Claude", "page", "ua", "self", json.dumps([canary]), NOW))
    con.execute("INSERT INTO requests(session_id, recv_ms, seq, facts, pv) VALUES(?,?,?,?,?)",
                (sid, t0, 0, json.dumps({"country": canary}), "pv1"))
    for n, at in enumerate(sealed_at):
        ts = t0 + n * SETTINGS["chunk_ms"]
        pad = canary + secrets.token_hex(padding)  # random: compression cannot shrink it
        streams.append(con, sid, "rrweb", [(ts, snapshot(ts, canary, own_css(canary) if n == 0 else CSS_SHARED)),
                                           (ts + 1, json.dumps({"type": 3, "data": {"pad": pad}}))], at)
        streams.seal(con, at, force=True, session_id=sid)
    streams.append(con, sid, "raw", [(NOW, json.dumps({"t": NOW, "ty": "keydown", "kc": "letter", "note": canary}))], NOW)
    con.commit()


def chunk_texts(home):
    """Every chunk header and payload line in every replay file, found by its magic and decompressed (zstd and zlib),
    without the database: what is on disk, live or dead."""
    texts, root = [], os.path.join(home, SETTINGS["replay_dir"])
    for folder, _, names in os.walk(root):
        for name in names:
            with open(os.path.join(folder, name), "rb") as f:
                data = f.read()
            at = data.find(replay_chunks.MAGIC)
            while at >= 0:
                (size,) = replay_chunks.HEADER_LENGTH.unpack_from(data, at + len(replay_chunks.MAGIC))
                start = at + replay_chunks.PREFIX
                header = json.loads(data[start:start + size])
                texts.append(json.dumps(header))
                payload = data[start + size:]
                if header["codec"] == "zstd":
                    d = codecs.ZSTD.ZstdDecompressor()
                else:
                    d = zlib.decompressobj()
                texts.append(d.decompress(payload).decode())
                at = data.find(replay_chunks.MAGIC, len(data) - len(d.unused_data))
    return "\n".join(texts)


def every_cell(db):
    """The text of every cell of every table of a database file."""
    con = sqlite3.connect(db)
    try:
        cells = []
        for (table,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            for row in con.execute(f"SELECT * FROM {table}"):
                cells += [v.decode("latin-1") if isinstance(v, bytes) else str(v) for v in row]
        return "\n".join(cells)
    finally:
        con.close()


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def raw_bytes(db):
    return b"".join(read_bytes(p) for p in (db, db + "-wal") if os.path.exists(p))


def http_status(url):
    try:
        with urllib.request.urlopen(url, timeout=START_TIMEOUT_S) as response:
            return response.status
    except OSError:  # not listening (yet)
        return None


def wait_for(ready):
    deadline = time.monotonic() + START_TIMEOUT_S
    while not ready():
        if time.monotonic() > deadline:
            raise AssertionError(f"not ready within {START_TIMEOUT_S} s")
        time.sleep(POLL_S)


def run(*args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = cli.main(["delete", *args])
    return code, out.getvalue()


class Planted(unittest.TestCase):
    """A scratch CAKE_HOME with two visits; CAKE_PORT points where no cake answers (never the person's own)."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="cake-delete-")
        self.addCleanup(shutil.rmtree, self.home, True)
        env = mock.patch.dict(os.environ, {"CAKE_HOME": self.home, "CAKE_PORT": "9"})  # port 9: discard, nothing answers
        env.start()
        self.addCleanup(env.stop)
        self.gone, self.kept = made_up_id(), made_up_id()
        self.gone_canary, self.kept_canary = "cake-canary-" + secrets.token_hex(8), "cake-canary-" + secrets.token_hex(8)
        con = store.db()
        old, mixed = NOW - 2 * HOUR, NOW - HOUR
        plant(con, self.gone, self.gone_canary, [old, mixed, NOW], padding=4000)
        plant(con, self.kept, self.kept_canary, [mixed, NOW], padding=10)
        store.set_setting(con, "migration", {"failed": [f"{self.gone}: the copy differs", f"{self.kept}: kept"]}, NOW)
        con.commit()
        self.kept_events = list(streams.read_events(con, self.kept))
        con.close()
        self.files = {when: replay_chunks.file_for(when) for when in (old, mixed, NOW)}
        self.backup = os.path.join(self.home, SETTINGS["backup_dir"], "cake-20261112-000000Z.db")
        os.makedirs(os.path.dirname(self.backup))
        source, copy = sqlite3.connect(paths.db_file()), sqlite3.connect(self.backup)
        source.backup(copy)
        source.close(), copy.close()
        with open(paths.log_file(), "w") as f:
            f.write(f"serving\nTraceback: chunk of {self.gone} failed\n  File x, in {self.gone}\nnote {self.kept}\nend\n")

    def assert_gone_everywhere(self):
        for tag in (self.gone, self.gone_canary):
            self.assertNotIn(tag, every_cell(paths.db_file()), "a table still holds it")
            self.assertNotIn(tag.encode(), raw_bytes(paths.db_file()), "the database file still holds its bytes")
            self.assertNotIn(tag, chunk_texts(self.home), "a replay chunk still holds it")
            self.assertNotIn(tag, every_cell(self.backup), "the backup still holds it")
            self.assertNotIn(tag.encode(), raw_bytes(self.backup), "the backup file still holds its bytes")
            self.assertNotIn(tag, read_text(paths.log_file()), "cake.log still names it")

    def assert_kept_as_before(self):
        con = store.db()
        try:
            self.assertEqual(list(streams.read_events(con, self.kept)), self.kept_events)
            for (table,) in con.execute(store.SESSION_TABLES).fetchall():
                n = con.execute(f"SELECT COUNT(*) FROM {table} WHERE session_id=?", (self.kept,)).fetchone()[0]
                self.assertGreater(n, 0, f"the other visit's {table} rows")
            total = con.execute("SELECT value FROM totals WHERE name='chunk_bytes'").fetchone()[0]
            self.assertEqual(total, con.execute("SELECT COALESCE(SUM(byte_length), 0) FROM chunks").fetchone()[0])
            self.assertIn(f"{self.kept}: kept", store.setting(con, "migration")["failed"])
        finally:
            con.close()
        self.assertIn(self.kept_canary, chunk_texts(self.home))
        self.assertIn(self.kept_canary, every_cell(self.backup))
        self.assertEqual(read_text(paths.log_file()), f"serving\nnote {self.kept}\nend\n")
