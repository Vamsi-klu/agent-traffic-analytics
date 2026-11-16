// Agent Cake page script, part: where a page view came from, and the browser's language and time zone.
//
// The fields PostHog's web analytics groups sessions by (posthog-js's packages/browser-common/src/utils/
// event-utils.ts; posthog-js, MIT), sent with each page record and with the record that begins a new session:
//   rd    the referring domain: the host of document.referrer, never the address itself ("" when there is none,
//         PostHog's $direct); PostHog's $referring_domain
//   utm   the page address's campaign parameters that are there, each cut to CFG.source.max_chars: the five UTM
//         parameters and gad_source (PostHog's CAMPAIGN_PARAMS that its channel rules read)
//   ck    which ad-click parameters the address carries (PostHog's PERSONAL_DATA_CAMPAIGN_PARAMS: gclid, fbclid, …),
//         only their names, never their values
//   lang  navigator.language (PostHog's $browser_language)
//   tzo   the time zone's offset from UTC in minutes, as Date.getTimezoneOffset() gives it (PostHog's
//         $timezone_offset)
// Both language and offset are also in the environment record, which arrives later; here they come with the page
// view, so a page left at once still has them.

C.referringDomain = function () {
  if (!document.referrer) return ''
  try {
    return new URL(document.referrer).host
  } catch (e) {
    return ''
  }
}

function campaign(params) {
  var found = {}
  CFG.source.campaign.forEach(function (name) {
    var value = params.get(name)
    if (value) found[name] = value.slice(0, CFG.source.max_chars)
  })
  return found
}

function clickIds(params) {
  return CFG.source.click_ids.filter(function (name) {
    return params.has(name)
  })
}

C.source = {
  /** The source fields of the page as it is now (see the top). */
  fields: function () {
    var params = new URLSearchParams(location.search)
    return {
      rd: C.referringDomain(),
      utm: campaign(params),
      ck: clickIds(params),
      lang: navigator.language || null,
      tzo: new Date().getTimezoneOffset()
    }
  }
}
