"""Background upkeep of the replay chunks: `serve` starts it in a daemon thread with start().

Every maintenance_tick_ms a round seals the windows that went quiet (streams.seal), so a finished visit is compressed
within seal_idle_ms of its last batch. Every maintenance_recompress_every_ms the round also checks whether it is a
good time for the heavy night work, and then recompresses old sessions and reclaims space (recompress.py): at night
(recompress_night_hours, local time; the end hour is excluded and the range may wrap past midnight), on AC power when
recompress_require_ac_power (macOS: pmset; Linux: /sys/class/power_supply; a machine without a battery, such as a
server, counts as on AC power), with the load per CPU under recompress_max_load_per_cpu, and no batch received for
recompress_quiet_ms (sessions.end_ms, open windows). Chunks dropped to free space or by a retention give their file
space back at the next round, by day as well (space.reclaim_if_due): on a server that is never quiet at night
the bytes would otherwise never come back.

Each round also places in visits, for visit_upgrade_round_ms at most, the tab sessions an AgentCake older than 0.6.2
recorded (visit_upgrade.py: after a backup, until none is left), gives the sessions that went quiet their final
verdict (judging.tick: judge_quiet_s) and, with what is left of its limit, judges anew the sessions an older judge
judged (after an upgrade, a few each round).

Upkeep.tick(now_ms) is one round; the tests call it with a clock and replaced probes, so nothing sleeps.
"""
import os
import subprocess
import sys
import threading
import time
import traceback
from datetime import timedelta

from agentcake import judging, recompress, space, store, streams, visit_upgrade
from agentcake.config import load_cfg
from agentcake.storage_config import SETTINGS, now_ms as clock_ms, when

POWER_SUPPLIES = "/sys/class/power_supply"


def is_night(now_ms, cfg=SETTINGS):
    start, end = cfg["recompress_night_hours"]
    hour = when(now_ms).astimezone().hour
    return start <= hour < end if start <= end else hour >= start or hour < end


def pmset_on_ac(text):
    """macOS `pmset -g batt` output: on AC power unless it says the battery is the source."""
    return "'Battery Power'" not in text


def sysfs_on_ac(root=POWER_SUPPLIES):
    """Linux: on AC power when a mains or USB supply is online, or when there is no battery at all."""
    if not os.path.isdir(root):
        return True
    kinds, online = [], []
    for name in os.listdir(root):
        kind = _read(os.path.join(root, name, "type"))
        kinds.append(kind)
        if kind in ("Mains", "USB"):
            online.append(_read(os.path.join(root, name, "online")) == "1")
    return "Battery" not in kinds or any(online)


class Probes:
    """The machine's power source and load; the tests replace them."""

    def __init__(self, cfg=SETTINGS):
        self.timeout_s = timedelta(milliseconds=cfg["power_probe_timeout_ms"]).total_seconds()

    def on_ac_power(self):
        if sys.platform == "darwin":
            try:
                out = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=self.timeout_s)
            except (OSError, subprocess.SubprocessError):
                return True  # no pmset to ask: assume a plugged-in machine, as on a server
            return pmset_on_ac(out.stdout)
        return sysfs_on_ac()

    def load_per_cpu(self):
        if not hasattr(os, "getloadavg"):
            return 0.0
        return os.getloadavg()[0] / (os.cpu_count() or 1)


class Upkeep:
    def __init__(self, cfg=SETTINGS, probes=None):
        self.cfg, self.probes = cfg, probes or Probes(cfg)
        self.next_heavy_ms = None

    def heavy_due(self, now_ms):
        return self.next_heavy_ms is None or now_ms >= self.next_heavy_ms

    def tick(self, now_ms):
        """One round: seal quiet windows and give back the space of dropped chunks; at most every
        maintenance_recompress_every_ms, the night work if it is time."""
        with store.LOCK:
            con = store.db()
            try:
                quiet = self._quiet(con, now_ms)  # read before sealing: sealing removes the open windows it looks at
                streams.seal(con, now_ms, cfg=self.cfg)
                con.commit()
                space.reclaim_if_due(con, now_ms, self.cfg)
            finally:
                con.close()
        budget = timedelta(milliseconds=load_cfg()["visit_upgrade_round_ms"]) / timedelta(seconds=1)
        try:
            visit_upgrade.step(now_ms, deadline=time.monotonic() + budget)
        except Exception:  # the upgrade tries again next round; judging and the night work must not wait for it
            traceback.print_exc()
        judging.tick(now_ms)
        if not self.heavy_due(now_ms):
            return
        self.next_heavy_ms = now_ms + self.cfg["maintenance_recompress_every_ms"]
        if quiet and is_night(now_ms, self.cfg) and self._plugged_in_and_idle():
            recompress.run(now_ms, self.cfg)
            with store.LOCK:
                con = store.db()
                try:
                    recompress.reclaim(con, now_ms, self.cfg)
                finally:
                    con.close()

    def _plugged_in_and_idle(self):
        if self.cfg["recompress_require_ac_power"] and not self.probes.on_ac_power():
            return False
        return self.probes.load_per_cpu() < self.cfg["recompress_max_load_per_cpu"]

    def _quiet(self, con, now_ms):
        latest = con.execute("SELECT MAX(t) FROM (SELECT MAX(end_ms) AS t FROM sessions "
                             "UNION ALL SELECT MAX(updated_ms) FROM open_chunks)").fetchone()[0]
        return latest is None or now_ms - latest >= self.cfg["recompress_quiet_ms"]


def start(cfg=SETTINGS):
    """Run Upkeep rounds every maintenance_tick_ms in a daemon thread (it ends with the process)."""
    upkeep, stop = Upkeep(cfg), threading.Event()

    def loop():
        while not stop.wait(timedelta(milliseconds=cfg["maintenance_tick_ms"]) / timedelta(seconds=1)):
            try:
                upkeep.tick(clock_ms())
            except Exception:  # a failed round must not end the thread: it goes to cake.log and the next round tries
                traceback.print_exc()

    threading.Thread(target=loop, name="cake-upkeep", daemon=True).start()
    return stop


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""
