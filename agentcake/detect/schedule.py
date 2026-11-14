"""When a session is judged (S3.4): on new data, once more when it has been quiet, again when an opened page shows it.

The rule (EXECUTION-BRIEF S3.4, with 0.3.3's server-mode rule folded in; the interface explains it from
judging.en.json "when_model_runs"):
  - new data: judge now, but a session that keeps sending at most every interval_ms (on a server
    public_judge_interval_ms, 0.3.3's 15 s; on this computer judge_interval_ms: a judgement reads the whole session,
    so judging every batch as cake 0.3.4 did would grow with its length);
  - quiet: once a session has sent nothing for quiet_ms (judge_quiet_s), judge it once more; that verdict is final;
  - reopened: new data after the final verdict opens the session again and is judged like any new data;
  - opened: a replay or dashboard page that shows a session judges it when it has data its last verdict did not see,
    whatever the interval (0.3.3's catching up before a page is drawn).
What runs in a judgement is verdict.judge(), all on this computer: the behaviour model is skipped for a Bot known by
name and for too few actions (behavior.run), and nothing calls an AI service or the network.

    Schedule(quiet_ms, interval_ms=0, clock=time.time)      Schedule.from_settings(settings, public)
    .on_data(state) / .on_tick(state) / .on_open(state) -> (Decision, State after it)
    .is_final(state), .stale(state)

State is what the sessions table already keeps: last_data_ms (end_ms, when the newest data arrived) and judged_ms
(when it was last judged, 0 before the first time). A verdict is final when it was made at least quiet_ms after the
newest data, so no column is needed for it and new data undoes it by itself. The clock is injected (seconds, like
time.time) so that tests move it by hand. The caller judges when Decision.judge is true, then stores the new State.
"""
import time
from dataclasses import dataclass

from agentcake.units import MS_PER_S


@dataclass(frozen=True)
class State:
    last_data_ms: int
    judged_ms: int = 0


@dataclass(frozen=True)
class Decision:
    """judge: run a judgement now; final: that judgement is the session's final one; why: new_data, reopened,
    waiting (inside the interval), quiet, opened, up_to_date or not_quiet."""

    judge: bool
    final: bool
    why: str


class Schedule:
    def __init__(self, quiet_ms, interval_ms=0, clock=time.time):
        self.quiet_ms, self.interval_ms, self.clock = quiet_ms, interval_ms, clock

    @classmethod
    def from_settings(cls, settings, public, clock=time.time):
        """From the settings (config.load_cfg()): judge_quiet_s, and public_judge_interval_ms on the public listener
        or judge_interval_ms on this computer's."""
        interval = settings["public_judge_interval_ms"] if public else settings["judge_interval_ms"]
        return cls(settings["judge_quiet_s"] * MS_PER_S, interval, clock)

    def now_ms(self):
        return int(self.clock() * MS_PER_S)

    def is_final(self, state):
        return bool(state.judged_ms) and state.judged_ms - state.last_data_ms >= self.quiet_ms

    def stale(self, state):
        """Its last verdict did not see its newest data."""
        return state.judged_ms < state.last_data_ms

    def _judged(self, state, now, why):
        final = now - state.last_data_ms >= self.quiet_ms
        return Decision(True, final, why), State(state.last_data_ms, now)

    def on_data(self, state):
        """New data arrived now; state: the session before it arrived."""
        now = self.now_ms()
        arrived = State(now, state.judged_ms)
        if self.interval_ms and state.judged_ms and now - state.judged_ms < self.interval_ms:
            return Decision(False, False, "waiting"), arrived
        return self._judged(arrived, now, "reopened" if self.is_final(state) else "new_data")

    def on_tick(self, state):
        """The periodic check: a session quiet for quiet_ms whose verdict is not final yet is judged once more."""
        now = self.now_ms()
        if self.is_final(state):
            return Decision(False, True, "up_to_date"), state
        if now - state.last_data_ms < self.quiet_ms:
            return Decision(False, False, "not_quiet"), state
        return self._judged(state, now, "quiet")

    def on_open(self, state):
        """A page that shows the session was opened: catch up when it has data its verdict did not see."""
        if not self.stale(state):
            return Decision(False, self.is_final(state), "up_to_date"), state
        return self._judged(state, self.now_ms(), "opened")
