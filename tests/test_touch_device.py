"""Whether a session's browser is a phone or tablet, from its pages' environment records (detect/touch_device.py).

    python3 -I -m unittest discover -s tests -p test_touch_device.py -v      (from the repository root)

claimed() is the browser's own word (its client hints say mobile, or its only pointer is coarse). fits() asks more:
every page that recorded its environment says so, has touch points, and has a screen of the size the device its
User-Agent names has, a phone's short side under the tablet boundary of data/devices.json and a tablet's at or over it,
both in CSS pixels (Chrome on an Android tablet shows the desktop site, its User-Agent names no device and its client
hints say Android: the Devices table divides its screen by the pixel ratio, fits() does not). An Android User-Agent
without a phone's mark, on a tablet's screen, is a tablet's (verdict.json android_tablet): a Pixel Tablet fits, though
the Devices table reads its User-Agent as a phone's, as posthog-js does; on a phone's screen the Devices table's type
stands, so the phones its rules know without Mobile (Pixel phones, ZTE) fit as phones, as they did before. One test per
condition shows what does not fit (which check it fails, with its facts: tests/test_touch_device_checks.py).
An iPad or iPhone showing the desktop site names a Mac in its User-Agent and is told by its worker's platform, on the
facts env.spoof.worker-mismatch leaves alone (the same three values in both data files); a page without its worker's
record takes the device the session's other pages' workers reported (one iPad, iPhone or iPod, and nothing else), and
without any it does not fit. No real visitor is in here: the User-Agents are the public forms of each device's.
"""
import copy, os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from test_env_rules import load_cases, merge  # noqa: E402
from agentcake import web_device  # noqa: E402
from agentcake.datafiles import load  # noqa: E402
from agentcake.detect import env_rules, touch_device  # noqa: E402

DEVICES = load("data/devices.json")
BOUNDARY = DEVICES["tablet_short_side_dp"]
PHONE, TABLET = DEVICES["any_device_type"], DEVICES["tablet_type"]  # the Devices table's types
IPHONE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 19_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
             "Version/19.0 Mobile/15E148 Safari/604.1")
IPAD_UA = ("Mozilla/5.0 (iPad; CPU OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 "
           "Mobile/15E148 Safari/604.1")
PIXEL_UA = ("Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 "
            "Mobile Safari/537.36")
ANDROID_TABLET_UA = ("Mozilla/5.0 (Linux; Android 14; SM-X710) AppleWebKit/537.36 (KHTML, like Gecko) "
                     "Chrome/157.0.0.0 Safari/537.36")
MAC_SAFARI_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
                 "Version/18.0 Safari/605.1.15")
DESKTOP_SITE_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 "
                   "Safari/537.36")
SWITCH_UA = "Mozilla/5.0 (Nintendo Switch; WifiWebAuthApplet) AppleWebKit/606.4 (KHTML, like Gecko) NF/6.0.1.15.4"
PHONE_SCREEN, TABLET_SCREEN, MONITOR = {"w": 390, "h": 844}, {"w": 820, "h": 1180}, {"w": 2560, "h": 1440}

IPHONE = {"userAgent": IPHONE_UA, "platform": "iPhone", "uaData": None, "vendor": "Apple Computer, Inc.",
          "maxTouchPoints": 5, "anyPointer": ["coarse"], "screen": PHONE_SCREEN, "dpr": 3}
IPAD = dict(IPHONE, userAgent=IPAD_UA, platform="iPad", screen=TABLET_SCREEN, dpr=2)
PIXEL = {"userAgent": PIXEL_UA, "platform": "Linux armv81", "vendor": "Google Inc.", "maxTouchPoints": 5,
         "uaData": {"brands": [], "platform": "Android", "mobile": True}, "anyPointer": ["coarse"],
         "screen": {"w": 412, "h": 915}, "dpr": 2.625}
ANDROID_TABLET = dict(PIXEL, userAgent=ANDROID_TABLET_UA, screen={"w": 800, "h": 1280}, dpr=2,
                      uaData={"brands": [], "platform": "Android", "mobile": False})
PIXEL_TABLET_UA = ("Mozilla/5.0 (Linux; Android 14; Pixel Tablet) AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/157.0.0.0 Safari/537.36")
FOLD_UA = ("Mozilla/5.0 (Linux; Android 14; SM-F946B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 "
           "Mobile Safari/537.36")
FIREFOX_TABLET_UA = "Mozilla/5.0 (Android 14; Tablet; rv:136.0) Gecko/136.0 Firefox/136.0"
# phones whose User-Agents leave Mobile out, which the Devices table's rules (posthog-js's) know as phones by model
ZTE_UA = ("Mozilla/5.0 (Linux; Android 11; ZTE A2121) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 "
          "Safari/537.36")
PIXEL_WITHOUT_MOBILE_UA = PIXEL_UA.replace("Mobile Safari", "Safari")
PIXEL_C_UA = ("Mozilla/5.0 (Linux; Android 8.1.0; Pixel C) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 "
              "Safari/537.36")
PIXEL_TABLET = dict(ANDROID_TABLET, userAgent=PIXEL_TABLET_UA, screen={"w": 1280, "h": 800})
IPAD_DESKTOP_SITE = dict(IPAD, userAgent=MAC_SAFARI_UA, platform="MacIntel")
IPHONE_DESKTOP_SITE = dict(IPHONE, userAgent=MAC_SAFARI_UA, platform="MacIntel")
# Chrome on an Android tablet or phone showing the desktop site: a Linux computer's User-Agent, Android's client hints
ANDROID_TABLET_DESKTOP_SITE = dict(ANDROID_TABLET, userAgent=DESKTOP_SITE_UA, platform="Linux armv8l")
ANDROID_PHONE_DESKTOP_SITE = dict(PIXEL, userAgent=DESKTOP_SITE_UA, uaData=dict(PIXEL["uaData"], mobile=False))


def page(env, worker=None):
    """A page's signals: its environment record and, when a worker answered, the platform the worker reported."""
    out = {"env": copy.deepcopy(env)}
    if worker:
        out["auto"] = {"workerConsistency": {"differs": ["platform"], "worker": {"platform": worker}}}
    return out


def fits(env, worker=None):
    return touch_device.fits([page(env, worker)])


class Claimed(unittest.TestCase):
    def test_client_hints_that_say_mobile_or_a_coarse_pointer_alone_say_so(self):
        self.assertTrue(touch_device.claimed([page({"uaData": {"mobile": True}, "anyPointer": ["fine"]})]))
        self.assertTrue(touch_device.claimed([page({"uaData": None, "anyPointer": ["coarse"]})]))

    def test_a_computer_with_a_touch_screen_keeps_its_fine_pointer_and_does_not(self):
        laptop = {"uaData": {"mobile": False}, "anyPointer": ["fine", "coarse"], "maxTouchPoints": 10}
        self.assertFalse(touch_device.claimed([page(laptop)]))

    def test_one_page_that_says_so_is_enough_and_a_page_without_a_record_says_nothing(self):
        self.assertTrue(touch_device.claimed([{"path": "/"}, page(IPHONE)]))
        for pages in ([], None, [{"path": "/"}], [{"env": None}]):
            with self.subTest(pages=pages):
                self.assertFalse(touch_device.claimed(pages))


class Fits(unittest.TestCase):
    """What a real phone's or tablet's record looks like, and each condition that one passing as it fails."""

    def test_phones_and_tablets_with_touch_points_and_a_screen_of_their_size_fit(self):
        for name, env in (("iphone", IPHONE), ("ipad", IPAD), ("pixel", PIXEL), ("android tablet", ANDROID_TABLET)):
            with self.subTest(name):
                self.assertTrue(fits(env))

    def test_a_screen_turned_on_its_side_is_the_same_screen(self):
        self.assertTrue(fits(dict(PIXEL, screen={"w": 915, "h": 412})))

    def test_chrome_showing_the_desktop_site_on_an_android_tablet_fits_whatever_its_pixel_ratio(self):
        """Its User-Agent names no device, so the device is the one its client hints and screen give, measured in CSS
        pixels as the screen it is checked against is (the Devices table divides by the pixel ratio: posthog-js's)."""
        for dpr in (1, 1.5, 2, 3):
            with self.subTest(dpr=dpr):
                self.assertTrue(fits(dict(ANDROID_TABLET_DESKTOP_SITE, dpr=dpr)))
        self.assertTrue(fits(ANDROID_PHONE_DESKTOP_SITE))
        self.assertTrue(fits(ANDROID_TABLET))

    def test_the_devices_table_still_reads_the_screen_as_posthog_js_does(self):
        hints = {key: ANDROID_TABLET_DESKTOP_SITE[key] for key in ("uaData", "maxTouchPoints", "screen", "dpr")}
        self.assertEqual(web_device.device_type(DESKTOP_SITE_UA, hints), DEVICES["any_device_type"])


class AndroidTablet(unittest.TestCase):
    """An Android User-Agent without a phone's mark, on a tablet's screen, is a tablet's (verdict.json "touch"
    android_tablet: MDN's advice to look for Mobi, and Chrome for Android leaving Mobile out on tablets), whatever the
    Devices table's rules read: they take a Pixel Tablet's for a phone's, as posthog-js does. On a phone's screen the
    Devices table's type stands: its rules know phones whose User-Agents leave Mobile out."""

    def test_a_pixel_tablet_fits_either_way_up(self):
        self.assertTrue(fits(PIXEL_TABLET))
        self.assertTrue(fits(dict(PIXEL_TABLET, screen={"w": 800, "h": 1280})))

    def test_the_devices_table_still_reads_a_pixel_tablet_as_posthog_js_does(self):
        self.assertEqual(web_device.device_type(PIXEL_TABLET_UA), DEVICES["any_device_type"])

    def test_phones_the_devices_table_knows_without_mobile_fit_on_a_phones_screen_as_before(self):
        for name, user_agent, screen in (("zte", ZTE_UA, {"w": 360, "h": 780}),
                                         ("pixel 7 without mobile", PIXEL_WITHOUT_MOBILE_UA, {"w": 412, "h": 915})):
            with self.subTest(name):
                self.assertEqual(web_device.device_type(user_agent), PHONE)
                self.assertEqual(failed(page(dict(ANDROID_TABLET, userAgent=user_agent, screen=screen))), [])
                self.assertTrue(fits(dict(ANDROID_TABLET, userAgent=user_agent, screen=screen)))

    def test_tablets_the_devices_table_reads_as_tablets_fit_as_before(self):
        for name, user_agent in (("galaxy tab", ANDROID_TABLET_UA), ("pixel c", PIXEL_C_UA),
                                 ("firefox on a tablet", FIREFOX_TABLET_UA)):
            with self.subTest(name):
                self.assertTrue(fits(dict(ANDROID_TABLET, userAgent=user_agent)))

    def test_a_phones_user_agent_keeps_its_mark_and_a_tablets_screen_does_not_fit(self):
        """A folding phone opened flat: its User-Agent says Mobile."""
        self.assertFalse(fits(dict(PIXEL, userAgent=FOLD_UA, screen={"w": 673, "h": 841})))
        self.assertEqual(failed(page(dict(PIXEL, userAgent=FOLD_UA, screen={"w": 673, "h": 841}))),
                         [{"check": "screen-too-large", "device": PHONE, "w": 673, "h": 841, "min": BOUNDARY}])
        self.assertTrue(fits(dict(PIXEL, userAgent=FOLD_UA, screen={"w": 412, "h": 915})))

    def test_a_tablets_user_agent_on_a_phones_screen_is_too_small_for_it(self):
        self.assertEqual(failed(page(dict(ANDROID_TABLET, screen=PHONE_SCREEN))),
                         [{"check": "screen-too-small", "device": TABLET, "w": 390, "h": 844, "min": BOUNDARY}])

    def test_the_mark_and_the_system_are_read_from_the_settings(self):
        settings = copy.deepcopy(load("data/verdict.json"))
        settings["touch"]["android_tablet"]["mobile_mark"] = "Safari"  # every Chrome User-Agent has it
        self.assertFalse(touch_device.fits([page(PIXEL_TABLET)], settings))
        settings["touch"]["android_tablet"]["mobile_mark"] = "Mobi"
        self.assertTrue(touch_device.fits([page(PIXEL_TABLET)], settings))

    def test_the_boundary_between_a_phone_and_a_tablet_is_the_devices_tables(self):
        self.assertTrue(fits(dict(PIXEL, screen={"w": BOUNDARY - 1, "h": 960})))
        self.assertFalse(fits(dict(PIXEL, screen={"w": BOUNDARY, "h": 960})))
        self.assertTrue(fits(dict(ANDROID_TABLET, screen={"w": BOUNDARY, "h": 960})))
        self.assertFalse(fits(dict(ANDROID_TABLET, screen={"w": BOUNDARY - 1, "h": 960})))

    def test_a_browser_that_does_not_say_it_is_one_does_not_fit(self):
        self.assertFalse(fits(dict(IPHONE, anyPointer=["fine"])))

    def test_no_touch_points_do_not_fit(self):
        for points in (0, None, True):
            with self.subTest(points=points):
                self.assertFalse(fits(dict(IPHONE, maxTouchPoints=points)))
        self.assertFalse(fits({key: value for key, value in IPHONE.items() if key != "maxTouchPoints"}))

    def test_no_recorded_screen_does_not_fit(self):
        self.assertFalse(fits({key: value for key, value in IPHONE.items() if key != "screen"}))
        for screen in (None, {}, {"w": 390}, {"w": 0, "h": 844}):
            with self.subTest(screen=screen):
                self.assertFalse(fits(dict(IPHONE, screen=screen)))

    def test_a_phones_user_agent_on_a_larger_screen_does_not_fit(self):
        for name, screen in (("a folding phone opened flat", {"w": 673, "h": 841}), ("a tablet", TABLET_SCREEN),
                             ("a monitor", MONITOR)):
            with self.subTest(name):
                self.assertFalse(fits(dict(IPHONE, screen=screen)))
                self.assertFalse(fits(dict(PIXEL, screen=screen)))

    def test_a_tablets_user_agent_on_a_phones_screen_does_not_fit(self):
        self.assertFalse(fits(dict(IPAD, screen=PHONE_SCREEN)))
        self.assertFalse(fits(dict(ANDROID_TABLET, screen=PHONE_SCREEN)))

    def test_a_user_agent_that_names_no_phone_or_tablet_does_not_fit(self):
        for name, user_agent in (("a computer", MAC_SAFARI_UA), ("a console", SWITCH_UA), ("none", None)):
            with self.subTest(name):
                self.assertFalse(fits(dict(IPAD, userAgent=user_agent)))
                self.assertFalse(fits(dict(IPHONE, userAgent=user_agent)))

    def test_every_page_that_recorded_its_environment_has_to_fit(self):
        self.assertTrue(touch_device.fits([page(IPHONE), {"path": "/left-early"}, page(IPHONE)]))
        self.assertFalse(touch_device.fits([page(IPHONE), page(dict(IPHONE, screen=MONITOR))]))
        self.assertFalse(touch_device.fits([page(IPHONE), page(dict(IPHONE, anyPointer=["fine"]))]))

    def test_a_session_without_an_environment_record_fits_nothing(self):
        for pages in ([], None, [{"path": "/"}]):
            with self.subTest(pages=pages):
                self.assertFalse(touch_device.fits(pages))

    def test_a_record_of_another_shape_than_cake_js_sends_is_read_as_not_recorded(self):
        """An upload is whatever its sender wrote: nothing in it may stop the judge."""
        android_hints_only = dict(PIXEL, userAgent="Mozilla/5.0 (X11; Linux x86_64) Chrome/157.0.0.0 Safari/537.36")
        odd = {"screen": "390x844", "uaData": "mobile", "anyPointer": "coarse", "userAgent": 5, "dpr": "3",
               "maxTouchPoints": "5", "platform": ["iPhone"]}
        for key, value in odd.items():
            for env in (IPHONE, PIXEL, android_hints_only, IPAD_DESKTOP_SITE):
                with self.subTest(key=key, platform=env["platform"]):
                    pages = [dict(page(dict(env, **{key: value}), worker="iPad"))]
                    self.assertIn(touch_device.fits(pages), (True, False))
                    self.assertIn(touch_device.claimed(pages), (True, False))
        self.assertFalse(fits(dict(IPHONE, screen="390x844")))
        self.assertFalse(fits(dict(IPHONE, userAgent=5)))
        self.assertFalse(touch_device.claimed([page({"uaData": "mobile", "anyPointer": "coarse"})]))
        for auto in ("x", {"workerConsistency": "x"}, {"workerConsistency": {"worker": "iPad"}}):
            with self.subTest(auto=auto):
                self.assertFalse(touch_device.fits([dict(page(IPAD_DESKTOP_SITE), auto=auto)]))


class DesktopSite(unittest.TestCase):
    """An iPad shows the desktop site by default, an iPhone when asked: the page reports a Mac, a worker the device."""

    def test_an_ipad_showing_the_desktop_site_is_told_by_its_workers_platform(self):
        self.assertTrue(fits(IPAD_DESKTOP_SITE, worker="iPad"))

    def test_an_iphone_showing_the_desktop_site_is_a_phone_with_a_phones_screen(self):
        self.assertTrue(fits(IPHONE_DESKTOP_SITE, worker="iPhone"))
        self.assertTrue(fits(IPHONE_DESKTOP_SITE, worker="iPod touch"))

    def test_the_screen_has_to_be_the_size_of_the_device_the_worker_names(self):
        self.assertFalse(fits(IPAD_DESKTOP_SITE, worker="iPhone"))
        self.assertFalse(fits(IPHONE_DESKTOP_SITE, worker="iPad"))

    def test_without_the_workers_record_it_cannot_be_told(self):
        self.assertFalse(fits(IPAD_DESKTOP_SITE))
        no_answer = dict(page(IPAD_DESKTOP_SITE), auto={"workerConsistency": {"differs": []}})
        self.assertFalse(touch_device.fits([no_answer]))

    def test_a_worker_that_reports_a_computer_tells_nothing(self):
        for worker in ("MacIntel", "Linux x86_64", "Win32"):
            with self.subTest(worker):
                self.assertFalse(fits(IPAD_DESKTOP_SITE, worker=worker))

    def test_a_page_that_reports_no_more_touch_points_than_a_mac_can_is_no_ipad(self):
        self.assertFalse(fits(dict(IPAD_DESKTOP_SITE, maxTouchPoints=1), worker="iPad"))

    def test_only_a_page_that_reports_a_macs_platform_is_read_this_way(self):
        self.assertFalse(fits(dict(IPAD_DESKTOP_SITE, platform="Win32"), worker="iPad"))

    def test_it_reads_the_facts_the_worker_mismatch_rule_leaves_alone(self):
        """The rule's exception and this reading are one set of facts: where the rule counts no mismatch, the worker
        names the device; where it does (no touch screen), it names nothing."""
        base = load_cases()["page"]

        def held(env, worker):
            signals = {"pages": [merge(base, page(env, worker))]}
            return "env.spoof.worker-mismatch" in [hit.rule for hit in env_rules.evaluate(signals).hits]
        self.assertEqual((held(IPAD_DESKTOP_SITE, "iPad"), fits(IPAD_DESKTOP_SITE, "iPad")), (False, True))
        no_touch = dict(IPAD_DESKTOP_SITE, maxTouchPoints=0)
        self.assertEqual((held(no_touch, "iPad"), fits(no_touch, "iPad")), (True, False))

    def test_a_page_without_its_workers_record_takes_the_device_the_sessions_workers_reported(self):
        """A page closed before its worker answered: the session is one device, so its other pages' worker tells."""
        self.assertTrue(touch_device.fits([page(IPAD_DESKTOP_SITE, worker="iPad"), page(IPAD_DESKTOP_SITE)]))
        self.assertTrue(touch_device.fits([page(IPAD_DESKTOP_SITE), page(IPAD_DESKTOP_SITE, worker="iPad")]))
        self.assertTrue(touch_device.fits([page(IPHONE_DESKTOP_SITE), page(IPHONE_DESKTOP_SITE, worker="iPhone")]))

    def test_without_a_workers_record_on_any_page_it_still_cannot_be_told(self):
        pages = [page(IPAD_DESKTOP_SITE), page(IPAD_DESKTOP_SITE)]
        self.assertFalse(touch_device.fits(pages))
        self.assertEqual([entry["check"] for entry in touch_device.failed_checks(pages)], ["no-worker"])

    def test_a_worker_that_reported_another_platform_on_any_page_lends_nothing(self):
        """The page without a record of its own is then read by its Mac User-Agent: no-worker is for a session where
        no worker reported anything."""
        for workers in (("MacIntel", None), ("iPad", "MacIntel", None), ("iPad", "iPhone", None)):
            with self.subTest(workers=workers):
                pages = [page(IPAD_DESKTOP_SITE, worker=worker) for worker in workers]
                self.assertFalse(touch_device.fits(pages))
                checks = [entry["check"] for entry in touch_device.failed_checks(pages)]
                self.assertIn("other-device", checks)
                self.assertNotIn("no-worker", checks)

    def test_only_a_page_that_looks_like_the_desktop_site_borrows(self):
        for name, env in (("a page that reports Windows", dict(IPAD_DESKTOP_SITE, platform="Win32")),
                          ("a page with a Mac's touch points", dict(IPAD_DESKTOP_SITE, maxTouchPoints=1))):
            with self.subTest(name):
                pages = [page(IPAD_DESKTOP_SITE, worker="iPad"), page(env)]
                self.assertFalse(touch_device.fits(pages))
                self.assertEqual([entry["check"] for entry in touch_device.failed_checks(pages)], ["other-device"])

    def test_the_page_that_borrows_still_has_to_have_the_borrowed_devices_screen(self):
        pages = [page(IPAD_DESKTOP_SITE, worker="iPad"), page(dict(IPAD_DESKTOP_SITE, screen=PHONE_SCREEN))]
        self.assertEqual(touch_device.failed_checks(pages),
                         [{"check": "screen-too-small", "device": TABLET, "w": 390, "h": 844, "min": BOUNDARY}])
        no_touch = [page(IPAD_DESKTOP_SITE, worker="iPad"), page(dict(IPAD_DESKTOP_SITE, maxTouchPoints=0))]
        self.assertEqual([entry["check"] for entry in touch_device.failed_checks(no_touch)], ["no-touch-points"])

    def test_both_data_files_name_the_same_three_values(self):
        """verdict.json's touch.desktop_site and the exception in env.spoof.worker-mismatch's match: the page's
        platform, the worker's and the touch points (a whole number over one is two or more)."""
        rule = next(r for r in load("data/env_rules.json")["rules"] if r["id"] == "env.spoof.worker-mismatch")
        found = dict(conditions(rule["match"]))
        desktop_site = load("data/verdict.json")["touch"]["desktop_site"]
        self.assertEqual(found[("env.platform", "eq")], desktop_site["page_platform"])
        self.assertEqual(found[("auto.workerConsistency.worker.platform", "regex")], desktop_site["worker_platform"])
        self.assertEqual(found[("env.maxTouchPoints", "gt")] + 1, desktop_site["min_touch_points"])


def conditions(match):
    """((path, operator), value) of every test on a path in an env_rules match, however deep."""
    if isinstance(match, dict):
        if "path" in match:
            yield from (((match["path"], op), value) for op, value in match.items() if op not in ("path", "exists"))
        for inner in match.values():
            yield from conditions(inner)
    elif isinstance(match, list):
        for inner in match:
            yield from conditions(inner)


def failed(*pages):
    return touch_device.failed_checks(list(pages))


if __name__ == "__main__":
    unittest.main()
