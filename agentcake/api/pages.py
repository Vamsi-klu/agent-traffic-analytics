"""The pages of a session in the order they opened (the replay page's pages section, under "Who acted, when": which
pages the session went to, the page it came in on and the page it left from).

PostHog's session list named each session's start point and end point, and its replay lists the session's events in
time order beside the player; this does the same for pages. A page opens when a page view begins: cake.js's page record
(the "Open" of actions.py), or an rrweb Meta event in a cake 0.3.x recording; a page view whose record never arrived
begins at its first action or its first batch, whichever came first. A single-page app changes the address without a
new page view, and cake.js writes the page's address on every batch it sends (batches.url: path and query, never the
fragment), so a new address is a new page from the first batch that carries it, at the time cake.js made that batch.
A session with nothing to go by (a cake 0.3.4 visit) has one page: its own address, from its start.

A page lasts until the next one opens, the last one until the session's end (the timeline's length). Its actions are
the visitor's input on it (All actions without the "Open" rows): an action belongs to the page of its own page view
open at that moment (before the view's first page: that page); an action without a page view, to the page open at
that moment. Who acted on a page is named as the session categories are: a human only, an agent only, both a
human and an agent (Human + agent), or unknown when all its actions are; a page without actions names nobody (None:
the page shows a dash, as no one acted on it).

    views(con, session_id) -> {page view: [Address]}   each page view's address and its later ones, oldest first; None:
                                                       the session's own address (cake 0.3.4)
    Visit(views, found, epoch)                         found: actions.recorded()
        .path_of(action)                               the address of the page an action was taken on
        .listed(length) -> [SessionPage]               the answer's "pages", in the order they opened
"""
from collections import namedtuple

from agentcake.api import visits

# An address of a page view: when cake.js first sent it (epoch ms on the events' clock; None when no batch says) and its
# path and query.
Address = namedtuple("Address", "t path")
# A page: when it opened (epoch ms), its address, and its page view (cake.js's pv; a 0.3.x Meta event's href; None for
# the session's own address).
Page = namedtuple("Page", "t path view")
OPEN = "open"  # the kind of the action that opens a page (actions.py)
HUMAN, AGENT, UNSURE = "human", "agent", "unsure"  # who took an action (a segment's actor)
HUMAN_AGENT, UNKNOWN = "human_agent", "unknown"  # who acted on a page, as the session categories name it


def views(con, session_id):
    """{page view: [Address]}: the address of each page view's first batch, then each address that differs from the
    batch before it, in the order cake.js numbered them; None: the session's own address."""
    rows = con.execute("SELECT pv, t, url FROM batches WHERE session_id=? AND url IS NOT NULL ORDER BY pv, seq",
                       (session_id,))
    out = {pv: [Address(*address) for address in history] for pv, history in visits.addresses(rows).items()}
    url = con.execute("SELECT url FROM sessions WHERE id=?", (session_id,)).fetchone()[0]
    out[None] = [Address(None, visits.page_path(url) if url else "/")]
    return out


class Visit:
    """The pages of one session and the page each of its actions was taken on."""

    def __init__(self, views, found, epoch):
        self.found, self.epoch = found, epoch
        self.pages = _opened(views, found) or [Page(epoch, views[None][0].path, None)]
        self._of_view = {}
        for index, opened in enumerate(self.pages):
            self._of_view.setdefault(opened.view, []).append(index)

    def page_of(self, action):
        """The index of the page an action was taken on (see the module docstring)."""
        indexes = self._of_view.get(action.view) or range(len(self.pages))
        found = indexes[0]
        for index in indexes:
            if self.pages[index].t <= action.t:
                found = index
        return found

    def path_of(self, action):
        return self.pages[self.page_of(action)].path

    def listed(self, length):
        """The answer's pages: path, when it opened and how long the visit stayed (ms inside 0 … length), its actions
        and who acted on it."""
        taken = [[] for _ in self.pages]
        for action in self.found:
            if action.kind != OPEN:
                taken[self.page_of(action)].append(action.who)
        opened = [min(length, max(0, round(page.t - self.epoch))) for page in self.pages]
        ends = opened[1:] + [length]
        return [{"path": page.path, "at_ms": at, "duration_ms": max(0, end - at), "actions": len(who), "who": named(who)}
                for page, at, end, who in zip(self.pages, opened, ends, taken)]


def named(actors):
    """Who acted, named as the session categories name it: both a human and an agent, human_agent; else whichever
    of them did; else unknown; None when nobody acted."""
    found = set(actors)
    if not found:
        return None
    if HUMAN in found and AGENT in found:
        return HUMAN_AGENT
    return next((who for who in (AGENT, HUMAN) if who in found), UNKNOWN)


def _opened(views, found):
    """The pages in the order they opened: one per Open action, one for each page view that has an address but no
    Open (from its first action or batch), and one for each later address of a page view."""
    pages = [Page(action.t, (views.get(action.view) or views[None])[0].path, action.view)
             for action in found if action.kind == OPEN]
    with_open = {action.view for action in found if action.kind == OPEN}
    first_action = {}
    for action in found:  # found is in time order
        first_action.setdefault(action.view, action.t)
    for view, history in views.items():
        if view is None:
            continue
        begun = [t for t in (first_action.get(view), history[0].t) if t is not None]
        if view not in with_open and begun:
            pages.append(Page(min(begun), history[0].path, view))
        pages += [Page(address.t, address.path, view) for address in history[1:]]
    return sorted(pages, key=lambda opened: opened.t)
