"""Sessions of every kind recorded into a scratch CAKE_HOME, for the disk-rule tests (tests/test_space.py and
tests/test_space_disk.py).

fresh_cake() makes a CAKE_HOME and returns cake 0.3.4's single-module names for the functions the tests call;
add_session() records a session (its sessions row, a replay of incompressible events, raw input, environment signals)
sealed into chunk files; add_mix() records MIX, one session of every kind; replay(), recorded() and
chunk_file_bytes() read back what is kept; disk_with() stands in for shutil.disk_usage.
"""
import json
import os
import random
import sys
import tempfile
import types
from collections import namedtuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
from agentcake import config, judging, replay_chunks, server, space, store, streams  # noqa: E402

# cake 0.3.4's single-module names, from the agentcake modules they moved to
CAKE = types.SimpleNamespace(db=store.db, prune=store.prune, load_cfg=config.load_cfg, save_cfg=config.save_cfg,
                             ensure_cfg=config.ensure_cfg, coerce=config.coerce, used_bytes=space.used_bytes,
                             free_space=space.free_space, space_status=space.space_status, rejudge=judging.rejudge,
                             H=server.LocalHandler)

DAY = 86400_000
MB = 1048576
EVENT_BYTES = 2000  # random bytes in each replay event, written as hex: compression cannot make a replay vanish
RAW_EVENTS = 40
Usage = namedtuple("Usage", "total used free")
# One session of every kind, oldest first: (id, verdict, agent share, group, ended this long ago): human-only x4,
# agent x2, mixed x2, unsure x1, self-declared agent with a 0% agent share x1, a human-only session still active (its
# last event 10 minutes ago). human1 also has a server-half row.
MIX = (("human1", "human", 0, "H1/L?", 10 * DAY), ("agent1", "agent", 100, "L?/V?", 9 * DAY),
       ("human2", "human", 0, "H1/L?", 8 * DAY), ("mixed1", "human", 30, "H1/L?", 7 * DAY),
       ("unsure1", "unsure", 0, "H1/L?", 6 * DAY), ("named1", "human", 0, "V1", 5 * DAY),
       ("human3", "human", 0, "H1/L?", 4 * DAY), ("agent2", "agent", 90, "server", 3 * DAY),
       ("mixed2", "agent", 60, "range", 2 * DAY), ("human4", "human", 0, "H1/L?", 1 * DAY),
       ("humanLive", "human", 0, "H1/L?", 10 * 60_000))


def fresh_cake():
    home = tempfile.mkdtemp(prefix="cake-test-")
    os.environ["CAKE_HOME"] = home  # agentcake reads CAKE_HOME on every call: nothing to reload
    return CAKE, home


def disk_with(free):
    """A stand-in for shutil.disk_usage: a disk with `free` bytes free."""
    return lambda path: Usage(2 * free, free, free)


ROOMY = disk_with(10 ** 15)  # a petabyte free: far above any floor


def add_session(cake, con, sid, *, verdict, agent_pct, group, end_ms, n_events=60, srv=False, freed=None):
    """A session and what cake.js recorded of it: n_events replay events (about 2 KB each once compressed), raw input
    and environment signals, sealed into chunks of the file of end_ms's hour (one file per session here)."""
    con.execute("""INSERT INTO sessions(id,start_ms,end_ms,url,ua,webdriver,sec_fetch,source,group_id,verdict,human_pct,agent_pct,unsure_pct,
                   segs,is_test,origin,judged_ms,replay_freed_ms) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,'site',?,?)""",
                (sid, end_ms - 60_000, end_ms, "https://example.com/", "Mozilla/5.0", 0, "{}", "src", group, verdict,
                 100 - agent_pct, agent_pct, 0, json.dumps([{"t0": end_ms - 60_000, "t1": end_ms, "who": verdict, "n": 3, "p": 0.5}]),
                 end_ms, freed))
    rng, start = random.Random(sid), end_ms - 60_000
    pads = (rng.getrandbits(8 * EVENT_BYTES).to_bytes(EVENT_BYTES, "big").hex() for _ in range(n_events))
    streams.append(con, sid, "rrweb", [(start + i, {"type": 3, "timestamp": end_ms, "pad": pad}) for i, pad in enumerate(pads)], end_ms)
    streams.append(con, sid, "raw", [(start + i, {"t": start + i, "ty": "pointermove", "x": i, "y": i}) for i in range(RAW_EVENTS)], end_ms)
    streams.append(con, sid, "env", [(start, {"wd": False, "langs": 2})], end_ms)
    streams.seal(con, end_ms, force=True, session_id=sid)
    if srv:
        con.execute("INSERT INTO srv(id, session_id, recv_ms, page_ms, path, body, net_match) VALUES(?,?,?,?,?,?,?)", ("tok-" + sid, sid, end_ms, end_ms, "/", json.dumps({"bs": {"t": "human"}}), 1))


def add_mix(cake, con, now):
    """Record MIX, its end times counted back from now."""
    for sid, verdict, agent_pct, group, ago in MIX:
        add_session(cake, con, sid, verdict=verdict, agent_pct=agent_pct, group=group, end_ms=now - ago,
                    srv=sid == "human1")


def replay(con, sid):
    """How many replay (rrweb) events a session has, wherever they are kept: chunks, open windows or 0.3.4 rows."""
    rows = con.execute(f"SELECT COUNT(*) FROM events WHERE session_id=? AND {streams.OLD_REPLAY_ROW}", (sid,)).fetchone()[0]
    return rows + sum(1 for _ in streams.read_events(con, sid, ["rrweb"]))


def recorded(con, sid, names=None):
    """Every event recorded for a session (or of the streams in names), as read back."""
    return list(streams.read_events(con, sid, names))


def chunk_file_bytes():
    root = replay_chunks.replay_dir()
    return sum(os.path.getsize(os.path.join(folder, name)) for folder, _, names in os.walk(root)
               for name in names if name.endswith(".bin"))
