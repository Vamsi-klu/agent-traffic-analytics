"""The city database on this computer: agentcake/geoip.py.

    python3 -I -m unittest discover -s tests -p test_geoip.py -v      (from the AgentCake folder)

A visitor's address is looked up in the city database (DB-IP's IP to City Lite, as geoip_build.py converts it) and
dropped: the country, region and city of its range come back, None for a region or a city DB-IP does not know, and
nothing at all without a database. A lookup opens no connection. The database is the one the updates and
`agentcake lists update` write in CAKE_HOME; a database replaced while AgentCake runs is used from the next lookup on.
Addresses are the documentation ranges' (geo_fixtures.py), placed in made-up places.
"""
import datetime
import json
import os
import shutil
import socket
import tempfile
import unittest
from unittest import mock

import geo_fixtures
from agentcake import geoip

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def offline(*args, **kwargs):
    raise AssertionError("a lookup opened a connection")


class GeoCase(unittest.TestCase):
    """A CAKE_HOME of its own."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="cake-geo-test-")
        self.addCleanup(shutil.rmtree, self.home, True)
        environment = mock.patch.dict(os.environ, {"CAKE_HOME": self.home})
        environment.start()
        self.addCleanup(environment.stop)


class Lookup(GeoCase):
    def setUp(self):
        super().setUp()
        geo_fixtures.install(geoip.user_folder())

    def test_documentation_addresses_find_their_country_region_and_city(self):
        for address, place in geo_fixtures.PLACES.items():
            self.assertEqual(geoip.place(address), place, address)

    def test_addresses_in_no_known_range_have_no_place(self):
        for address in geo_fixtures.NOWHERE:
            self.assertIsNone(geoip.place(address), address)

    def test_text_that_is_not_one_address_has_no_place(self):
        for text in ("", "not an address", "198.51.100.7, 10.0.0.1", "999.1.1.1", None):
            self.assertIsNone(geoip.place(text), text)

    def test_a_lookup_opens_no_connection(self):
        with mock.patch.object(socket, "socket", offline), mock.patch.object(socket, "create_connection", offline), \
                mock.patch.object(socket, "getaddrinfo", offline):
            for address, place in geo_fixtures.PLACES.items():
                self.assertEqual(geoip.place(address), place, address)

    def test_no_address_is_kept_after_a_lookup(self):
        for address in geo_fixtures.PLACES:
            geoip.place(address)
        kept = repr(geoip._OPENED) + repr({name: value for name, value in vars(geoip).items() if isinstance(value, str)})
        for address in geo_fixtures.PLACES:
            self.assertNotIn(address, kept)


class Folders(GeoCase):
    def test_without_a_database_there_is_no_place_and_no_status(self):
        self.assertIsNone(geoip.place("192.0.2.10"))
        self.assertIsNone(geoip.status())

    def test_a_database_replaced_while_running_is_used_from_the_next_lookup(self):
        geo_fixtures.install(geoip.user_folder(), geo_fixtures.single("192.0.2.10", "US"), month="2026-10")
        self.assertEqual(geoip.place("192.0.2.10")["country"], "US")
        staging = os.path.join(self.home, "staging")
        geo_fixtures.install(staging, geo_fixtures.single("192.0.2.10", "NZ"))
        retired = os.path.join(self.home, "retired")
        os.replace(geoip.user_folder(), retired)
        os.replace(staging, geoip.user_folder())
        self.assertEqual(geoip.place("192.0.2.10")["country"], "NZ")
        self.assertEqual(geoip.status()["month"], geo_fixtures.MONTH)

    def test_a_database_of_another_format_is_not_read_and_status_says_so(self):
        geo_fixtures.install(geoip.user_folder())
        about = os.path.join(geoip.user_folder(), geoip.FILES["about"])
        with open(about, encoding="utf-8") as f:
            changed = dict(json.load(f), format=geoip.FORMAT["version"] + 1)
        with open(about, "w", encoding="utf-8") as f:
            json.dump(changed, f)
        self.assertIsNone(geoip.place("192.0.2.10"))
        self.assertEqual(len(geoip.status()["errors"]), 1)

    def test_a_database_whose_month_is_not_one_is_not_read(self):
        geo_fixtures.install(geoip.user_folder())
        about = os.path.join(geoip.user_folder(), geoip.FILES["about"])
        with open(about, encoding="utf-8") as f:
            changed = dict(json.load(f), month="November")
        with open(about, "w", encoding="utf-8") as f:
            json.dump(changed, f)
        self.assertIsNone(geoip.place("192.0.2.10"))
        self.assertEqual(len(geoip.status()["errors"]), 1, "status says why, and does not fail")

    def test_a_record_file_cut_short_is_not_read(self):
        geo_fixtures.install(geoip.user_folder())
        records = os.path.join(geoip.user_folder(), geoip.FILES["ipv4"])
        with open(records, "r+b") as f:
            f.truncate(os.path.getsize(records) - 1)
        os.utime(os.path.join(geoip.user_folder(), geoip.FILES["about"]))  # as a new database's about.json would
        self.assertIsNone(geoip.place("192.0.2.10"))
        self.assertIn("records", geoip.status()["errors"][0])

    def test_a_record_file_cut_by_whole_records_is_not_read(self):
        """about.json counts each file's records: a file that lost its last records would give the last place left to
        every address above it."""
        geo_fixtures.install(geoip.user_folder())
        records = os.path.join(geoip.user_folder(), geoip.FILES["ipv4"])
        with open(records, "r+b") as f:
            f.truncate(os.path.getsize(records) - geoip.FORMAT["start_bytes"]["ipv4"] - geoip.FORMAT["place_bytes"])
        os.utime(os.path.join(geoip.user_folder(), geoip.FILES["about"]))
        self.assertIsNone(geoip.place("255.255.255.255"), "above the last range there is no place, not the last one")
        self.assertIsNone(geoip.place("192.0.2.10"))
        self.assertIn("records", geoip.status()["errors"][0])

    def test_a_database_swapped_in_while_it_is_being_opened_is_not_read_half_old_half_new(self):
        """Its files are opened one after the other: when `agentcake lists update` swaps the folder in between, the
        old record files' place numbers would be read in the new table of places (here 1 is US in the old database
        and JP in the new one)."""
        geo_fixtures.install(geoip.user_folder(), geo_fixtures.single("192.0.2.10", "US")
                             + geo_fixtures.single("198.51.100.7", "JP"), month="2026-10")
        staging = os.path.join(self.home, "staging")
        geo_fixtures.install(staging, geo_fixtures.single("192.0.2.9", "JP") + geo_fixtures.single("192.0.2.10", "US"))
        real_places = geoip._Places

        def swapped_first(path, count):
            os.replace(geoip.user_folder(), os.path.join(self.home, "retired"))
            os.replace(staging, geoip.user_folder())
            return real_places(path, count)

        with mock.patch.object(geoip, "_Places", swapped_first):
            during = geoip.place("192.0.2.10")
        self.assertIn((during or {}).get("country"), (None, "US"))
        self.assertEqual(geoip.place("192.0.2.10")["country"], "US")
        self.assertEqual(geoip.status()["month"], geo_fixtures.MONTH)


class Damaged(GeoCase):
    def test_an_about_json_that_is_no_object_is_not_read_and_raises_nothing(self):
        geo_fixtures.install(geoip.user_folder())
        about = os.path.join(geoip.user_folder(), geoip.FILES["about"])
        for content in ("[]", "null", "7"):
            with open(about, "w", encoding="utf-8") as f:
                f.write(content)
            self.assertIsNone(geoip.place("192.0.2.10"), content)
            self.assertEqual(len(geoip.status()["errors"]), 1, content)

    def test_a_record_that_names_no_place_gives_no_place_and_raises_nothing(self):
        """Opening reads only what fits together cheaply; a damaged record shows only when an address finds it, and
        then that address has no place: an upload is never refused for it."""
        geo_fixtures.install(geoip.user_folder())
        records = os.path.join(geoip.user_folder(), geoip.FILES["ipv4"])
        size = geoip.FORMAT["start_bytes"]["ipv4"] + geoip.FORMAT["place_bytes"]
        with open(records, "r+b") as f:
            data = bytearray(f.read())
            for at in range(0, len(data), size):  # every record names a place far past the last one
                data[at + geoip.FORMAT["start_bytes"]["ipv4"]:at + size] = b"\xff" * geoip.FORMAT["place_bytes"]
            f.seek(0)
            f.write(data)
        self.assertIsNone(geoip.place("192.0.2.10"))
        self.assertEqual(geoip.place("2001:db8::17")["country"], "CA", "the other family is still read")


class Source(GeoCase):
    def test_only_the_public_listener_with_trust_lb_sees_addresses(self):
        self.assertFalse(geoip.sees_addresses({}))
        self.assertFalse(geoip.sees_addresses({"public_listen": "127.0.0.1:8080", "trust_lb": False}))
        self.assertFalse(geoip.sees_addresses({"public_listen": "", "trust_lb": True}))
        self.assertTrue(geoip.sees_addresses({"public_listen": "127.0.0.1:8080", "trust_lb": True}))

    def test_the_source_of_places_is_none_missing_or_the_database(self):
        server = {"public_listen": "127.0.0.1:8080", "trust_lb": True}
        self.assertEqual(geoip.source({}), geoip.NONE)
        self.assertEqual(geoip.source(server), geoip.MISSING)
        geo_fixtures.install(geoip.user_folder())
        self.assertEqual(geoip.source(server), geoip.DATABASE)
        self.assertEqual(geoip.source({}), geoip.NONE, "a database is no use on this computer")


class PrivacyScan(unittest.TestCase):
    def test_the_privacy_scan_passes_over_the_city_database_as_published_data(self):
        with open(os.path.join(ROOT, "tools", "privacy", "rules.json"), encoding="utf-8") as f:
            skipped = json.load(f)["skip_folders"]
        self.assertIn(geoip.SETTINGS["folder"]["user_dir"], skipped)


class Status(GeoCase):
    def test_it_says_the_month_and_how_old_it_is(self):
        geo_fixtures.install(geoip.user_folder())
        found = geoip.status(today=datetime.date(2026, 11, 18))
        self.assertEqual((found["month"], found["months_old"], found["stale"], found["folder"]),
                         (geo_fixtures.MONTH, 0, False, geoip.paths.tilde(geoip.user_folder())))
        self.assertFalse(geoip.status(today=datetime.date(2026, 12, 31))["stale"], "December's may not be out yet")
        self.assertTrue(geoip.status(today=datetime.date(2027, 1, 2))["stale"])
        self.assertEqual(geoip.status(today=datetime.date(2027, 1, 2))["months_old"], 2)


if __name__ == "__main__":
    unittest.main()
