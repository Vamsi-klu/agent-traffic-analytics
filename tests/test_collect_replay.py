"""Recorded uploads sent through collect and read back (S2.1): every rrweb event and raw record comes back the same.

    python3 -I -m unittest discover -s tests -v      (from the Agent Cake folder)

Made-up visits (tests/synthetic_sessions.py), cut into upload format version 1 batches per page and posted in order,
then again shuffled with copies: each visit's rrweb events and raw records come back one for one, with their page
view. The same round trip on Agent Cake's own recordings is kept with those recordings, outside the published repository.
"""
import gzip
import hashlib
import http.client
import json
import os
import random
import sys
import tempfile
import unittest
from collections import defaultdict

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import synthetic_sessions  # noqa: E402
from agentcake import collect, config, store, streams  # noqa: E402
from agentcake.datafiles import load  # noqa: E402
from agentcake.responses import Request  # noqa: E402

KEY = "ck_replay_test"
RAW_PER_BATCH = 40  # lab records per made-up batch: about what cake.js sends every few seconds
GZIP_FROM = load("data/cakejs.json")["script"]["batch"]["compress_min_bytes"]
SHUFFLE_SEED = 1111
MADE_UP_VISITS = 3  # made-up sessions for the round trip the published repository runs (synthetic_sessions.py)
HOUR_MS = 3_600_000


def hex_id(*parts):
    """A 32-hex-digit id like cake.js's, made from the run's name."""
    return hashlib.sha256("/".join(map(str, parts)).encode()).hexdigest()[:32]


def batches_of(run, raw, rrweb, signals=None):
    """A visit as cake.js would have sent it: a page view per page of its raw records (their page path), batches of
    RAW_PER_BATCH raw records with the rrweb events of their time span; signals: {page path: [page views' signal
    records and User-Agent, in order]} (lab_batches' complete=True)."""
    signals = signals or {}
    views = []
    for item in raw:
        if not views or views[-1][-1]["pg"] != item["pg"]:
            views.append([])
        views[-1].append(item)
    starts = [view[0]["t"] for view in views] + [float("inf")]
    batches, user_agent = [], "Mozilla/5.0"
    for v, view in enumerate(views):
        page = signals[view[0]["pg"]].pop(0) if signals.get(view[0]["pg"]) else {"ua": None, "x": []}
        user_agent = page["ua"] or user_agent
        groups = [view[k:k + RAW_PER_BATCH] for k in range(0, len(view), RAW_PER_BATCH)]
        edges = [float("-inf") if v == 0 else starts[v]] + [g[0]["t"] for g in groups[1:]] + [starts[v + 1]]
        for seq, group in enumerate(groups):
            batches.append({"v": 1, "k": KEY, "s": hex_id(run), "pv": hex_id(run, v), "seq": seq, "t": group[-1]["t"],
                            "u": "http://lab.example" + view[0]["pg"], "ua": user_agent,
                            "e": [e for e in rrweb if edges[seq] <= e["timestamp"] < edges[seq + 1]],
                            "r": [{k: val for k, val in item.items() if k != "pg"} for item in group],
                            "x": page["x"] if seq == 0 else []})
    return batches


class Replay(unittest.TestCase):
    def setUp(self):
        os.environ["CAKE_HOME"] = tempfile.mkdtemp(prefix="cake-test-")
        os.environ.pop("CAKE_PORT", None)
        # replays are stored whatever this computer's free disk (K2, disk_min_free_mb, is test_space's)
        config.save_user(site_key=KEY, disk_min_free_mb=0)
        self.con = store.db()
        self.addCleanup(self.con.close)

    def post(self, batch, header_pairs=()):
        headers = http.client.HTTPMessage()
        for name, value in header_pairs:
            if name.lower() != "content-length":
                headers[name] = value
        body = json.dumps(batch, separators=(",", ":"), ensure_ascii=False).encode()
        body = gzip.compress(body) if len(body) >= GZIP_FROM else body
        answer = collect.from_local(Request("/collect", {}, headers, body))
        self.assertEqual(answer.status, 204, answer.body)

    def read(self, sid, stream):
        return [(json.loads(text), page) for _, _, text, page in
                streams.read_events(self.con, sid, [stream], with_page=True)]

    def stored(self):
        return {stream: self.con.execute("SELECT COUNT(*), SUM(n) FROM (SELECT session_id, SUM(n_events) AS n FROM "
                                         "(SELECT session_id, n_events FROM chunks WHERE stream=? UNION ALL SELECT "
                                         "session_id, n_events FROM open_chunks WHERE stream=?) GROUP BY session_id)",
                                         (stream, stream)).fetchone() for stream in ("rrweb", "raw", "env")}


def sent_once_each(test, batches):
    """Post the batches shuffled, a third of them twice, and check every record comes back once (in time order)."""
    deliveries = batches + random.Random(SHUFFLE_SEED).sample(batches, len(batches) // 3)
    random.Random(SHUFFLE_SEED).shuffle(deliveries)
    for batch in deliveries:
        test.post(batch)
    by_sid = defaultdict(lambda: defaultdict(list))
    for batch in batches:
        by_sid[batch["s"]]["rrweb"] += [(e["timestamp"], json.dumps(e, sort_keys=True)) for e in batch["e"]]
        by_sid[batch["s"]]["raw"] += [(r["t"], json.dumps(r, sort_keys=True)) for r in batch["r"]]
    for sid, want in by_sid.items():
        for stream, records in want.items():
            got = sorted((e["timestamp"] if stream == "rrweb" else e["t"], json.dumps(e, sort_keys=True))
                         for e, _ in test.read(sid, stream))
            test.assertEqual(got, sorted(records), (sid, stream))
    test.assertEqual(test.con.execute("SELECT COUNT(*) FROM batches").fetchone()[0], len(batches))


class MadeUp(Replay):
    """The round trip on made-up visits (tests/synthetic_sessions.py: written by rule, nobody recorded them), which
    the published repository has; the lab's own sessions (class Lab) stay on the machine that recorded them."""

    def test_made_up_visits_come_back_record_for_record(self):
        sent = {}
        for n in range(MADE_UP_VISITS):
            t0 = synthetic_sessions.T0 + n * HOUR_MS
            sent[f"made-up-{n}"] = batches_of(f"made-up-{n}", synthetic_sessions.agent_raw(t0),
                                              synthetic_sessions.agent_rrweb(t0))
        for batches in sent.values():
            for batch in batches:
                self.post(batch)
        for name, batches in sent.items():
            self.assertGreater(len(batches), 1, name)
            self.assertEqual(self.read(hex_id(name), "rrweb"), [(e, b["pv"]) for b in batches for e in b["e"]], name)
            self.assertEqual(self.read(hex_id(name), "raw"), [(r, b["pv"]) for b in batches for r in b["r"]], name)

    def test_shuffled_and_sent_twice_they_still_come_back_once_each(self):
        sent_once_each(self, [batch for n in range(MADE_UP_VISITS) for batch in batches_of(
            f"made-up-{n}", synthetic_sessions.agent_raw(synthetic_sessions.T0 + n * HOUR_MS),
            synthetic_sessions.agent_rrweb(synthetic_sessions.T0 + n * HOUR_MS))])


if __name__ == "__main__":
    unittest.main()
