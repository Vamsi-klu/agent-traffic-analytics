// Agent Cake page script, part: the session replay recorder, stream "e".
//
// rrweb's record (bundled into cake.js unchanged, see THIRD_PARTY.md) with the privacy rules of
// agentcake/data/privacy.json: every input masked (the replay keeps its length), text typed into
// editable elements masked, private elements (data-cake-private, passwords, payment card fields, and what the site
// owner hides in AgentCake's settings) not recorded at all.
// Each full snapshot is sent as soon as rrweb has emitted it (with the page record and whatever else is buffered), so
// a page left within a second still has its snapshot in cake. rrweb takes the first one at once when the document is
// already parsed (cake.js is loaded with defer), else at DOMContentLoaded.

var FULL_SNAPSHOT = 2 // protocol: rrweb EventType.FullSnapshot

C.replay = {
  start: function () {
    var record = C.rrweb && (C.rrweb.record || C.rrweb)
    if (typeof record !== 'function') {
      C.fault('rrweb', 'rrweb record is missing')
      return
    }
    var stopRecording = record({
      emit: function (event) {
        C.push('e', event)
        if (event.type === FULL_SNAPSHOT) C.flushSoon('snapshot')
      },
      maskAllInputs: CFG.privacy.mask_all_inputs,
      // Text typed into editable elements is page text, not an input value: masked like an input.
      maskTextSelector: CFG.privacy.mask_text_selector,
      // Private elements (and those the site owner hides, cake_main.js) become empty placeholders, as does cake.js's
      // own probe frame (automation.js).
      blockSelector: C.privateSelector + ',[' + CFG.env.probe_attr + ']',
      sampling: CFG.rrweb.sampling
    })
    if (stopRecording) C.onStop(stopRecording)
  }
}
