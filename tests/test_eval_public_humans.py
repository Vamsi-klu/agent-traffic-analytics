"""Public human data sets for the scoreboard: reading them in `agentcake eval`.

    python3 -I -m unittest discover -s tests -v

motion-attestation's 27 captures come from the checkout (tests/fixtures/motion_attestation, MIT).
"""
import os
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]

from agentcake import datafiles  # noqa: E402
from agentcake.evaluation import datasets, sessions, sources  # noqa: E402

SETTINGS = datafiles.load("data/eval.json")
FIXTURE = os.path.join(TESTS, "fixtures", "motion_attestation", "humans.json")


class MotionAttestationTest(unittest.TestCase):
    def test_every_capture_is_a_public_human_of_its_own_site(self):
        people = datasets.motion_attestation(FIXTURE)
        self.assertEqual(len(people), 27)
        self.assertEqual({p["set"] for p in people} | {p["site"] for p in people}, {"motion-attestation"})
        self.assertEqual(sum(p["touch"] for p in people), 6)

    def test_rows_judge_their_events_as_raw_input_and_a_phone_as_too_little_data(self):
        rows = sessions.public_humans(datasets.motion_attestation(FIXTURE))
        self.assertEqual({r["truth"]["class"] for r in rows}, {"human"})
        touch = [r for r, p in zip(rows, datasets.motion_attestation(FIXTURE)) if p["touch"]]
        self.assertEqual({r["behaviour"] for r in touch}, {"too_little_data"})
        self.assertTrue(all(r["evidence"]["behavior"]["raw_input"] for r in rows))

    def test_the_checkout_holds_them_and_eval_finds_them(self):
        where = sources.locate({}, SETTINGS)
        self.assertEqual(where["motion_attestation"], FIXTURE)


if __name__ == "__main__":
    unittest.main()
