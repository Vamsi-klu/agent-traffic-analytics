"""What the web metrics tests share (test_session_split.py, test_web_props.py, test_api_web.py): a CAKE_HOME of their
own, uploads posted to the local collect view the way cake.js sends them, and the rows they leave.

    WebCase              setUp: a fresh CAKE_HOME with a site key; post(body), one(sql, *args), rows(sql, *args)
    upload(seq, t, ...)  a version 1 upload of one tab (s) and page view (pv) at epoch ms t: one activity record (a
                         pointer move) unless activity=False, a page record with source fields when page is given
"""
import http.client
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from agentcake import collect, config, store  # noqa: E402
from agentcake.responses import Request  # noqa: E402

KEY = "ck_web_test"
TAB = "5b0e6c2f0d8a4a61b7f4c0b1e2d3a4f5"
PV = "c2a8f0e1d2c3b4a5968778695a4b3c2d"
VISITOR = "aa11bb22cc33dd44ee55ff6677889900"
T0 = 1794518371300
MINUTE_MS = 60_000
UA_IPHONE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
             "Version/17.0 Mobile/15E148 Safari/604.1")
UA_MAC_CHROME = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                 "Chrome/149.0.0.0 Safari/537.36")


def page_record(t, rd="", utm=None, ck=(), lang="en-US", tzo=480, kind="page"):
    return {"t": t, "ty": kind, "n": 1, "rd": rd, "utm": dict(utm or {}), "ck": list(ck), "lang": lang, "tzo": tzo}


def upload(seq, t, tab=TAB, pv=PV, visitor=VISITOR, activity=True, page=None, ua=UA_MAC_CHROME, url=None, env=None,
           person=None):
    """One upload (see the module docstring); page: a page record's fields (page_record's keywords) or None; person:
    the identify hash (idh) it carries, or None."""
    signals = [page_record(t, **page)] if page is not None else []
    if env is not None:
        signals.append({"t": t + 2, "ty": "env", "env": env})
    body = {"v": 1, "k": KEY, "s": tab, "pv": pv, "seq": seq, "t": t, "u": url or "https://shop.example.com/",
            "why": "timer", "ua": ua, "wd": False, "e": [],
            "r": [{"t": t + 1, "ty": "pointermove", "cx": 1, "cy": 1, "tr": 1}] if activity else [], "x": signals}
    if visitor:
        body["vid"] = visitor
    if person:
        body["idh"] = person
    return body


class WebCase(unittest.TestCase):
    settings = {}

    def setUp(self):
        os.environ["CAKE_HOME"] = tempfile.mkdtemp(prefix="cake-web-test-")
        os.environ.pop("CAKE_PORT", None)
        config.save_user(site_key=KEY, disk_min_free_mb=0, **self.settings)
        self.con = store.db()
        self.addCleanup(self.con.close)

    def post(self, body, public=False, **header_values):
        headers = http.client.HTTPMessage()
        for name, value in header_values.items():
            headers[name.replace("_", "-")] = value
        view = collect.from_public if public else collect.from_local
        answer = view(Request("/collect", {}, headers, json.dumps(body).encode()))
        self.assertEqual(answer.status, 204)
        return answer

    def one(self, sql, *args):
        return self.con.execute(sql, args).fetchone()

    def rows(self, sql, *args):
        return self.con.execute(sql, args).fetchall()
