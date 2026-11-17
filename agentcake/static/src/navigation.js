// AgentCake page script, part: a single-page app's page views.
//
// A page view is what PostHog counts as one ($pageview): each page load (cake.js's page record) and, as posthog-js
// does by default (capture_pageview 'history_change', packages/browser/src/extensions/history-autocapture.ts; MIT),
// each change of location.pathname within it, by pushState, replaceState or the back button; a change of the query
// string or the fragment alone is none. cake.js notes such a change with a "path" record (when, and the new path, which
// the address of every upload holds anyway). It compares the path whenever it records something, so a navigation is
// seen with the first event after it (the click that made it, the page's own changes), and the page's history methods
// are left as they are. A path record is activity, as PostHog's $pageview is (session.js).

var path = null // the path of the last page view; null until the page record is made

C.navigation = {
  /** From now on a new path is a page view (cake_main.js, right after the page record). */
  start: function () {
    path = location.pathname
  },
  /** A path record when the path changed since the last page view. */
  check: function () {
    if (path === null || location.pathname === path) return
    path = location.pathname
    C.push('x', { t: C.now(), ty: CFG.navigation.record, p: path })
  }
}
