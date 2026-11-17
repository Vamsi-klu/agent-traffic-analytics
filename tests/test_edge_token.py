"""Keeping the server half's tokens: edge_token.take_token, as collect calls it for each batch of cake.js.

    python3 -I -m unittest discover -s tests -p test_edge_token.py -v      (from the AgentCake folder)

Each test has its own CAKE_HOME with a secret, and posts batches the way cake.js sends them (or calls take_token with
its own clock). A token is kept once (ok). The page view that brought it bringing it again is dup. Another page view
of the same visit bringing it is reuse: the browser showed a stored copy of the page (a 304, or back to a page kept in
its cache), so the token is not kept twice, not counted twice and not taken for a replay. Another visit bringing a
kept token is replay; a token past the age the settings allow is stale; a changed byte or another secret's token is
bad; without a secret it is off. Collect answers 204 to all of them and keeps the batch: a token's fate is no error
for the visitor. The User-Agent, Accept-Language and network collect sees are compared with the token's; a difference
is kept on the token's srv row as a signal for the verdict's reasons, never a refusal. Revisits replays the visits of
case T8 (home, a link, home again, reload) for each answer a browser may give at the 304: a new token, the stored one,
none.
"""
import http.client
import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from agentcake import collect, config, edge_secret, edge_token, paths, store  # noqa: E402
from agentcake.netfacts import network_key  # noqa: E402
from agentcake.responses import Request  # noqa: E402
from agentcake.units import MS_PER_S  # noqa: E402

KEY = "ck_token_test"
VISIT, OTHER_VISIT = "5b0e6c2f0d8a4a61b7f4c0b1e2d3a4f5", "9c1d7e3f1a2b4c5d6e7f8091a2b3c4d5"
HOME, NEXT, HOME_AGAIN, RELOADED = ("a1" * 16, "b2" * 16, "c3" * 16, "d4" * 16)  # page views, as cake.js makes them
SITE = "http://127.0.0.1:8123"
CHROME_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
             "Chrome/149.0.0.0 Safari/537.36")
FIREFOX_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:144.0) Gecko/20100101 Firefox/144.0"
LANGUAGE = "en-US,en;q=0.9"
ADDRESS, SAME_NETWORK, OTHER_NETWORK = "192.0.2.10", "192.0.2.77", "198.51.100.10"  # documentation ranges
MINUTE_MS = 60 * MS_PER_S


class TokenCase(unittest.TestCase):
    settings = {}

    def setUp(self):
        os.environ["CAKE_HOME"] = tempfile.mkdtemp(prefix="cake-token-")
        os.environ.pop("CAKE_PORT", None)
        config.save_user(site_key=KEY, disk_min_free_mb=0, **self.settings)
        edge_secret.create_secret()
        self.secret = edge_secret.srv_secret()
        self.con = store.db()
        self.addCleanup(self.con.close)
        self.now = int(time.time() * MS_PER_S)  # collect checks a token's age against this computer's clock
        self.next_seq = {}

    def token(self, token_id="tok-home", path="/", age_ms=0, secret=None, **fields):
        """A token the site's middleware signed age_ms ago for a page request with Chrome's headers."""
        payload = {"v": 1, "id": token_id, "t": self.now - age_ms, "p": path, "al": LANGUAGE, "ua": CHROME_UA}
        payload.update(fields)
        return edge_token.sign_payload(secret or self.secret, payload)

    def post(self, token, pv=HOME, visit=VISIT, ua=CHROME_UA, language=LANGUAGE, version=1):
        """One batch of cake.js carrying token, through collect's local listener: (status, X-Cake-Token)."""
        seq = self.next_seq.get((visit, pv), 0)
        self.next_seq[(visit, pv)] = seq + 1
        body = {"k": KEY, "s": visit, "u": SITE + "/", "ua": ua, "wd": False, "e": [], "st": token,
                "x": [{"t": self.now, "ty": "page", "n": 1}]}
        if version:
            body.update(v=version, pv=pv, seq=seq, t=self.now, why="timer")
        headers = http.client.HTTPMessage()
        for name, value in (("User-Agent", ua), ("Accept-Language", language), ("Content-Type", "text/plain")):
            if value is not None:
                headers[name] = value
        response = collect.from_local(Request("/collect", {}, headers, json.dumps(body).encode()))
        return response.status, response.headers.get(collect.TOKEN_STATUS_HEADER)

    def srv(self, columns="session_id, pv, path, reuses"):
        return self.con.execute(f"SELECT id, {columns} FROM srv ORDER BY page_ms, id").fetchall()

    def linked(self, visit=VISIT):
        """{page view: the token ids its batches are linked to}."""
        found = {}
        for pv, token_id in self.con.execute("SELECT pv, token_id FROM batches WHERE session_id=? ORDER BY pv, seq",
                                             (visit,)):
            found.setdefault(pv, set()).add(token_id)
        return found


class Kept(TokenCase):
    def test_a_good_token_is_kept_once_for_its_visit_and_page_view(self):
        self.assertEqual(self.post(self.token()), (204, "ok"))
        self.assertEqual(self.srv(), [("tok-home", VISIT, HOME, "/", 0)])
        self.assertEqual(self.linked(), {HOME: {"tok-home"}})

    def test_the_page_view_that_brought_it_bringing_it_again_is_dup(self):
        token = self.token()
        self.assertEqual([self.post(token), self.post(token)], [(204, "ok"), (204, "dup")])
        self.assertEqual(self.srv(), [("tok-home", VISIT, HOME, "/", 0)])
        self.assertEqual(self.linked(), {HOME: {"tok-home"}})

    def test_another_page_view_of_the_visit_bringing_it_is_reuse(self):
        token = self.token()
        self.assertEqual(self.post(token, pv=HOME), (204, "ok"))
        self.assertEqual(self.post(token, pv=HOME_AGAIN), (204, "reuse"))
        self.assertEqual(self.srv(), [("tok-home", VISIT, HOME, "/", 1)], "one server half, reused once")
        self.assertEqual(self.linked(), {HOME: {"tok-home"}, HOME_AGAIN: {"tok-home"}})

    def test_a_reuse_counts_once_per_page_view(self):
        token = self.token()
        answers = [self.post(token, pv=HOME), self.post(token, pv=HOME_AGAIN), self.post(token, pv=HOME_AGAIN)]
        self.assertEqual([answer for _, answer in answers], ["ok", "reuse", "dup"])
        self.assertEqual(self.srv(), [("tok-home", VISIT, HOME, "/", 1)])

    def test_another_visit_bringing_a_kept_token_is_replay(self):
        token = self.token()
        self.assertEqual(self.post(token), (204, "ok"))
        self.assertEqual(self.post(token, visit=OTHER_VISIT), (204, "replay"))
        self.assertEqual(self.srv(), [("tok-home", VISIT, HOME, "/", 0)])
        self.assertEqual(self.linked(OTHER_VISIT), {HOME: {None}})

    def test_a_cake_034_batch_bringing_it_again_is_dup(self):
        token = self.token()
        self.assertEqual([self.post(token, version=None), self.post(token, version=None)], [(204, "ok"), (204, "dup")])
        self.assertEqual(self.srv(), [("tok-home", VISIT, None, "/", 0)])

    def test_a_changed_byte_anywhere_is_bad_and_nothing_is_kept(self):
        token = self.token()
        for at in (0, len("c1.") + 2, len(token) - 2):
            changed = token[:at] + ("A" if token[at] != "A" else "B") + token[at + 1:]
            with self.subTest(at=at):
                self.assertEqual(self.post(changed), (204, "bad"))
        self.assertEqual(self.srv(), [])

    def test_another_secrets_token_is_bad(self):
        self.assertEqual(self.post(self.token(secret=b"another secret, at least 32 bytes long")), (204, "bad"))
        self.assertEqual(self.srv(), [])

    def test_without_a_secret_a_token_is_off(self):
        os.remove(paths.secret_file())
        self.assertEqual(self.post(self.token()), (204, "off"))
        self.assertEqual(self.srv(), [])

    def test_a_refused_token_never_refuses_the_batch(self):
        for token in (self.token(age_ms=60 * MINUTE_MS), "c1.not.signed"):
            self.post(token, pv=NEXT)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM batches WHERE pv=?", (NEXT,)).fetchone()[0], 2)


class Age(TokenCase):
    settings = {"token_max_age_ms": 5 * MINUTE_MS, "token_max_future_ms": MINUTE_MS}

    def test_a_token_past_the_max_age_setting_is_stale(self):
        # a minute either side of the window: collect reads this computer's clock, which moves on while the test runs
        self.assertEqual(self.post(self.token("tok-old", age_ms=6 * MINUTE_MS)), (204, "stale"))
        self.assertEqual(self.post(self.token("tok-young", age_ms=4 * MINUTE_MS), pv=NEXT), (204, "ok"))
        self.assertEqual([row[0] for row in self.srv()], ["tok-young"])

    def test_a_token_from_further_ahead_than_the_setting_allows_is_stale(self):
        self.assertEqual(self.post(self.token("tok-ahead", age_ms=-2 * MINUTE_MS)), (204, "stale"))
        self.assertEqual(self.post(self.token("tok-near", age_ms=-MINUTE_MS // 2), pv=NEXT), (204, "ok"))


class Compared(TokenCase):
    """What collect sees of the upload request against what the site's server saw of the page request."""

    def take(self, token, ua=CHROME_UA, language=LANGUAGE, address=None, pv=HOME):
        came = edge_token.Delivery(session=VISIT, page_view=pv, seq=0, user_agent=ua, language=language,
                                   address=address)
        return edge_token.take_token(self.con, token, came, self.now)

    def compared(self):
        return self.con.execute("SELECT ua_match, lang_match, net_match FROM srv").fetchall()

    def test_the_same_user_agent_language_and_network_are_marked_same(self):
        token = self.token(ik=network_key(self.secret, ADDRESS, self.now))
        self.assertEqual(self.take(token, address=SAME_NETWORK), "ok")
        self.assertEqual(self.compared(), [(1, 1, 1)])

    def test_another_user_agent_is_a_signal_not_a_refusal(self):
        self.assertEqual(self.take(self.token(), ua=FIREFOX_UA), "ok")
        self.assertEqual(self.compared(), [(0, 1, None)])

    def test_another_language_is_a_signal_not_a_refusal(self):
        self.assertEqual(self.take(self.token(), language="de-DE,de;q=0.9"), "ok")
        self.assertEqual(self.compared(), [(1, 0, None)])

    def test_another_network_is_a_signal_not_a_refusal(self):
        token = self.token(ik=network_key(self.secret, ADDRESS, self.now))
        self.assertEqual(self.take(token, address=OTHER_NETWORK), "ok")
        self.assertEqual(self.compared(), [(1, 1, 0)])

    def test_what_either_side_lacks_is_not_compared(self):
        self.assertEqual(self.take(self.token("tok-bare", al=None, ua=None)), "ok")
        self.assertEqual(self.take(self.token("tok-full"), ua=None, language=None, pv=NEXT), "ok")
        self.assertEqual(self.compared(), [(None, None, None), (None, None, None)])

    def test_values_are_compared_as_the_token_cuts_and_cleans_them(self):
        long_ua = CHROME_UA + " Extra/1.0" * 40
        cut = edge_token.EDGE["cut"]["user_agent"]
        token = self.token(ua=long_ua[:cut], al=LANGUAGE[:edge_token.EDGE["cut"]["accept_language"]])
        self.assertEqual(self.take(token, ua=" " + long_ua + "\x7f"), "ok")
        self.assertEqual(self.compared(), [(1, 1, None)])

    def test_the_comparison_is_kept_but_the_address_and_network_key_are_not(self):
        key = network_key(self.secret, ADDRESS, self.now)
        self.take(self.token(ik=key), address=ADDRESS)
        dump = json.dumps(self.con.execute("SELECT * FROM srv").fetchall())
        self.assertNotIn(ADDRESS, dump)
        self.assertNotIn(key, dump)


class Revisits(TokenCase):
    """Case T8's visits on a site whose HTML is revalidated: home, a link, the link back home (a 304), reload."""

    def visit(self, at_the_304):
        """The four page views; at_the_304(n) is the token the page sees for the n-th revisit: new, stored or None."""
        home, nxt = self.token("tok-home"), self.token("tok-next", path="/next")
        answers = [self.post(home, pv=HOME), self.post(nxt, pv=NEXT)]
        for n, pv in enumerate((HOME_AGAIN, RELOADED)):
            answers.append(self.post(at_the_304(n, home), pv=pv))
        return [answer for _, answer in answers]

    def test_a_browser_that_shows_the_304s_new_token_gives_each_page_its_own(self):
        answers = self.visit(lambda n, home: self.token(f"tok-revisit-{n}"))
        self.assertEqual(answers, ["ok", "ok", "ok", "ok"])
        self.assertEqual(len(self.srv()), 4)
        self.assertEqual(self.linked(), {HOME: {"tok-home"}, NEXT: {"tok-next"}, HOME_AGAIN: {"tok-revisit-0"},
                                         RELOADED: {"tok-revisit-1"}})

    def test_a_browser_that_shows_the_stored_token_reuses_it_without_counting_it_twice(self):
        answers = self.visit(lambda n, home: home)
        self.assertEqual(answers, ["ok", "ok", "reuse", "reuse"])
        self.assertEqual(self.srv(), [("tok-home", VISIT, HOME, "/", 2), ("tok-next", VISIT, NEXT, "/next", 0)])
        self.assertEqual(self.linked()[RELOADED], {"tok-home"})

    def test_a_browser_that_shows_no_token_loses_only_that_page_views_server_half(self):
        answers = self.visit(lambda n, home: None)
        self.assertEqual(answers, ["ok", "ok", None, None])
        self.assertEqual([row[0] for row in self.srv()], ["tok-home", "tok-next"])
        self.assertEqual(self.linked()[HOME_AGAIN], {None})

    def test_back_to_a_page_stored_longer_than_the_max_age_is_stale_not_an_error(self):
        stored = self.token("tok-home", age_ms=config.load_cfg()["token_max_age_ms"] + MINUTE_MS)
        self.assertEqual(self.post(stored, pv=HOME_AGAIN), (204, "stale"))

    def test_a_stored_page_opened_in_a_new_tab_is_replay_not_an_error(self):
        """A new tab is a new visit (cake.js keeps the visit in sessionStorage): the old visit's token is a replay."""
        token = self.token()
        self.post(token)
        self.assertEqual(self.post(token, visit=OTHER_VISIT, pv=HOME_AGAIN), (204, "replay"))


class OlderDatabase(unittest.TestCase):
    def test_a_srv_table_from_cake_0_3_4_gets_the_new_columns(self):
        os.environ["CAKE_HOME"] = tempfile.mkdtemp(prefix="cake-token-old-")
        os.environ.pop("CAKE_PORT", None)
        con = sqlite3.connect(paths.db_file())
        con.execute("CREATE TABLE srv(id TEXT PRIMARY KEY, session_id TEXT, recv_ms INT, page_ms INT, path TEXT, "
                    "body TEXT, net_match INT)")
        con.execute("INSERT INTO srv VALUES('tok-old', 's1', 1, 1, '/', '{}', 1)")
        con.commit()
        con.close()
        con = store.db()
        self.addCleanup(con.close)
        self.assertEqual(con.execute("SELECT id, pv, ua_match, lang_match, net_match, reuses FROM srv").fetchall(),
                         [("tok-old", None, None, None, 1, 0)])


if __name__ == "__main__":
    unittest.main()
