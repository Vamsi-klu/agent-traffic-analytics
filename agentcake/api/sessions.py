"""GET /api/sessions?verdict=&turns=&evidence=&agent=&range=&cursor=: the session list, one page at a time (the
session list page draws it).

First the sessions with data newer than their verdict are judged (judging.catch_up); then, newest first, the sessions
that count (visits.py) with the verdict (visits.VERDICTS; none or "all" is every verdict), of an Agent session's
split `turns` (agent_only or human_agent, which narrows the list to Agent sessions), on thin `evidence` (Human sessions
cake could not tell), of the agent named exactly as agent_names lists it, in the range. A page holds data/api.json
page_size sessions; `next` is an opaque cursor for the page after it (the last row's start and id: rows added since do
not shift the pages), null on the last page; total is how many sessions every filter keeps. counts are under the agent
and range filters whatever the verdict and split; agent_names (the named agents: an agent no name fits has no name
to filter by) under the range only, so the agent filter can always be changed.
"""
import base64
import binascii
from http import HTTPStatus

from agentcake import judging
from agentcake.api import answers, periods, visits

CURSOR_SEPARATOR = ":"
BASE64_BLOCK = 4  # protocol: base64 text comes in blocks of 4 characters


@answers.view
def view(request):
    verdict = answers.choice(request, "verdict", ("all",) + visits.VERDICTS)
    turns = answers.choice(request, "turns", visits.TURNS)
    evidence = answers.choice(request, "evidence", visits.EVIDENCE)
    agent = answers.text_param(request, "agent")
    range_key = answers.choice(request, "range", tuple(answers.numbers()["range_days"]))
    after = read_cursor(answers.text_param(request, "cursor"))
    judging.catch_up()
    now, size = periods.now_ms(), answers.numbers()["page_size"]
    scope = visits.Scope().between(periods.window(range_key, now)[0])
    listed = scope.agent(agent)
    rows = listed.group(verdict).group(turns).group(evidence)
    con = visits.connect()
    try:
        results, keys = visits.page(con, rows.before(after) if after else rows, size + 1, now)
        body = {"counts": visits.counts(con, listed), "total": visits.total(con, rows),
                "agent_names": [name for name, _ in visits.agents(con, scope) if name], "results": results[:size],
                "next": cursor(keys[size - 1]) if len(results) > size else None, "page_size": size}
    finally:
        con.close()
    return answers.ok(body)


def cursor(key):
    start_ms, session_id = key
    return base64.urlsafe_b64encode(f"{start_ms}{CURSOR_SEPARATOR}{session_id}".encode()).decode().rstrip("=")


def read_cursor(text):
    """(start_ms, id) of a cursor this view gave out, None for none; Refused (400) for anything else."""
    if text is None:
        return None
    try:
        start, _, session_id = base64.urlsafe_b64decode(text + "=" * (-len(text) % BASE64_BLOCK)).decode().partition(
            CURSOR_SEPARATOR)
        if not session_id:
            raise ValueError(text)
        return int(start), session_id
    except (ValueError, binascii.Error, UnicodeDecodeError):
        raise answers.Refused(answers.error(HTTPStatus.BAD_REQUEST, "bad_cursor")) from None
