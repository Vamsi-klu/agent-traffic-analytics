"""Which check of a real phone or tablet a session's environment records fail (detect/touch_device.failed_checks()).

    python3 -I -m unittest discover -s tests -p test_touch_device_checks.py -v      (from the repository root)

One entry per check, with the facts of the first record that failed it, in the order of touch_device.CHECKS: a page
whose browser does not say it is a phone or tablet fails that check alone, touch points and a screen are checked each,
and with both, whether the screen is the size of the device the record names. A record that fits fails nothing, and so
does a session without a record (it fits nothing all the same), and a record fits exactly when it fails no check. The
records and User-Agents are tests/test_touch_device.py's: no real visitor is in here.
"""
import os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from test_touch_device import (ANDROID_PHONE_DESKTOP_SITE, ANDROID_TABLET, ANDROID_TABLET_DESKTOP_SITE,  # noqa: E402
                               BOUNDARY, DEVICES, IPAD, IPAD_DESKTOP_SITE, IPHONE, IPHONE_DESKTOP_SITE,
                               MAC_SAFARI_UA, MONITOR, PHONE, PHONE_SCREEN, PIXEL, SWITCH_UA, TABLET, failed, page)
from agentcake.detect import touch_device  # noqa: E402


class FailedChecks(unittest.TestCase):
    """Which check of a real phone or tablet a record fails: one entry per check, with the facts of the first record
    that failed it, in the order of touch_device.CHECKS; nothing for a record that fits, nor for a session without a
    record (the browser's claim is read from one, so a phone always has one: fits() still fits nothing there)."""

    def test_a_real_phone_or_tablet_fails_no_check(self):
        for name, env in (("iphone", IPHONE), ("ipad", IPAD), ("pixel", PIXEL), ("android tablet", ANDROID_TABLET),
                          ("android desktop site", ANDROID_TABLET_DESKTOP_SITE)):
            with self.subTest(name):
                self.assertEqual(failed(page(env)), [])
        self.assertEqual(failed(page(IPAD_DESKTOP_SITE, worker="iPad")), [])

    def test_a_page_whose_browser_does_not_say_it_is_one_fails_that_check_alone(self):
        """A computer's page in a phone's session: its touch points and screen are no phone's to check."""
        laptop = dict(IPHONE, anyPointer=["fine"], maxTouchPoints=0, screen=MONITOR, userAgent=MAC_SAFARI_UA)
        self.assertEqual(failed(page(IPHONE), page(laptop)), [{"check": "not-claimed"}])

    def test_no_touch_points_say_what_was_recorded(self):
        self.assertEqual(failed(page(dict(IPHONE, maxTouchPoints=0))), [{"check": "no-touch-points", "points": 0}])
        for points in (None, True, "5"):  # not recorded, or not a number
            with self.subTest(points=points):
                self.assertEqual(failed(page(dict(IPHONE, maxTouchPoints=points))),
                                 [{"check": "no-touch-points", "points": None}])

    def test_no_recorded_screen(self):
        for screen in (None, {}, {"w": 390}, {"w": 0, "h": 844}, "390x844"):
            with self.subTest(screen=screen):
                self.assertEqual(failed(page(dict(IPHONE, screen=screen))), [{"check": "no-screen"}])

    def test_a_user_agent_that_names_no_phone_or_tablet_gives_the_device_type(self):
        self.assertEqual(failed(page(dict(IPHONE, userAgent=MAC_SAFARI_UA))),
                         [{"check": "other-device", "device": DEVICES["no_device_type"]}])
        self.assertEqual(failed(page(dict(IPHONE, userAgent=SWITCH_UA))),
                         [{"check": "other-device", "device": "Console"}])

    def test_a_phones_user_agent_on_a_larger_screen(self):
        for name, screen in (("a folding phone opened flat", {"w": 673, "h": 841}), ("a monitor", MONITOR)):
            with self.subTest(name):
                self.assertEqual(failed(page(dict(PIXEL, screen=screen))),
                                 [{"check": "screen-too-large", "device": PHONE, "w": screen["w"], "h": screen["h"],
                                   "min": BOUNDARY}])

    def test_a_tablets_user_agent_on_a_phones_screen(self):
        self.assertEqual(failed(page(dict(IPAD, screen=PHONE_SCREEN))),
                         [{"check": "screen-too-small", "device": TABLET, "w": 390, "h": 844, "min": BOUNDARY}])

    def test_the_desktop_site_without_the_workers_record(self):
        expected = [{"check": "no-worker", "platform": "MacIntel", "points": IPAD["maxTouchPoints"]}]
        self.assertEqual(failed(page(IPAD_DESKTOP_SITE)), expected)
        self.assertEqual(failed(dict(page(IPAD_DESKTOP_SITE), auto={"workerConsistency": {"differs": []}})), expected)

    def test_the_desktop_site_whose_worker_reports_a_computer_names_the_computer(self):
        self.assertEqual(failed(page(IPAD_DESKTOP_SITE, worker="MacIntel")),
                         [{"check": "other-device", "device": DEVICES["no_device_type"]}])

    def test_the_desktop_site_on_a_screen_of_another_device_than_the_workers(self):
        self.assertEqual(failed(page(IPAD_DESKTOP_SITE, worker="iPhone")),
                         [{"check": "screen-too-large", "device": PHONE, "w": 820, "h": 1180, "min": BOUNDARY}])
        self.assertEqual(failed(page(IPHONE_DESKTOP_SITE, worker="iPad")),
                         [{"check": "screen-too-small", "device": TABLET, "w": 390, "h": 844, "min": BOUNDARY}])

    def test_several_checks_are_listed_in_the_order_of_the_checks(self):
        bare = {key: value for key, value in IPHONE.items() if key not in ("screen", "maxTouchPoints")}
        self.assertEqual(failed(page(bare)), [{"check": "no-touch-points", "points": None}, {"check": "no-screen"}])
        pages = [page(dict(PIXEL, screen=MONITOR)), page(dict(IPHONE, maxTouchPoints=0)), page(PIXEL),
                 page(dict(PIXEL, screen={"w": 673, "h": 841}))]
        self.assertEqual(failed(*pages), [{"check": "no-touch-points", "points": 0},
                                          {"check": "screen-too-large", "device": PHONE, "w": 2560, "h": 1440,
                                           "min": BOUNDARY}])
        self.assertEqual([entry["check"] for entry in failed(*pages)],
                         [check for check in touch_device.CHECKS if check in ("no-touch-points", "screen-too-large")])

    def test_a_session_without_a_record_fails_no_check_and_fits_nothing(self):
        for pages in ([], None, [{"path": "/"}], [{"env": None}]):
            with self.subTest(pages=pages):
                self.assertEqual(touch_device.failed_checks(pages), [])
                self.assertFalse(touch_device.fits(pages))

    def test_a_record_fits_exactly_when_it_fails_no_check(self):
        envs = [IPHONE, IPAD, PIXEL, ANDROID_TABLET, ANDROID_TABLET_DESKTOP_SITE, ANDROID_PHONE_DESKTOP_SITE,
                dict(IPHONE, anyPointer=["fine"]), dict(IPHONE, maxTouchPoints=0), dict(IPHONE, screen=None),
                dict(IPHONE, screen=MONITOR), dict(IPAD, screen=PHONE_SCREEN), dict(IPAD, userAgent=SWITCH_UA),
                dict(IPHONE, userAgent=None), IPAD_DESKTOP_SITE, IPHONE_DESKTOP_SITE]
        for env in envs:
            for worker in (None, "iPad", "iPhone", "MacIntel"):
                with self.subTest(platform=env["platform"], user_agent=str(env["userAgent"])[:40], worker=worker):
                    pages = [page(env, worker)]
                    self.assertEqual(touch_device.fits(pages), not touch_device.failed_checks(pages))

    def test_a_record_of_another_shape_than_cake_js_sends_fails_checks_without_an_error(self):
        odd = {"screen": "390x844", "uaData": "mobile", "anyPointer": "coarse", "userAgent": 5, "dpr": "3",
               "maxTouchPoints": "5", "platform": ["iPhone"]}
        for key, value in odd.items():
            for env in (IPHONE, PIXEL, IPAD_DESKTOP_SITE):
                with self.subTest(key=key, platform=env["platform"]):
                    found = failed(page(dict(env, **{key: value}), worker="iPad"))
                    self.assertTrue(all(entry["check"] in touch_device.CHECKS for entry in found))


if __name__ == "__main__":
    unittest.main()
