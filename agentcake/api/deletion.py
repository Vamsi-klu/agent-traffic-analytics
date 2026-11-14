"""POST /api/delete {"sessions": ["<id>", ...]}: deletes those visits in this process (delete.py) and answers
what was deleted, as delete.delete_sessions() returns it; `agentcake delete` uses it while cake runs. {"all": true} is
the settings page's "Delete all data" (after its Dialog): every session in the database, each as thoroughly
as one; with none left it answers {"sessions": []}. Only the local listener has it (routes.py), and only this
computer's own pages, or a program on this computer such as `agentcake delete` (no Origin), may post its JSON
(answers.local_only, answers.json_object). Moved here from agentcake/api.py when each resource of the API got its
own module.
"""
import sqlite3
from http import HTTPStatus

from agentcake import delete, store
from agentcake.api import answers
from agentcake.wording import text


@answers.view
def view(request):
    ids = _named(answers.json_object(request))
    if ids is None:
        return answers.error_text(HTTPStatus.BAD_REQUEST, text("delete_api_bad_body"))
    if not ids:
        return answers.ok({"sessions": []})
    try:
        result = delete.delete_sessions(ids)
    except delete.WipeRefused as e:
        return answers.error_text(HTTPStatus.CONFLICT, str(e))
    except (OSError, sqlite3.Error) as e:
        return answers.error_text(HTTPStatus.INTERNAL_SERVER_ERROR, str(e))
    return answers.ok(result)


def _named(body):
    """The session ids a body names: its list, or every session's for {"all": true}; None for anything else."""
    if "all" in body:
        return _every_session() if body == {"all": True} else None
    ids = body.get("sessions")
    return ids if isinstance(ids, list) and ids and all(delete.valid_id(i) for i in ids) else None


def _every_session():
    con = store.db()
    try:
        return [sid for (sid,) in con.execute("SELECT id FROM sessions ORDER BY start_ms") if delete.valid_id(sid)]
    finally:
        con.close()
