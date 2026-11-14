"""A visit's stored uploads in cake.js's upload format (S2.1): agentcake/visit_batches.py.

    python3 -I -m unittest discover -s tests -p test_visit_batches.py -v      (from the Agent Cake folder)

What collect stored comes back as one batch per page view, with the page view's header from its first batch and its
records in time order, each once; a cake 0.3.4 visit comes back as one batch without a page view.
"""
import http.client
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from agentcake import collect, config, store, visit_batches  # noqa: E402
from agentcake.responses import Request  # noqa: E402

KEY = "ck_visit_batches"
T0 = 1794518371300


def upload(pv, seq, start, n=2):
    t = T0 + start
    return {"v": 1, "k": KEY, "s": "visit1", "pv": pv, "seq": seq, "t": t, "u": f"https://shop.example/{pv}?{seq}",
            "e": [{"type": 3, "timestamp": t + i, "data": {"i": i}} for i in range(n)],
            "r": [{"t": t + i + 0.5, "ty": "click", "tr": 1} for i in range(n)],
            "x": [{"t": t + 0.2, "ty": "page" if seq == 0 else "probes", "n": 1}]}


class VisitBatches(unittest.TestCase):
    def setUp(self):
        os.environ["CAKE_HOME"] = tempfile.mkdtemp(prefix="cake-test-")
        os.environ.pop("CAKE_PORT", None)
        # replays are stored whatever this computer's free disk (K2, disk_min_free_mb, is test_space's)
        config.save_user(site_key=KEY, disk_min_free_mb=0)
        self.con = store.db()
        self.addCleanup(self.con.close)

    def post(self, body):
        return collect.from_local(Request("/collect", {}, http.client.HTTPMessage(), json.dumps(body).encode()))

    def test_one_batch_per_page_view_with_its_records_in_time_order(self):
        sent = [upload("pvA", 0, 0), upload("pvB", 0, 500), upload("pvA", 1, 2000), upload("pvB", 1, 2500)]
        for body in sent + sent[:1]:  # the first batch arrives twice
            self.post(body)
        got = visit_batches.batches(self.con, "visit1")
        self.assertEqual([b["pv"] for b in got], ["pvA", "pvB"])
        for rebuilt in got:
            mine = [body for body in sent if body["pv"] == rebuilt["pv"]]
            self.assertEqual((rebuilt["s"], rebuilt["t"], rebuilt["u"]), ("visit1", mine[0]["t"], mine[0]["u"]))
            for key in ("e", "r", "x"):
                self.assertEqual(rebuilt[key], [record for body in mine for record in body[key]], key)

    def test_a_cake_034_visit_is_one_batch_without_a_page_view(self):
        self.post({"k": KEY, "s": "visit1", "u": "https://shop.example/", "e": [{"type": 4, "timestamp": T0, "data": {}}]})
        (rebuilt,) = visit_batches.batches(self.con, "visit1")
        self.assertEqual((rebuilt["pv"], rebuilt["u"], rebuilt["e"]), (None, "https://shop.example/",
                                                                       [{"type": 4, "timestamp": T0, "data": {}}]))

    def test_an_unknown_visit_has_no_batches(self):
        self.assertEqual(visit_batches.batches(self.con, "nobody"), [])


if __name__ == "__main__":
    unittest.main()
