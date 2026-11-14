"""When a session is judged, and what is kept of its verdict (S3.4 wiring; cake 0.3.3's lazy judging folded in).

The moments are schedule.py's, on the sessions row's end_ms (newest data) and judged_ms (latest verdict):
    state(con, session_id) -> schedule.State      collect reads it before it keeps a batch
    on_data(session_id, before, now_ms, public)   after collect committed a batch: judge now, or (on a server, inside
                                                  public_judge_interval_ms) wait for the interval, a tick or an open
    tick(now_ms)                                  the maintenance round: the final verdict of sessions gone quiet,
                                                  then, with what is left of its limit, sessions an older judge judged
    on_open(session_id, now_ms=None)              a replay or a session's page is opened: judge it when its verdict
                                                  is stale, or an older judge's
    model_version()                               the version of the judge, which each verdict keeps (see below)
    catch_up(limit=None, now_ms=None)             the dashboard and the sessions list: stale sessions, latest first
    on_log_lines(session_ids, now_ms)             POST /edge kept web server log lines for these sessions (S4.4):
                                                  judge each now (a log line moves no end_ms, so no moment above
                                                  would come back for it)
    rejudge(con, session_id, now_ms=None)         judge now, in the caller's transaction
A judgement reads the session's evidence (evidence.py), runs verdict.judge() (a listed Bot and too few actions never
reach the behaviour model) and writes the sessions row (class, Agent row, name, confidence, reasons and layers as
JSON, the rest of the verdict, cake 0.3.4's columns space.py reads, and the first and last recorded action that a
session's length is made of: activity.py, S5.1; and the version of the judge), its segments (who by the verdict, who
by the behaviour model) and its labels (every name a layer found). A session whose replay was removed to free space
keeps the verdict made from it (0.3.4).

The version of the judge is a fingerprint of its code (detect/, judging.py, evidence.py) and of every data file
shipped with it (data/), as store.SCHEMA_VERSION is of the tables: nothing to raise by hand. A session an older judge
judged (cake 0.3.4's among them, which kept no version) is judged anew when it is opened, and by the maintenance round
with what is left of its limit, latest first, one transaction each: after an upgrade the sessions already kept get the
new rules and percents too (11/13), a few at a time.

Everything runs on this computer: no AI service, no network. A judgement that fails is rolled back and written to the
log (cake.log) with its traceback: the session keeps its previous verdict and is tried again at the next moment, and
the upload, the maintenance round or the page that asked goes on.
"""
import functools
import hashlib
import json
import os
import time
import traceback

from agentcake import activity, datafiles, evidence, paths, store
from agentcake.config import load_cfg
from agentcake.detect import verdict, verdict_text
from agentcake.detect.schedule import Schedule, State
from agentcake.units import MS_PER_S, PERCENT

OLD_VERDICTS = {"not_sure": "unsure", "too_little_data": "unsure"}  # 0.3.4's verdict column knew human/agent/unsure
DETAIL = ("judging", "display_name", "operator", "kind", "name_certainty", "name_method", "category", "verification",
          "impersonating", "percent")
MODEL_CODE = ("detect", "judging.py", "evidence.py")  # the judge's code, in the package folder
MODEL_DATA = "data"  # the data files shipped with it: all of them (the judge reads most, and words some columns)
OLDER_JUDGE = ("SELECT id FROM sessions WHERE judged_ms > 0 AND model_version IS NOT ? AND replay_freed_ms IS NULL "
               "AND end_ms <= ? ORDER BY end_ms DESC LIMIT ?")


def load_numbers():
    return datafiles.load("data/api.json")


def _now_ms():
    return int(time.time() * MS_PER_S)


def model_files(root):
    """The files a verdict is made from, as paths under root ("/" between folders), sorted: the judge's code and every
    data file shipped with it. Python's caches and hidden files (a Finder's .DS_Store) are not part of the judge."""
    found = []
    for part in MODEL_CODE + (MODEL_DATA,):
        top = os.path.join(root, part)
        if os.path.isfile(top):
            found.append(part)
        for folder, folders, files in os.walk(top):
            folders[:] = [name for name in folders if not name.startswith((".", "__"))]
            found += [os.path.relpath(os.path.join(folder, name), root).replace(os.sep, "/")
                      for name in files if not name.startswith(".") and not name.endswith(".pyc")]
    return sorted(found)


def fingerprint(root):
    """sha256 of model_files(root): each file's path and length, then its bytes."""
    digest = hashlib.sha256()
    for name in model_files(root):
        with open(os.path.join(root, name), "rb") as handle:
            content = handle.read()
        digest.update(f"{name}\n{len(content)}\n".encode("utf-8"))
        digest.update(content)
    return digest.hexdigest()


@functools.lru_cache(maxsize=None)
def model_version():
    """The version of the judge each verdict keeps (sessions.model_version): the fingerprint of this package's."""
    return fingerprint(paths.PACKAGE_DIR)


def _plan(c, public, now_ms):
    """The schedule from the settings, its clock fixed at now_ms."""
    return Schedule.from_settings(c, public, clock=lambda: now_ms / MS_PER_S)


def _locked(work):
    with store.LOCK:
        con = store.db()
        try:
            out = work(con)
            con.commit()
            return out
        finally:
            con.close()


def state(con, session_id):
    row = con.execute("SELECT end_ms, judged_ms FROM sessions WHERE id=?", (session_id,)).fetchone()
    return State(row[0] or 0, row[1] or 0) if row else State(0, 0)


def on_data(session_id, before, now_ms, public, c=None):
    """New data of the session was committed at now_ms; before: state() read before it was kept. Returns the
    schedule's Decision."""
    c = c or load_cfg()
    decision, _ = _plan(c, public, now_ms).on_data(before)
    if decision.judge:
        _locked(lambda con: _judge_logged(con, session_id, now_ms, c))
    return decision


def tick(now_ms, c=None, limit=None):
    """One maintenance round, at most limit (stale_judge_batch_sessions) judgements, latest first: once more the
    sessions quiet for judge_quiet_s whose verdict is not final, in one transaction; then, with what is left, the quiet
    sessions an older judge judged (cake 0.3.4's among them), one transaction each, so that uploads go on between them.
    A session whose replay was freed keeps its verdict (rejudge) and is left out. Returns how many were judged."""
    c = c or load_cfg()
    plan = _plan(c, bool(c.get("public_listen")), now_ms)
    limit = limit or c["stale_judge_batch_sessions"]

    def finals(con):
        rows = con.execute("SELECT id, end_ms, judged_ms FROM sessions WHERE (verdict_class IS NOT NULL OR "
                           "judged_ms = 0) AND judged_ms < end_ms + ? AND end_ms <= ? ORDER BY end_ms DESC LIMIT ?",
                           (plan.quiet_ms, now_ms - plan.quiet_ms, limit)).fetchall()
        due = [session_id for session_id, end_ms, judged_ms in rows
               if plan.on_tick(State(end_ms or 0, judged_ms or 0))[0].judge]
        return len(due), sum(_judge_logged(con, session_id, now_ms, c) is not None for session_id in due)
    tried, judged = _locked(finals)
    if tried >= limit:
        return judged
    older = _locked(lambda con: con.execute(OLDER_JUDGE, (model_version(), now_ms - plan.quiet_ms,
                                                          limit - tried)).fetchall())
    for (session_id,) in older:
        judged += _locked(lambda con, session_id=session_id: _judge_logged(con, session_id, now_ms, c)) is not None
    return judged


def on_open(session_id, now_ms=None, c=None):
    """A page that shows the session was opened: judge it when its verdict is stale or an older judge's (cake
    0.3.4's among them). Returns whether it was judged (None for no such session)."""
    c, now_ms = c or load_cfg(), now_ms or _now_ms()

    def work(con):
        row = con.execute("SELECT end_ms, judged_ms, model_version FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not row:
            return None
        end_ms, judged_ms, version = row
        older_judge = bool(judged_ms) and version != model_version()
        plan = _plan(c, bool(c.get("public_listen")), now_ms)
        if older_judge or plan.on_open(State(end_ms or 0, judged_ms or 0))[0].judge:
            return _judge_logged(con, session_id, now_ms, c) is not None
        return False
    return _locked(work)


def catch_up(limit=None, now_ms=None, c=None):
    """Before the dashboard or the sessions list is drawn: judge the sessions with data newer than their verdict,
    latest first, at most limit (stale_judge_batch_sessions). Returns how many were judged."""
    c, now_ms = c or load_cfg(), now_ms or _now_ms()

    def work(con):
        stale = con.execute("SELECT id FROM sessions WHERE judged_ms < end_ms ORDER BY end_ms DESC LIMIT ?",
                            (limit or c["stale_judge_batch_sessions"],)).fetchall()
        return sum(_judge_logged(con, session_id, now_ms, c) is not None for (session_id,) in stale)
    return _locked(work)


def on_log_lines(session_ids, now_ms, c=None):
    """A web server's log lines were kept for these sessions (POST /edge, S4.4): judge each one now, one transaction
    each, so uploads go on between them. A log line tells of a page request in the past and moves no session's
    end_ms: the schedule's interval and its quiet and stale rules, which all wait for newer data, would leave a final
    verdict without it. Returns how many were judged."""
    c = c or load_cfg()
    return sum(_locked(lambda con, session_id=session_id: _judge_logged(con, session_id, now_ms, c)) is not None
               for session_id in session_ids)


def _judge_logged(con, session_id, now_ms, c):
    """rejudge(), rolled back and logged when it fails (see the module docstring); returns its verdict or None."""
    con.execute("SAVEPOINT judging")
    try:
        result = rejudge(con, session_id, now_ms, c)
    except Exception:  # a session that cannot be judged must not stop collect, a page or the round: logged, retried
        con.execute("ROLLBACK TO judging")
        traceback.print_exc()
        result = None
    con.execute("RELEASE judging")
    return result


def rejudge(con, session_id, now_ms=None, c=None):
    """Judge the session now and write the verdict, in the caller's transaction; returns the verdict (None when
    the session is unknown or its replay was freed, whose verdict stands)."""
    now_ms = now_ms or _now_ms()
    row = con.execute("SELECT replay_freed_ms FROM sessions WHERE id=?", (session_id,)).fetchone()
    if row is None:
        return None
    if row[0]:  # its replay was removed to free space: the verdict made from it stands (0.3.4)
        con.execute("UPDATE sessions SET judged_ms=MAX(judged_ms, end_ms) WHERE id=?", (session_id,))
        return None
    case, raw, rrweb = evidence.session_evidence(con, session_id, c, now_ms / MS_PER_S)
    result = verdict.judge(case, raw=raw, rrweb=rrweb)
    _write(con, session_id, result, now_ms, activity.span(raw, rrweb, activity.page_starts(con, session_id)))
    return result


def _source(result):
    """cake 0.3.4's source column: the name, else Unnamed for an agent, else the verdict, as the interface words them
    (D39: where an agent runs and what kind it is are reasons, never its name)."""
    words = verdict_text.judging()
    if result["display_name"]:
        return result["display_name"]
    if result["row"]:
        return words["names"]["unnamed"]["label"]
    verdict = load_numbers()["verdicts"].get(result["class"])  # none for a prefetch, which is no visit
    return words["verdicts"][verdict]["label"] if verdict else words["layers"]["exclusion"]


def _write(con, session_id, result, now_ms, actions):
    shares = {who: round(share * PERCENT) for who, share in result["shares"].items()}
    old_segments = [{"t0": s["start"], "t1": s["end"], "who": s["who"], "n": s["n"], "p": s["p"]}
                    for s in result["segments"]]
    con.execute("UPDATE sessions SET verdict_class=?, agent_row=?, agent_name=?, confidence=?, reasons=?, layers=?, "
                "verdict_detail=?, verdict=?, human_pct=?, agent_pct=?, unsure_pct=?, source=?, group_id=?, segs=?, "
                "judged_ms=?, first_action_ms=?, last_action_ms=?, model_version=? WHERE id=?",
                (result["class"], result["row"], result["name"], result["confidence"], json.dumps(result["reasons"]),
                 json.dumps(result["layers"]), json.dumps({key: result[key] for key in DETAIL}),
                 OLD_VERDICTS.get(result["class"], result["class"]), shares["human"], shares["agent"],
                 shares["unsure"], _source(result), result["judging"], json.dumps(old_segments), now_ms, *actions,
                 model_version(), session_id))
    con.execute("DELETE FROM segments WHERE session_id=?", (session_id,))
    con.executemany("INSERT OR REPLACE INTO segments(session_id, t_start, t_end, actor, share, n_actions, model) "
                    "VALUES(?,?,?,?,?,?,?)", [(session_id, s["start"], s["end"], s["who"], s["p"], s["n"],
                                               s["model_who"]) for s in result["segments"]])
    con.execute("DELETE FROM labels WHERE session_id=?", (session_id,))
    con.executemany("INSERT OR IGNORE INTO labels(session_id, name, layer, method, certainty, evidence, judged_ms) "
                    "VALUES(?,?,?,?,?,?,?)", [(session_id, row["name"], row["layer"], row["method"], row["certainty"],
                                               json.dumps(row["evidence"]), now_ms) for row in result["candidates"]])
