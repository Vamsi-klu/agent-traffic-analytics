"""GET and POST /api/settings: what the settings page shows and changes (S5.1; S5.5 draws it and adds what it needs).

GET answers Settings (web/src/data/types.ts):
    site_domain, site_key   the website's domain (as PostHog 1.0's setup page asked for its app_url) and the key its
                   page script sends; script_tag is the line a site adds to its pages with that key (site_setup.py:
                   the local page's address, or path_prefix on the site's own domain in server mode)
    sources, last_seen, route, server_half    where visits come from and when each source last sent something, where
                   the website's visits arrive, which headers the site's server never got and the last log import
                   (sources.py)
    refresh_ms     how often the open page asks again where visits come from (I3: data/api.json settings)
    lists          the date of the agent and network lists in use, how old they are, whether that is past I4 (the
                   lists come with each release, D23) and the command that updates them (detect/lists.py)
    retention_days, budget_mb, auto_free    the settings of these names (defaults.json, then the user's config.json:
                   the names cake 0.3.4 used); retention_choices from defaults.json, budget_choices_mb from
                   data/api.json, with the budget in use among them when it was set to another value
    storage        bytes used, the warning share, the days until full at last week's pace, the disk (its free space
                   against disk_min_free_mb) and why new replays are stopped, if they are (space.space_status, K2);
                   disk() is these with budget_mb and auto_free, which the dashboard's Disk bar shows too (S5.3);
                   free_to_pct, the share of the budget freeing space brings cake's data down to
                   (auto_free_target_ratio), which the page's description of auto_free states
    hook_dom, hide_selectors    the two settings of the page script, which /cake.js carries (assets.runtime_values)
    layers         the four layers that judge and whether each runs here, which are not settings (data/api.json;
                   verify runs in server mode only)
    database       where the database is (~ for the home folder) and how many sessions count (visits.py)
POST takes JSON from this computer's own pages (answers.json_object, answers.local_only) with only the fields to
change (SettingsUpdate): retention_days, budget_mb, auto_free, site_domain, hook_dom and hide_selectors, each of its
JSON type, checked as `agentcake config set` checks it (config.coerce: site_domain loses a scheme and slashes, a
selector list is one line without braces), budget_mb also one of the listed choices; they are saved to config.json.
Anything else is a 400 naming the field, and nothing is saved. The answer is the whole Settings.
"""
import datetime
from http import HTTPStatus

from agentcake import config, paths, site_setup
from agentcake.api import answers, periods, sources, visits
from agentcake.detect import lists
from agentcake.space import space_status
from agentcake.units import MS_PER_S, PERCENT

SAVED = {"retention_days": int, "budget_mb": int, "auto_free": bool, "site_domain": str, "hook_dom": bool,
         "hide_selectors": str}
KIND_NAMES = {bool: "boolean", int: "integer", str: "string"}  # how api.en.json "kinds" names a JSON type


@answers.view
def view(request):
    return answers.ok(current())


@answers.view
def save(request):
    changes = _changes(answers.json_object(request), current())
    if changes:
        config.save_user(**changes)
    return answers.ok(current())


def current():
    c, numbers, now = config.load_cfg(), answers.numbers(), periods.now_ms()
    con = visits.connect()
    try:
        storage = disk(con, c)
        where = sources.sources(con, c, now)
        sessions = visits.counts(con, visits.Scope())["all"]
    finally:
        con.close()
    budget, key = storage["budget_mb"], c.get("site_key")
    return {"site_domain": c.get("site_domain") or "", "site_key": key,
            "script_tag": site_setup.SNIPPET.format(src=site_setup.script_src(c),
                                                    site_key=key or answers.words()["script_key_placeholder"]),
            **where,
            "refresh_ms": numbers["settings"]["refresh_ms"],
            "lists": _lists(now),
            "retention_days": int(c["retention_days"]), "retention_choices": list(config.SCHEMA["retention_days"]["choices"]),
            "budget_mb": budget, "budget_choices_mb": sorted(set(numbers["budget_choices_mb"]) | {budget}),
            "auto_free": storage["auto_free"],
            "storage": {**{key: storage[key] for key in ("used_bytes", "warn_at_pct", "days_left", "disk",
                                                         "replays_stopped")},
                        "free_to_pct": round(c["auto_free_target_ratio"] * PERCENT)},
            "hook_dom": bool(c["hook_dom"]), "hide_selectors": c["hide_selectors"],
            "layers": dict(numbers["settings"]["layers"], verify=bool(c.get("public_listen"))),
            "database": {"path": paths.tilde(paths.db_file()), "sessions": sessions}}


def _lists(now_ms):
    today = datetime.datetime.fromtimestamp(now_ms / MS_PER_S, datetime.timezone.utc).date()
    status = lists.current().status(today=today)
    return {key: status[key] for key in ("built", "age_days", "max_age_days", "stale")} | {
        "update_command": answers.words()["lists_update"].format(launcher=paths.tilde(paths.launcher()))}


def disk(con, c):
    """The disk budget and what cake's data uses of it: used_bytes, budget_mb, warn_at_pct, days_left, auto_free; and
    the disk under it, against disk_min_free_mb, with why new replays are stopped, if they are (K2, D34)."""
    space = space_status(con, c)
    return {"used_bytes": space["used"],
            "budget_mb": max(1, round(float(c["budget_mb"]))),  # a test's tiny budget is a fraction of a MB
            "warn_at_pct": round(c["budget_warn_ratio"] * PERCENT), "days_left": space["days_left"],
            "auto_free": bool(c["auto_free"]), "disk": space["disk"], "replays_stopped": space["replays_stopped"]}


def _changes(update, now):
    """The settings to save from a POST body, or Refused for the first field that cannot be."""
    changes = {}
    for key, value in update.items():
        if key not in SAVED:
            raise _refused("unknown_setting", field=key)
        changes[key] = _saved(key, value, now)
    return changes


def _saved(key, value, now):
    kind = SAVED[key]
    if type(value) is not kind:  # True is an int to Python, not to JSON
        raise _refused("bad_type", field=key, kind=answers.words()["kinds"][KIND_NAMES[kind]])
    if key == "budget_mb" and value not in now["budget_choices_mb"]:
        raise _refused("bad_choice", field=key, choices=", ".join(map(str, now["budget_choices_mb"])))
    try:
        return config.coerce(key, value)
    except ValueError as problem:
        raise _refused("bad_value", problem=str(problem)) from None


def _refused(entry, **values):
    return answers.Refused(answers.error(HTTPStatus.BAD_REQUEST, entry, **values))
