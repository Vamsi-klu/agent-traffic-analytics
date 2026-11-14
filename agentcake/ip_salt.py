"""The salt of the visitors' address hashes: random, one per period of ip_salt_days, then replaced.

current(con, now_ms) gives the salt in use, and makes a new one when there is none yet or the period of the one there
has ended. It is kept in the database's settings table (key "ip_salt": the salt and when its period began), never next
to an address: only the hashes netfacts.address_hashes() makes with it are stored. A replaced salt is gone, so the
hashes made with it can no longer be computed again from an address; requests within one period stay comparable
(the same address, the same network).

Gone means from the files as well (a privacy scan found the old salt's bytes in cake.db after a replacement): the new
salt is written with secure_delete on (the old cell is zeroed, not only unlinked) and committed at once, then the
write-ahead log is checkpointed into cake.db and emptied (TRUNCATE), so neither file keeps a copy of the old page. The
caller holds store.LOCK, asks for the salt before its transaction's first write (collect_store, log_match), and
commits its own work.
"""
import secrets

from agentcake import store
from agentcake.config import load_cfg
from agentcake.datafiles import sizes
from agentcake.units import MS_PER_DAY

SETTING = "ip_salt"


def current(con, now_ms):
    kept = store.setting(con, SETTING)
    period_ms = load_cfg()["ip_salt_days"] * MS_PER_DAY
    if kept is None or now_ms - kept["since_ms"] >= period_ms or now_ms < kept["since_ms"]:
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
