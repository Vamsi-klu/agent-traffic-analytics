"""The behaviour layer as the verdict step runs it (agentcake.detect.behavior, plan step S3.4).

    python3 -I -m unittest discover -s tests -v      (from the repository root)

It counts the action segments before anything else: a phone or tablet, or fewer actions than the model's minimum
(behavior_model.json), gives "too little data" without calling the model. Otherwise it returns the model's own result
(S3.7's judge_session). An rrweb-only recording is rebuilt into raw events and read as such (raw_input False). It also
reads assistive-tool signs: keyboard navigation (cake.js sends a key's class, never the key) without a pointer.
"""
import os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import synthetic_sessions  # noqa: E402  (made up by rule: no recording)
from agentcake.detect import behavior, model  # noqa: E402

T0 = 1_794_500_000_000


def never(*args, **kwargs):
    raise AssertionError("the behaviour model was called")


def keys(kind, n, gap_ms=600):
    return [{"t": T0 + i * gap_ms, "ty": "keydown", "kc": kind, "tr": 1} for i in range(n)]


class Run(unittest.TestCase):
    def test_too_few_actions_do_not_call_the_model(self):
        one_click = [{"t": T0, "ty": "mousemove", "cx": 5, "cy": 5, "tr": 1},
                     {"t": T0 + 400, "ty": "click", "cx": 5, "cy": 5, "tr": 1}]
        result = behavior.run(raw=one_click, model=never)
        self.assertEqual((result["verdict"], result["evidence"], result["n_actions"]),
                         ("too_little_data", {"reason": "few_actions"}, 1))
        self.assertIsNone(result["timeline"])

    def test_phone_or_tablet_does_not_call_the_model(self):
        result = behavior.run(raw=synthetic_sessions.agent_raw(), touch=True, model=never)
        self.assertEqual((result["verdict"], result["evidence"]), ("too_little_data", {"reason": "touch"}))

    def test_no_events_at_all_is_too_little_data(self):
        self.assertEqual(behavior.run(model=never)["verdict"], "too_little_data")

    def test_enough_actions_return_the_models_own_result(self):
        raw = synthetic_sessions.agent_raw()
        self.assertEqual(behavior.run(raw=raw), model.judge_session(raw))

    def test_minimum_comes_from_the_model_parameters(self):
        raw = synthetic_sessions.agent_raw()
        params = dict(model.load_params(), min_actions=10_000)
        self.assertEqual(behavior.run(raw=raw, params=params, model=never)["verdict"], "too_little_data")

    def test_rrweb_only_recording_is_read_without_raw_input(self):
        seen = {}

        def spy(events, raw_input=True, **kwargs):
            seen.update(raw_input=raw_input, n=len(events))
            return model.judge_session(events, raw_input=raw_input, **kwargs)
        result = behavior.run(rrweb=synthetic_sessions.agent_rrweb(), model=spy)
        self.assertEqual((seen["raw_input"], result["raw_input"]), (False, False))
        self.assertGreater(seen["n"], 0)


class AssistiveSigns(unittest.TestCase):
    def test_keyboard_navigation_without_a_pointer(self):
        self.assertEqual(behavior.assistive_signs(keys("tab", 6) + keys("arrow", 4)), {"keys": 10, "pointer_moves": 0})

    def test_a_pointer_or_few_navigation_keys_are_no_sign(self):
        moving = keys("tab", 10) + [{"t": T0 + 50, "ty": "mousemove", "cx": 1, "cy": 1, "tr": 1}]
        self.assertIsNone(behavior.assistive_signs(moving))
        self.assertIsNone(behavior.assistive_signs(keys("tab", 2)))
        self.assertIsNone(behavior.assistive_signs(keys("letter", 30)))

    def test_a_made_up_automated_browser_shows_no_sign(self):
        self.assertIsNone(behavior.assistive_signs(synthetic_sessions.agent_raw()))


if __name__ == "__main__":
    unittest.main()
