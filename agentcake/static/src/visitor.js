// AgentCake page script, part: the visitor id, which AgentCake counts visitors by, and the identify hash kept with it.
//
// As PostHog does (posthog-js's packages/browser/src/posthog-core.ts: an anonymous id persisted with
// 'localStorage+cookie' for cookie_expiration 365 days, renewed whenever it is written; posthog-js, Apache-2.0), the
// browser keeps a random id, made from nothing about the device or the visitor, for CFG.visitor.max_age_ms (365 days)
// after its last page view on the site. Only in localStorage: PostHog's cookie half exists so that sibling subdomains
// and the site's own server can read the id, which AgentCake needs neither for, and a cookie would go to the site's
// server with every request; the page script reads and sets no cookie. localStorage has no expiry of its own, so the id
// is kept with the time of its last use and replaced once that is older than a year.
// Where localStorage cannot be used (a private window, storage turned off), the id lives only as long as the page,
// as PostHog's id does in memory: each such page view counts as a visitor of its own.
// After the site calls window.cake.identify(), the same entry also holds the identify hash (identify.js), as
// PostHog keeps the identified distinct id in the same persistence: it lasts as long as the id, and every page view
// that begins with it sends it. window.cake.reset() puts a new id without a hash in its place; window.cake.stop()
// forgets both (cake_main.js); with data-consent="required" nothing is read or written before start.

var entry = null // { id, t, h }: the id, its last use (epoch ms) and, once identified, the hash; this page's copy

function read(now) {
  try {
    var stored = JSON.parse(localStorage.getItem(CFG.storage.visitor) || 'null')
    if (stored && typeof stored.id === 'string' && now - stored.t <= CFG.visitor.max_age_ms) return stored
  } catch (e) {
    return null
  }
  return null
}

function write() {
  try {
    localStorage.setItem(CFG.storage.visitor, JSON.stringify(entry))
  } catch (e) {
    return false // storage refused: the id and its hash stay this page's own
  }
  return true
}

C.visitor = {
  /** The visitor id at a page view's start (`now`, epoch ms): the stored one, else a new one; its time renewed. */
  id: function (now) {
    var stored = read(now)
    entry = { id: stored ? stored.id : C.randomId(), t: now }
    if (stored && typeof stored.h === 'string') entry.h = stored.h
    write()
    return entry.id
  },
  /** The identify hash kept with the id, or null when the site has not identified this visitor. */
  hash: function () {
    return entry && entry.h ? entry.h : null
  },
  /** Keeps the identify hash with the id. Another tab may have changed the entry since this page began: the hash
   * goes into the stored one; when there is none (storage refused, or emptied meanwhile) it stays this page's. */
  identify: function (hash, now) {
    entry = read(now) || entry
    entry.h = hash
    entry.t = now
    write()
  },
  /** The stored id and hash, when another tab has changed them since this page took its copy (window.cake.reset() or
   * identify() there): this page takes them, as posthog-js's tabs take a new distinct id from the persistence they
   * share (session.js asks when the tab's session begins anew). Returns the entry taken, or null when nothing changed
   * or nothing is stored (storage refused, or emptied by window.cake.stop() in another tab). */
  follow: function (now) {
    var stored = read(now)
    if (!stored || !entry || (stored.id === entry.id && stored.h === entry.h)) return null
    entry = stored
    return entry
  },
  /** A new id, without a hash, in place of the old one (window.cake.reset()); returns it. */
  renew: function (now) {
    entry = { id: C.randomId(), t: now }
    write()
    return entry.id
  },
  /** Forgets the id and its hash (the visitor said no, or the site called reset() before cake.js started). */
  forget: function () {
    entry = null
    try {
      localStorage.removeItem(CFG.storage.visitor)
    } catch (e) {
      return false
    }
    return true
  }
}
