// Agent Cake page script, part: raw input events and page-structure changes (plan step S1.3), stream "r".
//
// Ported from the research lab's raw.js (our research code, 11/11;
// our own code). It records raw values only; cake judges later. The field names are the lab's, so the lab's
// behaviour features (plan step S3.6) read cake's data unchanged. Added here: pointerId, tilt and the number of
// coalesced pointer samples (signals sig-057, sig-058 of the signal audit).
// Privacy (plan step S1.4, rules in agentcake/data/privacy.json): never which key was pressed, only the time, a key
// class and whether event.code is empty; never what was typed, only the input type and the field's length; nothing
// typed into a private element (data-cake-private, passwords, payment card fields) at all, and no selector or box of
// a private element on any other event.

function selectorOf(el) {
  if (!el || el.nodeType !== Node.ELEMENT_NODE) return null
  if (el.id) return '#' + el.id
  var holder = el.closest && el.closest('[id]')
  return (holder ? '#' + holder.id + ' ' : '') + el.tagName.toLowerCase()
}

function rectOf(el) {
  if (!el || !el.getBoundingClientRect) return null
  var r = el.getBoundingClientRect()
  return [C.round(r.left), C.round(r.top), C.round(r.width), C.round(r.height)]
}

// The key classes (the lab's, from privacy.json). Only the class leaves the page, never the key.
var classes = CFG.privacy.key_classes
var singleCharacter = classes.single_character.map(function (entry) {
  return { name: entry.class, pattern: new RegExp(entry.pattern, entry.flags) }
})

function keyClass(e) {
  var k = e.key || ''
  if (k.length === 1) {
    var match = singleCharacter.filter(function (c) {
      return c.pattern.test(k)
    })[0]
    return match ? match.name : classes.single_character_other
  }
  if (Object.prototype.hasOwnProperty.call(classes.named, k)) return classes.named[k]
  var prefix = Object.keys(classes.prefixes).filter(function (p) {
    return k.indexOf(p) === 0
  })[0]
  return prefix ? classes.prefixes[prefix] : classes.other
}

// The length of what a field holds, never the text: an input's value, or an editable element's text.
function valueLength(el) {
  if (!el) return null
  if (typeof el.value === 'string') return el.value.length
  if (el.isContentEditable) return (el.textContent || '').length
  return null
}

var droppedInPrivate = {}
CFG.privacy.private_dropped_events.forEach(function (type) {
  droppedInPrivate[type] = true
})

function isPrivate(el) {
  return !!(el && el.closest && el.closest(C.privateSelector))
}

var targetEvents = {}
CFG.raw.target_events.forEach(function (type) {
  targetEvents[type] = true
})

function pageState() {
  return {
    hf: document.hasFocus() ? 1 : 0,
    vs: document.visibilityState === 'visible' ? 1 : 0
  }
}

function inputRecord(e) {
  var o = { t: C.epoch(e.timeStamp), ty: e.type, tr: e.isTrusted ? 1 : 0 }
  var state = pageState()
  o.hf = state.hf
  o.vs = state.vs
  if ('clientX' in e) {
    o.cx = e.clientX
    o.cy = e.clientY
    o.sx = e.screenX
    o.sy = e.screenY
    o.mx = e.movementX
    o.my = e.movementY
    o.b = e.buttons
    o.d = e.detail
  }
  if ('pointerType' in e) {
    o.pt = e.pointerType
    o.pr = e.pressure
    o.w = e.width
    o.h = e.height
    o.pid = e.pointerId
    o.tlx = e.tiltX
    o.tly = e.tiltY
    if (e.type === 'pointermove' && e.getCoalescedEvents) o.co = e.getCoalescedEvents().length
  }
  if (e.type === 'wheel') {
    o.dx = e.deltaX
    o.dy = e.deltaY
    o.dm = e.deltaMode
  }
  if (e.type === 'scroll') {
    o.y = Math.round(scrollY)
    o.x = Math.round(scrollX)
  }
  if (e.type === 'keydown' || e.type === 'keyup') {
    o.kc = keyClass(e)
    o.ce = e.code ? 0 : 1
    o.rp = e.repeat ? 1 : 0
  }
  if (e.type === 'input') {
    o.it = e.inputType || null
    o.ic = e.isComposing ? 1 : 0
    o.len = valueLength(e.target)
  }
  if (targetEvents[e.type]) {
    var target = e.target
    o.s = selectorOf(target)
    o.r = rectOf(target && target.closest ? target.closest(CFG.raw.target_selector) || target : target)
  }
  return o
}

function onInput(e) {
  // The innermost target, also inside an open shadow root (the window sees the shadow host).
  var origin = e.composedPath ? e.composedPath()[0] : e.target
  var privateTarget = isPrivate(origin) || isPrivate(e.target)
  if (privateTarget && droppedInPrivate[e.type]) return
  var record = inputRecord(e)
  if (privateTarget) {
    CFG.privacy.private_dropped_fields.forEach(function (field) {
      delete record[field]
    })
  }
  C.push('r', record)
}

function stateRecord(type) {
  var o = pageState()
  o.t = C.now()
  o.ty = type
  return o
}

// Elements added directly under <html> or <body>. Claude in Chrome 1.0.106 adds an attribute-less <div> holding a
// closed shadow root there (the lab's bh-detect test 2). Only reads: never calls attachShadow on page elements.
function watchDirectChildren() {
  var seen = new WeakSet()
  var note = function (el, how) {
    if (!el || el.nodeType !== Node.ELEMENT_NODE || seen.has(el) || el.tagName === 'SCRIPT') return
    if (el.hasAttribute(CFG.env.probe_attr)) return // cake.js's own probe frame (env.js)
    seen.add(el)
    var display = null
    try {
      display = getComputedStyle(el).display
    } catch (e) {
      display = null
    }
    var parent = 'other'
    if (el.parentNode === document.body) parent = 'body'
    else if (el.parentNode === document.documentElement) parent = 'html'
    C.push('r', {
      t: C.now(),
      ty: 'dom_add',
      how: how,
      tag: el.tagName,
      nattr: el.attributes.length,
      attrs: Array.prototype.map
        .call(el.attributes, function (a) {
          return a.name
        })
        .slice(0, CFG.raw.dom_attr_names_max),
      open_shadow: el.shadowRoot ? 1 : 0,
      disp: display,
      parent: parent
    })
  }
  var observer = new MutationObserver(function (mutations) {
    mutations.forEach(function (m) {
      m.addedNodes.forEach(function (n) {
        note(n, 'added')
      })
    })
  })
  observer.observe(document.documentElement, { childList: true })
  if (document.body) observer.observe(document.body, { childList: true })
  C.onStop(function () {
    observer.disconnect()
  })
  // Elements already there when cake.js started are found by a later scan of attribute-less children.
  C.later(function () {
    var kids = Array.prototype.slice.call(document.body ? document.body.children : [])
    kids.concat(Array.prototype.slice.call(document.documentElement.children)).forEach(function (el) {
      var skip = el.tagName === 'SCRIPT' || el.tagName === 'HEAD' || el.tagName === 'BODY'
      if (!skip && el.attributes.length === 0) note(el, 'scan')
    })
  }, CFG.raw.dom_scan_delay_ms)
}

// Window geometry, recorded whenever it changes (on resize and on a slow poll: moving a window fires no event).
function watchGeometry() {
  var last = ''
  var check = function (why) {
    var g = [innerWidth, innerHeight, outerWidth, outerHeight, screenX, screenY, devicePixelRatio]
    g.push(screen.width, screen.height)
    var key = g.join(',')
    if (key === last) return
    last = key
    var o = stateRecord('geo')
    o.why = why
    o.g = g
    C.push('r', o)
  }
  check('load')
  C.listen(window, 'resize', function () {
    check('resize')
  })
  C.every(function () {
    check('poll')
  }, CFG.raw.geo_poll_ms)
}

C.raw = {
  /** The input, visibility, focus and geometry listeners: at once, when cake.js starts. */
  listen: function () {
    var options = { capture: true, passive: true }
    CFG.raw.events.forEach(function (type) {
      C.listen(window, type, onInput, options)
    })
    C.listen(window, 'scroll', onInput, options)
    C.listen(document, 'visibilitychange', function () {
      C.push('r', stateRecord('visibility'))
    })
    C.listen(window, 'focus', function () {
      C.push('r', { t: C.now(), ty: 'winfocus' })
    })
    C.listen(window, 'blur', function () {
      C.push('r', { t: C.now(), ty: 'winblur' })
    })
    watchGeometry()
  },
  /** The watch on elements added under <html> and <body>: after rrweb has started (it adds and removes a frame of
   * its own as it starts, which is not the page's). */
  watchDom: watchDirectChildren
}
