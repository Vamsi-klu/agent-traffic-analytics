"""The JSON API the local pages read (S5.1), one module per resource like PostHog 1.0's posthog/api/<resource>.py.

The compiled pages (web/dist, served by assets.py) hold no data: each asks for JSON under /api, in the shapes of the
contract in web/src/data/ (types.ts, schema/, fixtures/; the tests check every answer against schema/ with
tests/json_schema.py). Keys are snake_case, times inside a session are whole ms from its start, wall-clock times come
in words, and every answer that is not 2xx is {"error": "<a sentence the page can show>"}. Only the local listener
(127.0.0.1) serves /api, and only to this computer's own pages (answers.local_only).

    overview.py     GET /api/overview?source=&range=                          the dashboard
    sessions.py     GET /api/sessions?verdict=&agent=&source=&range=&cursor=  the session list, one page at a time
    session.py      GET /api/session/<id>                                     one session: verdict, timeline, reasons
                    GET /api/session/<id>/replay?chunk=<n>                    one chunk of its replay (replay.py)
    settings.py     GET and POST /api/settings
    onboarding.py   GET /api/setup                                            the home page's ways to connect
    registration.py GET and POST /api/register                                the registration card (S5.8)
    health.py       GET /api/health (doctor, status), GET /healthz (the public listener's health check)
    visits.py       which sessions count, the filters, and each session as the lists show it
    reasons.py, actions.py, replay.py, server_half.py    the parts of one session's answer
    coverage.py     the dashboard's note on what is recorded and how it is decided
    periods.py      the date ranges, and wall-clock times in words
    answers.py      JSON answers, error bodies, and who may ask
"""
