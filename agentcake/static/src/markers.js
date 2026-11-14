// Agent Cake page script, part: the marks agent products draw on the page, and when each was there (plan steps S3.3,
// S3.7; GOAL A5), stream "x".
//
// Some agent products draw on the page while they work: Claude in Chrome a "working" tag and a Stop button, Comet a
// stop button, Browser Use a box around each action. When such a mark appears and goes away tells cake when the
// agent's turn began and ended, so where a person may have taken over. The marks and how to find each are data
// (agentcake/data/agent_markers.json, CFG.markers), since a product redraws them with a new version:
//   - element ids and a CSS selector: the mark is an element of the page's own DOM, there or not;
//   - spots to hit-test: the mark is drawn inside an extension's closed shadow root, which no selector reaches.
//     document.elementFromPoint at a spot returns the root's host while the mark covers the spot. The host has the
//     shape CFG.markers.host (an attribute-less, empty <div> with display: contents under <body>): such an element
//     draws no box of its own, so a hit on it is a hit on what its shadow root draws.
// It looks every CFG.markers.every_ms while the page is visible (a hidden page shows no mark, so its marks are not
// known then; it looks again the moment the page is shown) and sends a "marker" record when a mark appears or goes
// away: which mark and when, nothing of the page. It only reads the page: it adds, moves and changes nothing.
// What it costs stays small on any page: ids are looked up directly at each look; the selectors are matched against
// the whole page once, when the watch starts, and after that only against what changes (a MutationObserver hands
// over added elements and the elements whose attributes the selectors read changed), so a page that keeps changing
// costs in proportion to the change; a whole-page search runs again only at a look after something was removed while
// a selector's mark was there (to see whether it went). The spots are hit-tested only while <body> or <html> has a
// child of the host's shape, which a page without such an extension never has. A "markers" record says when the
// watch began, and at exit how many looks it made and how long all of its work took.

var watch = CFG.markers
var byElement = []
var byPoint = []
var bySelector = []
var anySelector = ''
var selectorHit = {}
var recheck = false
var shown = {}
var looks = 0
var spentMs = 0
var longestMs = 0
var watching = false

// A selector the browser cannot parse is left out (its mark keeps its ids) and reported, once; an empty fragment
// parses it without a search.
function parses(marker) {
  try {
    document.createDocumentFragment().querySelector(marker.selector)
    return true
  } catch (e) {
    C.fault('markers', marker.id + ': ' + (e && e.message))
    return false
  }
}

// The whole page: when the watch starts, and for the marks seen before whose element may have gone.
function searchPage(marks) {
  var any = marks.length > 0 && document.querySelector(anySelector) !== null
  marks.forEach(function (marker) {
    selectorHit[marker.id] = any && document.querySelector(marker.selector) !== null
  })
}

// An element that was added or whose watched attribute changed, with what it holds: a mark not yet there may be.
function searchIn(node) {
  if (node.nodeType !== Node.ELEMENT_NODE) return
  if (!node.matches(anySelector) && !node.querySelector(anySelector)) return
  bySelector.forEach(function (marker) {
    if (selectorHit[marker.id]) return
    selectorHit[marker.id] = node.matches(marker.selector) || node.querySelector(marker.selector) !== null
  })
}

function anySelectorHit() {
  return bySelector.some(function (marker) {
    return selectorHit[marker.id]
  })
}

function onMutations(mutations) {
  mutations.forEach(function (mutation) {
    if (mutation.type === 'attributes') {
      if (anySelectorHit()) recheck = true
      searchIn(mutation.target)
      return
    }
    if (mutation.removedNodes.length && anySelectorHit()) recheck = true
    Array.prototype.forEach.call(mutation.addedNodes, searchIn)
  })
}

function present(marker) {
  if (selectorHit[marker.id]) return true
  return (marker.ids || []).some(function (id) {
    return document.getElementById(id) !== null
  })
}

// The viewport without its scroll bars, which is where position: fixed places a mark (in quirks mode, the body's).
function viewport() {
  var root = document.compatMode === 'BackCompat' ? document.body : document.documentElement
  return root ? { width: root.clientWidth, height: root.clientHeight } : { width: innerWidth, height: innerHeight }
}

function isHost(el) {
  var shape = watch.host
  if (el.tagName !== shape.tag || el.attributes.length || el.firstChild || el.shadowRoot) return false
  return getComputedStyle(el).display === shape.display
}

// The children of <body> and <html> that have the host's shape (none, on a page no such extension draws on).
function hosts() {
  var parents = { body: document.body, html: document.documentElement }
  var found = []
  watch.host.parents.forEach(function (name) {
    var parent = parents[name]
    if (!parent) return
    Array.prototype.forEach.call(parent.children, function (el) {
      if (isHost(el)) found.push(el)
    })
  })
  return found
}

function lit(marker, found, size) {
  return marker.spots.some(function (spot) {
    var y = 'top' in spot ? spot.top : size.height - spot.bottom
    return found.indexOf(document.elementFromPoint(spot.x * size.width, y)) >= 0
  })
}

function note(marker, on, t) {
  if (!!shown[marker.id] === on) return
  shown[marker.id] = on
  C.push('x', { t: t, ty: 'marker', m: marker.id, on: on ? 1 : 0 })
}

// Every piece of the watch's work (a look, a batch of DOM changes) is timed, for the exit record.
function timed(fn) {
  return function (arg) {
    var started = performance.now()
    fn(arg)
    var took = performance.now() - started
    spentMs += took
    longestMs = Math.max(longestMs, took)
  }
}

function look() {
  if (document.visibilityState !== 'visible') return
  looks++
  var t = C.now()
  if (recheck) {
    recheck = false
    searchPage(bySelector.filter(function (marker) {
      return selectorHit[marker.id]
    }))
  }
  byElement.forEach(function (marker) {
    note(marker, present(marker), t)
  })
  if (byPoint.length) {
    var found = hosts()
    var size = found.length ? viewport() : null
    byPoint.forEach(function (marker) {
      note(marker, found.length > 0 && lit(marker, found, size), t)
    })
  }
}

function watchDom() {
  var observer = new MutationObserver(timed(onMutations))
  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: watch.attributes
  })
  C.onStop(function () {
    observer.disconnect()
  })
}

C.markers = {
  /** The watch: an idle task after load (a mark shown before then is noted at the first look). */
  start: function () {
    watch.markers.forEach(function (marker) {
      if (marker.spots) byPoint.push(marker)
      else byElement.push(marker.selector && !parses(marker) ? { id: marker.id, ids: marker.ids } : marker)
    })
    bySelector = byElement.filter(function (marker) {
      return marker.selector
    })
    anySelector = bySelector
      .map(function (marker) {
        return marker.selector
      })
      .join(',')
    watching = true
    C.push('x', { t: C.now(), ty: 'markers', why: 'start', list: watch.version, every_ms: watch.every_ms })
    if (anySelector !== '') {
      searchPage(bySelector)
      watchDom()
    }
    var timedLook = timed(look)
    timedLook()
    C.every(timedLook, watch.every_ms)
    C.listen(document, 'visibilitychange', timedLook)
  },
  /** At exit: how many looks so far, and the time all of the watch's work took (ms) and its longest piece. */
  atExit: function () {
    if (!watching) return
    C.push('x', {
      t: C.now(),
      ty: 'markers',
      why: 'exit',
      looks: looks,
      ms: C.round(spentMs),
      longest_ms: C.round(longestMs)
    })
  }
}
