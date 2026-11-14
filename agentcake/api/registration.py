"""GET and POST /api/register: the local dashboard's registration card (the sending is agentcake/register.py).

GET answers Registration (web/src/data/types.ts): whether this data folder has registered (until it has, the pages
show the card before anything else), what it sent and when (the settings page shows it), the rules the card checks
before its button turns on (the ones register.payload() checks), and where to write to have a registration deleted.

POST is the press of "Register & Continue", from this computer's own pages only (answers.view, answers.json_object),
its body the JSON the card's "See what is sent" showed:
    409   this data folder has registered already, or another press is being sent right now
    400   a body the page does not write (register.payload says what is wrong); nothing is sent
    503   register_url is empty; nothing is sent, no connection is opened
    502   it could not be sent, or the receiver did not take it (register.send says why); nothing is kept
    200   the receiver took it: what was sent is kept (register.keep) and the answer is the new Registration
Nothing is tried again and nothing waits in a queue: the card says what happened and asks again next time. Only the
local listener has these routes (routes.py), like POST /api/delete.
"""
import threading
from http import HTTPStatus

from agentcake import register, store
from agentcake.api import answers, periods
from agentcake.config import load_cfg

SENDING = threading.Lock()  # one registration on its way at a time, however many tabs press


@answers.view
def view(request):
    con = store.db()
    try:
        return answers.ok(current(con))
    finally:
        con.close()


@answers.view
def press(request):
    answers.json_object(request)  # 415 unless JSON, 400 unless one JSON object
    if not SENDING.acquire(blocking=False):
        return answers.error(HTTPStatus.CONFLICT, "register_busy")
    try:
        return _send(request.body)
    finally:
        SENDING.release()


def _send(body):
    con = store.db()
    try:
        if register.kept(con):
            return answers.error(HTTPStatus.CONFLICT, "register_already")
        try:
            text = register.payload(body)
        except register.Invalid as invalid:
            return answers.error(HTTPStatus.BAD_REQUEST, invalid.entry, **invalid.values)
        url = load_cfg()["register_url"]
        if not url:
            return answers.error(HTTPStatus.SERVICE_UNAVAILABLE, "register_no_address")
        try:
            register.send(text, url)
        except register.NotSent as failed:
            return answers.error(HTTPStatus.BAD_GATEWAY, failed.entry, **failed.values)
        register.keep(con, text, periods.now_ms())
        return answers.ok(current(con))
    finally:
        con.close()


def current(con):
    rules, sent = register.rules(), register.kept(con)
    return {"registered": sent is not None,
            "sent": {"body": sent["body"], "when": periods.when(sent["sent_ms"], periods.now_ms())} if sent else None,
            "email_pattern": rules["email_pattern"], "email_max_chars": rules["email_max_chars"],
            "company_max_chars": rules["company_max_chars"], "delete_contact": rules["delete_contact"]}
