"""The privacy scan (GOAL S1, plan step S6.5): tools/privacy_scan.py and tools/privacy/.

    python3 -I -m unittest discover -s tests -p test_privacy_scan.py -v      (from the Agent Cake folder)

A data folder made the way cake makes one (store.db(), streams, cake.log, a backup, an export) gets one planted thing
of every kind, in a database cell, in replay chunks (zstd and zlib), in a dead chunk a reclaim has not removed, in
log lines and in an exported JSON file: each is found, counted and located, and nothing printed holds what was
planted. Clean data full of what looks almost like it (browser versions, millisecond times, CSS pseudo-elements,
retina image names, cake's own listen addresses, the published address lists) is 0 found. Zeros where `agentcake
delete` wiped a chunk are passed over; bytes that are not a chunk are reported, never passed as clean. Every value
planted is made up: documentation addresses (RFC 5737, RFC 3849), example.com, random canaries and card numbers.
"""
import contextlib
import io
import json
import os
import secrets
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from agentcake import paths, store, streams  # noqa: E402
from agentcake.storage_config import SETTINGS  # noqa: E402
from tools import privacy_scan  # noqa: E402
from tools.privacy import rules as rules_module  # noqa: E402

NOW = 1794520800000 + 40 * 60_000
CHROME_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/149.0.0.0 Safari/537.36"


def made_up_card():
    """A random 16-digit number starting 4000 with a valid Luhn check digit, printed in groups of four."""
    body = "4000" + "".join(str(secrets.randbelow(10)) for _ in range(11))
    check = next(d for d in "0123456789" if rules_module.luhn_valid(body + d))
    number = body + check
    return " ".join(number[i:i + 4] for i in range(0, 16, 4))


def clean_events(ts):
    """rrweb and environment events with everything that looks almost like a finding."""
    css = ("a::after{content:''} ::-webkit-scrollbar{width:0} p::before{} @media (max-width:720px){x{y:z}} "
           ".logo{background:url(img/logo@2x.png)} @font-face{src:url(f/inter@2x.woff2)}") * 4
    return [json.dumps({"type": 2, "timestamp": ts, "data": {"node": {"type": 0, "childNodes": [
                {"type": 2, "tagName": "style", "attributes": {"_cssText": css}, "childNodes": []},
                {"type": 3, "textContent": "Open 09:00-17:30, order 4242 4242 by 20:09:54"}]}}}),
            json.dumps({"type": 3, "timestamp": ts + 5, "data": {"source": 1, "positions": [{"x": 523, "y": 88,
                        "id": 4, "timeOffset": -12}]}}),
            json.dumps({"t": ts + 6.4, "ty": "env", "env": {"userAgent": CHROME_UA, "uaFullVersion": "131.0.0.0",
                        "cookieEnabled": True, "devicePixelRatio": 2.0000000298023224, "t0": 1794518371012.3}}),
            json.dumps({"t": ts + 7, "ty": "keydown", "kc": "letter", "ce": 0, "rp": 0, "tr": 1})]


class Folder(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="cake-scan-")
        self.addCleanup(shutil.rmtree, self.home, True)
        env = mock.patch.dict(os.environ, {"CAKE_HOME": self.home})
        env.start()
        self.addCleanup(env.stop)
        self.con = store.db()
        self.addCleanup(self.con.close)

    def visit(self, sid, events, stream="rrweb", cfg=SETTINGS, ua=CHROME_UA, net=None):
        self.con.execute("INSERT OR IGNORE INTO sessions(id, start_ms, end_ms, url, ua, net) VALUES(?,?,?,?,?,?)",
                         (sid, NOW, NOW, "http://127.0.0.1:7878/demo/checkout", ua, net))
        streams.append(self.con, sid, stream, [(NOW + n, e) for n, e in enumerate(events)], NOW, cfg)
        streams.seal(self.con, NOW, force=True, session_id=sid, cfg=cfg)
        self.con.commit()

    def write(self, rel, text):
        path = os.path.join(self.home, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def scan(self, *more, canaries=()):
        self.con.commit()
        return privacy_scan.scan(self.home, more, canaries)

    def main(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = privacy_scan.main([self.home, *args])
        return code, out.getvalue()


class CleanData(Folder):
    def test_cakes_own_kind_of_data_is_zero_found(self):
        self.visit(secrets.token_hex(16), clean_events(NOW))
        self.visit(secrets.token_hex(16), clean_events(NOW + 10_000), stream="env", cfg=dict(SETTINGS, codec="zlib"))
        self.write("config.json", json.dumps({"port": 7878, "public_listen": "0.0.0.0:8080", "site_key": "ck_1a2b3c"}))
        self.write("cake.log", "Agent Cake 0.4.0 serving http://127.0.0.1:7878/ (data folder ~/.cake)\n"
                               "public listener on [::1]:8080, 2026-11-12 20:09:54\n")
        self.write("lists/2026-11-12/ip_ranges.json", json.dumps({"ranges": [{"v4": ["20.171.206.0/24"]}]}))
        self.write("srv_secret", secrets.token_urlsafe(48))
        result = self.scan()
        self.assertEqual((result["found"], result["unreadable"]), (0, []), result)
        skipped = {path for path, _ in result["skipped"]}
        self.assertEqual(skipped - {"cake.db-wal", "cake.db-shm"}, {"lists/", "srv_secret"}, "and the open database's "
                                                                                           "log and index files")
        self.assertGreater(result["read"]["chunk lines"], 0)
        self.assertGreater(result["read"]["cells"], 0)
        self.assertEqual(self.main()[0], 0)

    def test_zeros_where_a_chunk_was_wiped_are_passed_over(self):
        sid = secrets.token_hex(16)
        self.visit(sid, clean_events(NOW))
        self.visit(secrets.token_hex(16), clean_events(NOW + 1))
        rel, offset, length = self.con.execute("SELECT file, byte_offset, byte_length FROM chunks WHERE session_id=?",
                                               (sid,)).fetchone()
        with open(os.path.join(self.home, SETTINGS["replay_dir"], rel), "r+b") as f:
            f.seek(offset)
            f.write(bytes(length))
        result = self.scan()
        self.assertEqual((result["found"], result["unreadable"]), (0, []))
        self.assertEqual(result["read"]["chunks"], 1, "the other visit's chunk, found after the zeros")


class PlantedData(Folder):
    def setUp(self):
        super().setUp()
        self.canary = "cake-canary-" + secrets.token_hex(8)
        self.card = made_up_card()
        self.secret = secrets.token_urlsafe(48)
        self.d = secrets.token_urlsafe(32)
        self.write("srv_secret", self.secret)
        sid = secrets.token_hex(16)
        self.visit(sid, [json.dumps({"type": 3, "data": {"text": "2001:db8:85a3::8a2e:370:7334"}}),
                         json.dumps({"type": 3, "data": {"text": "Card 4242 4242 4242 4242"}})],
                   net=json.dumps({"country": "ZZ", "ip": "203.0.113.77"}))
        self.visit(sid, [json.dumps({"t": NOW, "ty": "keydown", "key": "a", "note": self.card})], stream="raw")
        self.visit(sid, [json.dumps({"t": NOW, "ty": "x", "typed": self.canary})], stream="env",
                   cfg=dict(SETTINGS, codec="zlib"))
        self.styled = "cake-canary-" + secrets.token_hex(8)  # only inside a zlib-compressed stylesheet
        css = f".promo::after{{content:'{self.styled}'}}" + ".grid{display:grid;gap:1rem}" * 20  # long enough to cut
        self.visit(sid, [json.dumps({"type": 2, "timestamp": NOW, "data": {"node": {"type": 2, "tagName": "style",
                                     "attributes": {"_cssText": css}, "childNodes": []}}})],
                   cfg=dict(SETTINGS, codec="zlib"))
        dead = secrets.token_hex(16)
        self.visit(dead, [json.dumps({"type": 3, "data": {"text": "mail visitor@example.com"}})])
        streams.drop_replay(self.con, dead)  # dropped, not reclaimed: its bytes are still in the file
        self.con.execute("INSERT INTO srv(id, session_id, recv_ms, page_ms, path, body, net_match) "
                         "VALUES('t1', ?, ?, ?, '/', ?, 1)",
                         (sid, NOW, NOW, json.dumps({"cookie": "sid=0123456789", "authorization": "Basic dXNlcjpwYXNz"})))
        self.write("cake.log", "\n".join([
            "client 198.51.100.23 sent", "{'code': 'KeyA'}", "Cookie: sid=1", "-----BEGIN PRIVATE KEY-----",
            f"secret leaked {self.secret}", "token Bearer abcdefghijklmnop1234567890"]) + "\n")
        outside = tempfile.mkdtemp(prefix="cake-export-")  # an export kept outside the data folder
        self.addCleanup(shutil.rmtree, outside, True)
        self.export = os.path.join(outside, "visit.json")
        with open(self.export, "w", encoding="utf-8") as f:
            f.write(json.dumps({"typed": self.canary, "jwk": {"kty": "OKP", "crv": "Ed25519", "x": "A" * 43,
                                                              "d": self.d}}) + "\n")
        self.planted = [self.canary, self.card, self.card.replace(" ", ""), self.secret, self.d, "203.0.113.77",
                        "198.51.100.23", "2001:db8:85a3::8a2e:370:7334", "visitor@example.com", "sid=0123456789",
                        "dXNlcjpwYXNz", "abcdefghijklmnop1234567890"]

    def test_each_kind_is_found_counted_and_located(self):
        result = self.scan(canaries=[self.canary])
        want = {"ipv4": 2, "ipv6": 1, "canary": 1, "card_number": 1, "test_card": 1, "key_name": 2, "cookie": 2,
                "authorization": 2, "private_key": 1, "srv_secret": 1, "email": 1}
        self.assertEqual(result["by_kind"], want)
        where = result["where"]
        self.assertTrue(where["ipv4"][0].startswith("cake.db sessions.net row "))
        self.assertRegex(where["ipv4"][1], r"^cake\.log line 1$")
        self.assertRegex(where["ipv6"][0], r"^replays/\S+\.bin chunk@\d+ line 1$")
        self.assertRegex(where["canary"][0], r"^replays/\S+\.bin chunk@\d+ line 1$", "inside a zlib chunk")
        self.assertRegex(where["email"][0], r"^replays/\S+\.bin chunk@\d+ line 1$", "inside a dead chunk")
        self.assertTrue(where["cookie"][0].startswith("cake.db srv.body row "))
        self.assertEqual(where["srv_secret"], ["cake.log line 5"])
        self.assertEqual(result["unreadable"], [])
        self.assertIn("srv_secret", [path for path, _ in result["skipped"]])

    def test_a_compressed_stylesheet_is_read_decompressed(self):
        result = self.scan(canaries=[self.styled])
        self.assertEqual(result["by_kind"]["canary"], 1)
        self.assertRegex(result["where"]["canary"][0], r"^cake\.db styles\.body row \d+$")

    def test_an_export_given_next_to_the_folder_is_read_too(self):
        result = self.scan(self.export, canaries=[self.canary])
        self.assertEqual(result["by_kind"]["canary"], 2)
        self.assertEqual(result["by_kind"]["private_key"], 2, "the PEM line and the JWK with d")
        self.assertIn("visit.json line 1", result["where"]["canary"])

    def test_nothing_printed_holds_what_was_planted(self):
        for args in ([], ["--json"]):
            code, out = self.main(self.export, "--canary", self.canary, *args)
            self.assertEqual(code, 1)
            for value in self.planted:
                self.assertNotIn(value, out)
            self.assertNotIn(self.home, out, "the folder's own path is not printed")
        self.assertEqual(json.loads(self.main("--json")[1])["by_kind"]["ipv4"], 2)

    def test_bytes_that_are_not_a_chunk_are_reported_not_passed(self):
        rel = self.con.execute("SELECT file FROM chunks LIMIT 1").fetchone()[0]
        with open(os.path.join(self.home, SETTINGS["replay_dir"], rel), "ab") as f:
            f.write(b"CKC1\x00\x00\x00\x09not json!" + secrets.token_bytes(64))
        result = self.scan()
        self.assertEqual(len(result["unreadable"]), 1, result["unreadable"])
        self.assertEqual(self.main()[0], 1)


class Rules(unittest.TestCase):
    rules = rules_module.Rules(canaries=["cake-canary-x1"], secret="S3cr3t-value-of-the-folder")

    def kinds(self, text):
        return sorted(self.rules.find(text))

    def test_addresses(self):
        for text, want in [("ip 198.51.100.7.", ["ipv4"]), ("http://203.0.113.5/x", ["ipv4"]),
                           ("HeadlessChrome/149.0.0.0", []), ('"uaFullVersion":"131.0.0.0"', []),
                           ("127.0.0.1 and 0.0.0.0 and ::1", []), ("999.1.1.1 1.2.3", []),
                           ("2001:db8::1", ["ipv6"]), ("::ffff:203.0.113.9", ["ipv4"]),
                           ("a::before ::-webkit-x 20:09:54 00:1a:2b:3c:4d:5e", [])]:
            self.assertEqual(self.kinds(text), want, text)

    def test_cards(self):
        for text, want in [("4242 4242 4242 4242", ["test_card"]), ("4242424242424242", ["test_card"]),
                           ("pay 4000-0000-0000-0002 now", ["card_number"]), ("3782 822463 10005", ["card_number"]),
                           ("1794518371369", []), ("t:1794518371302.4", []), ("4242-4242 4242 4242", []),
                           ("4242 4242 4242 4243", []), ("0.4242424242424242", []), ("id4242424242424242", [])]:
            self.assertEqual(self.kinds(text), want, text)

    def test_keys_headers_secrets_and_mail(self):
        for text, want in [('{"key":"a"}', ["key_name"]), ("{'code': 'ArrowLeft'}", ["key_name"]),
                           ('"keyCode": 65', ["key_name"]), ('"kc":"letter"', []), ('"key":"value_long"', []),
                           ('"Cookie": "a=b"', ["cookie"]), ('"cookieEnabled": true', []),
                           ("Authorization: Basic x", ["authorization"]), ("Bearer short", []),
                           ('{"kty":"OKP","x":"' + "A" * 43 + '"}', []), ("cake-canary-X1 typed", ["canary"]),
                           ("S3cr3t-value-of-the-folder", ["srv_secret"]), ("a@example.com", ["email"]),
                           ("logo@2x.png react@18.3.1", [])]:
            self.assertEqual(self.kinds(text), want, text)


if __name__ == "__main__":
    unittest.main()
