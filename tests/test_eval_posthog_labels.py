"""How `agentcake eval` reads the answers of S9.2's PostHog training set (plan step S3.7, D36).

    python3 -I -m unittest discover -s tests -v

The training set gives each unit its truth and how it is known (truth_strength), whether it is the site owner's
(owner), the person it is held out with (holdout) and whether the user has yet to confirm its label (pending). The
site owner's presumed humans and pending labels are weak answers: listed in their own groups, never pooled or fitted.
S1.5's dataset, which has none of these fields, is read as before.
"""
import os
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(TESTS), TESTS]

from agentcake import datafiles  # noqa: E402
from agentcake.evaluation import behaviour, calibration, tables  # noqa: E402

SETTINGS = datafiles.load("data/eval.json")
GROUPS = SETTINGS["posthog"]


def unit(label, truth=None, strength=None, owner=False, pending=False, group=None, reason="", unit_id="u:x"):
    out = {"label": label, "group": group, "reason": reason, "unit_id": unit_id, "owner": owner, "pending": pending}
    if truth is not None:
        out.update(truth=truth, truth_strength=strength)
    return out


def read(u):
    group = behaviour.posthog_group(u, GROUPS)
    return group, tables.posthog_truth(u, group, SETTINGS)


class TrainingSetTest(unittest.TestCase):
    def test_the_users_labels_are_a_group_of_their_own(self):
        self.assertEqual(read(unit("probably-human", "human", "user", owner=True, group="owner")),
                         ("user-labelled", {"class": "human"}))
        self.assertEqual(read(unit("agent", "agent", "user", group="other-agent")), ("user-labelled", {"class": "agent"}))

    def test_the_site_owners_presumed_humans_are_weak(self):
        for strength in ("presumed", "presumed+cake"):
            self.assertEqual(read(unit("probably-human", "human", strength, owner=True, group="owner")),
                             ("owner-presumed", {"class": "human", "weak": True}))

    def test_visitors_presumed_human_count(self):
        self.assertEqual(read(unit("probably-human", "human", "presumed", group="visitor")),
                         ("visitor", {"class": "human"}))

    def test_a_pending_label_is_weak_and_apart(self):
        self.assertEqual(read(unit("agent", "agent", "user", pending=True, group="other-agent")),
                         ("pending", {"class": "agent", "weak": True}))

    def test_a_hard_agent_keeps_its_datasets_group(self):
        self.assertEqual(read(unit("agent", "agent", "hard", group="claude-chrome")),
                         ("claude-chrome", {"class": "agent"}))

    def test_unknown_or_mixed_truth_is_no_answer(self):
        self.assertEqual(read(unit("unknown", "unknown", "none"))[1], {})

    def test_s15s_units_are_read_by_group_as_before(self):
        self.assertEqual(read(unit("probably-human", group="owner")), ("owner", {"class": "human"}))
        self.assertEqual(read(unit("agent", reason="agent window")), ("claude-chrome", {"class": "agent"}))


class HoldoutTest(unittest.TestCase):
    def test_a_session_is_held_out_with_its_person_where_the_data_set_names_one(self):
        self.assertEqual(calibration._fold({"source": "posthog", "holdout": "owner"}), "posthog / owner")
        self.assertEqual(calibration._fold({"source": "public_humans", "holdout": None}), "public_humans")


if __name__ == "__main__":
    unittest.main()
