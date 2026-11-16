"""GET and POST /api/register: agentcake/api/registration.py.

    python3 -I -m unittest discover -s tests -p test_api_registration.py -v      (from the AgentCake folder)

GET tells the local page whether this data folder has registered (until it has, the dashboard shows the card first),
what it sent, and the rules the card checks. POST is the press of "Register and continue": the body the page showed goes,
once and byte for byte, to register_url (here a stand-in on a free port of this computer), and what was sent is kept;
when it cannot be sent (nothing listening, refused, no address) the answer says why, nothing is kept and nothing is
tried again. Only this computer's own pages may post, only JSON, only on the local listener. Before the press, the whole
first run (a fresh data folder, a cake.js upload, doctor, the local page and the questions it asks) opens no connection
to anything but this computer.
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from api_client import Client, contract_problems  # noqa: E402
from cake_server import pages_stub  # noqa: E402
from receiver import LOOPBACK, OutsideGuard, Receiver, closed_url, free_port  # noqa: E402
from test_collect import batch  # noqa: E402
from test_register import written  # noqa: E402
from agentcake import config, doctor, register, routes, server  # noqa: E402

PROXY_VARIABLES = ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")


class RegistrationCase(unittest.TestCase):
    def setUp(self):
        os.environ["CAKE_HOME"] = tempfile.mkdtemp(prefix="cake-test-")
        os.environ.pop("CAKE_PORT", None)
        proxies = {name: os.environ.pop(name) for name in PROXY_VARIABLES if name in os.environ}
        self.addCleanup(os.environ.update, proxies)  # the stand-in is on this computer: no proxy in between
        config.save_user(site_key="ck_registration", disk_min_free_mb=0)
        self.client = Client()

    def receiver(self, **kwargs):
        receiver = Receiver(**kwargs)
        self.addCleanup(receiver.close)
        config.save_user(register_url=receiver.url)
        return receiver

    def state(self):
        answer = self.client.get("/api/register")
        self.assertEqual(answer.status, 200, answer.body)
        self.assertEqual(contract_problems(answer.body, "register"), [])
        return answer.body

    def press(self, body=None, **kwargs):
        raw = (written() if body is None else body).encode("utf-8")
        return self.client.post("/api/register", raw, **kwargs)

    def refused(self, answer, status):
        self.assertEqual(answer.status, status, answer.body)
        self.assertEqual(contract_problems(answer.body, "error"), [])
        self.assertFalse(self.state()["registered"], "nothing kept")
        return answer.body["error"]


class Register(RegistrationCase):
    def test_before_registering_the_page_is_told_to_ask_and_given_the_rules(self):
        state = self.state()
        self.assertEqual((state["registered"], state["sent"]), (False, None))
        self.assertEqual(state["delete_contact"], "admin@tartini.ai", "the address PRIVACY.md gives")
        self.assertIn("write to admin@tartini.ai", open(os.path.join(os.path.dirname(HERE), "PRIVACY.md")).read())

    def test_a_press_sends_once_exactly_what_the_page_showed_and_it_is_kept(self):
        receiver, body = self.receiver(), written(product_updates=True)
        answer = self.press(body)
        self.assertEqual(answer.status, 200, answer.body)
        self.assertEqual(contract_problems(answer.body, "register"), [])
        self.assertEqual([r["body"] for r in receiver.requests], [body.encode("utf-8")])
        state = self.state()
        self.assertTrue(state["registered"])
        self.assertEqual(state["sent"]["body"], body, "the settings page shows what was sent")

    def test_a_folder_registers_once(self):
        receiver = self.receiver()
        self.assertEqual(self.press().status, 200)
        self.assertEqual(self.press(written(email="other@example.com")).status, 409)
        self.assertEqual(len(receiver.requests), 1)
        self.assertIn("owner@example.com", self.state()["sent"]["body"])

    def test_nothing_listening_says_why_keeps_nothing_and_tries_nothing_again(self):
        url = closed_url()
        config.save_user(register_url=url)
        with OutsideGuard() as guard:
            message = self.refused(self.press(), 502)
        self.assertIn(url.split("/")[2], message, "it names where it tried")
        port = int(url.split("/")[2].rsplit(":", 1)[1])
        self.assertEqual([where for where in guard.local if isinstance(where, tuple) and where[1] == port],
                         [(LOOPBACK, port)], "one attempt, no retry")

    def test_a_receiver_that_refuses_is_reported_with_its_answer_and_asked_once(self):
        receiver = self.receiver(status=404)
        self.assertIn("404", self.refused(self.press(), 502))
        self.assertEqual(len(receiver.requests), 1)
        self.assertEqual(self.press().status, 502, "a second press is a second press, still not kept")
        self.assertEqual(len(receiver.requests), 2)

    def test_an_empty_address_sends_nothing_and_says_so(self):
        config.save_user(register_url="")
        with OutsideGuard() as guard:
            message = self.refused(self.press(), 503)
        self.assertIn("register_url", message)
        self.assertEqual((guard.outside, guard.local), ([], []), "not one connection tried")

    def test_a_body_the_page_does_not_write_is_400_and_sends_nothing(self):
        receiver = self.receiver()
        self.assertIn("email address", self.refused(self.press(written(email="owner@example")), 400))
        self.assertIn("as it appears on the page", self.refused(self.press(json.dumps(json.loads(written()))), 400))
        self.assertIn("isn't a registration field", self.refused(self.press(written(site="shop.example.com")), 400))
        self.assertEqual(receiver.requests, [])

    def test_only_this_computers_pages_may_post_and_only_json(self):
        receiver = self.receiver()
        self.refused(self.press(headers={"Origin": "https://evil.example"}), 403)
        self.refused(self.press(content_type="application/x-www-form-urlencoded"), 415)
        self.refused(self.press(headers={"Host": "evil.example"}), 403)
        self.assertEqual(receiver.requests, [])

    def test_only_the_local_listener_has_it(self):
        for method in ("GET", "POST"):
            self.assertIsNone(routes.resolve(routes.PUBLIC, method, "/api/register"))
            self.assertIsNotNone(routes.resolve(routes.LOCAL, method, "/api/register"))


class NothingLeavesBeforeThePress(RegistrationCase):
    """The first run, on a real local listener (a free port) with a guard on every socket of this process."""

    def setUp(self):
        super().setUp()
        os.environ["CAKE_PORT"] = str(free_port())
        self.addCleanup(os.environ.pop, "CAKE_PORT", None)
        os.environ["CAKE_WEB_DIR"] = pages_stub()
        self.addCleanup(os.environ.pop, "CAKE_WEB_DIR", None)

    def ask(self, base, path, body=None, content_type="text/plain"):
        headers = {"Content-Type": content_type} if body is not None else {}
        request = urllib.request.Request(base + path, data=body, headers=headers)
        with urllib.request.urlopen(request, timeout=config.load_cfg()["http_timeout_s"]) as response:
            return response.status, response.read()

    def test_the_first_run_opens_no_connection_beyond_this_computer(self):
        with OutsideGuard() as guard:
            c = config.ensure_cfg()  # the first start makes the site key
            local, _ = server.make_listeners(c)
            threading.Thread(target=local.serve_forever, daemon=True).start()
            try:
                base = config.base_url(c)
                self.assertEqual(self.ask(base, "/cake.js")[0], 200)
                upload = batch(k=c["site_key"], u="http://localhost:3000/")  # a dev server on this computer
                status, _ = self.ask(base, "/collect", json.dumps(upload).encode())
                self.assertLess(status, 300, "collect needs no registration")
                with contextlib.redirect_stdout(io.StringIO()) as printed:
                    doctor.doctor()
                self.assertNotIn("regist", printed.getvalue().lower(), "doctor needs no registration")
                self.assertEqual(self.ask(base, "/")[0], 200, "the local page opens")
                for path in ("/api/setup", "/api/overview", "/api/settings"):
                    self.assertEqual(self.ask(base, path)[0], 200, path)
                status, answer = self.ask(base, "/api/register")
                self.assertEqual((status, json.loads(answer)["registered"]), (200, False), "the card is shown")
            finally:
                local.shutdown()
                local.server_close()
        self.assertEqual(guard.outside, [], "nothing left this computer")
        self.assertTrue(guard.local, "the guard saw this test's own requests")

    def test_the_guard_stops_and_notes_what_would_leave(self):
        with OutsideGuard() as guard, self.assertRaises(register.NotSent):
            register.send(written(), config.DEFAULTS["register_url"])
        self.assertEqual(len(guard.outside), 1, "one lookup of the receiving address, refused before any request")


if __name__ == "__main__":
    unittest.main()
