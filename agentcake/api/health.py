"""GET /api/health on the local listener, and GET /healthz on server mode's public listener.

/api/health is what `agentcake status`, `start`, `doctor`, `migrate` and `delete` ask the running cake (daemon.py),
in the fields of cake 0.3.4 but its demo shop's: version, data folder (absolute: migrate compares it), site key,
sessions (every row), real sessions (not self-checks, and not uploads from another site: site_origin.py), self-check
visits, and the disk: budget and use, the disk's free space and why new replays are stopped (space.space_status);
on a server, whether the visitor's address it reads is a CDN's own (address_check.current: doctor reads it); and
places: where visitors' countries, regions and cities come from (places.answer, with the city database in use,
geoip.status): on a server without the city database, source "missing" and the command that downloads it; and
updates: whether the lists and the city database are updated once a month, the last update and the failed runs in a
row (updates.status).
Like every /api answer it is for this computer only (answers.local_only).
/healthz answers the load balancer's health check: "ok", nothing about the data.
"""
from http import HTTPStatus

from agentcake import __version__, address_check, config, geoip, paths, store, updates
from agentcake.api import answers, places
from agentcake.responses import TEXT, Response
from agentcake.space import space_status


@answers.view
def view(request):
    c, con = config.load_cfg(), store.db()
    try:
        total, real, selfcheck = con.execute(
            "SELECT COUNT(*), SUM(is_test = 0 AND COALESCE(origin, 'site') != 'other'), SUM(is_test = 1) "
            "FROM sessions").fetchone()
        space = space_status(con, c)
        checked = address_check.current(con, c)
    finally:
        con.close()
    return answers.ok({"ok": True, "version": __version__, "home": paths.home(), "site_key": c.get("site_key"),
                       "sessions": total, "real_sessions": real or 0, "selfcheck_visits": selfcheck or 0,
                       "space": space, "address_check": checked,
                       "places": dict(places.answer(c), update_command=places.update_command(),
                                      database=geoip.status()),
                       "updates": updates.status(c)})


def healthz(request):
    return Response(HTTPStatus.OK, "ok", TEXT)
