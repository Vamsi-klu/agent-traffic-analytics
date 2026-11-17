// AgentCake page script, part: the server-half token.
//
// As in cake 0.3.3: the site's server (its cake middleware) puts a signed token in
// the Server-Timing header of the response that opened this page (`Server-Timing: cake;desc="c1.<body>.<sig>"`).
// cake.js reads it from the page's navigation entry and sends it with every batch of this page until cake has
// accepted one batch that carried it (a 2xx answer). The token is signed by the server and never opened here.
// A single-page app's route change (history.pushState) stays in this page view, whose token went already. A page the
// browser shows from its cache carries the token stored with it (after a 304, the 304's own new one; going back to a
// stored page, that page's earlier one): it goes all the same, and collect answers reuse and keeps it once
// (checked in Chromium, WebKit and Firefox). A page the back-forward cache restores is the same page view: nothing new.

var token = null

C.token = {
  read: function () {
    try {
      var nav = performance.getEntriesByType('navigation')[0]
      var entries = (nav && nav.serverTiming) || []
      entries.forEach(function (entry) {
        if (entry.name === CFG.token.entry && entry.description) token = entry.description
      })
    } catch (e) {
      C.fault('token', e)
    }
  },
  /** The token still to be delivered, or null. */
  pending: function () {
    return token
  },
  /** Called when cake answered 2xx to a batch carrying value. */
  accepted: function (value) {
    if (value === token) token = null
  }
}
