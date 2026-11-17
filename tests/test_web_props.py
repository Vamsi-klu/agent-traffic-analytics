"""What the web analytics tables group a session by: agentcake/web_props.py (collect-time keep, and fill for sessions
recorded before cake.js sent these fields).

    python3 -I -m unittest discover -s tests -p test_web_props.py -v

An upload's visitor id (and the first identify hash it carried), its first page record's source (the referring domain, the campaign parameters, which click ids
were there: names only), the channel PostHog's rules give them, the device from the User-Agent (and the screen and
client hints of the environment record), the load balancer's country, region and city, and the language and time zone
offset are kept in session_web. The earliest page record of a session gives its entry source. A session recorded by an
older cake.js is filled from what was kept: only the domain of the referrer its page record sent whole, and the
campaign parameters of its landing address. No full referrer address is ever written by them.
"""
import json
import unittest

from web_uploads import MINUTE_MS, T0, TAB, UA_IPHONE, VISITOR, WebCase, upload
from agentcake import streams, web_props

FULL_REFERRER = "https://www.example.org/private/path?q=secret-search-term#frag"


class Keep(WebCase):
    def row(self, *columns):
        return self.one(f"SELECT {', '.join(columns)} FROM session_web WHERE session_id=?", TAB)

    def test_the_visitor_id_of_the_uploads_is_kept(self):
        self.post(upload(0, T0))
        self.assertEqual(self.row("visitor"), (VISITOR,))

    def test_an_upload_without_a_visitor_id_leaves_none(self):
        self.post(upload(0, T0, visitor=None))
        self.assertEqual(self.row("visitor"), (None,))

    def test_the_first_identify_hash_of_the_uploads_is_kept(self):
        self.post(upload(0, T0))
        self.assertEqual(self.row("person"), (None,))
        self.post(upload(1, T0 + 1000, person="a" * 64))
        self.post(upload(2, T0 + 2000, person="b" * 64))
        self.assertEqual(self.row("visitor", "person"), (VISITOR, "a" * 64))

    def test_the_first_page_records_source_and_channel_are_kept(self):
        utm = {"utm_source": "newsletter", "utm_medium": "email", "utm_campaign": "spring", "gad_source": "1"}
        page = {"rd": "www.google.com", "utm": utm, "ck": ["gclid", "fbclid"]}
        self.post(upload(0, T0, page=page))
        self.assertEqual(self.row("referring_domain", "utm_source", "utm_medium", "utm_campaign", "gad_source",
                                  "click_ids", "channel", "language", "tz_offset"),
                         ("www.google.com", "newsletter", "email", "spring", "1", "gclid fbclid", "Paid Search",
                          "en-US", 480))

    def test_the_earliest_page_record_gives_the_entry_source(self):
        self.post(upload(1, T0 + MINUTE_MS, page={"rd": "shop.example.com"}))
        self.post(upload(0, T0, page={"rd": "chatgpt.com"}))
        self.assertEqual(self.row("referring_domain", "channel"), ("chatgpt.com", "AI"))

    def test_a_visit_without_a_referrer_is_direct(self):
        self.post(upload(0, T0, page={}))
        self.assertEqual(self.row("referring_domain", "channel"), ("", "Direct"))

    def test_a_click_id_is_kept_by_name_only(self):
        self.post(upload(0, T0, page={"ck": ["gclid", "not-a-click-id"]}))
        self.assertEqual(self.row("click_ids"), ("gclid",))

    def test_the_device_comes_from_the_user_agent(self):
        self.post(upload(0, T0, ua=UA_IPHONE))
        self.assertEqual(self.row("browser", "os", "device_type"), ("Mobile Safari", "iOS", "Mobile"))

    def test_an_android_tablet_is_told_by_its_screen_as_posthog_does(self):
        ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
        env = {"uaData": {"platform": "Android"}, "maxTouchPoints": 5, "screen": {"w": 1600, "h": 2560}, "dpr": 2,
               "language": "de-DE", "tzOffset": -60}
        self.post(upload(0, T0, ua=ua, env=env))
        self.assertEqual(self.row("device_type", "language", "tz_offset"), ("Tablet", "de-DE", -60))

    def test_a_session_begun_on_an_open_page_keeps_the_device_its_page_was_told_by(self):
        # cake.js begins a new session on a page after 30 minutes without activity; the environment record that told
        # the tablet by its screen was made once, when the page opened, under the session before
        ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
        env = {"uaData": {"platform": "Android"}, "maxTouchPoints": 5, "screen": {"w": 1600, "h": 2560}, "dpr": 2}
        self.post(upload(0, T0, ua=ua, env=env, page={}))
        later = "0123456789abcdef0123456789abcdef"
        self.post(upload(1, T0 + 31 * MINUTE_MS, tab=later, ua=ua, page={"kind": "session"}))
        self.assertEqual(self.one("SELECT device_type FROM session_web WHERE session_id=?", later), ("Tablet",))

    def test_the_load_balancers_place_is_kept_on_a_server(self):
        self.settings = {}
        from agentcake import config
        config.save_user(trust_lb=True, public_listen="127.0.0.1:0")
        self.post(upload(0, T0), public=True, X_Cake_Region="US", X_Cake_Subdivision="USCA",
                  X_Cake_City="Mountain View")
        self.assertEqual(self.row("country", "subdivision", "city"), ("US", "USCA", "Mountain View"))

    def test_without_the_load_balancer_there_is_no_place(self):
        self.post(upload(0, T0), X_Cake_Region="US", X_Cake_City="Mountain View")
        self.assertEqual(self.row("country", "subdivision", "city"), (None, None, None))


class Fill(WebCase):
    def old_session(self, ref=FULL_REFERRER, url="https://shop.example.com/?utm_source=news&gclid=abc123"):
        """A session as an older cake.js recorded it: its page record sent the referrer whole and no source."""
        body = upload(0, T0, visitor=None, activity=True, url=url)
        body["x"] = [{"t": T0, "ty": "page", "n": 1, "ref": ref},
                     {"t": T0 + 5, "ty": "env", "env": {"language": "fr-FR", "tzOffset": -60}}]
        self.post(body)
        self.con.execute("DELETE FROM session_web")  # recorded before session_web existed
        self.con.commit()

    def filled(self):
        web_props.fill(self.con, [TAB])
        self.con.commit()
        return self.one("SELECT referring_domain, utm_source, click_ids, channel, language, tz_offset, browser, "
                        "visitor FROM session_web WHERE session_id=?", TAB)

    def test_an_old_session_gets_the_referrers_domain_and_its_addresss_campaign(self):
        self.old_session()
        # a gclid makes the visit paid; neither "news" nor www.example.org names a paid channel: Paid Unknown (PostHog)
        self.assertEqual(self.filled(), ("www.example.org", "news", "gclid", "Paid Unknown", "fr-FR", -60, "Chrome",
                                         None))

    def test_no_full_referrer_address_is_ever_written_to_session_web(self):
        self.old_session()
        self.filled()
        cells = [json.dumps(row) for row in self.rows("SELECT * FROM session_web")]
        for secret in ("/private/path", "secret-search-term", "#frag"):
            self.assertFalse(any(secret in cell for cell in cells), secret)

    def test_a_session_already_described_is_not_filled_again(self):
        self.post(upload(0, T0, page={"rd": "chatgpt.com"}))
        web_props.fill(self.con, [TAB])
        self.assertEqual(self.one("SELECT referring_domain FROM session_web WHERE session_id=?", TAB), ("chatgpt.com",))

    def test_a_session_without_a_page_record_takes_its_own_address(self):
        body = upload(0, T0, visitor=None, url="https://shop.example.com/?utm_campaign=launch")
        self.post(body)
        self.con.execute("DELETE FROM session_web")
        self.con.commit()
        self.assertEqual(self.filled()[:4], ("", None, None, "Direct"))
        self.assertEqual(self.one("SELECT utm_campaign FROM session_web WHERE session_id=?", TAB), ("launch",))

    def test_a_session_whose_address_cannot_be_read_is_described_without_a_campaign(self):
        self.post(upload(0, T0, visitor=None, url="https://["))  # not a URL urllib can read (an unclosed IPv6 host)
        self.con.execute("DELETE FROM session_web")
        self.con.commit()
        self.assertEqual(self.filled()[:4], ("", None, None, "Direct"))
        self.assertIsNotNone(self.one("SELECT entry_t FROM session_web WHERE session_id=?", TAB)[0])

    def test_the_page_record_is_read_from_the_stored_signals(self):
        self.old_session()
        texts = [text for _, _, text in streams.read_events(self.con, TAB, ["env"])]
        self.assertTrue(any('"ty":"page"' in text for text in texts))



class Addresses(unittest.TestCase):
    """A visit's source from its addresses: one that cannot be read (an upload's u and ref are any text) has no query
    and no domain, as a missing one has, and never stops the request that describes sessions."""

    def test_an_address_that_cannot_be_read_has_no_query_and_no_domain(self):
        for url in ("https://[?utm_source=x", "http://[/cart", "", None):
            with self.subTest(url=url):
                self.assertEqual(web_props._query(url), {})
                self.assertEqual(web_props._domain(url), "")

    def test_a_readable_address_gives_its_query_and_its_host(self):
        self.assertEqual(web_props._query("https://shop.example/?utm_source=x&gclid=1"),
                         {"utm_source": ["x"], "gclid": ["1"]})
        self.assertEqual(web_props._domain("https://User@Shop.Example:8080/cart"), "shop.example:8080")
        self.assertEqual(web_props._domain(7), "")


if __name__ == "__main__":
    unittest.main()
