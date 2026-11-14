// Agent Cake page script, part: what the two bundled detectors find in the page, stream "x".
//
// BotD (FingerprintJS, MIT) and botscent's page half (MIT) run in the page; neither sends anything anywhere (cake's
// copy of BotD has its telemetry request removed, botscent has no network code). cake keeps what they report, raw:
// BotD's result and its per-detector detections; botscent's verdict, reasons and probe statuses when it starts, when
// its verdict changes, a few seconds in (CFG.botscent.sample_ms, as the lab did) and when the page is left.

var stopOurBotscent = null

function botscentRecord(why) {
  var api = window.botscent
  if (!api) return
  try {
    var verdict = api.verdict()
    var diagnostics = api.diagnostics()
    C.push('x', {
      t: C.now(),
      ty: 'botscent',
      why: why,
      type: verdict.type,
      agent: verdict.agent_name || null,
      reasons: verdict.reasons || [],
      probes: diagnostics.probes || null,
      transport: diagnostics.transport,
      ver: diagnostics.version
    })
  } catch (e) {
    C.fault('botscent', e)
  }
}

function startBotscent() {
  // A site that already runs botscent keeps its own copy; cake only reads it and never stops it.
  if (!window.botscent) {
    try {
      C.startBotscent()
      stopOurBotscent = window.botscent && window.botscent.start()
    } catch (e) {
      C.fault('botscent', e)
      return
    }
    C.onStop(function () {
      if (stopOurBotscent) stopOurBotscent()
    })
  }
  C.listen(window, 'botscent', function () {
    botscentRecord('change')
  })
  C.later(function () {
    botscentRecord('later')
  }, CFG.botscent.sample_ms)
  botscentRecord('start')
}

function runBotd() {
  if (typeof C.botdLoad !== 'function') return Promise.resolve()
  return C.botdLoad().then(
    function (detector) {
      var record = { t: C.now(), ty: 'botd' }
      try {
        record.result = detector.detect()
        record.detections = detector.getDetections ? detector.getDetections() : null
      } catch (e) {
        record.error = String(e && e.message)
      }
      C.push('x', record)
    },
    function (e) {
      C.push('x', { t: C.now(), ty: 'botd', error: String(e && e.message) })
    }
  )
}

C.detectors = {
  startBotscent: startBotscent,
  runBotd: runBotd,
  atExit: function () {
    botscentRecord('exit')
  }
}
