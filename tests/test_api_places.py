"""The Geography table's places on a server: /api/web's country, region and city rows, its place answer
(agentcake/api/places.py), /api/health's, and the session list opened from a row.

    python3 -I -m unittest discover -s tests -p test_api_places.py -v      (from the AgentCake folder)

Sessions come in on the public listener with the load balancer's address header, and the city database
(geo_fixtures.py: documentation addresses in made-up places) gives them their place. As PostHog's web analytics breaks
them down: Country has a Not set row for the sessions it knows no country of; Region and City count a session with
its country, a country's sessions without a region or a city are that country's own Not set row, and a session without
a country is in neither. Without the city database the server's sessions are all Not set and the answers name the
command that downloads it; with it, they carry DB-IP's credit. A region a load balancer gave before (a CLDR id, kept as
it was) still reads by its name.
"""
import json
import unittest
from unittest import mock

import geo_fixtures
from api_client import Client, contract_problems
from web_uploads import T0, WebCase, upload
from agentcake import config, geoip
from agentcake.api import periods

ADDRESSES = {"us": "192.0.2.10", "de": "192.0.2.200", "au": "203.0.113.200", "nowhere": geo_fixtures.beside("198.51.100.255", 2)}
TABS = {name: f"{n:032x}" for n, name in enumerate(ADDRESSES, start=1)}
MINUTE_MS = 60_000


class Places(WebCase):
    settings = {"public_listen": "127.0.0.1:0", "trust_lb": True}

    def visit(self, name, verdict="human"):
        self.post(upload(0, T0, tab=TABS[name], visitor=TABS[name]), public=True, X_Cake_Client_IP=ADDRESSES[name])
        self.con.execute("UPDATE sessions SET verdict_class=?, judged_ms=end_ms + 1 WHERE id=?", (verdict, TABS[name]))
        self.con.commit()

    def get(self, path="/api/web", **query):
        now = self.one("SELECT MAX(start_ms) FROM sessions")[0] + MINUTE_MS
        with mock.patch.object(periods, "now_ms", return_value=now):
            answer = Client().get(path, **query)
        self.assertEqual(answer.status, 200)
        return answer.body

    def rows(self, body, dimension):
        found = next(d["rows"] for d in body["tables"]["geography"] if d["dimension"] == dimension)
        return {row["key"]: (row["value"], row["country"], row["agent"] + row["human"]) for row in found}


class WithTheCityDatabase(Places):
    def setUp(self):
        super().setUp()
        geo_fixtures.install(geoip.user_folder())
        for name in ADDRESSES:
            self.visit(name)

    def test_the_answer_says_the_database_and_carries_db_ips_credit(self):
        body = self.get()
        self.assertEqual(contract_problems(body, "web"), [])
        self.assertEqual(body["place"]["source"], "database")
        self.assertEqual(body["place"]["attribution"], {"text": "IP Geolocation by DB-IP", "url": "https://db-ip.com"})

    def test_country_has_a_not_set_row_for_an_address_in_no_country(self):
        self.assertEqual(self.rows(self.get(), "country"), {"US": ("US", None, 1), "DE": ("DE", None, 1),
                                                           "AU": ("AU", None, 1), None: (None, None, 1)})

    def test_region_and_city_are_counted_with_their_country_and_not_set_by_country(self):
        body = self.get()
        self.assertEqual(self.rows(body, "region"), {"US:California": ("California", "US", 1),
                                                     "DE:": (None, "DE", 1), "AU:": (None, "AU", 1)})
        self.assertEqual(self.rows(body, "city"), {"US:Mountain View": ("Mountain View", "US", 1),
                                                   "DE:Berlin": ("Berlin", "DE", 1), "AU:": (None, "AU", 1)})

    def test_a_countrys_not_set_row_opens_its_sessions(self):
        page = self.get("/api/sessions", dimension="region", key="DE:")
        self.assertEqual([row["id"] for row in page["results"]], [TABS["de"]])
        page = self.get("/api/sessions", dimension="city", key="AU:")
        self.assertEqual([row["id"] for row in page["results"]], [TABS["au"]])
        page = self.get("/api/sessions", dimension="country")
        self.assertEqual([row["id"] for row in page["results"]], [TABS["nowhere"]])

    def test_a_cldr_region_kept_before_reads_by_its_name(self):
        self.con.execute("UPDATE session_web SET subdivision='USCA' WHERE session_id=?", (TABS["us"],))
        self.con.commit()
        self.assertEqual(self.rows(self.get(), "region")["US:USCA"], ("California", "US", 1))

    def test_the_session_pages_network_line_carries_db_ips_credit_with_its_country(self):
        placed = Client().get(f"/api/session/{TABS['us']}").body
        self.assertEqual(contract_problems(placed, "session"), [])
        network = placed["server"]["network"]
        self.assertEqual((network["country"], network["attribution"]["url"]), ("US", "https://db-ip.com"))
        nowhere = Client().get(f"/api/session/{TABS['nowhere']}").body["server"]["network"]
        self.assertEqual((nowhere["country"], nowhere["attribution"]), (None, None))

    def test_health_says_the_database_in_use(self):
        body = Client().get("/api/health").body
        self.assertEqual(contract_problems(body, "health"), [])
        self.assertEqual((body["places"]["source"], body["places"]["database"]["month"]), ("database", "2026-11"))


class WithoutTheCityDatabase(Places):
    def setUp(self):
        super().setUp()
        for name in ADDRESSES:
            self.visit(name)

    def test_every_session_is_not_set_and_the_answers_name_the_command(self):
        body = self.get()
        self.assertEqual(contract_problems(body, "web"), [])
        self.assertEqual(body["place"]["source"], "missing")
        self.assertEqual(body["place"], {"source": "missing", "attribution": None}, "no command: a server updates")
        self.assertEqual(self.rows(body, "country"), {None: (None, None, len(ADDRESSES))})
        self.assertEqual((self.rows(body, "region"), self.rows(body, "city")), ({}, {}))
        health = Client().get("/api/health").body
        self.assertEqual(contract_problems(health, "health"), [])
        self.assertEqual((health["places"]["source"], health["places"]["database"]), ("missing", None))
        self.assertTrue(health["places"]["update_command"].endswith("lists update"))

    def test_once_it_is_downloaded_the_next_sessions_have_places(self):
        geo_fixtures.install(geoip.user_folder())
        self.post(upload(0, T0 + MINUTE_MS, tab="e" * 32), public=True, X_Cake_Client_IP=ADDRESSES["us"])
        self.assertEqual(self.get()["place"]["source"], "database")
        self.assertEqual(json.loads(self.one("SELECT net FROM sessions WHERE id=?", "e" * 32)[0])["country"], "US")


class OnThisComputer(Places):
    settings = {}

    def test_health_says_there_is_no_source_of_places(self):
        geo_fixtures.install(geoip.user_folder())
        body = Client().get("/api/health").body
        self.assertEqual((body["places"]["source"], body["places"]["attribution"]), ("none", None))
        config.save_user(public_listen="127.0.0.1:0", trust_lb=True)
        self.assertEqual(Client().get("/api/health").body["places"]["source"], "database")


if __name__ == "__main__":
    unittest.main()
