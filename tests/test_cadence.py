"""agentcake/detect/cadence.py: isHumanCadence's class of a session's typing, on cake.js's raw events (plan step S3.7,
decision D36), and the model's session-level check that reads it (model.py, basis "typing_cadence").

    python3 -I -m unittest discover -s tests -v      (from the repository root)

Made-up typing, nobody recorded it: a script that holds every key as long and waits as long between keys ends at bot;
a hand's uneven holds and gaps, with keys pressed before the last came up and a correction now and then, ends at
human; a coarse clock, a finger and fewer than 20 key holds give no evidence; the class moves with the library's
hysteresis. The model takes typing that ends at bot for an agent only with evidence of a second kind, and never in a
recording without raw input.
"""
import math
import os
import random
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]

from agentcake.detect import cadence, model  # noqa: E402
from test_model import ev, hand_clicks, jump_clicks  # noqa: E402

PARAMS = model.load_params()["cadence"]
CLASSES = PARAMS["classes"]
T0 = 100_000


def typed(presses, deleted=()):
    """keydown, input and keyup records of keys pressed and released at the given (down, up) times; the field takes
    each character 1 ms after its key goes down. The keys at the indexes in deleted are Backspace."""
    out = []
    for n, (down, up) in enumerate(presses):
        key_class = "delete" if n in deleted else "letter"
        out += [ev(down, "keydown", kc=key_class, rp=0), ev(down + 1, "input"), ev(up, "keyup", kc=key_class, rp=0)]
    return out


def script(keys=30, hold=50, gap=100, t0=T0):
    """Every key held hold ms, the next pressed gap ms after the last came up."""
    return [(t0 + n * (hold + gap), t0 + n * (hold + gap) + hold) for n in range(keys)]


def hand(keys=60, seed=11, t0=T0):
    """A hand: holds around 95 ms, gaps around 160 ms spread like a person's (log-normal), a pause every few keys, and
    a fifth of the keys pressed before the last came up."""
    rng, presses, t = random.Random(seed), [], t0
    for n in range(keys):
        hold = max(30, rng.gauss(95, 25))
        if presses and rng.random() < 0.2:
            down = max(presses[-1][0] + 20, presses[-1][1] - rng.uniform(15, 40))
        else:
            gap = rng.lognormvariate(math.log(160), 0.45) + (rng.uniform(500, 1500) if n % 8 == 7 else 0)
            down = (presses[-1][1] if presses else t) + gap
        presses.append((down, down + hold))
    return presses


class Typing(unittest.TestCase):
    def test_a_script_that_types_evenly_ends_at_bot(self):
        result = cadence.judge(typed(script()), PARAMS)
        self.assertEqual((result["class"], result["samples"]), ("bot", 30))
        self.assertLess(result["score"], CLASSES["unknown_to_bot"])

    def test_a_hands_uneven_typing_ends_at_human(self):
        result = cadence.judge(typed(hand(), deleted={13, 41}), PARAMS)
        self.assertEqual(result["class"], "human")
        self.assertGreaterEqual(result["score"], CLASSES["unknown_to_human"])

    def test_typing_that_ends_at_bot_says_which_keys_its_evidence_covers(self):
        presses = script()
        self.assertEqual(cadence.judge(typed(presses), PARAMS)["span"], [presses[0][0], presses[-1][1]])
        self.assertIsNone(cadence.judge(typed(hand(), deleted={13, 41}), PARAMS)["span"])

    def test_the_window_holds_the_last_keys_only(self):
        self.assertEqual(cadence.judge(typed(script(keys=80)), PARAMS)["samples"], PARAMS["window"])


class NoEvidence(unittest.TestCase):
    def test_fewer_key_holds_than_min_samples(self):
        self.assertIsNone(cadence.judge(typed(script(keys=PARAMS["min_samples"] - 1)), PARAMS))

    def test_a_coarse_clock(self):
        """A privacy browser's 33 ms grid: the field's input comes at the key's own time, every other gap a step."""
        coarse = [(down, up) for down, up in script(hold=33, gap=99)]
        events = [{**e, "t": e["t"] - 1} if e["ty"] == "input" else e for e in typed(coarse)]
        self.assertIsNone(cadence.judge(events, PARAMS))
        self.assertTrue(cadence.fine_clock(typed(coarse), PARAMS["fine_clock_ms"]), "the same keys on a fine clock")

    def test_a_finger_or_a_pen(self):
        touched = typed(script()) + [ev(T0 - 500, "pointerdown", pt="touch")]
        self.assertIsNone(cadence.judge(touched, PARAMS))


class Hysteresis(unittest.TestCase):
    def test_the_class_moves_as_the_librarys(self):
        moves = [(0.30, "unknown", "bot"), (0.40, "bot", "bot"), (0.46, "bot", "unknown"), (0.40, "unknown", "unknown"),
                 (0.71, "unknown", "human"), (0.65, "human", "human"), (0.59, "human", "unknown")]
        for score, current, after in moves:
            self.assertEqual(cadence.classify(score, current, CLASSES), after, (score, current))


class SessionCheck(unittest.TestCase):
    """The model's basis typing_cadence: a hand's clicks around typing that ends at bot."""

    def session(self, *extra):
        return hand_clicks(6, t0=1000) + typed(script(t0=40_000)) + list(extra)

    def test_alone_it_is_one_kind_of_evidence_and_not_enough(self):
        result = model.judge_session(self.session())
        self.assertEqual(result["evidence"]["typing_cadence"]["class"], "bot")
        self.assertEqual((result["verdict"], result["evidence"]["one_kind"]), ("unsure", "keys"))

    def test_with_a_second_kind_it_makes_an_agent(self):
        result = model.judge_session(self.session(*jump_clicks(2, t0=70_000)))
        self.assertEqual((result["verdict"], result["basis"]), ("agent", ["typing_cadence"]))

    def test_its_keys_are_the_agents_on_the_timeline(self):
        result = model.judge_session(self.session(*jump_clicks(2, t0=70_000)))
        presses = script(t0=40_000)
        self.assertEqual(result["timeline"]["checks"],
                         [{"check": "typing_cadence", "from": presses[0][0], "to": presses[-1][1]}])
        typed_actions = [a for a in result["timeline"]["actions"] if presses[0][0] <= a["t"] <= presses[-1][1]]
        self.assertEqual({a["who"] for a in typed_actions}, {"agent"})

    def test_never_without_raw_input(self):
        result = model.judge_session(self.session(*jump_clicks(2, t0=70_000)), raw_input=False)
        self.assertNotIn("typing_cadence", result["basis"])

    def test_a_hands_typing_leaves_a_human(self):
        result = model.judge_session(hand_clicks(6, t0=1000) + typed(hand(t0=40_000), deleted={13, 41}))
        self.assertEqual((result["verdict"], result["evidence"]["typing_cadence"]["class"]), ("human", "human"))


class Stretches(unittest.TestCase):
    """model.checked_stretches: what each session-level check covers on the timeline."""

    def test_teleport_clicks_cover_their_own_moments(self):
        events = jump_clicks(3, t0=5000)
        moments = model.teleport_clicks(events)
        self.assertTrue(moments)
        self.assertEqual(model.checked_stretches(["teleport_clicks"], {}, events),
                         [{"check": "teleport_clicks", "from": t, "to": t} for t in moments])

    def test_the_move_rate_covers_all_the_movement_only_when_no_segment_located_the_agent(self):
        events = jump_clicks(3, t0=5000)
        moves = sorted(e["t"] for e in events if e["ty"] == "mousemove")
        self.assertEqual(model.checked_stretches(["active_move_rate"], {}, events),
                         [{"check": "active_move_rate", "from": moves[0], "to": moves[-1]}])
        self.assertEqual(model.checked_stretches(["rules", "active_move_rate"], {}, events), [])


if __name__ == "__main__":
    unittest.main()
