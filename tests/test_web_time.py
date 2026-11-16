"""A session's page views by path and its active time: agentcake/web_time.py (with collect and web_props.fill).

    python3 -I -m unittest discover -s tests -p test_web_time.py -v

Page views are PostHog's: each page load and each new path (A, B, A is three); a new query string alone is none; a
session begun on a page after 30 minutes without activity has none of its own; an older cake.js's single-page app is
counted from its batches' paths. Active time is the session's time less the time its page was hidden (Clarity's
active time spent): from the raw visibility records, and a page that opened hidden, in the order they happened whatever
order their batches arrive in (an exit batch parked in sessionStorage goes after the next one), also for a session
kept before that order was followed.
"""
import unittest

from web_uploads import KEY, MINUTE_MS, T0, TAB, UA_MAC_CHROME, WebCase, page_record, upload
from agentcake import web_props, web_time

S = 1000  # ms in a second, to write the times below


def path_record(t, path):
    return {"t": t, "ty": "path", "p": path}


def visibility(t, shown):
    return {"t": t, "ty": "visibility", "vs": 1 if shown else 0, "hf": 1 if shown else 0}


def click(t):
    """A made-up click: an action, the session's last record in these tests."""
    return {"t": t, "ty": "click", "tr": 1}


class PageViews(WebCase):
    def views(self, session=TAB):
        return dict(self.rows("SELECT path, views FROM web_paths WHERE session_id=?", session))

    def post_signals(self, seq, t, signals, raw=(), url="https://shop.example.com/a?x=1", **fields):
        body = upload(seq, t, url=url, **fields)
        body["x"], body["r"] = list(signals), list(raw) or body["r"]
        self.post(body)

    def test_a_page_load_is_a_page_view_of_its_path(self):
        self.post_signals(0, T0, [dict(page_record(T0), p="/a")])
        self.assertEqual(self.views(), {"/a": 1})

    def test_each_new_path_is_a_page_view_and_going_back_counts_again(self):
        self.post_signals(0, T0, [dict(page_record(T0), p="/a"), path_record(T0 + S, "/b"),
                                  path_record(T0 + 2 * S, "/a")])
        self.assertEqual(self.views(), {"/a": 2, "/b": 1})

    def test_a_page_record_without_a_path_takes_its_addresss(self):
        self.post_signals(0, T0, [page_record(T0)], url="https://shop.example.com/landing?utm_source=x")
        self.assertEqual(self.views(), {"/landing": 1})

    def test_a_session_begun_on_a_page_has_no_page_view_of_its_own(self):
        self.post_signals(0, T0, [dict(page_record(T0), p="/a")])
        self.post_signals(1, T0 + 31 * MINUTE_MS, [dict(page_record(T0 + 31 * MINUTE_MS, kind="session"))])
        second = self.rows("SELECT session_id FROM session_web WHERE session_id != ?", TAB)[0][0]
        self.assertEqual(self.views(second), {})

    def test_an_older_cake_js_is_counted_from_its_batches_paths(self):
        body = upload(0, T0, url="https://shop.example.com/a")
        body["x"] = [{"t": T0, "ty": "page", "n": 1, "ref": ""}]
        self.post(body)
        self.post(upload(1, T0 + S, url="https://shop.example.com/a?page=2"))  # the query alone: none
        self.post(upload(2, T0 + 2 * S, url="https://shop.example.com/b"))
        self.post(upload(3, T0 + 3 * S, url="https://shop.example.com/a"))
        self.con.execute("DELETE FROM session_web")
        self.con.execute("DELETE FROM web_paths")
        self.con.commit()
        web_props.fill(self.con, [TAB])
        self.assertEqual(self.views(), {"/a": 2, "/b": 1})

    def test_a_cake_0_3_4_visit_is_one_page_view_of_its_address(self):
        # cake 0.3.4's script sent no version, page view or record kinds: its visit has no batch rows, one page
        self.post({"k": KEY, "s": TAB, "u": "https://shop.example.com/checkout?step=2", "ua": UA_MAC_CHROME,
                   "wd": False, "e": [{"type": 3, "timestamp": T0, "data": {}}]})
        self.con.execute("DELETE FROM session_web")
        self.con.commit()
        web_props.fill(self.con, [TAB])
        self.assertEqual(self.views(), {"/checkout": 1})


class ActiveTime(WebCase):
    def times(self):
        return self.one("SELECT first_t, last_t, hidden_ms, hidden_since FROM session_web WHERE session_id=?", TAB)

    def test_the_time_page_hidden_is_left_out(self):
        body = upload(0, T0, page={})
        body["r"] = [visibility(T0 + 10 * S, False), visibility(T0 + 40 * S, True),
                     {"t": T0 + 60 * S, "ty": "pointermove", "cx": 1, "cy": 1, "tr": 1}]
        self.post(body)
        self.assertEqual(web_time.active(*self.times()), (30 * S, 60 * S))

    def test_a_page_still_hidden_is_inactive_until_the_last_record(self):
        body = upload(0, T0, page={})
        body["r"] = [visibility(T0 + 20 * S, False)]
        body["x"].append({"t": T0 + 50 * S, "ty": "leave", "why": "hidden"})
        self.post(body)
        self.assertEqual(web_time.active(*self.times()), (20 * S, 50 * S))

    def test_a_page_that_opened_hidden_is_inactive_until_shown(self):
        body = upload(0, T0, page={})
        body["x"][0]["vis"] = "hidden"
        body["r"] = [visibility(T0 + 15 * S, True), click(T0 + 25 * S)]
        self.post(body)
        self.assertEqual(web_time.active(*self.times()), (10 * S, 25 * S))

    def test_visibility_across_batches_is_followed(self):
        first = upload(0, T0, page={})
        first["r"] = [visibility(T0 + 5 * S, False)]
        second = upload(1, T0 + 30 * S)
        second["r"] = [visibility(T0 + 35 * S, True), click(T0 + 45 * S)]
        self.post(first)
        self.post(second)
        self.assertEqual(web_time.active(*self.times()), (15 * S, 45 * S))

    def test_a_hidden_change_arriving_after_the_next_batch_is_followed_in_time_order(self):
        # cake.js parks an exit batch too big for keepalive and sends it after the next batch (transport.js tick)
        first = upload(0, T0, page={})
        first["r"] = [visibility(T0 + 10 * S, False)]
        second = upload(1, T0 + 30 * S)
        second["r"] = [visibility(T0 + 40 * S, True), click(T0 + 60 * S)]
        self.post(second)
        self.post(first)
        self.assertEqual(web_time.active(*self.times()), (30 * S, 60 * S))

    def test_batches_in_any_order_give_the_time_they_give_in_order(self):
        batches = []
        for n, (t, shown) in enumerate([(10, False), (40, True), (70, False), (90, True)]):
            body = upload(n, T0 + (t - 5) * S, page={} if n == 0 else None)
            body["r"] = [visibility(T0 + t * S, shown)]
            batches.append(body)
        batches[-1]["r"].append(click(T0 + 100 * S))
        for body in (batches[2], batches[0], batches[3], batches[1]):
            self.post(body)
        # from the page record at 5 s to the click at 100 s, hidden from 10 to 40 s and from 70 to 90 s
        self.assertEqual(web_time.active(*self.times()), (95 * S - 30 * S - 20 * S, 95 * S))

    def test_the_last_hidden_of_a_page_stamped_after_the_next_page_began_counts_for_nothing(self):
        # two documents' clocks: the page left fires its "hidden" as it unloads, after the next page's script ran
        first = upload(0, T0, page={}, pv="a" * 32)
        first["r"] = [visibility(T0 + 10 * S + 100, False)]
        second = upload(0, T0 + 10 * S, page={}, pv="b" * 32)
        second["r"] = [click(T0 + 30 * S)]
        self.post(first)
        self.post(second)
        self.assertEqual(web_time.active(*self.times()), (30 * S, 30 * S))

    def test_a_page_shown_again_from_the_back_forward_cache_is_the_tabs_again(self):
        # A, then B, then back to A as it was (no new page view): B's "hidden" and A's "visible" end each stretch
        a, b = "a" * 32, "b" * 32
        bodies = [upload(0, T0, page={}, pv=a), upload(0, T0 + 20 * S, page={}, pv=b), upload(1, T0 + 50 * S, pv=b),
                  upload(1, T0 + 51 * S, pv=a)]
        bodies[0]["r"] = [visibility(T0 + 10 * S, False)]  # A left at 10 s, B began at 20 s
        bodies[2]["r"] = [visibility(T0 + 50 * S, False)]  # B left at 50 s
        bodies[3]["r"] = [visibility(T0 + 51 * S, True), click(T0 + 60 * S)]  # A back at 51 s
        for body in bodies:
            self.post(body)
        self.assertEqual(web_time.active(*self.times()), (60 * S - 10 * S - 1 * S, 60 * S))

    def test_a_session_kept_before_the_order_was_followed_is_recomputed_from_what_was_kept(self):
        first = upload(0, T0, page={})
        first["r"] = [visibility(T0 + 10 * S, False)]
        self.post(first)
        # a row an earlier AgentCake wrote has no vis_t; its hidden period is cleared here, so the answer shows that
        # the next batch reads the kept records instead of going on from the row
        self.con.execute("UPDATE session_web SET vis_t=NULL, hidden_since=NULL WHERE session_id=?", (TAB,))
        self.con.commit()
        second = upload(1, T0 + 30 * S)
        second["r"] = [visibility(T0 + 40 * S, True), click(T0 + 60 * S)]
        self.post(second)
        self.assertEqual(web_time.active(*self.times()), (30 * S, 60 * S))

    def test_a_session_recorded_before_this_has_the_time_of_all_its_records(self):
        # as collect widens the time batch by batch: from the first record of any stream to the last
        body = upload(0, T0, visitor=None)
        body["x"] = [{"t": T0, "ty": "page", "n": 1, "ref": ""}]  # an older cake.js's page record
        body["r"] = [click(T0 + 60 * S)]
        self.post(body)
        live = self.times()
        self.con.execute("DELETE FROM session_web")
        self.con.commit()
        web_props.fill(self.con, [TAB])
        self.assertEqual((self.times(), web_time.active(*self.times())), (live, (60 * S, 60 * S)))

    def test_a_session_without_records_has_no_time(self):
        self.assertIsNone(web_time.active(None, None, 0, None))


if __name__ == "__main__":
    unittest.main()
