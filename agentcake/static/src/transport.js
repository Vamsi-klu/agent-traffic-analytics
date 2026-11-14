// Agent Cake page script, part: batches, sequence numbers and sending (format: docs/collect-format.md).
//
// Every record the other parts make goes through C.push(stream, record) into this page view's buffer. The streams
// are "e" (rrweb events), "r" (raw input records) and "x" (signal records). C.flush(why) sends the buffer as one or
// more batches of at most CFG.batch.max_bytes:
//   - every interval: CFG.batch.interval_min_ms, doubled after each interval with nothing to send up to
//     interval_max_ms, and back to the minimum as soon as there is data again;
//   - as soon as the buffer holds CFG.batch.max_bytes;
//   - right after rrweb's full snapshot and after the environment snapshot, so a page left at once still arrives;
//   - when the page is hidden or left ("exit").
//
// How a batch travels: fetch with credentials omitted (no cookie goes with it, even when cake is on the site's own
// origin), as text/plain so the browser sends no CORS preflight. The Fetch spec lets a page have 64 KiB of
// keepalive bodies in flight; a batch that fits that budget goes with keepalive and survives the page being left.
// Bigger batches are gzipped first where the browser can (CompressionStream, sent with CFG.gzip_query). At exit
// nothing asynchronous can be waited for, so exit batches go as plain JSON with keepalive while the budget lasts.
// Whatever cannot go with keepalive is first parked in sessionStorage and taken out once cake has answered; the next
// page of the visit sends whatever is still parked. So a batch can arrive twice: batches are numbered per page view
// (pv, seq) and cake keeps one copy.

var STREAMS = ['e', 'r', 'x']
var EXIT = 'exit'
var encoder = new TextEncoder()

var buffer = emptyRecords()
var bufferChars = 0
var accepted = { e: 0, r: 0, x: 0 }
var dropped = { e: 0, r: 0, x: 0, b: 0 }
var header = null
var endpoint = null
var seq = 0
var interval = CFG.batch.interval_min_ms
var timer = null
var sizeFlushQueued = false
var keepaliveInFlight = 0
var tokenInFlight = false
var sending = {}
var compressing = {}

function emptyRecords() {
  return { e: [], r: [], x: [] }
}

/** Adds one record to the buffer. Over the per-page limit or CFG.batch.max_record_bytes it is counted, not kept. */
C.push = function (stream, record) {
  if (C.off) return
  if (accepted[stream] >= CFG.limits.records_per_page[stream]) {
    dropped[stream]++
    return
  }
  var text
  try {
    text = JSON.stringify(record)
  } catch (e) {
    dropped[stream]++
    return
  }
  if (text.length > CFG.batch.max_record_bytes) {
    dropped[stream]++
    return
  }
  accepted[stream]++
  buffer[stream].push(text)
  bufferChars += text.length + 1
  if (header && bufferChars >= CFG.batch.max_bytes && !sizeFlushQueued) {
    sizeFlushQueued = true
    C.flushSoon('size')
  }
}

/** Flushes once the code running now has finished (used from inside the recorder's callbacks). */
C.flushSoon = function (why) {
  setTimeout(function () {
    C.flush(why)
  }, 0)
}

/** Sends what is buffered. Returns whether anything was sent. */
C.flush = function (why) {
  sizeFlushQueued = false
  if (C.off || !header) return false
  var exit = why === EXIT
  if (exit) sendCompressingPlain()
  var groups = takeGroups()
  if (!groups.length && C.token.pending() && !tokenInFlight) groups.push(emptyRecords())
  groups.forEach(function (records) {
    dispatch(makeBatch(records, why), exit)
  })
  return groups.length > 0
}

C.transport = {
  /** Starts sending to url; every batch carries fixedHeader (format version, site key, visit and page view ids). */
  start: function (url, fixedHeader) {
    endpoint = url
    header = fixedHeader
    C.onStop(function () {
      clearTimeout(timer)
    })
    timer = setTimeout(tick, interval)
  },
  /** Sends again what earlier pages of the visit (or this one) parked (an idle task after load, and every tick). */
  resendParked: sendParked,
  /** Forgets everything not sent yet, here and parked (the visitor said no). */
  discard: function () {
    buffer = emptyRecords()
    bufferChars = 0
    compressing = {}
    C.store.remove(CFG.storage.pending)
  }
}

function tick() {
  var sent = C.flush('timer')
  sendParked()
  interval = sent
    ? CFG.batch.interval_min_ms
    : Math.min(interval * CFG.batch.interval_growth, CFG.batch.interval_max_ms)
  if (!C.off) timer = setTimeout(tick, interval)
}

// The buffer cut into groups of at most CFG.batch.max_bytes; one record bigger than that goes alone.
function takeGroups() {
  var groups = []
  var current = emptyRecords()
  var chars = 0
  STREAMS.forEach(function (stream) {
    buffer[stream].forEach(function (text) {
      if (chars && chars + text.length > CFG.batch.max_bytes) {
        groups.push(current)
        current = emptyRecords()
        chars = 0
      }
      current[stream].push(text)
      chars += text.length + 1
    })
  })
  if (chars) groups.push(current)
  buffer = emptyRecords()
  bufferChars = 0
  return groups
}

function makeBatch(records, why) {
  var head = {}
  Object.keys(header).forEach(function (key) {
    head[key] = header[key]
  })
  head.seq = seq++
  head.t = C.now()
  head.u = location.origin + location.pathname + location.search
  head.why = why
  var token = C.token.pending()
  if (token) head.st = token
  if (dropped.e || dropped.r || dropped.x || dropped.b) {
    head.dr = { e: dropped.e, r: dropped.r, x: dropped.x, b: dropped.b }
  }
  // The records are already JSON (made once, when pushed): splice them into the header object.
  var body = JSON.stringify(head).slice(0, -1)
  STREAMS.forEach(function (stream) {
    body += ',"' + stream + '":[' + records[stream].join(',') + ']'
  })
  return { id: header.pv + ':' + head.seq, body: body + '}', token: token, parked: false }
}

function fitsKeepalive(size) {
  return size <= CFG.batch.keepalive_max_bytes - keepaliveInFlight
}

function dispatch(batch, exit) {
  var bytes = encoder.encode(batch.body)
  if (exit) {
    if (fitsKeepalive(bytes.length)) post(batch, bytes, false, true)
    else if (!batch.parked) park(batch)
    return
  }
  if (window.CompressionStream && bytes.length >= CFG.batch.compress_min_bytes) {
    gzipThenPost(batch, bytes)
    return
  }
  postKeepingCopy(batch, bytes, false)
}

function gzipThenPost(batch, bytes) {
  compressing[batch.id] = batch
  var zipped = new Blob([bytes]).stream().pipeThrough(new CompressionStream('gzip'))
  // compressing no longer holds the batch when the page was left meanwhile (it went plain) or the visitor said no
  // (window.cake.stop() dropped it): then it does not go, zipped or not.
  new Response(zipped).arrayBuffer().then(
    function (buf) {
      if (compressing[batch.id] !== batch) return
      delete compressing[batch.id]
      postKeepingCopy(batch, new Uint8Array(buf), true)
    },
    function (e) {
      if (compressing[batch.id] !== batch) return
      delete compressing[batch.id]
      C.fault('gzip', e)
      postKeepingCopy(batch, bytes, false)
    }
  )
}

// At exit a gzip still being made cannot be waited for: those batches go plain.
function sendCompressingPlain() {
  Object.keys(compressing).forEach(function (id) {
    var batch = compressing[id]
    delete compressing[id]
    dispatch(batch, true)
  })
}

// A batch too big for keepalive dies with the page if the page is left before cake answers: park a copy first.
function postKeepingCopy(batch, payload, gzipped) {
  var keepalive = fitsKeepalive(payload.byteLength)
  if (!keepalive && !batch.parked) park(batch)
  post(batch, payload, gzipped, keepalive)
}

function post(batch, payload, gzipped, keepalive) {
  var size = payload.byteLength
  if (keepalive) keepaliveInFlight += size
  if (batch.token) tokenInFlight = true
  sending[batch.id] = true
  var settled = function () {
    if (keepalive) keepaliveInFlight -= size
    if (batch.token) tokenInFlight = false
    delete sending[batch.id]
  }
  fetch(endpoint + (gzipped ? CFG.gzip_query : ''), {
    method: 'POST',
    body: payload,
    keepalive: keepalive,
    credentials: 'omit',
    headers: { 'Content-Type': CFG.content_type }
  }).then(
    function (response) {
      settled()
      if (response.ok && batch.token) C.token.accepted(batch.token)
      // Kept for later only when cake may take it then (busy, down); a refusal (wrong key, too big) is final.
      if (response.ok || CFG.batch.retry_statuses.indexOf(response.status) < 0) unpark(batch)
      else if (!batch.parked) park(batch)
    },
    function () {
      settled()
      if (!batch.parked) park(batch)
    }
  )
}

function readParked() {
  try {
    var items = JSON.parse(C.store.get(CFG.storage.pending) || '[]')
    return Array.isArray(items) ? items : []
  } catch (e) {
    return []
  }
}

function park(batch) {
  if (C.off) return // the visitor said no: an upload that fails now is dropped, not kept for a later start()
  var items = readParked()
  var chars = batch.body.length
  items.forEach(function (item) {
    chars += item.body.length
  })
  var stored = chars <= CFG.batch.pending_max_bytes
  if (stored) {
    items.push({ id: batch.id, body: batch.body })
    stored = C.store.set(CFG.storage.pending, JSON.stringify(items))
  }
  if (stored) batch.parked = true
  else dropped.b++
}

function unpark(batch) {
  if (!batch.parked) return
  var items = readParked().filter(function (item) {
    return item.id !== batch.id
  })
  if (items.length) C.store.set(CFG.storage.pending, JSON.stringify(items))
  else C.store.remove(CFG.storage.pending)
  batch.parked = false
}

// Parked batches (this page's or an earlier page's of the visit) go again; each keeps its own pv and seq.
function sendParked() {
  if (C.off) return
  readParked().forEach(function (item) {
    if (sending[item.id] || compressing[item.id]) return
    dispatch({ id: item.id, body: item.body, token: null, parked: true }, false)
  })
}
