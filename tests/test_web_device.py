"""A session's browser, system and device type, named as PostHog names them: agentcake/web_device.py with
data/devices.json (transcribed from posthog-js's user-agent-utils.ts).

    python3 -I -m unittest discover -s tests -p test_web_device.py -v

The User-Agents below are common ones; what each should give follows the order of PostHog's checks: Edge before
Chrome, Chrome on iOS before Safari, an iPad a tablet, a phone mobile, an Android browser whose User-Agent names no
device (its "desktop site" mode) a tablet or a phone by its screen's short side, an unknown device a desktop.
"""
import unittest

from agentcake import web_device
from agentcake.web_device import Device

CASES = {
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 "
    "Safari/537.36": Device("Chrome", "Mac OS X", "Desktop"),
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 "
    "Edg/149.0.0.0": Device("Microsoft Edge", "Windows", "Desktop"),
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 "
    "Safari/605.1.15": Device("Safari", "Mac OS X", "Desktop"),
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1": Device("Mobile Safari", "iOS", "Mobile"),
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/149.0 "
    "Mobile/15E148 Safari/604.1": Device("Chrome iOS", "iOS", "Mobile"),
    "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1": Device("Mobile Safari", "iOS", "Tablet"),
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Mobile "
    "Safari/537.36": Device("Chrome", "Android", "Mobile"),
    "Mozilla/5.0 (Linux; Android 13; SM-X700) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 "
    "Safari/537.36": Device("Chrome", "Android", "Tablet"),
    "Mozilla/5.0 (X11; Linux x86_64; rv:139.0) Gecko/20100101 Firefox/139.0": Device("Firefox", "Linux", "Desktop"),
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 "
    "OPR/120.0.0.0": Device("Opera", "Windows", "Desktop"),
    "Mozilla/5.0 (X11; CrOS x86_64 14541.0.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 "
    "Safari/537.36": Device("Chrome", "Chrome OS", "Desktop"),
    "Mozilla/5.0 (Linux; Android 12; SAMSUNG SM-S908B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/27.0 "
    "Chrome/125.0.0.0 Mobile Safari/537.36": Device("Samsung Internet", "Android", "Mobile"),
    # no Safari token and "like Gecko": PostHog's last browser rule names it Firefox
    "Mozilla/5.0 (PlayStation 5 3.11) AppleWebKit/605.1.15 (KHTML, like Gecko)": Device("Firefox", "PlayStation",
                                                                                         "Console"),
}


class Describe(unittest.TestCase):
    def test_common_user_agents_are_named_as_posthog_names_them(self):
        for user_agent, expected in CASES.items():
            with self.subTest(user_agent=user_agent):
                self.assertEqual(web_device.describe(user_agent), expected)

    def test_without_a_user_agent_nothing_is_named(self):
        self.assertEqual(web_device.describe(None), Device("", "", ""))

    def test_an_android_browser_naming_no_device_is_told_by_its_screen(self):
        # Android's "desktop site" mode sends a desktop User-Agent; its client hints still say Android
        reduced = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 "
                   "Safari/537.36")
        tablet = {"uaData": {"platform": "Android"}, "maxTouchPoints": 5, "screen": {"w": 1600, "h": 2560}, "dpr": 2}
        phone = {"uaData": {"platform": "Android"}, "maxTouchPoints": 5, "screen": {"w": 1080, "h": 2400}, "dpr": 3}
        self.assertEqual(web_device.describe(reduced, tablet).device_type, "Tablet")
        self.assertEqual(web_device.describe(reduced, phone).device_type, "Mobile")

    def test_an_apple_vendor_without_safari_in_the_user_agent_is_safari(self):
        in_app = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
                  "Mobile/15E148")
        self.assertEqual(web_device.describe(in_app, {"vendor": "Apple Computer, Inc."}).browser, "Mobile Safari")


if __name__ == "__main__":
    unittest.main()
