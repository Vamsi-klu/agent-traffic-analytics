"""Matching log lines to visits: agentcake/log_match.py, fed the way `logs import` feeds it.

    python3 -I -m unittest discover -s tests -p test_log_match.py -v      (from the AgentCake folder)

A made-up hour of a shop: visitors who agreed to analytics run cake.js, whose uploads go through collect's own storage
(collect_store.record, the load balancer giving each visitor's address); other visitors only show in the web server's
log, with static files, uploads to AgentCake, redirects and 404s around the page requests. Some visitors share an
address (an office behind one NAT), some of those a User-Agent too, some open two tabs, a few leave a tab in the
background long enough that cake.js's first upload comes late, two people behind one address open the same link
within a second (only their User-Agents tell them apart), and the web server's clock runs a little ahead.
The same visits are written in all five formats; each page request with a visit behind it must match that visit
(N5, at least 95 %); a line of a visitor without a visit must match nothing and leave nothing behind; importing
twice stores each line once; the stored row keeps results (range, hashes, and the signature's outcome, which the
verdict reads as it reads an upload's), never the address.
"""
import base64
import json
import os
import random
import shutil
import sqlite3
import sys
import tempfile
import unittest
from collections import Counter
from dataclasses import dataclass, field, replace
from unittest import mock

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]
from agentcake import collect_store, config, log_formats, log_match, logs, netfacts, store, upload  # noqa: E402
from agentcake import evidence, visit_batches  # noqa: E402
from agentcake.datafiles import sizes  # noqa: E402
from agentcake.detect import webbotauth  # noqa: E402
from log_samples import (FORMAT_OF_SAMPLE, FORMATS, LANGUAGES, LINE_WRITERS, PAGES, SIGNER_HOST, SITE_HOST,  # noqa
                         STATIC, UPLOAD, USER_AGENTS, WHOLE_SECONDS, Truth, browser_headers, published_ipv6)
from test_webbotauth import AGENT  # noqa: E402

N5_MIN = 0.95  # threshold N5: log lines matched to their visit by address hash, User-Agent and 30 s
T0 = 1794500000000  # when the shop's hour begins (epoch ms)
HOUR_MS = 3_600_000
IMPORT_AT = T0 + 3 * HOUR_MS
SERVER_CLOCK_AHEAD_MS = 700  # the web server's clock against AgentCake's
SITE_KEY = "ck_logmatchtest"
NAT_PAIRS = 12
LB = netfacts.lb_headers()


@dataclass
class PageView:
    session: str
    pv: str
    path: str
    opened_ms: int        # when the page request reached the web server (AgentCake's clock)
    uploads: list = field(default_factory=list)


@dataclass
class Visitor:
    ip: str
    ua: str
    language: str
    sessions: list = field(default_factory=list)  # [[PageView]] per session


def population(seed=7, visitors=180, strangers=120, span_ms=2 * HOUR_MS):
    """Visitors with visits (uploads and page requests) and strangers (page requests only) arriving over span_ms, and
    every log line's truth with the page view it opened (None for anything that opened no page view of a visit)."""
    rng = random.Random(seed)
    office = [f"203.0.113.{n}" for n in range(10, 16)]
    people, lines = [], []
    for number in range(visitors):
        shared = rng.random() < 0.3
        ip = rng.choice(office) if shared else f"{rng.choice(('192.0.2.', '198.51.100.'))}{number % 250 + 1}"
        ip = published_ipv6() if number % 60 == 0 else ip
        ua = rng.choice(USER_AGENTS[:3]) if shared and rng.random() < 0.5 else rng.choice(USER_AGENTS)
        person = Visitor(ip, ua, rng.choice(LANGUAGES))
        start = T0 + rng.randrange(0, span_ms)
        for tab in range(2 if rng.random() < 0.08 else 1):
            person.sessions.append(visit_pages(rng, f"s{number}t{tab}", start + tab * rng.randrange(1000, 20000)))
        people.append(person)
        for views in person.sessions:
            for view in views:
                lines += page_lines(rng, person, view)
    for number in range(NAT_PAIRS):
        lines += same_link_behind_one_address(rng, number, office[number % len(office)], T0 + rng.randrange(0, span_ms),
                                              people)
    for number in range(strangers):
        ip = rng.choice(office) if rng.random() < 0.2 else f"{rng.choice(('192.0.2.', '198.51.100.'))}{number + 1}"
        stranger = Visitor(ip, rng.choice(USER_AGENTS), rng.choice(LANGUAGES))
        opened = T0 + rng.randrange(0, span_ms)
        lines += page_lines(rng, stranger, PageView(None, None, rng.choice(PAGES), opened))
    lines.sort(key=lambda pair: pair[0].t_ms)
    return people, lines


def same_link_behind_one_address(rng, number, ip, opened, people):
    """Two people behind one office address open the same link within a second; the first one's browser uploads
    later than the second's, and a third, who never ran cake.js, opens it in between. Only the User-Agent tells
    their lines apart."""
    path = rng.choice(PAGES)
    first_ua, second_ua, third_ua = rng.sample(USER_AGENTS[:-1], 3)
    out = []
    for name, ua, at, delay in (("a", first_ua, opened, 6_000), ("b", second_ua, opened + 800, 1_500)):
        person = Visitor(ip, ua, rng.choice(LANGUAGES))
        view = PageView(f"nat{number}{name}", f"nat{number}{name}p0", path, at)
        view.uploads = [at + delay, at + delay + 4_000, at + delay + 30_000]
        person.sessions.append([view])
        people.append(person)
        out += page_lines(rng, person, view)
    out += page_lines(rng, Visitor(ip, third_ua, rng.choice(LANGUAGES)), PageView(None, None, path, opened + 300))
    return out


def visit_pages(rng, session, start):
    views, opened = [], start
    for number in range(rng.randint(1, 5)):
        view = PageView(session, f"{session}p{number}", rng.choice(PAGES), opened)
        late = rng.random() < 0.02  # a tab opened in the background: timers held back, the first upload late
        first = opened + (rng.randrange(31_000, 60_000) if late else rng.randrange(300, 9_000))
        leave = opened + rng.randrange(4_000, 90_000)
        # cake.js sends every 2 to 10 s; matching reads a page view's first upload, so its first, one later and the
        # beacon sent when the page is left (it reaches AgentCake after the next page request) stand for them all
        view.uploads.append(first)
        if leave > first + 2_000:
            view.uploads.append(rng.randrange(first + 2_000, leave))
        view.uploads.append(max(leave, first) + 50)
        views.append(view)
        opened = max(leave, first) + rng.randrange(20, 400)
    return views


def page_lines(rng, person, view):
    """The log lines one page view leaves: maybe a redirect first, the page, its static files, its uploads."""
    logged = view.opened_ms + SERVER_CLOCK_AHEAD_MS
    signed = rng.random() < 0.05
    headers = browser_headers(rng, person.ua, person.language, "document", signed)
    out = []
    if rng.random() < 0.05:
        out.append((Truth(logged - 40, person.ip, "GET", "/go", "HTTP/1.1", 301, SITE_HOST, "https", headers), None))
    page = Truth(logged, person.ip, "GET", view.path, "HTTP/2.0", rng.choice((200, 200, 200, 304)), SITE_HOST, "https",
                 headers)
    out.append((page, view if view.session else None))
    for k in range(rng.randint(1, 3)):
        out.append((replace(page, t_ms=logged + 100 + 150 * k, target=rng.choice(STATIC), status=200,
                            headers=browser_headers(rng, person.ua, person.language, "image")), None))
    for t in view.uploads:
        out.append((replace(page, t_ms=t + SERVER_CLOCK_AHEAD_MS, method="POST", target=UPLOAD, status=204), None))
    return out


def upload_once(con, view, seq, recv_ms, person, c):
    """One cake.js upload of this page view, stored by collect's own code with the load balancer's address."""
    pairs = [("Host", SITE_HOST), ("User-Agent", person.ua), ("Accept-Language", person.language),
             ("Content-Type", "text/plain"), ("Origin", f"https://{SITE_HOST}"), ("Sec-Fetch-Site", "same-origin"),
             ("Sec-Fetch-Mode", "cors"), ("Sec-Fetch-Dest", "empty"), (LB["ip"], person.ip)]
    facts = netfacts.request_facts(dict(pairs), "site", True, netfacts.look_up(person.ip))
    batch = upload.read_batch({"v": 1, "k": SITE_KEY, "s": view.session, "pv": view.pv, "seq": seq, "t": recv_ms,
                               "u": f"https://{SITE_HOST}{view.path}", "ua": person.ua},
                              sizes()["max_chars"], c["max_events_per_post"])
    visit = collect_store.Visit(origin="site", sec_fetch="{}", net=None, address=person.ip, public=True, facts=facts)
    collect_store.record(con, batch, visit, recv_ms, c)


def store_visits(con, people, c):
    """Every upload, in the order they arrive (the address salt only ever moves forward in time)."""
    uploads = [(recv_ms, seq, view, person) for person in people for views in person.sessions for view in views
               for seq, recv_ms in enumerate(view.uploads)]
    for recv_ms, seq, view, person in sorted(uploads, key=lambda upload: upload[0]):
        upload_once(con, view, seq, recv_ms, person, c)
    con.commit()


def envelopes(sample, lines, run="testrun"):
    """What `logs import` sends for these lines in this sample's format: page requests in batches."""
    log_format = log_formats.named(FORMAT_OF_SAMPLE.get(sample, sample))
    records = []
    for truth, _ in lines:
        record = log_format.parse(LINE_WRITERS[sample](truth))
        if record is not None and logs.is_page_request(record):
            records.append(logs.to_json(record))
    batch = logs.BATCH_RECORDS
    return [{"v": logs.ENVELOPE_VERSION, "run": run, "format": log_format.name, "fields": {"missing": [], "empty": []},
             "records": records[i:i + batch]} for i in range(0, max(len(records), 1), batch)]


def log_rows(con):
    rows = con.execute("SELECT session_id, recv_ms, pv, facts FROM requests WHERE seq IS NULL").fetchall()
    return [(sid, recv_ms, pv, json.loads(text)) for sid, recv_ms, pv, text in rows
            if json.loads(text).get("source") == "log"]


def logged_ms(sample, truth):
    """The time a log row of this line holds: the line's own, in whole seconds for the combined format."""
    return truth.t_ms // 1000 * 1000 if sample in WHOLE_SECONDS else truth.t_ms


def signer_directory():
    return webbotauth.KeyDirectory({SIGNER_HOST: [AGENT.jwk]}, webbotauth.default_settings())


class Shop(unittest.TestCase):
    """One database of visits for every test of this module; each test imports into its own copy."""

    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp(prefix="agentcake-log-match-")
        cls.env = mock.patch.dict(os.environ, {"CAKE_HOME": cls.home})
        cls.env.start()
        cls.c = config.load_cfg()
        cls.people, cls.lines = population()
        cls.shop_envelopes = {}
        con = store.db()
        store_visits(con, cls.people, cls.c)
        con.close()

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        shutil.rmtree(cls.home, ignore_errors=True)

    def fresh_copy(self):
        folder = tempfile.mkdtemp(prefix="agentcake-log-match-copy-")
        self.addCleanup(shutil.rmtree, folder, True)
        source = sqlite3.connect(os.path.join(self.home, "cake.db"))
        copy = sqlite3.connect(os.path.join(folder, "c.db"))
        source.backup(copy)
        source.close()
        self.addCleanup(copy.close)
        return copy, folder

    def run_import(self, con, sample, lines=None, c=None, directory=None):
        if lines is None and sample not in self.shop_envelopes:  # the shop's own lines: written and read once
            self.shop_envelopes[sample] = envelopes(sample, self.lines)
        totals = Counter()
        for envelope in self.shop_envelopes[sample] if lines is None else envelopes(sample, lines):
            totals.update(log_match.record(con, envelope, IMPORT_AT, c or self.c, directory=directory))
        con.commit()
        return totals

    def measure(self, sample):
        """N5 for one format: the share of page requests with a visit behind them that matched that visit."""
        con, _ = self.fresh_copy()
        self.run_import(con, sample, directory=signer_directory())
        stored = {(sid, recv_ms) for sid, recv_ms, _, _ in log_rows(con)}
        expected = [(truth, view) for truth, view in self.lines if view is not None]
        matched = sum(1 for truth, view in expected if (view.session, logged_ms(sample, truth)) in stored)
        return matched / len(expected), len(expected), len(stored)


class MatchingN5(Shop):
    def test_page_requests_match_their_visits_in_every_format(self):
        for sample in FORMATS:
            rate, expected, _ = self.measure(sample)
            with self.subTest(format=sample):
                self.assertGreaterEqual(rate, N5_MIN, f"{sample}: {rate:.3f} of {expected}")

    def test_each_line_kept_is_kept_with_the_page_view_it_opened(self):
        con, _ = self.fresh_copy()
        self.run_import(con, "nginx-agentcake", directory=signer_directory())
        opened = {(view.session, truth.t_ms): view.pv for truth, view in self.lines if view is not None}
        rows = log_rows(con)
        self.assertEqual([row for row in rows if opened.get((row[0], row[1])) != row[2]], [])

    def test_strangers_lines_match_no_visit_and_leave_nothing(self):
        """Not one line of this shop is kept with a visit it does not belong to: it would put one visitor's request,
        a signature or Sec-Fetch values, into someone else's visit."""
        con, _ = self.fresh_copy()
        totals = self.run_import(con, "nginx-agentcake")
        visits = {(view.session, truth.t_ms) for truth, view in self.lines if view is not None}
        rows = log_rows(con)
        self.assertEqual([row[:2] for row in rows if (row[0], row[1]) not in visits], [])
        self.assertEqual(totals["matched"], len(rows))
        self.assertGreater(totals["unmatched"], 0)
        self.assertEqual(totals["records"], totals["matched"] + totals["unmatched"] + totals["duplicates"])

    def test_importing_the_same_lines_twice_stores_them_once(self):
        con, _ = self.fresh_copy()
        first = self.run_import(con, "apache-agentcake")
        again = self.run_import(con, "apache-agentcake")
        self.assertEqual(again["matched"], 0)
        self.assertEqual(again["duplicates"], first["matched"])
        self.assertEqual(len(log_rows(con)), first["matched"])


class StoredRows(Shop):
    def test_a_row_keeps_the_page_requests_results_and_never_the_address(self):
        con, folder = self.fresh_copy()
        self.run_import(con, "caddy-json", directory=signer_directory())
        sid, recv_ms, pv, facts = log_rows(con)[0]
        collect = json.loads(con.execute("SELECT facts FROM requests WHERE session_id=? AND seq IS NOT NULL",
                                         (sid,)).fetchone()[0])
        self.assertEqual((facts["source"], facts["format"], facts["method"]), ("log", "caddy-json", "GET"))
        self.assertEqual((facts["ip_hash"], facts["net_hash"]), (collect["ip_hash"], collect["net_hash"]))
        self.assertNotIn("?", facts["path"])
        self.assertIn("status", facts)
        self.assertIn("User-Agent".lower(), [name.lower() for name, _ in facts["headers"]])
        self.assertNotIn("cookie", [name.lower() for name, _ in facts["headers"]])
        con.close()
        addresses = {truth.ip for truth, _ in self.lines}
        for name in os.listdir(folder):
            with open(os.path.join(folder, name), "rb") as f:
                text = f.read().decode("latin-1")
            for address in addresses:
                self.assertNotIn(address, text, name)

    def test_an_address_in_a_published_range_gets_the_range_like_an_upload(self):
        con, _ = self.fresh_copy()
        self.run_import(con, "nginx-agentcake")
        ipv6 = published_ipv6()
        found = netfacts.look_up(ipv6)
        rows = [facts for _, _, _, facts in log_rows(con) if facts.get("range") == found["range"]]
        self.assertTrue(rows, "the visitor from a published range")
        self.assertEqual(rows[0]["ip_class"], netfacts.network_class(found))

    def test_a_signed_page_request_is_verified_with_the_bundled_keys(self):
        con, _ = self.fresh_copy()
        self.run_import(con, "nginx-agentcake", directory=signer_directory())
        checked = [facts[evidence.WEB_BOT_AUTH] for _, _, _, facts in log_rows(con) if evidence.WEB_BOT_AUTH in facts]
        self.assertTrue(checked)
        self.assertEqual({(check["outcome"], check["signer"]) for check in checked}, {("verified", SIGNER_HOST)})
        con, _ = self.fresh_copy()
        self.run_import(con, "nginx-agentcake")  # the release's keys: this signer is not among them
        outcomes = {facts[evidence.WEB_BOT_AUTH]["outcome"] for _, _, _, facts in log_rows(con)
                    if evidence.WEB_BOT_AUTH in facts}
        self.assertEqual(outcomes, {"declared"})

    def test_the_verdict_reads_a_logged_signature_like_an_uploads(self):
        con, _ = self.fresh_copy()
        self.run_import(con, "nginx-agentcake", directory=signer_directory())
        signed = next(sid for sid, _, _, facts in log_rows(con) if evidence.WEB_BOT_AUTH in facts)
        found, _, _ = evidence.session_evidence(con, signed, self.c)
        self.assertEqual((found["signatures"]["collector"].outcome, found["signatures"]["collector"].signer),
                         ("verified", SIGNER_HOST))

    def test_a_changed_signature_does_not_verify(self):
        con, _ = self.fresh_copy()
        truth, view = next((t, v) for t, v in self.lines
                           if v is not None and "signature" in t.headers and v.uploads[0] - t.t_ms < 25_000)
        label, encoded = truth.headers["signature"].split("=", 1)
        signature = bytearray(base64.b64decode(encoded.strip(":")))
        signature[10] ^= 1
        changed = f"{label}=:{base64.b64encode(signature).decode()}:"
        lines = [(replace(truth, headers=dict(truth.headers, signature=changed)), view)]
        self.run_import(con, "caddy-json", lines=lines, directory=signer_directory())
        self.assertEqual([facts[evidence.WEB_BOT_AUTH]["outcome"] for _, _, _, facts in log_rows(con)], ["invalid"])

    def test_collect_requests_of_a_visit_leave_its_log_rows_out(self):
        con, _ = self.fresh_copy()
        self.run_import(con, "nginx-agentcake")
        sid = log_rows(con)[0][0]
        uploads = con.execute("SELECT COUNT(*) FROM requests WHERE session_id=? AND seq IS NOT NULL", (sid,)).fetchone()
        self.assertEqual(len(visit_batches.collect_requests(con, sid)), uploads[0])


class Settings(Shop):
    def one_view(self):
        """A page view with no other page view of the same address and User-Agent within a minute of it, so that
        only the window or the clock difference decides whether a line matches it."""
        firsts = [(p.ip, p.ua, v.uploads[0], v) for p in self.people for views in p.sessions for v in views]
        for ip, ua, first, view in firsts:
            near = [v for i, u, f, v in firsts if (i, u) == (ip, ua) and v is not view and abs(f - first) < 60_000]
            if not near:
                return next(p for p in self.people if p.ip == ip and p.ua == ua), view
        raise AssertionError("the shop has no page view on its own")

    def line_at(self, person, view, at_ms):
        headers = {"user-agent": person.ua, "sec-fetch-dest": "document"}
        return [(Truth(at_ms, person.ip, "GET", view.path, "HTTP/2.0", 200, SITE_HOST, "https", headers), view)]

    def test_the_window_comes_from_log_match_window_s(self):
        person, view = self.one_view()
        lines = self.line_at(person, view, view.uploads[0] - 31_000)  # the first upload 31 s after the page request
        con, _ = self.fresh_copy()
        self.assertEqual(self.run_import(con, "caddy-json", lines=lines)["matched"], 0)
        wider = dict(self.c, log_match_window_s=40)
        self.assertEqual(self.run_import(con, "caddy-json", lines=lines, c=wider)["matched"], 1)

    def test_the_clock_difference_allowed_comes_from_log_match_skew_s(self):
        person, view = self.one_view()
        lines = self.line_at(person, view, view.uploads[0] + 1_500)  # logged 1.5 s after the first upload arrived
        con, _ = self.fresh_copy()
        self.assertEqual(self.run_import(con, "caddy-json", lines=lines, c=dict(self.c, log_match_skew_s=1))
                         ["matched"], 0)
        self.assertEqual(self.run_import(con, "caddy-json", lines=lines)["matched"], 1)

    def test_a_record_that_is_not_one_is_counted_bad_and_skipped(self):
        con, _ = self.fresh_copy()
        bad = [{"t": "soon"}, {"t": T0, "ip": 7}, "text", {"t": T0, "ip": "192.0.2.1", "m": "GET", "u": "/", "s": 200,
                                                           "hd": {"user-agent": ["a list"]}}]
        totals = log_match.record(con, {"v": logs.ENVELOPE_VERSION, "run": "r", "format": "combined", "fields": {},
                                        "records": bad}, IMPORT_AT, self.c)
        self.assertEqual((totals["bad"], totals["matched"]), (len(bad), 0))


if __name__ == "__main__":
    unittest.main()
