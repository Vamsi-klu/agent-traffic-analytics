"""Network facts of every upload request: agentcake/netfacts.py, and its salt (ip_salt.py) through collect.

    python3 -I -m unittest discover -s tests -p test_netfacts.py -v      (from the AgentCake folder)

Each upload request keeps its User-Agent, Accept-Language, the three low-entropy sec-ch-ua headers, Sec-Fetch-*,
Origin and the Web Bot Auth headers as sent, every header name in order, and where it came from; cookies,
credentials and forwarding headers keep only their names. The visitor's address counts only on the public listener
with trust_lb, from the load balancer's header: it is looked up in the bundled lists (published range, relay, CDN,
cloud) and in the city database (country, region, city: never from a header a client could write), hashed with a salt
that is replaced every ip_salt_days, and then dropped; the privacy scan finds it in no file.
"""
import http.client
import ipaddress
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import geo_fixtures  # noqa: E402
from agentcake import collect, config, geoip, ip_salt, netfacts, store, visit_batches  # noqa: E402
from agentcake.datafiles import load, sizes  # noqa: E402
from agentcake.detect import env_signals  # noqa: E402
from agentcake.responses import Request  # noqa: E402
from tools import privacy_scan  # noqa: E402

KEY = "ck_netfacts_test"
T0 = 1794518371300
RANGES = load("data/lists/ip_ranges.json")["ranges"]
LB = netfacts.lb_headers()
# The place headers AgentCake 0.5 read from a load balancer: a visitor can send them too, and none is read any more
CLIENT_PLACE = [["X-Cake-Region", "FR"], ["X-Cake-Subdivision", "FRIDF"], ["X-Cake-City", "Paris"]]
CHROME = [["Host", "shop.example"], ["Connection", "keep-alive"], ["sec-ch-ua-platform", '"macOS"'],
          ["User-Agent", "Mozilla/5.0 (Macintosh) Chrome/149.0.0.0 Safari/537.36"],
          ["sec-ch-ua", '"Chromium";v="149", "Not)A;Brand";v="24"'], ["Content-Type", "text/plain"],
          ["sec-ch-ua-mobile", "?0"], ["Accept", "*/*"], ["Origin", "https://shop.example"],
          ["Sec-Fetch-Site", "same-origin"], ["Sec-Fetch-Mode", "cors"], ["Sec-Fetch-Dest", "empty"],
          ["Referer", "https://shop.example/cart?coupon=x"], ["Accept-Encoding", "gzip"],
          ["Accept-Language", "en-US,en;q=0.9"], ["Cookie", "session=secret-cookie-value"]]


def address_of(kind, version=4):
    """The first address of the first bundled range of this kind (agent, bot, relay, cdn, cloud)."""
    block = next(r for r in RANGES if r["kind"] == kind and r[f"v{version}"])[f"v{version}"][0]
    return str(next(ipaddress.ip_network(block).hosts()))


def message(pairs):
    headers = http.client.HTTPMessage()
    for name, value in pairs:
        headers[name] = value
    return headers


def facts_for(pairs, lb=True, origin="site"):
    headers = message(pairs)
    address = netfacts.client_address(headers, {"trust_lb": lb}, public=True)
    return netfacts.request_facts(headers, origin, lb, netfacts.look_up(address))


def batch(seq=0, pv="pv1"):
    return {"v": 1, "k": KEY, "s": "visit1", "pv": pv, "seq": seq, "t": T0, "u": "https://shop.example/",
            "e": [], "r": [{"t": T0 + seq, "ty": "click", "tr": 1}], "x": []}


class RequestFacts(unittest.TestCase):
    def test_the_listed_headers_are_kept_as_sent_with_every_name_in_order(self):
        facts = facts_for(CHROME, lb=False)
        kept = dict(facts["headers"])
        for name in ("User-Agent", "sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform", "Accept-Language", "Origin",
                     "Sec-Fetch-Site", "Sec-Fetch-Mode", "Sec-Fetch-Dest"):
            self.assertEqual(kept[name], dict(CHROME)[name], name)
        self.assertEqual(facts["names"], [name.lower() for name, _ in CHROME])
        self.assertEqual(facts["origin"], "site")

    def test_cookies_credentials_referer_and_forwarding_headers_keep_only_their_names(self):
        pairs = CHROME + [["Authorization", "Bearer abc"], ["X-Forwarded-For", "198.51.100.7"],
                          ["Forwarded", "for=198.51.100.7"], ["X-Real-IP", "198.51.100.7"]]
        text = json.dumps(facts_for(pairs, lb=False))
        for secret in ("secret-cookie-value", "Bearer abc", "198.51.100.7", "coupon=x"):
            self.assertNotIn(secret, text)
        self.assertIn("x-forwarded-for", text, "the name stays: the order of names is a fact")

    def test_signature_headers_are_kept_as_sent(self):
        sig = [["Signature-Agent", '"https://chatgpt.com"'], ["Signature-Input", 'sig1=("@authority");created=1'],
               ["Signature", "sig1=:AAAA:"]]
        self.assertEqual([pair for pair in facts_for(CHROME + sig, lb=False)["headers"] if pair[0].startswith("Signature")],
                         sig)

    def test_values_are_cut_to_their_caps(self):
        caps = sizes()["max_chars"]
        facts = facts_for([["User-Agent", "u" * 1000], ["Accept-Language", "a" * 1000], ["Signature", "s" * 1000]], lb=False)
        lengths = {name: len(value) for name, value in facts["headers"]}
        self.assertEqual(lengths, {"User-Agent": caps["user_agent"], "Accept-Language": caps["header_value"],
                                   "Signature": caps["signature_header"]})

    def test_without_the_load_balancer_layer_there_are_no_address_facts(self):
        pairs = CHROME + [[LB["ip"], address_of("cloud")]] + CLIENT_PLACE
        for facts in (facts_for(pairs, lb=False),
                      netfacts.request_facts(message(pairs), "site", False, None)):
            self.assertNotIn("ip_class", facts, "unknown, not 'no class'")
            self.assertNotIn("country", facts)
        self.assertIsNone(netfacts.client_address(message(pairs), {"trust_lb": True}, public=False), "local listener")
        self.assertIsNone(netfacts.client_address(message(CHROME + [["X-Forwarded-For", "198.51.100.7"]]),
                                                  {"trust_lb": True}, public=True), "forwarding headers never count")

    def test_an_address_gets_its_published_range_and_network_class(self):
        cases = {address_of("agent"): ("agent", None), address_of("relay"): (None, "relay"),
                 address_of("relay", 6): (None, "relay"), address_of("cdn"): (None, "cdn"),
                 address_of("cloud"): (None, "cloud"), "198.51.100.23": (None, None), "2001:db8::17": (None, None),
                 "::ffff:" + address_of("agent"): ("agent", None)}
        for address, (range_kind, network) in cases.items():
            facts = facts_for(CHROME + [[LB["ip"], address]])
            self.assertEqual(facts["range_kind"], range_kind, address)
            self.assertIn("ip_class", facts, address)
            if network:
                self.assertEqual(facts["ip_class"], network, address)
            self.assertNotIn(address, json.dumps(facts))
        agent = facts_for(CHROME + [[LB["ip"], address_of("agent")]])
        self.assertEqual((agent["range_id"], agent["operator"]), ("openai-chatgpt-user", "OpenAI"))
        self.assertIn("chatgpt-user", agent["verifies"])

    def test_proxy_hops_reads_x_forwarded_for_that_many_entries_from_the_right(self):
        """Each proxy adds the address it was reached from at the right of X-Forwarded-For; with N proxies of your
        own, the N-th entry from the right is the one the first of them added: the visitor's. Anything to its left
        came with the request and can be anything (PostHog 1.0 takes the leftmost)."""
        def read(hops, *lines, trust_lb=True, public=True, extra=()):
            pairs = CHROME + [["X-Forwarded-For", line] for line in lines] + list(extra)
            return netfacts.client_address(message(pairs), {"trust_lb": trust_lb, "proxy_hops": hops}, public)

        visitor, spoofed, proxy = "203.0.113.7", "198.51.100.66", "192.0.2.10"
        self.assertEqual(read(1, visitor), visitor)
        self.assertEqual(read(1, f"{spoofed}, {visitor}"), visitor)
        self.assertEqual(read(2, f"{spoofed},{visitor}, {proxy}"), visitor)
        self.assertEqual(read(2, spoofed, f"{visitor}, {proxy}"), visitor, "several header lines, in order")
        self.assertEqual(read(3, f"{visitor}, {proxy}, 192.0.2.11"), visitor)
        self.assertIsNone(read(2, visitor), "fewer entries than proxies: never the leftmost instead")
        self.assertEqual(read(1, f"{visitor}:51234"), visitor, "a port some proxies add")
        self.assertEqual(read(1, "[2001:db8::7]:443"), "2001:db8::7")
        self.assertEqual(read(1, "2001:db8::7"), "2001:db8::7")
        self.assertIsNone(read(1, "unknown"))
        self.assertIsNone(read(1, f"{visitor}, "), "an empty entry is not an address")
        self.assertEqual(read(0, visitor, extra=[[LB["ip"], proxy]]), proxy, "0: the load balancer's header only")
        self.assertEqual(read(1, visitor, extra=[[LB["ip"], proxy]]), visitor, "N: X-Forwarded-For only")
        self.assertIsNone(read(1, visitor, trust_lb=False), "no forwarding header counts without trust_lb")
        self.assertIsNone(read(1, visitor, public=False), "the local listener")

    def test_the_proxy_hops_setting_is_a_count_from_zero(self):
        schema = load("defaults.json")["proxy_hops"]
        self.assertEqual((schema["default"], schema["min"]), (0, 0))
        self.assertEqual(config.coerce("proxy_hops", "2"), 2)
        with self.assertRaises(ValueError):
            config.coerce("proxy_hops", "-1")

    def test_an_unreadable_address_gives_no_address_facts(self):
        for value in ("", "not an address", "198.51.100.7, 10.0.0.1", "999.1.1.1"):
            self.assertNotIn("ip_class", facts_for(CHROME + [[LB["ip"], value]]), value)


class Place(unittest.TestCase):
    """The country, region and city of the visitor's address come from the city database on this server."""

    def setUp(self):
        environment = mock.patch.dict(os.environ, {"CAKE_HOME": tempfile.mkdtemp(prefix="cake-test-")})
        environment.start()
        self.addCleanup(environment.stop)
        geo_fixtures.install(geoip.user_folder())

    def net(self, pairs):
        return netfacts.net_facts(message(pairs), {"trust_lb": True})[0]

    def test_the_place_comes_from_the_city_database(self):
        for address, place in geo_fixtures.PLACES.items():
            pairs = CHROME + [[LB["ip"], address]]
            facts, net = facts_for(pairs), self.net(pairs)
            self.assertEqual({key: facts.get(key) for key in place}, place, address)
            self.assertEqual({key: net.get(key) for key in place}, place, address)
            self.assertNotIn(address, json.dumps([facts, net]))

    def test_a_place_a_client_writes_in_a_header_is_never_read(self):
        net = self.net(CHROME + [[LB["ip"], "192.0.2.200"]] + CLIENT_PLACE)
        self.assertEqual((net["country"], net["subdivision"], net["city"]), ("DE", None, "Berlin"))
        for facts in (facts_for(CHROME + [[LB["ip"], geo_fixtures.beside("198.51.100.255", 2)]] + CLIENT_PLACE),
                      self.net(CHROME + [[LB["ip"], geo_fixtures.beside("198.51.100.255", 2)]] + CLIENT_PLACE),
                      self.net(CHROME + CLIENT_PLACE)):
            self.assertFalse({"country", "subdivision", "city"} & set(facts), "an address in no country, or none")

    def test_without_a_database_there_is_no_place(self):
        shutil.rmtree(geoip.user_folder())
        pairs = CHROME + [[LB["ip"], "198.51.100.7"]]
        self.assertNotIn("country", facts_for(pairs))
        self.assertNotIn("country", self.net(pairs))
        self.assertIn("ip_class", facts_for(pairs), "the lists are still read")


class Salt(unittest.TestCase):
    def setUp(self):
        os.environ["CAKE_HOME"] = tempfile.mkdtemp(prefix="cake-test-")
        self.con = store.db()
        self.addCleanup(self.con.close)

    def test_hashes_tell_the_same_address_and_network_apart_and_change_with_the_salt(self):
        salt = ip_salt.current(self.con, T0)
        a, b, c = (netfacts.address_hashes(salt, ip) for ip in ("198.51.100.23", "198.51.100.24", "203.0.113.23"))
        self.assertEqual(a, netfacts.address_hashes(salt, "198.51.100.23"))
        self.assertEqual(a, netfacts.address_hashes(salt, "::ffff:198.51.100.23"), "one address, two spellings")
        self.assertNotEqual(a["ip_hash"], b["ip_hash"])
        self.assertEqual(a["net_hash"], b["net_hash"], "same /24")
        self.assertNotEqual(a["net_hash"], c["net_hash"])
        self.assertEqual(len(a["ip_hash"]), sizes()["ip_hash_hex"])
        self.assertNotEqual(netfacts.address_hashes(os.urandom(len(salt)), "198.51.100.23"), a)


class Collected(unittest.TestCase):
    def setUp(self):
        os.environ["CAKE_HOME"] = tempfile.mkdtemp(prefix="cake-test-")
        os.environ.pop("CAKE_PORT", None)
        config.save_user(site_key=KEY, trust_lb=True, site_domain="shop.example")
        self.con = store.db()
        self.addCleanup(self.con.close)

    def post(self, body, pairs, public=True):
        view = collect.from_public if public else collect.from_local
        return view(Request("/collect", {}, message(pairs), json.dumps(body).encode())).status

    def facts(self):
        return [(pv, seq, json.loads(facts)) for pv, seq, facts in
                self.con.execute("SELECT pv, seq, facts FROM requests ORDER BY rowid")]

    def test_every_upload_request_is_written_with_its_batch_key_copies_too(self):
        for body in (batch(0), batch(1), batch(1)):
            self.assertEqual(self.post(body, CHROME, public=False), 204)
        self.assertEqual([(pv, seq) for pv, seq, _ in self.facts()], [("pv1", 0), ("pv1", 1), ("pv1", 1)])
        self.assertTrue(all("ip_class" not in facts for *_, facts in self.facts()), "local: no address")

    def test_on_the_public_listener_the_address_is_looked_up_hashed_and_dropped(self):
        address = address_of("agent")
        geo_fixtures.install(geoip.user_folder(), geo_fixtures.single(address, "US", "Texas", "San Antonio"))
        self.assertEqual(self.post(batch(), CHROME + [[LB["ip"], address]] + CLIENT_PLACE), 204)
        (_, _, facts), = self.facts()
        self.assertEqual((facts["range_kind"], facts["country"], facts["city"]), ("agent", "US", "San Antonio"))
        self.assertEqual(len(facts["ip_hash"]), sizes()["ip_hash_hex"])
        net = json.loads(self.con.execute("SELECT net FROM sessions").fetchone()[0])
        self.assertEqual((net["country"], net["subdivision"], net["city"]), ("US", "Texas", "San Antonio"))
        for folder, _, files in os.walk(os.environ["CAKE_HOME"]):
            for name in files:
                with open(os.path.join(folder, name), "rb") as f:
                    self.assertNotIn(address.encode(), f.read(), name)
        scanned = privacy_scan.scan(os.environ["CAKE_HOME"])
        self.assertEqual((scanned["found"], scanned["unreadable"]), (0, []), "S1: no address in any file")

    def test_visit_batches_hands_the_requests_to_from_cake(self):
        self.post(batch(0), CHROME + [[LB["ip"], address_of("cloud")]])
        self.post(batch(1), [pair for pair in CHROME if pair[0] != "Accept-Language"] + [[LB["ip"], "198.51.100.23"]])
        signals = env_signals.from_cake(visit_batches.batches(self.con, "visit1"),
                                        visit_batches.collect_requests(self.con, "visit1"))
        collected = signals["collect"]
        self.assertEqual(collected["requests"], 2)
        self.assertEqual(collected["headers"]["accept-language"]["present"], 1)
        self.assertEqual(collected["headers"]["sec-fetch-site"]["values"], ["same-origin"])
        self.assertEqual(collected["ip_classes"], ["cloud"])


if __name__ == "__main__":
    unittest.main()
