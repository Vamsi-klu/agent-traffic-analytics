"""The salt of the visitors' address hashes: random, one per period of ip_salt_days, then replaced.

current(con, now_ms) gives the salt in use, and makes a new one when there is none yet or the period of the one there
has ended, or when the clock was set back more than BACKWARD_TOLERANCE_MS before that period began. It is kept in the
database's settings table (key "ip_salt": the salt and when its period began), never next
to an address: only the hashes netfacts.address_hashes() makes with it are stored. A replaced salt is gone, so the
hashes made with it can no longer be computed again from an address; requests within one period stay comparable
(the same address, the same network).

Gone means from the files as well (a privacy scan found the old salt's bytes in cake.db after a replacement): the new
salt is written with secure_delete on (the old cell is zeroed, not only unlinked) and committed at once, then the
write-ahead log is checkpointed into cake.db and emptied (TRUNCATE), so neither file keeps a copy of the old page. The
caller holds store.LOCK, asks for the salt before its transaction's first write (collect_store, log_match), and
commits its own work.

The callers take their time before they wait for store.LOCK (collect, a log import), so a time taken first can reach
the lock after a later one that started the salt: two first uploads 6 ms apart did, and the second salt made the
first upload's hashes match nothing. A time at most BACKWARD_TOLERANCE_MS before the period began keeps the salt; it
covers the longest usual wait for the lock (a delete holds it while it runs), and a wait longer still can start a
second salt as before. In exchange, each time the clock steps back by up to the tolerance, the salt outlives its
period by that step; a clock set back further starts a new salt.
"""
import secrets

from agentcake import store
from agentcake.config import load_cfg
from agentcake.datafiles import sizes
from agentcake.units import MS_PER_DAY, MS_PER_S, S_PER_HOUR

SETTING = "ip_salt"
BACKWARD_TOLERANCE_MS = S_PER_HOUR * MS_PER_S  # how far before its period a time may be and keep the salt (above)


def current(con, now_ms):
    kept = store.setting(con, SETTING)
    period_ms = load_cfg()["ip_salt_days"] * MS_PER_DAY
    if kept is None or now_ms - kept["since_ms"] >= period_ms or kept["since_ms"] - now_ms > BACKWARD_TOLERANCE_MS:
        kept = {"salt": secrets.token_hex(sizes()["random_bytes"]["ip_salt"]), "since_ms": now_ms}
        _replace(con, kept, now_ms)
    return bytes.fromhex(kept["salt"])


def _replace(con, kept, now_ms):
    """Write the new salt over the old one, commit, and leave no copy of the old one in cake.db or its log. The
    connection's own secure_delete setting is put back: the caller's writes after this are not slowed down."""
    secure_delete = con.execute("PRAGMA secure_delete").fetchone()[0]
    con.execute("PRAGMA secure_delete=ON")
    try:
        store.set_setting(con, SETTING, kept, now_ms)
        con.commit()
    finally:
        con.execute(f"PRAGMA secure_delete={secure_delete}")
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
