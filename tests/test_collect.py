"""POST /collect: agentcake/collect.py with collect_store.py, upload.py and site_origin.py.

    python3 -I -m unittest discover -s tests -p test_collect.py -v      (from the Agent Cake folder)

Each test posts uploads to the collect view in its own CAKE_HOME. A batch goes into its streams (rrweb, raw input,
signals) with its page view; a batch sent twice is stored once (s, pv, seq); a cake 0.3.4 batch is still stored; an
upload from another site is kept and flagged, and the dashboard leaves it out; uploads and records over the limits
are refused and counted; a full disk budget stops only the replay; the token is taken and linked to its page view;
the session is judged from its chunks (the verdict, judging.py) and the replay reads them (/api/session). The recorded uploads (the lab's 26 sessions,
cake.js itself) are in test_collect_replay.py.
"""
import gzip
import http.client
import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from agentcake import collect, config, edge_secret, edge_token, evidence, store, streams  # noqa: E402
from agentcake.detect import verdict  # noqa: E402
from agentcake.responses import Request  # noqa: E402
from api_client import Client  # noqa: E402
from agentcake.units import MS_PER_DAY, MS_PER_S  # noqa: E402

KEY = "ck_collect_test"
SID = "5b0e6c2f0d8a4a61b7f4c0b1e2d3a4f5"
PV, PV2 = "c2a8f0e1d2c3b4a5968778695a4b3c2d", "0d9e8f7a6b5c4d3e2f1a0b9c8d7e6f5a"
T0 = 1794518371300
SITE = "https://shop.example.com"


def batch(seq=0, pv=PV, sid=SID, e=3, r=4, x=2, start=0, **fields):
    """A version 1 batch with e rrweb events, r raw records and x signal records."""
    t = T0 + start + seq * 2000
    body = {"v": 1, "k": KEY, "s": sid, "pv": pv, "seq": seq, "t": t + 0.5, "u": SITE + "/demo", "why": "timer",
            "ua": "Mozilla/5.0 (Macintosh) Chrome/149.0.0.0", "wd": False,
            "e": [{"type": 3, "data": {"source": 2, "type": 2, "id": 9, "x": i, "y": i}, "timestamp": t + i}
                  for i in range(e)],
            "r": [{"t": t + i + 0.3, "ty": "pointermove", "cx": i, "cy": 2 * i, "tr": 1} for i in range(r)],
            "x": [{"t": t + i + 0.1, "ty": "page" if i == 0 else "env", "n": 1} for i in range(x)]}
    body.update(fields)
    return body


class CollectCase(unittest.TestCase):
    settings = {}

    def setUp(self):
        os.environ["CAKE_HOME"] = tempfile.mkdtemp(prefix="cake-test-")
        os.environ.pop("CAKE_PORT", None)
        # replays are stored whatever this computer's free disk (disk_min_free_mb, is test_space's)
        config.save_user(site_key=KEY, disk_min_free_mb=0, **self.settings)
        self.con = store.db()
        self.addCleanup(self.con.close)

    def post(self, body, public=False, gz=False, **header_values):
        headers = http.client.HTTPMessage()
        for name, value in header_values.items():
            headers[name.replace("_", "-")] = value
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        return (collect.from_public if public else collect.from_local)(
            Request("/collect", {}, headers, gzip.compress(raw) if gz else raw))

    def stream(self, stream, sid=SID):
        return [(json.loads(text), page) for _, _, text, page in
                streams.read_events(self.con, sid, [stream], with_page=True)]

    def one(self, sql, *args):
        return self.con.execute(sql, args).fetchone()

    def refusal(self, reason):
        return self.one("SELECT posts, records FROM refusals WHERE reason=?", reason)


class Streams(CollectCase):
    def test_a_batch_goes_into_its_streams_with_its_page_view(self):
        sent = batch(dr={"e": 1})
        self.assertEqual(self.post(sent).status, 204)
        self.assertEqual(self.stream("rrweb"), [(e, PV) for e in sent["e"]])
        self.assertEqual(self.stream("raw"), [(r, PV) for r in sent["r"]])
        self.assertEqual(self.stream("env"), [(x, PV) for x in sent["x"]])
        row = self.one("SELECT t, url, why, dropped, n_rrweb, n_raw, n_env, token_id FROM batches WHERE session_id=? "
                       "AND pv=? AND seq=0", SID, PV)
        self.assertEqual(row, (sent["t"], SITE + "/demo", "timer", '{"e":1}', 3, 4, 2, None))
        self.assertEqual(self.one("SELECT url, ua, origin FROM sessions WHERE id=?", SID),
                         (SITE + "/demo", sent["ua"], "site"))

    def test_a_batch_sent_twice_is_stored_once(self):
        for _ in range(2):
            self.assertEqual(self.post(batch()).status, 204, "a copy is accepted, so cake.js stops sending it")
        self.post(batch(seq=1))
        self.assertEqual(len(self.stream("rrweb")), 6)
        self.assertEqual(self.one("SELECT COUNT(*) FROM batches")[0], 2)

    def test_the_same_number_from_another_tab_is_another_batch(self):
        """A tab opened from another one copies its sessionStorage: same visit id, its own page view and numbers."""
        self.post(batch(seq=0, pv=PV))
        self.post(batch(seq=0, pv=PV2, start=500))
        pages_seen = [page for _, page in self.stream("rrweb")]
        self.assertEqual(sorted(pages_seen), sorted([PV] * 3 + [PV2] * 3))

    def test_a_cake_034_batch_is_stored_without_a_dedup_key(self):
        old = {"k": KEY, "s": "sess034", "u": SITE + "/", "ua": "Mozilla/5.0",
               "e": [{"type": 3, "timestamp": T0, "data": {"source": 2, "type": 2, "x": 1, "y": 1}}]}
        self.assertEqual(self.post(old).status, 204)
        self.post(old)
        self.assertEqual(self.stream("rrweb", "sess034"), [(old["e"][0], None)] * 2, "0.3.4 had no key: both kept")
        self.assertEqual(self.one("SELECT COUNT(*) FROM batches")[0], 0)

    def test_a_gzip_upload_is_unzipped(self):
        self.assertEqual(self.post(batch(e=50), gz=True).status, 204)
        self.assertEqual(len(self.stream("rrweb")), 50)

    def test_a_session_pruned_by_retention_takes_its_batches_along(self):
        self.post(batch(sid="oldvisit"))
        self.post(batch(sid="newvisit"))
        self.con.execute("UPDATE sessions SET end_ms=? WHERE id='oldvisit'", (T0 - 31 * MS_PER_DAY,))
        store.prune(self.con, 30)
        self.assertEqual([r[0] for r in self.con.execute("SELECT DISTINCT session_id FROM batches")], ["newvisit"])

    def test_records_without_a_time_are_left_out_and_counted(self):
        sent = batch(e=0, r=0, x=0)
        sent["e"] = [{"type": 3}, {"type": 3, "timestamp": T0}]
        self.post(sent)
        self.assertEqual(len(self.stream("rrweb")), 1)
        self.assertEqual(self.refusal("bad_record"), (1, 1))


class Refused(CollectCase):
    settings = {"max_events_per_post": 10, "max_events_per_session": 5}

    def test_wrong_site_key_unreadable_and_keyless_uploads_are_refused_and_counted(self):
        self.assertEqual(self.post(batch(k="ck_other")).status, 403)
        self.assertEqual(self.post(b"not json").status, 400)
        self.assertEqual(self.post(batch(s=None)).status, 400)
        self.assertEqual(self.post(dict(batch(), seq=None)).status, 400)
        self.assertEqual(self.post(gzip.compress(b" " * 20_000_000)).status, 413)
        for reason in ("site_key", "bad_body", "no_session", "bad_batch", "too_large"):
            self.assertEqual(self.refusal(reason)[0], 1, reason)
        self.assertEqual(self.one("SELECT COUNT(*) FROM sessions")[0], 0)

    def test_an_upload_over_the_per_post_limit_is_refused_and_counted(self):
        self.assertEqual(self.post(batch(e=6, r=6, x=0)).status, 413)
        self.assertEqual(self.refusal("post_limit"), (1, 12))
        self.assertEqual(self.one("SELECT COUNT(*) FROM sessions")[0], 0, "nothing of it is stored")

    def test_records_over_the_per_session_limit_are_refused_and_counted(self):
        for seq in range(3):
            self.assertEqual(self.post(batch(seq=seq, e=3, r=1, x=0)).status, 204)
        self.assertEqual(len(self.stream("rrweb")), 5, "the first five, in the order they came")
        self.assertEqual(len(self.stream("raw")), 3, "each stream has its own limit")
        self.assertEqual(self.one("SELECT events_refused FROM sessions WHERE id=?", SID), (4,))
        self.assertEqual(self.refusal("session_limit"), (2, 4))


class OtherSites(CollectCase):
    settings = {"site_domain": "shop.example.com"}

    def test_an_upload_from_another_site_is_kept_flagged_and_left_out_of_the_dashboard(self):
        self.post(batch(sid="fromsite"), Origin=SITE)
        self.post(batch(sid="elsewhere", u="https://copy.example.net/"), Origin="https://copy.example.net")
        self.post(batch(sid="elsewhere", seq=1), Origin=SITE)  # a later upload does not clear the flag
        origins = dict(self.con.execute("SELECT id, origin FROM sessions"))
        self.assertEqual(origins, {"fromsite": "site", "elsewhere": "other"})
        self.assertEqual(len(self.stream("rrweb", "elsewhere")), 6, "still recorded")
        client = Client()
        listing = client.get("/api/sessions").body
        dashboard = client.get("/api/overview").body
        self.assertEqual([row["id"] for row in listing["results"]], ["fromsite"])
        self.assertEqual((listing["counts"]["all"], dashboard["counts"]["all"]), (1, 1), "the dashboard counts only the site's")
        self.assertEqual(client.get("/api/session/elsewhere").status, 404)


class Budget(CollectCase):
    settings = {"budget_mb": 0.0001, "auto_free": False}

    def test_a_full_budget_stops_the_replay_only(self):
        self.assertEqual(self.post(batch()).status, 204)
        self.assertEqual(self.stream("rrweb"), [])
        self.assertEqual(self.one("SELECT events_dropped FROM sessions WHERE id=?", SID), (3,))
        self.assertEqual(len(self.stream("raw")), 4, "raw input and signals are still kept: judging needs them")
        self.assertEqual(len(self.stream("env")), 2)


class Token(CollectCase):
    def test_the_token_is_taken_once_and_linked_to_its_page_view(self):
        edge_secret.create_secret()
        secret = edge_secret.srv_secret()
        served = int(time.time() * MS_PER_S)  # the token's age is checked against this computer's clock
        token = edge_token.sign_payload(secret, {"v": 1, "id": "tok-7", "t": served, "p": "/demo"})
        self.assertEqual(self.post(batch(st=token)).headers.get("X-Cake-Token"), "ok")
        self.assertEqual(self.post(batch(seq=1, st=token)).headers.get("X-Cake-Token"), "dup")
        self.assertIsNone(self.post(batch(st=token)).headers.get("X-Cake-Token"), "a batch sent again is not read again")
        self.assertEqual(self.one("SELECT session_id, path FROM srv WHERE id='tok-7'"), (SID, "/demo"))
        self.assertEqual([r[0] for r in self.con.execute("SELECT token_id FROM batches ORDER BY seq")], ["tok-7"] * 2)


class Clock:
    """collect's time module, a second further on each upload."""

    def __init__(self, start_ms):
        self.ms = start_ms

    def time(self):
        self.ms += MS_PER_S
        return self.ms / MS_PER_S


class Judged(CollectCase):
    def test_the_session_is_judged_from_its_chunks_and_the_replay_reads_them(self):
        sent = [batch(seq=n, e=5, r=0, x=0) for n in range(4)]
        with mock.patch.object(collect, "time", Clock(T0)):
            for body in sent:
                self.post(body)
        events = [e for body in sent for e in body["e"]]
        client = Client()
        chunks = client.get(f"/api/session/{SID}").body["replay"]["chunks"]
        replay = [event for n in range(len(chunks))
                  for event in client.get(f"/api/session/{SID}/replay", chunk=str(n)).body["events"]]
        self.assertEqual(replay, events)
        # collect judged the first upload, the later ones fell inside judge_interval_ms, and opening the replay
        # judged the session again on everything it sent, read from its chunks
        case, raw, rrweb = evidence.session_evidence(self.con, SID)
        self.assertEqual((raw, rrweb), ([], events))
        expected = verdict.judge(case, raw=raw, rrweb=rrweb)
        row = self.one("SELECT verdict_class, agent_row, agent_name, human_pct, agent_pct, judged_ms >= end_ms "
                       "FROM sessions WHERE id=?", SID)
        self.assertEqual(row, (expected["class"], expected["row"], expected["name"],
                               round(expected["shares"]["human"] * 100), round(expected["shares"]["agent"] * 100), 1))


if __name__ == "__main__":
    unittest.main()
