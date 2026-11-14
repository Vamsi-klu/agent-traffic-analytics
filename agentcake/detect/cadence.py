"""How a session's keys were typed: isHumanCadence's score and class of the typing, on cake.js's raw events (plan step
S3.7, decision D36; job behavior-best, a lead from the open-source bench, S9.6).

    judge(events, params) -> {"class": "bot" | "unknown" | "human", "score", "samples", "span"}, or None: no evidence
    classify(score, current, thresholds) -> the class after one more score (the library's hysteresis)
    fine_clock(events, fine_clock_ms) -> whether two events of one page ever came less than fine_clock_ms apart

Part of the behaviour layer (model.py reads it as a session-level check). params: agentcake/data/behavior_model.json
"cadence". Input: a session's events in the raw-event format (segment.py).

The library is isHumanCadence 1.5.1 (github.com/RoloBits/isHumanCadence, commit 21b39ea3, MIT: its notice is at the
end of this docstring; THIRD_PARTY.md). Its observer, analyzer, anti-spoof check and classification (src/observer.ts,
analyzer.ts, anti-spoof.ts, utils.ts, index.ts) are rewritten here, their weights and thresholds unchanged. After every
key release it scores the last `window` key holds and gaps between keys on six measures: how much the holds vary; how
the gaps fit a person's log-normal shape rather than an even spread, and follow one another; their entropy; the share
of corrections; how evenly the pauses between bursts come; and the share of keys pressed before the last came up. A
measure without enough samples scores 0.5, and one that has nothing to measure (no correction, no rollover, fewer than
two pauses) does not vote. The class moves with hysteresis: from unknown to bot below unknown_to_bot, back to unknown
only at bot_to_unknown, to human at unknown_to_human and back below human_to_unknown. The class the last release leaves
is the session's, once the window holds at least min_samples key holds. span: for a session that ends at bot, the
stretch its evidence covers, [from, to] in ms: from the first press of the window in which the class last turned bot
to the last key released (None otherwise); model.py gives the actions inside it to the agent.

Two differences from the library, both from what cake.js records (docs/collect-format.md): a key's class, never the key,
so Backspace and Delete are the "delete" class, and the four modifier keys are one class, counted as the library counts
Shift (it skips Control, Alt and Meta and the key pressed with them); and one run over the whole session instead of one
per page. On the lab's sessions and the recorder's people this gives the scores the bench measured with the library.

No evidence at all (None), so that no person is taken for an agent:
- when the window holds fewer than min_samples key holds;
- in a session where a finger or a pen gave input: a phone's or a tablet's virtual keyboard sends each key's down and
  up together;
- when the session's clock is coarse: privacy browsers round event times (LibreWolf to a 33 ms grid, Firefox's
  resistFingerprinting more), which makes every hold look alike. The clock is fine when two consecutive events of one
  page came more than 0 and less than fine_clock_ms apart.

isHumanCadence's notice:

    MIT License

    Copyright (c) 2025 ApoloDev

    Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
    documentation files (the "Software"), to deal in the Software without restriction, including without limitation
    the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
    permit persons to whom the Software is furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all copies or substantial portions of
    the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
    THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
    TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.
"""
import math

KEYDOWN, KEYUP, INPUT = "keydown", "keyup", "input"
TOUCH_OR_PEN = frozenset({"touch", "pen"})  # protocol: PointerEvent.pointerType of a finger or a pen
TOUCH_EVENTS = frozenset({"touchstart", "touchend"})
DELETE = "delete"  # cake.js's key class of Backspace and Delete (privacy.json page.key_classes)
BOT, UNKNOWN, HUMAN = "bot", "unknown", "human"
NO_VOTE = None  # a measure with nothing to measure (the library's NO_DATA): left out of the weighted mean
# The normal distribution's approximation the library uses (utils.ts normalCDF): Abramowitz and Stegun 26.2.17.
AS_P = 0.2316419  # protocol: Abramowitz and Stegun 26.2.17
AS_A = (0.31938153, -0.356563782, 1.781477937, -1.821255978, 1.330274429)  # protocol: Abramowitz and Stegun 26.2.17


def judge(events, params):
    """The typing's class, its last score and the key holds in its window; None when it gives no evidence."""
    events = sorted(events, key=lambda e: e["t"])
    if any(e.get("pt") in TOUCH_OR_PEN or e.get("ty") in TOUCH_EVENTS for e in events):
        return None
    if not fine_clock(events, params["fine_clock_ms"]):
        return None
    typing = _Typing(params)
    for e in events:
        typing.add(e)
    if len(typing.dwells) < params["min_samples"]:
        return None
    span = [typing.bot_from, typing.bot_to] if typing.current == BOT else None
    return {"class": typing.current, "score": typing.score, "samples": len(typing.dwells), "span": span}


def classify(score, current, thresholds):
    """The library's hysteresis (index.ts classify)."""
    if current == BOT:
        return UNKNOWN if score >= thresholds["bot_to_unknown"] else BOT
    if current == HUMAN:
        return UNKNOWN if score < thresholds["human_to_unknown"] else HUMAN
    if score >= thresholds["unknown_to_human"]:
        return HUMAN
    return BOT if score < thresholds["unknown_to_bot"] else UNKNOWN


def fine_clock(events, fine_clock_ms):
    """Whether two consecutive events of one page came more than 0 and less than fine_clock_ms apart."""
    last_by_page = {}
    for e in sorted(events, key=lambda e: e["t"]):
        last = last_by_page.get(e.get("pg"))
        if last is not None and 0 < e["t"] - last < fine_clock_ms:
            return True
        last_by_page[e.get("pg")] = e["t"]
    return False


class _Typing:
    """The library's observer (observer.ts), fed one event at a time, and its class after every key release."""

    def __init__(self, params):
        self.params = params
        self.dwells, self.flights, self.presses = [], [], []  # presses: the window's press times, as its dwells
        self.bot_from = self.bot_to = None
        self.corrections = self.rollovers = self.total = self.held = 0
        self.last_down = self.last_press = self.last_release = None
        self.repeating = False
        self.current, self.score = UNKNOWN, None

    def add(self, e):
        kind, t = e.get("ty"), e["t"]
        if kind == KEYDOWN:
            self._down(e, t)
        elif kind == KEYUP:
            self._up(t)
        elif kind == INPUT and (self.last_down is None or
                                t - self.last_down > self.params["input_without_keystroke_ms"]):
            self.last_release = None  # text came without a key (a paste, an autofill): no gap to the next key

    def _down(self, e, t):
        self.last_down = t
        if e.get("kc") == DELETE:
            self.corrections += 1  # before the repeat check, as the library counts them
        if e.get("rp"):
            self.repeating = True
            return
        self.held += 1
        self.rollovers += self.held > 1
        self.total += 1
        if self.last_release is not None and self.held == 1:
            self.flights = (self.flights + [t - self.last_release])[-self.params["window"]:]
        self.last_press = t

    def _up(self, t):
        if self.last_press is not None and not self.repeating:
            self.dwells = (self.dwells + [t - self.last_press])[-self.params["window"]:]
            self.presses = (self.presses + [self.last_press])[-self.params["window"]:]
        self.repeating = False
        self.held = max(0, self.held - 1)
        self.last_release = t
        self.score = score(self.dwells, self.flights, self.corrections, self.rollovers, self.total, self.params)
        was, self.current = self.current, classify(self.score, self.current, self.params["classes"])
        if self.current != BOT:
            self.bot_from = self.bot_to = None
            return
        if was != BOT:  # the window that turned it: its first press
            self.bot_from = self.presses[0] if self.presses else t
        self.bot_to = t


def score(dwells, flights, corrections, rollovers, total, params):
    """The library's score (analyzer.ts): the weighted mean of the measures that vote, between 0 and 1."""
    measures = {"dwell_variance": _dwell_variance(dwells, params["dwell"]),
                "flight_fit": _flight_fit(flights, params),
                "timing_entropy": _timing_entropy(flights, params["entropy"]),
                "correction_ratio": _share_score(corrections, total, params["correction"]),
                "burst_regularity": _burst_regularity(flights, params["burst"]),
                "rollover_rate": _share_score(rollovers, total, params["rollover"])}
    voting = {name: value for name, value in measures.items() if value is not NO_VOTE}
    weight = sum(params["weights"][name] for name in voting)
    if not weight:
        return 0
    return min(1, max(0, sum(params["weights"][name] * value for name, value in voting.items()) / weight))


def _dwell_variance(dwells, rule):
    if len(dwells) < rule["min_samples"]:
        return rule["neutral"]
    spread = _spread(dwells)
    return _sigmoid(spread, *rule["up"]) * _sigmoid(spread, *rule["down"])


def _flight_fit(flights, params):
    rule, spoof = params["flight"], params["spoof"]
    if len(flights) < rule["min_samples"]:
        return rule["neutral"]
    fast = sum(1 for gap in flights if gap < rule["floor_ms"]) / len(flights)
    return _genuine(flights, spoof) * (rule["floor_penalty"] if fast > rule["floor_share"] else 1)


def _genuine(flights, spoof):
    """anti-spoof.ts detectSpoof's genuineScore: log-normal shape, an uneven spread, and gaps that follow each other."""
    follow = abs(_autocorrelation(flights))
    follow_score = min(1, follow / spoof["autocorr_max"]) if follow > spoof["autocorr_floor"] else 0
    genuine = (spoof["log_normality"] * _log_normality(flights, spoof)
               + spoof["uniformity"] * (1 - _uniformity(flights, spoof)) + spoof["autocorrelation"] * follow_score)
    return min(1, max(0, genuine))


def _log_normality(flights, spoof):
    logged = [math.log(gap) for gap in flights if gap > 0]
    if len(logged) < spoof["min_samples"]:
        return spoof["neutral"]
    centre, spread = _mean(logged), _spread(logged)
    if spread == 0:
        return 0
    return _ks_score(_ks(logged, lambda x: _normal_cdf((x - centre) / spread)), len(logged), spoof)


def _uniformity(flights, spoof):
    low, high = min(flights), max(flights)
    if high == low:
        return 0
    return _ks_score(_ks(flights, lambda x: (x - low) / (high - low)), len(flights), spoof)


def _ks(samples, cdf):
    """The Kolmogorov-Smirnov distance between the samples and a distribution."""
    ordered = sorted(samples)
    n, distance = len(ordered), 0
    for i, x in enumerate(ordered):
        expected = cdf(x)
        distance = max(distance, abs((i + 1) / n - expected), abs(i / n - expected))
    return distance


def _ks_score(distance, n, spoof):
    critical = spoof["ks_critical"] / math.sqrt(n)
    if distance <= critical:
        return spoof["pass_base"] + spoof["pass_bonus"] * (1 - distance / critical)
    return max(0, spoof["fail_base"] * critical / distance)


def _timing_entropy(flights, rule):
    if len(flights) < rule["min_samples"]:
        return rule["neutral"]
    bits = _entropy(flights, rule["bins"])
    low, high = min(flights), max(flights)
    fluctuation = high / low if low > 0 else 0
    return (rule["entropy_weight"] * _sigmoid(bits, *rule["up"]) * _sigmoid(bits, *rule["down"])
            + rule["fluctuation_weight"] * _sigmoid(fluctuation, *rule["fluctuation"]))


def _entropy(values, bins):
    """Shannon entropy in bits of the values in `bins` equal bins between their least and their greatest."""
    low, high = min(values), max(values)
    if high == low:
        return 0
    counts = [0] * bins
    for value in values:
        counts[min(math.floor((value - low) / (high - low) * bins), bins - 1)] += 1
    return -sum(count / len(values) * math.log2(count / len(values)) for count in counts if count)


def _share_score(count, total, rule):
    """correctionRatio and rolloverRate: how far the share of keys rises above none, scaled by a sigmoid."""
    if total < rule["min_keys"]:
        return rule["neutral"]
    if not count:
        return NO_VOTE
    share = count / total
    floor = _sigmoid(0, *rule["sigmoid"])
    lifted = (_sigmoid(share, *rule["sigmoid"]) - floor) / (1 - floor)
    excessive = rule.get("excessive")
    return lifted * rule["excessive_penalty"] if excessive is not None and share > excessive else lifted


def _burst_regularity(flights, rule):
    if len(flights) < rule["min_samples"]:
        return rule["neutral"]
    pauses = [gap for gap in flights if gap > rule["pause_ms"]]
    if len(pauses) < rule["min_pauses"]:
        return NO_VOTE
    centre = _mean(pauses)
    return _sigmoid(_spread(pauses) / centre if centre > 0 else 0, *rule["sigmoid"])


def _mean(values):
    return sum(values) / len(values)


def _spread(values):
    """The population standard deviation in plain floating point, as the library's utils.ts stddev."""
    centre = _mean(values)
    return math.sqrt(sum((v - centre) * (v - centre) for v in values) / len(values))


def _autocorrelation(values):
    """The lag-one autocorrelation (utils.ts)."""
    centre = _mean(values)
    spread = sum((v - centre) ** 2 for v in values)  # protocol: a sum of squares
    follow = sum((values[i] - centre) * (values[i - 1] - centre) for i in range(1, len(values)))
    return follow / spread if spread else 0


def _normal_cdf(x):
    t = 1 / (1 + AS_P * abs(x))
    polynomial = 0
    for a in reversed(AS_A):  # Horner's form of a1 t + a2 t^2 + ... + a5 t^5
        polynomial = (polynomial + a) * t
    tail = math.exp(-x * x / 2) / math.sqrt(math.tau) * polynomial  # protocol: the normal density
    return 1 - tail if x >= 0 else tail


def _sigmoid(x, slope, midpoint):
    try:
        return 1 / (1 + math.exp(-slope * (x - midpoint)))
    except OverflowError:  # the library's JavaScript reads exp() past its range as Infinity: a sigmoid of 0
        return 0.0
