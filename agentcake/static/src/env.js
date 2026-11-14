// Agent Cake page script, part: the environment of a page view and the globals automation leaves (plan step S1.3),
// stream "x".
//
// Ported from the research lab's env.js (our research code, 11/11;
// our own code): raw values only, cake judges later, field names as the lab's (cake's environment rules, S3.3, read
// them). The table of distinctive globals is BotD's (MIT, in cakejs.json env.distinctive_globals); the error-stack
// read is BotD's errorTrace idea. The two CDP-binding scans (exposed_installed, unnamed_native_globals) follow ideas of
// rebrowser-bot-detector, in our own code (see automation.js for why none of its code is used).
// Left out of the lab version: the cookie read (cake reads no cookie), the CSP probe (it loaded a script from another
// origin of the site), the per-click snapshots (raw.js records every click) and the lab's run fields.

// Each pattern is [source, flags].
var patterns = {}
Object.keys(CFG.env.global_patterns).forEach(function (name) {
  var pattern = CFG.env.global_patterns[name]
  patterns[name] = new RegExp(pattern[0], pattern[1])
})

function matching(names, pattern) {
  return names.filter(function (name) {
    return pattern.test(name)
  })
}

function webgl() {
  try {
    var gl = document.createElement('canvas').getContext('webgl')
    if (!gl) return { vendor: null, renderer: null }
    var info = gl.getExtension('WEBGL_debug_renderer_info')
    var out = {
      vendor: info ? gl.getParameter(info.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR),
      renderer: info ? gl.getParameter(info.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER)
    }
    // Browsers allow only a few live WebGL contexts per page: give this one back so the site's own are never evicted.
    var lose = gl.getExtension('WEBGL_lose_context')
    if (lose) lose.loseContext()
    return out
  } catch (e) {
    return { error: e.message }
  }
}

function mediaMatches(feature, values) {
  return values.filter(function (value) {
    return matchMedia('(' + feature + ': ' + value + ')').matches
  })
}

function environment() {
  var n = navigator
  var wd = Object.getOwnPropertyDescriptor(Navigator.prototype, 'webdriver')
  return {
    webdriver: n.webdriver,
    webdriver_type: typeof n.webdriver,
    webdriver_getter_native: wd && wd.get ? /\[native code\]/.test(Function.prototype.toString.call(wd.get)) : null,
    webdriver_on_proto: !!wd,
    webdriver_own_prop: Object.getOwnPropertyDescriptor(n, 'webdriver') !== undefined,
    navigator_own_props: Object.getOwnPropertyNames(n),
    userAgent: n.userAgent,
    appVersion: n.appVersion,
    vendor: n.vendor,
    productSub: n.productSub,
    uaData: n.userAgentData
      ? { brands: n.userAgentData.brands, platform: n.userAgentData.platform, mobile: n.userAgentData.mobile }
      : null,
    languages: n.languages,
    language: n.language,
    platform: n.platform,
    hardwareConcurrency: n.hardwareConcurrency,
    deviceMemory: n.deviceMemory,
    plugins: n.plugins ? n.plugins.length : null,
    mimeTypes: n.mimeTypes ? n.mimeTypes.length : null,
    pdfViewerEnabled: n.pdfViewerEnabled,
    cookieEnabled: n.cookieEnabled,
    doNotTrack: n.doNotTrack,
    maxTouchPoints: n.maxTouchPoints,
    screen: { w: screen.width, h: screen.height, aw: screen.availWidth, ah: screen.availHeight, cd: screen.colorDepth },
    window: { iw: innerWidth, ih: innerHeight, ow: outerWidth, oh: outerHeight, sx: screenX, sy: screenY },
    viewport: { cw: document.documentElement.clientWidth, ch: document.documentElement.clientHeight },
    dpr: devicePixelRatio,
    tzOffset: new Date().getTimezoneOffset(),
    notificationPermission: C.safe(function () {
      return window.Notification ? Notification.permission : 'no Notification'
    }),
    windowChrome: typeof window.chrome,
    chromeRuntime: C.safe(function () {
      return !!(window.chrome && window.chrome.runtime)
    }),
    chromeKeys: C.safe(function () {
      return window.chrome ? Object.keys(window.chrome) : null
    }),
    hasFocus: document.hasFocus(),
    visibilityState: document.visibilityState,
    historyLength: history.length,
    referrer: document.referrer,
    anyPointer: mediaMatches('any-pointer', ['fine', 'coarse', 'none']),
    anyHover: mediaMatches('any-hover', ['hover', 'none']),
    prefersColorScheme: matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light',
    connectionRtt: C.safe(function () {
      return n.connection ? n.connection.rtt : null
    }),
    windowExternal: C.safe(function () {
      return String(window.external)
    }),
    evalLength: eval.toString().length,
    process: typeof window.process
  }
}

// Globals that automation frameworks leave on window and document. Reads property descriptors only, so no getter of
// the page runs.
function globals() {
  var winKeys = Object.getOwnPropertyNames(window)
  var docKeys = Object.getOwnPropertyNames(document)
  var out = {}
  Object.keys(CFG.env.distinctive_globals).forEach(function (kind) {
    var hit = CFG.env.distinctive_globals[kind].filter(function (name) {
      return winKeys.indexOf(name) >= 0 || docKeys.indexOf(name) >= 0
    })
    if (hit.length) out['botdprop_' + kind] = hit
  })
  out.selenium_cdc = matching(winKeys, patterns.selenium_cdc_window)
  out.selenium_cdc = out.selenium_cdc.concat(matching(docKeys, patterns.selenium_cdc_document))
  out.playwright_globals = matching(winKeys, patterns.playwright)
  out.puppeteer_globals = matching(winKeys, patterns.puppeteer)
  out.exposed_installed = []
  out.unnamed_native_globals = []
  winKeys.forEach(function (name) {
    try {
      var d = Object.getOwnPropertyDescriptor(window, name)
      if (!d || typeof d.value !== 'function') return
      // Playwright's exposeFunction marks its bindings; a nameless native function is a CDP binding. The name is
      // checked first: turning a site's own (named) function into source text can be slow.
      if (d.value.__installed === true) out.exposed_installed.push(name)
      if (d.value.name !== '') return
      if (/\{\s*\[native code\]\s*\}\s*$/.test(Function.prototype.toString.call(d.value))) {
        out.unnamed_native_globals.push(name)
      }
    } catch (e) {
      return
    }
  })
  return out
}

function errorStack() {
  try {
    null[0]()
  } catch (e) {
    return String(e.stack || '').slice(0, CFG.env.stack_chars)
  }
  return null
}

// The environment snapshot is made in three idle tasks (the WebGL context and the first Intl call take ~10–20 ms
// each) and sent as one record after the last.
var snapshot = null

C.env = {
  environment: function () {
    snapshot = environment()
  },
  webgl: function () {
    if (snapshot) snapshot.webgl = webgl()
  },
  timeZone: function () {
    if (!snapshot) return
    snapshot.tz = C.safe(function () {
      return Intl.DateTimeFormat().resolvedOptions().timeZone
    })
    C.push('x', { t: C.now(), ty: 'env', env: snapshot })
  },
  /** The automation traces, once per page view (an idle task after load). */
  automationTraces: function () {
    C.push('x', {
      t: C.now(),
      ty: 'auto',
      globalsAtLoad: globals(),
      errorStack: errorStack(),
      docInterception: C.safe(C.automation.documentInterception)
    })
  },
  /** At exit: the globals again (some frameworks add theirs late) and what the DOM-lookup watch saw. */
  atExit: function () {
    var record = C.automation.lookups()
    record.t = C.now()
    record.ty = 'globals'
    record.globalsAtEnd = globals()
    C.push('x', record)
  }
}
