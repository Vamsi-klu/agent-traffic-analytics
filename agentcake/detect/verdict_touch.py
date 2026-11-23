"""When a phone or tablet the behaviour model did not run on is a Human (rule 5 of verdict.py), and what its behaviour
layer says.

    human(evidence, identity, browsers) -> bool
    reasons(evidence, cls) -> [reason]     the behaviour layer's reasons for such a visit, its class decided

evidence: the session's (verdict.py's docstring), whose phone keys are touch (touch_device.claimed(): the browser says
it is a phone or tablet), touch_fits (touch_device.fits(): its environment records fit a real one) and touch_failed
(touch_device.failed_checks(): the checks of a real one they fail, with their facts); identity: what its name and
verification layers found (verdict_identity.identify); browsers: the environment hits that only name the browser the
page is open in (attribute.browser_rules).

The behaviour model knows a mouse and a keyboard, so it judges no phone or tablet, and an agent that drives one and
leaves no trace cannot be told from a human there. Such a visit is a Human, as any other, when all of this holds (the
owner's rule of 2026-11-22):
  - its browser says it is a phone or tablet, which is why the model did not run (touch_device.claimed());
  - its environment records fit a real one (the evidence's touch_fits, touch_device.fits());
  - the name layer found nothing, and neither did the verification layer: no reason of theirs is listed, except what a
    verification layer that is off says of itself (in local mode it checks nothing);
  - the environment layer found nothing but weak hits, which only inform. verdict.py asks only then: hard hits, and
    soft ones (the checks for a computer passing as a phone or tablet are soft), are decided before. Nor does a hit name
    the browser, or an agent product's indicator show on a page (the evidence's marks).
A visit that fails one of these and is no Agent or Bot stays what it was: Too little data, or Not sure with soft hits
alone (a Human on limited evidence, as the interface shows both).

Its behaviour layer says that the model was not used. When the visit stays a Human on limited evidence and its records
do not fit a real phone or tablet, it then says which check they failed, one reason per check with its facts (the
owner's rule of 2026-11-23). The other conditions have their own reasons already (the soft hits', the name and
verification layers', a browser's product rule, an indicator's), so nothing more is said of them; nor is it of an Agent
or a Bot on a phone, or of a real phone or tablet. The evaluation's recordings of events alone are phones by their
data set's label, without records or checks (evaluation/evidence.py): they say no more than that the model was not used.
"""
from agentcake.detect import touch_device
from agentcake.detect.verdict_text import reason

TOUCH = "touch"  # behavior.run()'s reason for a phone or tablet
TOO_LITTLE, NOT_SURE, OFF = "too_little_data", "not_sure", "off"
LIMITED = (TOO_LITTLE, NOT_SURE)  # the classes the interface shows as a Human on limited evidence (api/visits.py)
NAME, VERIFY = "name", "verify"
PAGE = "page"  # the half the environment records come from
FAILED_CHECK_REASONS = {touch_device.NOT_CLAIMED: "behavior.touch-not-claimed",
                        touch_device.NO_TOUCH_POINTS: "behavior.touch-no-touch-points",
                        touch_device.NO_SCREEN: "behavior.touch-no-screen",
                        touch_device.OTHER_DEVICE: "behavior.touch-other-device",
                        touch_device.SCREEN_TOO_LARGE: "behavior.touch-screen-too-large",
                        touch_device.SCREEN_TOO_SMALL: "behavior.touch-screen-too-small",
                        touch_device.NO_WORKER: "behavior.touch-no-worker"}


def human(evidence, identity, browsers):
    """Whether the session is a real phone's or tablet's with nothing else found on it (see the module docstring)."""
    result = evidence.get("behavior") or {}
    skipped = result.get("verdict") == TOO_LITTLE and (result.get("evidence") or {}).get("reason") == TOUCH
    if not (skipped and evidence.get("touch_fits")):
        return False
    return not (browsers or evidence.get("marks") or _found(identity))


def reasons(evidence, cls):
    """The behaviour layer's reasons for a visit it did not run on because it is a phone or tablet, of class cls: that
    the model was not used, then, for a Human on limited evidence, each check of a real phone or tablet its records
    failed (see the module docstring)."""
    failed = (evidence.get("touch_failed") or ()) if cls in LIMITED else ()
    return [reason("behavior.touch", PAGE)] + [_failed_check(check) for check in failed]


def _failed_check(check):
    """The reason for one failed check (touch_device.failed_checks()'s entry), worded with its facts."""
    facts = {name: value for name, value in check.items() if name != touch_device.CHECK}
    return reason(FAILED_CHECK_REASONS[check[touch_device.CHECK]], PAGE, **facts)


def _found(identity):
    """The reasons of the name and verification layers that are findings: all of them, but for the words of a
    verification layer that is off."""
    verifying = identity.verify_layer.get("state") != OFF
    return [r for r in identity.reasons if r["layer"] == NAME or (r["layer"] == VERIFY and verifying)]
