"""When a session is judged (agentcake.detect.schedule, plan step S3.4), on an injected clock: nothing sleeps.

    python3 -I -m unittest discover -s tests -v      (from the repository root)

EXECUTION-BRIEF S3.4: a batch arrives -> judged once; quiet for the configured time -> judged once more and final;
new data after that -> opened again and judged; on a server a sending session is judged at most every
public_judge_interval_ms, and opening a replay with new data catches up; a Bot known by name and a session with too
few actions never reach the behaviour model; and the whole run opens no socket.
"""
import os, socket, sys, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import synthetic_sessions  # noqa: E402  (made up by rule: no recording)
from verdict_cases import T0, UPTIMEROBOT, evidence  # noqa: E402
from agentcake import config  # noqa: E402
from agentcake.detect import model, schedule, verdict  # noqa: E402

QUIET_S, INTERVAL_MS = 60, 15000
MS = 1000


class Clock:
    """time.time() for the schedule, moved by hand."""

    def __init__(self, ms):
        self.ms = ms

    def __call__(self):
        return self.ms / MS

    def advance(self, seconds):
        self.ms += int(seconds * MS)


def server_schedule(clock):
    return schedule.Schedule(quiet_ms=QUIET_S * MS, interval_ms=INTERVAL_MS, clock=clock)


class Settings(unittest.TestCase):
    def test_quiet_time_and_interval_come_from_the_settings(self):
        with mock.patch.dict(config.DEFAULTS, {"judge_quiet_s": 90, "public_judge_interval_ms": 5000,
                                               "judge_interval_ms": 2000}):
            on_server = schedule.Schedule.from_settings(config.load_cfg(), public=True)
            on_laptop = schedule.Schedule.from_settings(config.load_cfg(), public=False)
        self.assertEqual((on_server.quiet_ms, on_server.interval_ms), (90 * MS, 5000))
        self.assertEqual((on_laptop.quiet_ms, on_laptop.interval_ms), (90 * MS, 2000))

    def test_the_settings_are_in_defaults(self):
        for key in ("judge_quiet_s", "public_judge_interval_ms", "judge_interval_ms"):
            self.assertIn(key, config.SCHEMA)


class WhenToJudge(unittest.TestCase):
    def setUp(self):
        self.clock = Clock(T0)
        self.plan = server_schedule(self.clock)

    def test_a_batch_is_judged_once(self):
        decision, state = self.plan.on_data(schedule.State(last_data_ms=0, judged_ms=0))
        self.assertEqual((decision.judge, decision.final, decision.why), (True, False, "new_data"))
        self.assertEqual(state, schedule.State(last_data_ms=T0, judged_ms=T0))
        self.assertEqual(self.plan.on_open(state)[0].judge, False)

    def test_quiet_session_is_judged_once_more_and_then_final(self):
        _, state = self.plan.on_data(schedule.State(0, 0))
        self.clock.advance(QUIET_S - 1)
        self.assertFalse(self.plan.on_tick(state)[0].judge)
        self.clock.advance(1)
        decision, state = self.plan.on_tick(state)
        self.assertEqual((decision.judge, decision.final, decision.why), (True, True, "quiet"))
        self.assertTrue(self.plan.is_final(state))
        self.clock.advance(QUIET_S)
        self.assertFalse(self.plan.on_tick(state)[0].judge)

    def test_new_data_after_the_final_verdict_opens_it_again(self):
        _, state = self.plan.on_data(schedule.State(0, 0))
        self.clock.advance(QUIET_S)
        _, state = self.plan.on_tick(state)
        self.clock.advance(300)
        decision, state = self.plan.on_data(state)
        self.assertEqual((decision.judge, decision.final, decision.why), (True, False, "reopened"))
        self.assertFalse(self.plan.is_final(state))

    def test_on_a_server_new_data_waits_for_the_interval_and_opening_catches_up(self):
        _, state = self.plan.on_data(schedule.State(0, 0))
        self.clock.advance(INTERVAL_MS / MS / 3)
        decision, state = self.plan.on_data(state)
        self.assertEqual((decision.judge, decision.why), (False, "waiting"))
        self.assertTrue(self.plan.stale(state))
        decision, state = self.plan.on_open(state)
        self.assertEqual((decision.judge, decision.why), (True, "opened"))
        self.assertEqual(self.plan.on_open(state)[0].why, "up_to_date")
        self.clock.advance(INTERVAL_MS / MS)
        self.assertEqual(self.plan.on_data(state)[0].why, "new_data")

    def test_opening_a_quiet_stale_session_gives_the_final_verdict(self):
        _, state = self.plan.on_data(schedule.State(0, 0))
        self.clock.advance(1)
        _, state = self.plan.on_data(state)  # waiting: inside the interval
        self.clock.advance(QUIET_S)
        decision, state = self.plan.on_open(state)
        self.assertEqual((decision.judge, decision.final), (True, True))

    def test_on_this_computer_every_batch_is_judged(self):
        plan = schedule.Schedule(quiet_ms=QUIET_S * MS, interval_ms=0, clock=self.clock)
        _, state = plan.on_data(schedule.State(0, 0))
        self.clock.advance(1)
        self.assertEqual(plan.on_data(state)[0].judge, True)


class Counting:
    """The behaviour model, counted."""

    def __init__(self):
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        return model.judge_session(*args, **kwargs)


def refuse(*args, **kwargs):
    raise AssertionError("judging tried to use the network")


class WholeRun(unittest.TestCase):
    """Batches, quiet, reopening and an opened replay, judged through verdict.judge with sockets refused."""

    def drive(self, case, raw):
        clock, counting = Clock(T0), Counting()
        plan = server_schedule(clock)
        state, results = schedule.State(0, 0), []

        def step(decision_state):
            nonlocal state
            decision, state = decision_state
            if decision.judge:
                results.append(verdict.judge(case, raw=raw, model=counting))

        with mock.patch.object(socket, "socket", refuse), mock.patch.object(socket, "create_connection", refuse), \
                mock.patch.object(socket, "getaddrinfo", refuse):
            step(plan.on_data(state))
            clock.advance(5)
            step(plan.on_data(state))  # inside the interval: waits
            step(plan.on_open(state))  # the replay is opened: catches up
            clock.advance(QUIET_S)
            step(plan.on_tick(state))  # quiet: final
            clock.advance(600)
            step(plan.on_data(state))  # reopened
        return results, counting.calls

    def test_agent_session_is_judged_four_times_on_this_computer(self):
        results, calls = self.drive(evidence(), synthetic_sessions.agent_raw())
        self.assertEqual((len(results), calls), (4, 4))
        self.assertEqual({r["class"] for r in results}, {"agent"})

    def test_bot_known_by_name_never_reaches_the_model(self):
        results, calls = self.drive(evidence(uas=UPTIMEROBOT), synthetic_sessions.agent_raw())
        self.assertEqual((len(results), calls), (4, 0))
        self.assertEqual({r["class"] for r in results}, {"bot"})

    def test_too_few_actions_never_reach_the_model(self):
        one_click = [{"t": T0, "ty": "mousemove", "cx": 5, "cy": 5, "tr": 1},
                     {"t": T0 + 400, "ty": "click", "cx": 5, "cy": 5, "tr": 1}]
        results, calls = self.drive(evidence(), one_click)
        self.assertEqual((len(results), calls), (4, 0))
        self.assertEqual({r["class"] for r in results}, {"too_little_data"})


if __name__ == "__main__":
    unittest.main()
