"""Whether a session's browser is a phone or tablet, read from the environment records of its pages, and which check of
a real one its records fail.

    claimed(pages) -> bool    the browser's own word, on any page: its client hints say mobile, or it has a coarse
                              pointer and no fine one
    fits(pages, settings=None) -> bool
                              every page that recorded its environment is a real one's: the browser says so, it has
                              touch points, and its screen is the size of the device its User-Agent names
    failed_checks(pages, settings=None) -> [{"check": one of CHECKS, its facts...}]
                              the checks of fits() the records fail, each once, with the facts of the first record that
                              failed it, in the order of CHECKS; none when every record passes, and none for a session
                              without a record (which fits nothing all the same)

pages: env_signals' pages ([{"env": cake.js's environment record, "auto": {"workerConsistency": ...}}, ...]); a page
left before cake.js made the record has none and says nothing, and a session without any record fits nothing. A record
is whatever the upload held, so a value of another shape than cake.js sends is read as not recorded.

claimed() is why the behaviour model does not run (it knows a mouse and a keyboard: behavior.py), and what the
environment rules read as the signals' "touch" (env_rules.evaluate). fits() is what the verdict asks before it calls
such a visit a Human with nothing else to go on (verdict_touch.py): a browser passing as a phone keeps a computer's
screen, or has no touch screen. failed_checks() is what the verdict says of a visit that stays a Human on limited
evidence because its records do not fit. A session the model skipped always has a record (the claim is read from one),
so no check says that none was made. The device a User-Agent names is web_device.device_type()'s, the Devices table's
(posthog-js's rules, data/devices.json): its Mobile needs a screen whose short side, in CSS pixels, is under
tablet_short_side_dp, its Tablet one of that size or more, and any other type (a desktop, a console, a wearable)
fits nothing. An Android User-Agent without a phone's mark, on a screen of a tablet's size, is a tablet's (verdict.json
"touch" android_tablet: MDN's "Browser detection using the user agent", mdn/content 6ad108adad74, looks for Mobi
anywhere in the User-Agent, and Chrome's "User-Agent Strings", GoogleChrome/developer.chrome.com 4e2b66893293, gives
Chrome for Android's tablet User-Agent without Mobile; the method only, no text copied). The Devices table keeps
posthog-js's rules, and those read some such User-Agents as a phone's (its pattern for Pixel phones takes in "Pixel
Tablet"), so there the Devices table shows Mobile while the type checked here is Tablet: the table names what
posthog-js names, the check needs the device the browser says it is. On a phone's screen the Devices table's type
stands, as it did before the rule: its rules know phones whose User-Agents leave Mobile out (Pixel phones, ZTE and
other models), which fit as phones; the price is that a Pixel Tablet's User-Agent on a phone's screen fits as a phone,
which no real device shows. A User-Agent that names no device, as Chrome's on an Android tablet showing the desktop site
(its default there), leaves the type to the client hints and the screen. The Devices table divides that screen by the
pixel ratio, as posthog-js does; here the type is read without it, from the same CSS pixels the screen is checked in,
or such a tablet would read as a phone and fit nothing whenever its ratio takes the short side under the boundary. An
iPad or iPhone showing the desktop site names a Mac in its User-Agent, so there the device is the one its worker's
platform names: the page reports a Mac's platform with more touch points than any Mac has while a worker still
reports the device (verdict.json "touch" desktop_site, the facts env.spoof.worker-mismatch leaves alone: after
fpscanner's isBenignIOSMacPlatformSplit, MIT, github.com/antoinevastel/fpscanner 4255cfd8a23f, the condition only, no
code copied). A page without a worker's record of its own (closed before its worker answered: cake.js starts the
worker after it records the environment) takes the device the session's workers reported on its other pages, the
session being one device, when they reported one iPad, iPhone or iPod and no other platform; its screen and touch
points are checked as any page's. Without that it cannot be told and does not fit. Nor does a folding phone opened
flat (a phone's User-Agent, with its Mobile, and a tablet's screen): both stay as they were, a Human on limited
evidence.

The checks (CHECKS), with the facts each gives. A page whose browser does not say it is a phone or tablet fails that
check alone: its other values are no phone's. The device type is read only with touch points and a screen.
    not-claimed        the browser does not say it is a phone or tablet
    no-touch-points    no touch points; points: the recorded value, None when it is not a number
    no-screen          no screen size
    other-device       the device type is none of a phone's or a tablet's; device: that type (Desktop, Console, ...)
    screen-too-large   the device type is a phone's (Mobile) and the screen's short side is the boundary or more;
                       device: that type (the one checked here), w, h: the screen, min: the boundary
                       (tablet_short_side_dp)
    screen-too-small   the device type is a tablet's and the screen's short side is under the boundary; device, w, h,
                       min
    no-worker          the desktop site of an iPad or iPhone, and no worker's record of a platform on any page of the
                       session; platform: the page's, points: its touch points. Where workers reported something the
                       page cannot take (another platform, or a second device), it fails other-device
"""
import re

from agentcake import web_device
from agentcake.datafiles import load

SETTINGS_FILE = "data/verdict.json"
COARSE, FINE = "coarse", "fine"  # protocol: CSS any-pointer values
NOT_CLAIMED, NO_TOUCH_POINTS, NO_SCREEN = "not-claimed", "no-touch-points", "no-screen"
OTHER_DEVICE, SCREEN_TOO_LARGE, SCREEN_TOO_SMALL, NO_WORKER = (
    "other-device", "screen-too-large", "screen-too-small", "no-worker")
CHECKS = (NOT_CLAIMED, NO_TOUCH_POINTS, NO_SCREEN, OTHER_DEVICE, SCREEN_TOO_LARGE, SCREEN_TOO_SMALL, NO_WORKER)
CHECK = "check"


def claimed(pages):
    """Whether the browser says it is a phone or tablet on any page that recorded its environment."""
    return any(_says_so(env) for env, _ in _records(pages))


def fits(pages, settings=None):
    """Whether every environment record of the session is a real phone's or tablet's (see the module docstring)."""
    return bool(_records(pages)) and not failed_checks(pages, settings)


def failed_checks(pages, settings=None):
    """The checks of a real phone or tablet that the session's environment records fail (see the module docstring)."""
    rule = (settings or load(SETTINGS_FILE))["touch"]
    records = _records(pages)
    workers = {_worker_platform(auto) for _, auto in records} - {None}  # what the session's workers reported
    lent, first = _lent_worker(workers, rule), {}
    for env, auto in records:
        for failed in _failed(env, auto, rule, (lent, bool(workers))):
            first.setdefault(failed[CHECK], failed)
    return [first[check] for check in CHECKS if check in first]


def _records(pages):
    """(environment record, the page's automation checks) of each page that recorded its environment."""
    found = [page for page in pages or () if isinstance(page, dict) and isinstance(page.get("env"), dict)]
    return [(page["env"], _object(page.get("auto"))) for page in found]


def _lent_worker(workers, rule):
    """The device the session's workers reported (workers: the platforms), for a page that shows the desktop site
    without a worker's record of its own (the session is one device): the one platform they reported, when it names an
    iPad, iPhone or iPod; None when no worker reported a platform, or one reported another platform or a second
    device."""
    if len(workers) != 1:
        return None
    (platform,) = workers
    return platform if re.search(rule["desktop_site"]["worker_platform"], platform) else None


def _says_so(env):
    pointers = env.get("anyPointer") if isinstance(env.get("anyPointer"), list) else []
    return bool(_object(env.get("uaData")).get("mobile")) or (COARSE in pointers and FINE not in pointers)


def _failed(env, auto, rule, session):
    """The checks one record fails: the browser's word first, then its touch points and its screen, and with both,
    whether the screen is the size of the device the record names. session: (the device the session's workers lend,
    whether any of them reported a platform)."""
    if not _says_so(env):
        return [{CHECK: NOT_CLAIMED}]
    screen = _object(env.get("screen"))
    sides, points = [screen.get("w"), screen.get("h")], env.get("maxTouchPoints")
    failed = []
    if not _positive(points):
        failed.append({CHECK: NO_TOUCH_POINTS, "points": points if _number(points) else None})
    if not all(_positive(side) for side in sides):
        failed.append({CHECK: NO_SCREEN})
    return failed or _device_failed(env, auto, rule, sides, session)


def _device_failed(env, auto, rule, sides, session):
    """The check a record with touch points and a screen fails when its screen is not the size of its device."""
    (lent, any_worker), devices = session, load(web_device.RULES)
    boundary = devices["tablet_short_side_dp"]
    tablet_screen = min(sides) >= boundary
    device = _device_type(env, auto, rule, lent, tablet_screen)
    phone, tablet = devices["any_device_type"], devices["tablet_type"]
    if device == (tablet if tablet_screen else phone):
        return []
    if device in (phone, tablet):
        too = SCREEN_TOO_LARGE if device == phone else SCREEN_TOO_SMALL
        return [{CHECK: too, "device": device, "w": sides[0], "h": sides[1], "min": boundary}]
    if _desktop_site(env, rule) and not any_worker:
        return [{CHECK: NO_WORKER, "platform": env["platform"], "points": env["maxTouchPoints"]}]
    return [{CHECK: OTHER_DEVICE, "device": device}]


def _device_type(env, auto, rule, lent, tablet_screen):
    """The type of device the page's User-Agent names; for the desktop site on an iPad or iPhone, the type its
    worker's platform names, or the session's workers' when the page has no worker's record (lent); for Android without
    a phone's mark on a screen of a tablet's size (tablet_screen), a tablet. Called with touch points and a screen that
    are numbers."""
    worker = _worker_platform(auto)
    worker = lent if worker is None else worker
    if _desktop_site(env, rule) and worker is not None and re.search(rule["desktop_site"]["worker_platform"], worker):
        return web_device.device_type(worker)
    user_agent = env.get("userAgent") if isinstance(env.get("userAgent"), str) else ""
    if tablet_screen and _android_tablet(user_agent, rule):
        return load(web_device.RULES)["tablet_type"]
    # what web_device reads of the record, in the shapes it expects, but its pixel ratio: a User-Agent that names no
    # device then gets the type of the screen in the CSS pixels it is checked in (see the module docstring)
    hints = {"uaData": _object(env.get("uaData")), "maxTouchPoints": env["maxTouchPoints"], "screen": env["screen"]}
    return web_device.device_type(user_agent, hints)


def _android_tablet(user_agent, rule):
    """Whether the User-Agent names Android without a phone's mark: a tablet's (verdict.json "touch" android_tablet)."""
    android = rule["android_tablet"]
    return bool(re.search(android["user_agent"], user_agent)) and not re.search(android["mobile_mark"], user_agent)


def _desktop_site(env, rule):
    """Whether the page reports a Mac's platform with more touch points than any Mac has (verdict.json "touch"
    desktop_site). Called with touch points that are a number."""
    desktop_site = rule["desktop_site"]
    return (env.get("platform") == desktop_site["page_platform"]
            and env["maxTouchPoints"] >= desktop_site["min_touch_points"])


def _worker_platform(auto):
    """The platform the page's worker reported, None without a worker's record of it."""
    platform = _object(_object(auto.get("workerConsistency")).get("worker")).get("platform")
    return platform if isinstance(platform, str) else None


def _object(value):
    return value if isinstance(value, dict) else {}


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _positive(value):
    return _number(value) and value > 0
