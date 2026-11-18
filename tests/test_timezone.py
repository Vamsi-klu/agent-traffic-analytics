"""agentcake/timezone.py: AgentCake's timezone, the setting `timezone` or this computer's, and what the pages call it.

    python3 -I -m unittest discover -s tests -p test_timezone.py -v      (from the AgentCake folder)

The setting names an IANA zone the timezone database knows (zoneinfo), or nothing: then AgentCake follows this
computer, whose clock and name come from the C library (time.localtime), as $TZ or /etc/localtime set it. What the pages
call a zone is its abbreviation (PST, PDT, JST, UTC) or, when the database has none, its offset (UTC+05:45); the
settings page lists IANA's zone.tab zones and UTC, each with its offset, as PostHog's time zone setting does.
"""
import datetime
import os
import sys
import tempfile
import time
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from agentcake import timezone  # noqa: E402

NOVEMBER = int(datetime.datetime(2026, 11, 12, 12, tzinfo=datetime.timezone.utc).timestamp() * 1000)
JULY = int(datetime.datetime(2026, 7, 12, 12, tzinfo=datetime.timezone.utc).timestamp() * 1000)


class ComputerIn:
    """With this computer's timezone set by $TZ (or $TZ unset, when name is None)."""

    def __init__(self, name):
        self.name = name

    def __enter__(self):
        environ = {key: value for key, value in os.environ.items() if key != "TZ"}
        if self.name is not None:
            environ["TZ"] = self.name
        self.patch = mock.patch.dict(os.environ, environ, clear=True)
        self.patch.start()
        time.tzset()

    def __exit__(self, *_):
        self.patch.stop()
        time.tzset()


class Names(unittest.TestCase):
    def test_a_timezone_is_a_name_the_timezone_database_knows(self):
        for name in ("America/Los_Angeles", "Asia/Shanghai", "Asia/Kolkata", "UTC"):
            self.assertTrue(timezone.known(name), name)
        for name in ("", "Mars/Olympus", "../../etc/passwd", "/etc/localtime", "Asia/../Asia/Shanghai",
                     "Asia/Shanghai\x00", "asia/shanghai", "Asia/Shanghai ", "x" * 300, None):
            self.assertFalse(timezone.known(name), repr(name))

    def test_the_setting_names_the_zone_and_nothing_follows_this_computer(self):
        self.assertEqual(timezone.chosen({"timezone": "Asia/Shanghai"}), ZoneInfo("Asia/Shanghai"))
        self.assertIsNone(timezone.chosen({"timezone": ""}))
        self.assertIsNone(timezone.chosen({"timezone": "Mars/Olympus"}), "a name set by hand that names no zone")


class ThisComputer(unittest.TestCase):
    def test_tz_names_this_computers_zone(self):
        for tz, name in (("Asia/Tokyo", "Asia/Tokyo"), (":America/Los_Angeles", "America/Los_Angeles"),
                         ("UTC", "UTC"), ("", "UTC"), ("JST-9", None)):
            with ComputerIn(tz):
                self.assertEqual(timezone.machine_name(), name, repr(tz))

    def files(self, localtime, named=None):
        """This computer's /etc/localtime (a link to that path, or a copy when None) and /etc/timezone (with named in
        it, or none), in a folder of their own."""
        folder = tempfile.mkdtemp(prefix="cake-tz-")
        link, file = os.path.join(folder, "localtime"), os.path.join(folder, "timezone")
        if localtime:
            os.symlink(localtime, link)
        else:
            open(link, "wb").close()
        if named is not None:
            with open(file, "w") as f:
                f.write(named)
        return mock.patch.multiple(timezone, LOCALTIME=link, TIMEZONE_FILE=file)

    def test_without_tz_the_zone_etc_localtime_links_to(self):
        with ComputerIn(None), self.files("/var/db/timezone/tz/2026f/zoneinfo/America/Los_Angeles"):
            self.assertEqual(timezone.machine_name(), "America/Los_Angeles")
        with ComputerIn(None), self.files(None, "Europe/Berlin\n"):
            self.assertEqual(timezone.machine_name(), "Europe/Berlin", "a copy of the zone: Debian's /etc/timezone")
        with ComputerIn(None), self.files(None):
            self.assertIsNone(timezone.machine_name(), "no name anywhere: none, never a guess")


class Short(unittest.TestCase):
    def test_this_computers_zone_is_called_what_its_clock_calls_it(self):
        for tz, november, july in (("UTC", "UTC", "UTC"), ("Asia/Tokyo", "JST", "JST"),
                                   ("America/Los_Angeles", "PST", "PDT"), ("Asia/Kathmandu", "UTC+05:45", "UTC+05:45"),
                                   ("America/Sao_Paulo", "UTC-03:00", "UTC-03:00")):
            with ComputerIn(tz):
                self.assertEqual((timezone.short(None, NOVEMBER), timezone.short(None, JULY)), (november, july), tz)

    def test_a_zone_set_is_called_what_its_clock_calls_it(self):
        for name, november, july in (("UTC", "UTC", "UTC"), ("America/Los_Angeles", "PST", "PDT"),
                                     ("Asia/Kolkata", "IST", "IST"), ("Asia/Kathmandu", "UTC+05:45", "UTC+05:45")):
            zone = ZoneInfo(name)
            self.assertEqual((timezone.short(zone, NOVEMBER), timezone.short(zone, JULY)), (november, july), name)


class Listed(unittest.TestCase):
    def test_utc_then_every_zone_of_zone_tab_with_its_offset(self):
        zones = timezone.listed(NOVEMBER)
        names = [zone["name"] for zone in zones]
        self.assertEqual(zones[0], {"name": "UTC", "label": "UTC (UTC+00:00)"})
        self.assertEqual(names[1:], sorted(names[1:]))
        self.assertEqual(len(names), len(set(names)))
        self.assertGreater(len(names), 300)
        self.assertTrue(all(timezone.known(name) for name in names))
        by_name = {zone["name"]: zone["label"] for zone in zones}
        self.assertEqual(by_name["America/Los_Angeles"], "America / Los Angeles (UTC-08:00)")
        self.assertEqual(by_name["Asia/Kolkata"], "Asia / Kolkata (UTC+05:30)")
        self.assertEqual({zone["name"]: zone["label"] for zone in timezone.listed(JULY)}["America/Los_Angeles"],
                         "America / Los Angeles (UTC-07:00)")


if __name__ == "__main__":
    unittest.main()
