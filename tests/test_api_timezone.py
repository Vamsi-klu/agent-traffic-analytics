"""AgentCake's timezone on a scratch database: with the setting `timezone` (Settings, or `agentcake config set
timezone`) every answer writes its days, hours and times in that zone, as PostHog's project time zone does: the date
ranges and their counts, the Trends chart's days and hours and the note that names the zone, and the words
"Today 10:00" of the session list, the session page and the settings page. Unset, they follow this computer (UTC
here). The settings page reads and saves it, and lists the zones it may be set to; a name the timezone database
doesn't know is refused.

    python3 -I -m unittest discover -s tests -p test_api_timezone.py -v      (from the AgentCake folder)
"""
import datetime
import os
import time
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

import visit_rows
from api_client import Client, contract_problems
from web_uploads import MINUTE_MS, WebCase, upload
from agentcake import config
from agentcake.api import periods

LOS_ANGELES, SHANGHAI = "America/Los_Angeles", "Asia/Shanghai"
NOW = 1_794_546_780_000  # Thursday 2026-11-12 21:13 in Los Angeles: Friday 13:13 in Shanghai, Friday 05:13 in UTC


def at(zone, *fields):
    return int(datetime.datetime(*fields, tzinfo=ZoneInfo(zone)).timestamp() * 1000)


# Sessions by when they began: 10:00 is Friday 02:00 in Shanghai, 07:00 is Thursday 23:00 there; a week ago is
# Thursday 2026-11-05 02:00 in Los Angeles, 18:00 in Shanghai
STARTS = {"ten": at(LOS_ANGELES, 2026, 11, 12, 10, 0), "seven": at(LOS_ANGELES, 2026, 11, 12, 7, 0),
          "week ago": at(LOS_ANGELES, 2026, 11, 5, 2, 0)}


class Scratch(WebCase):
    """Three sessions on this computer, which runs on UTC."""

    def setUp(self):
        super().setUp()
        zone = mock.patch.dict(os.environ, {"TZ": "UTC"})
        zone.start()
        self.addCleanup(zone.stop)
        self.addCleanup(time.tzset)
        time.tzset()
        self.tabs = {}
        for name, start in STARTS.items():
            tab = f"{len(self.tabs) + 1:032x}"
            self.post(dict(upload(0, start, tab=tab, pv=tab), bs=tab))  # each a session of its own
            self.con.execute("UPDATE sessions SET start_ms=?, end_ms=?, verdict_class='human', judged_ms=? WHERE id=?",
                             (start, start + MINUTE_MS, NOW, tab))
            visit_rows.refreshed(self.con)
            self.tabs[name] = tab

    def get(self, path, timezone=None, **query):
        """The answer with the setting at timezone (None: never set)."""
        if timezone is not None:
            config.save_user(timezone=timezone)
        with mock.patch.object(periods, "now_ms", return_value=NOW):
            answer = Client().get(path, **query)
        self.assertEqual(answer.status, 200, answer.body)
        return answer.body

    def when(self, timezone=None):
        """{session: its time in words} on the session list."""
        rows = self.get("/api/sessions", timezone)["results"]
        return {name: next(row["when"] for row in rows if row["id"] == tab) for name, tab in self.tabs.items()}


class Answers(Scratch):
    def test_the_session_list_writes_times_in_the_timezone_set(self):
        self.assertEqual(self.when()["seven"], "Yesterday 15:00", "never set: this computer's, UTC")
        self.assertEqual(self.when(LOS_ANGELES)["ten"], "Today 10:00")
        self.assertEqual(self.when(LOS_ANGELES)["seven"], "Today 07:00")
        self.assertEqual(self.when(SHANGHAI)["ten"], "Today 02:00")
        self.assertEqual(self.when(SHANGHAI)["seven"], "Yesterday 23:00")
        self.assertEqual(self.when("")["seven"], "Yesterday 15:00", "set back to nothing: this computer's again")

    def test_the_session_page_and_the_settings_page_too(self):
        tab = self.tabs["seven"]
        self.assertEqual(self.get(f"/api/session/{tab}", SHANGHAI)["session"]["when"], "Yesterday 23:00")
        self.assertEqual(self.get(f"/api/session/{tab}", LOS_ANGELES)["session"]["when"], "Today 07:00")
        self.assertEqual(self.get("/api/settings", SHANGHAI)["last_seen"]["site"], "Today 02:01")
        self.assertEqual(self.get("/api/settings", LOS_ANGELES)["last_seen"]["site"], "Today 10:01")

    def test_the_last_7_days_start_at_the_timezones_midnight(self):
        self.assertEqual(self.get("/api/overview", LOS_ANGELES, range="7d")["counts"]["all"], 3)
        self.assertEqual(self.get("/api/overview", SHANGHAI, range="7d")["counts"]["all"], 2,
                         "a week ago is Thursday 18:00 in Shanghai, before its days, from Friday 2026-11-06")
        self.assertEqual(self.get("/api/sessions", SHANGHAI, range="7d")["total"], 2)

    def test_the_trends_days_hours_and_note_are_the_timezones(self):
        self.assertEqual(self.get("/api/web")["time_zone"], "UTC", "never set: this computer's own")
        days = {zone: self.get("/api/web", zone, range="7d")["trends"]["points"] for zone in (LOS_ANGELES, SHANGHAI)}
        self.assertEqual([p["label"] for p in days[LOS_ANGELES]], [f"Nov {day}" for day in range(5, 13)])
        self.assertEqual([p["label"] for p in days[SHANGHAI]], [f"Nov {day}" for day in range(6, 14)])
        self.assertEqual([p["human"]["sessions"] for p in days[LOS_ANGELES]], [1, 0, 0, 0, 0, 0, 0, 2])
        self.assertEqual([p["human"]["sessions"] for p in days[SHANGHAI]], [0, 0, 0, 0, 0, 0, 1, 1],
                         "07:00 in Los Angeles is Thursday 23:00 in Shanghai")
        hours = self.get("/api/web", "Asia/Kolkata", range="24h")["trends"]["points"]
        self.assertEqual((len(hours), hours[0]["label"], hours[-1]["label"]), (25, "Nov 12, 10:00", "Nov 13, 10:00"))
        self.assertEqual(self.get("/api/web", LOS_ANGELES)["time_zone"], "PST")
        self.assertEqual(self.get("/api/web", "Asia/Kathmandu")["time_zone"], "UTC+05:45")
        self.assertEqual(self.get("/api/web", "")["time_zone"], "UTC", "set back to nothing: this computer's again")

    def test_a_name_set_by_hand_that_names_no_zone_follows_this_computer(self):
        unset = self.get("/api/sessions")
        self.assertEqual(self.get("/api/sessions", "Mars/Olympus"), unset)
        self.assertEqual(self.get("/api/web")["time_zone"], "UTC")


class SettingsPage(Scratch):
    def save(self, value):
        with mock.patch.object(periods, "now_ms", return_value=NOW):
            return Client().post("/api/settings", {"timezone": value})

    def test_the_settings_say_the_timezone_and_this_computers(self):
        body = self.get("/api/settings")
        self.assertEqual(contract_problems(body, "settings"), [])
        self.assertEqual((body["timezone"], body["timezone_machine"]), ("", {"name": "UTC", "short": "UTC"}))

    def test_the_settings_page_saves_a_timezone_and_nothing_follows_this_computer_again(self):
        answer = self.save(SHANGHAI)
        self.assertEqual((answer.status, answer.body["timezone"]), (200, SHANGHAI))
        self.assertEqual(config.load_cfg()["timezone"], SHANGHAI)
        self.assertEqual(self.when()["seven"], "Yesterday 23:00")
        self.assertEqual(self.save("").body["timezone"], "")
        self.assertEqual(self.when()["seven"], "Yesterday 15:00")

    def test_a_name_the_timezone_database_doesnt_know_is_refused_and_nothing_is_saved(self):
        for value in ("Mars/Olympus", "../../etc/passwd", "PST", "Asia/Shanghai\x00"):
            answer = self.save(value)
            self.assertEqual(answer.status, 400, value)
            self.assertEqual(contract_problems(answer.body, "error"), [])
            self.assertIn("time zone", answer.body["error"])
        self.assertEqual(self.save(8).status, 400, "a number is no name")
        self.assertEqual(config.load_cfg()["timezone"], "")

    def test_the_zones_the_settings_page_lists(self):
        body = self.get("/api/timezones")
        self.assertEqual(contract_problems(body, "timezones"), [])
        self.assertEqual(body["zones"][0], {"name": "UTC", "label": "UTC (UTC+00:00)"})
        labels = {zone["name"]: zone["label"] for zone in body["zones"]}
        self.assertEqual(labels[LOS_ANGELES], "America / Los Angeles (UTC-08:00)")
        self.assertEqual(labels[SHANGHAI], "Asia / Shanghai (UTC+08:00)")


if __name__ == "__main__":
    unittest.main()
