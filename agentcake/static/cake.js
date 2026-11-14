/*! Agent Cake page script (cake.js), upload format v1, build fd9973afe7c8. Made by agentcake/build_js.py from agentcake/static/src/ and agentcake/data/cakejs.json; do not edit. Bundles rrweb record, BotD, botscent page half, whose licences follow. */
/*! rrweb record 2.0.0-alpha.18 (rrweb-io/rrweb, record UMD build as shipped with cake 0.3.x (local source checked at commit 3339038d)):
MIT License

Copyright (c) 2018 Contributors (https://github.com/rrweb-io/rrweb/graphs/contributors)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
*/
/*! BotD 2.0.0 (@fingerprintjs/botd 2.0.0, dist/botd.esm.js; telemetry and export removed (see the file's header)):
MIT License

Copyright (c) 2025 FingerprintJS, Inc

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
*/
/*! botscent page half 1.2.0 (botscent 1.2.0 on npm, dist/botscent.js, unchanged (github.com/nalinbhardwaj/botscent commit 7f948003)):
MIT License

Copyright (c) 2026 Nalin Bhardwaj

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
*/
;(function () {
  'use strict'
  if (window.cake && window.cake.version) return // cake.js is already running on this page
  var STARTED = performance.now() // cake.js reports how long its own first task took
  var TAG = document.currentScript
  var CFG = {"format_version":1,"collect_path":"collect","attr":{"site":"data-site","consent":"data-consent"},"consent":{"required":"required","commands":{"start":"start","stop":"stop"}},"defaults":{"hook_dom":false,"hide_selectors":""},"storage":{"session":"cake_sid","page_number":"cake_pn","pending":"cake_pending","frames_done":"cake_frames"},"id_bytes":16,"time_precision":10,"idle_timeout_ms":1000,"idle_gap_ms":50,"content_type":"text/plain","gzip_query":"?z=gzip","token":{"entry":"cake"},"batch":{"max_bytes":51200,"interval_min_ms":2000,"interval_max_ms":10000,"interval_growth":2,"keepalive_max_bytes":60000,"compress_min_bytes":2048,"pending_max_bytes":1048576,"max_record_bytes":4194304,"retry_statuses":[408,429,500,502,503,504]},"limits":{"records_per_page":{"e":100000,"r":200000,"x":5000},"error_chars":200},"rrweb":{"sampling":{"mousemove":50,"scroll":150,"input":"last"}},"raw":{"events":["pointermove","pointerdown","pointerup","pointerover","mousemove","mousedown","mouseup","mouseover","click","dblclick","contextmenu","wheel","keydown","keyup","input","change","focus","blur","touchstart","touchend"],"target_events":["pointerdown","pointerup","click","mouseover","focus","blur","input","keydown","keyup","mousedown","mouseup","change","dblclick","contextmenu","wheel"],"target_selector":"a,button,input,select,textarea,label,summary,[role=button],[role=link]","geo_poll_ms":500,"dom_scan_delay_ms":5000,"dom_attr_names_max":8},"env":{"frame_history_writes":300,"frame_burst_writes":50,"frame_burst_gap_ms":20,"probe_attr":"data-cake-probe","cdp_rounds":3,"cdp_message":"cake probe","cdp_round_ms":100,"cdp_name_lookups_per_round":1.5,"stack_chars":400,"distinctive_globals":{"awesomium":["awesomium"],"cef":["RunPerfTest"],"cefsharp":["CefSharp"],"coachjs":["emit"],"fminer":["fmget_targets"],"geb":["geb"],"nightmare":["__nightmare","nightmare"],"phantomas":["__phantomas"],"phantomjs":["callPhantom","_phantom"],"rhino":["spawn"],"selenium":["_Selenium_IDE_Recorder","_selenium","calledSelenium"],"wdio":["wdioElectron"],"webdriver":["webdriver","__webdriverFunc","__lastWatirAlert","__lastWatirConfirm","__lastWatirPrompt","_WEBDRIVER_ELEM_CACHE","ChromeDriverw","__driver_evaluate","__webdriver_evaluate","__selenium_evaluate","__fxdriver_evaluate","__driver_unwrapped","__webdriver_unwrapped","__selenium_unwrapped","__fxdriver_unwrapped","__webdriver_script_func","__webdriver_script_fn"],"domAutomation":["domAutomation","domAutomationController"]},"global_patterns":{"selenium_cdc_window":["^cdc_|^\\$cdc_|^([a-z]){3}_.*_(Array|Promise|Symbol)$",""],"selenium_cdc_document":["^\\$cdc_|^\\$wdc_|selenium|webdriver|driver",""],"playwright":["^__pw|playwright","i"],"puppeteer":["^puppeteer_|^__puppeteer","i"]},"hook":{"methods":["getElementById","querySelector","querySelectorAll","getElementsByClassName"],"markers":{"pptr":"pptr:","utilityScript":"UtilityScript.","puppeteerEval":"__puppeteer_evaluation_script__"},"checks_max":2000,"hits_max":20,"arg_chars":60,"stack_frames":5}},"probes":{"timeout_ms":3000,"source_chars":60,"high_entropy_hints":["fullVersionList","platformVersion","architecture","model","bitness"],"native_getters":{"Navigator":["webdriver","userAgent","platform","languages","plugins","hardwareConcurrency"]},"native_methods":{"Permissions":["query"],"WebGLRenderingContext":["getParameter"],"Function":["toString"]},"fonts":["Ubuntu","Droid Sans","Cambria","DejaVu Sans","Liberation Sans"],"font_bases":["monospace","serif","sans-serif"],"font_sample":"mmmmmmmmmmlli0123456789","font_px":32},"botscent":{"sample_ms":3000},"privacy":{"mask_all_inputs":true,"private_selector":"[data-cake-private], input[type=password], [autocomplete^=\"cc-\"]","mask_text_selector":"[contenteditable]:not([contenteditable=\"false\"])","private_dropped_events":["keydown","keyup","input","change"],"private_dropped_fields":["s","r"],"key_classes":{"single_character":[{"class":"digit","pattern":"\\d","flags":""},{"class":"space","pattern":"\\s","flags":""},{"class":"letter","pattern":"[a-z]","flags":"i"}],"single_character_other":"symbol","named":{"Backspace":"delete","Delete":"delete","Enter":"enter","Tab":"tab","Shift":"modifier","Control":"modifier","Alt":"modifier","Meta":"modifier","CapsLock":"modifier","Unidentified":"unidentified","":"unidentified"},"prefixes":{"Arrow":"arrow"},"other":"other"}},"markers":{"version":"2026-11-13","every_ms":250,"host":{"tag":"DIV","parents":["body","html"],"display":"contents"},"attributes":["id","rel","href","data-codex-favicon-badge","data-browser-use-highlight","data-browser-use-interaction-highlight","data-browser-use-coordinate-highlight","data-stagehand-mask","data-skyvern-otp-box","unique_id"],"markers":[{"id":"claude-chrome.working","spots":[{"x":0.5,"top":12},{"x":0.5,"bottom":12}]},{"id":"claude-chrome.waiting","spots":[{"x":0.5,"top":56}]},{"id":"claude-chrome.bottom","spots":[{"x":0.5,"bottom":52}]},{"id":"claude-chrome.page-dom","ids":["claude-agent-stop-container","claude-agent-stop-button","claude-agent-glow-border","claude-phantom-cursor","claude-static-indicator-container"]},{"id":"claude-chrome.styles","ids":["claude-agent-animation-styles"]},{"id":"comet.overlay","selector":"[id^=\"pplx-agent\"]"},{"id":"chatgpt-chrome.badge","selector":"head [data-codex-favicon-badge], head link[rel~=\"icon\"][href*=\"data-codex-favicon-badge\"]"},{"id":"fellou.highlight","ids":["eko-highlight-container"]},{"id":"browser-use.highlight","ids":["browser-use-debug-highlights","browser-use-demo-panel"],"selector":"[data-browser-use-highlight], [data-browser-use-interaction-highlight], [data-browser-use-coordinate-highlight]"},{"id":"stagehand.overlay","ids":["__v3_cursor_overlay__"],"selector":"[data-stagehand-mask]"},{"id":"skyvern.overlay","ids":["boundingBoxContainer"],"selector":"[data-skyvern-otp-box]"},{"id":"skyvern.ids","selector":"[unique_id]"}]}}
  var RUNTIME = /*cake:runtime*/{}/*cake:runtime*/
  var BUILD = "fd9973afe7c8"
  var C = {}
  var SCOPE = {}
  // ---- static/rrweb-record.min.js
  ;(function () {
  var exports, module, define // the UMD wrapper below gives its export to SCOPE, not to a page loader
(function (g, f) {
    if ("object" == typeof exports && "object" == typeof module) {
      module.exports = f();
    } else if ("function" == typeof define && define.amd) {
      define("rrwebRecord", [], f);
    } else if ("object" == typeof exports) {
      exports["rrwebRecord"] = f();
    } else {
      g["rrwebRecord"] = f();
    }
  }(this, () => {
var exports = {};
var module = { exports };
"use strict";var sr=Object.defineProperty,ir=Object.defineProperties;var ar=Object.getOwnPropertyDescriptors;var ke=Object.getOwnPropertySymbols;var ut=Object.prototype.hasOwnProperty,ht=Object.prototype.propertyIsEnumerable;var dt=(e,t,r)=>t in e?sr(e,t,{enumerable:!0,configurable:!0,writable:!0,value:r}):e[t]=r,F=(e,t)=>{for(var r in t||(t={}))ut.call(t,r)&&dt(e,r,t[r]);if(ke)for(var r of ke(t))ht.call(t,r)&&dt(e,r,t[r]);return e},Te=(e,t)=>ir(e,ar(t));var ft=(e,t)=>{var r={};for(var n in e)ut.call(e,n)&&t.indexOf(n)<0&&(r[n]=e[n]);if(e!=null&&ke)for(var n of ke(e))t.indexOf(n)<0&&ht.call(e,n)&&(r[n]=e[n]);return r};var lr=Object.defineProperty,cr=(e,t,r)=>t in e?lr(e,t,{enumerable:!0,configurable:!0,writable:!0,value:r}):e[t]=r,g=(e,t,r)=>cr(e,typeof t!="symbol"?t+"":t,r),pt;Object.defineProperty(exports,Symbol.toStringTag,{value:"Module"});var I=(e=>(e[e.DomContentLoaded=0]="DomContentLoaded",e[e.Load=1]="Load",e[e.FullSnapshot=2]="FullSnapshot",e[e.IncrementalSnapshot=3]="IncrementalSnapshot",e[e.Meta=4]="Meta",e[e.Custom=5]="Custom",e[e.Plugin=6]="Plugin",e[e.Asset=7]="Asset",e[e.Annotation=8]="Annotation",e))(I||{}),R=(e=>(e[e.Mutation=0]="Mutation",e[e.MouseMove=1]="MouseMove",e[e.MouseInteraction=2]="MouseInteraction",e[e.Scroll=3]="Scroll",e[e.ViewportResize=4]="ViewportResize",e[e.Input=5]="Input",e[e.TouchMove=6]="TouchMove",e[e.MediaInteraction=7]="MediaInteraction",e[e.StyleSheetRule=8]="StyleSheetRule",e[e.CanvasMutation=9]="CanvasMutation",e[e.Font=10]="Font",e[e.Log=11]="Log",e[e.Drag=12]="Drag",e[e.StyleDeclaration=13]="StyleDeclaration",e[e.Selection=14]="Selection",e[e.AdoptedStyleSheet=15]="AdoptedStyleSheet",e[e.CustomElement=16]="CustomElement",e))(R||{}),H=(e=>(e[e.MouseUp=0]="MouseUp",e[e.MouseDown=1]="MouseDown",e[e.Click=2]="Click",e[e.ContextMenu=3]="ContextMenu",e[e.DblClick=4]="DblClick",e[e.Focus=5]="Focus",e[e.Blur=6]="Blur",e[e.TouchStart=7]="TouchStart",e[e.TouchMove_Departed=8]="TouchMove_Departed",e[e.TouchEnd=9]="TouchEnd",e[e.TouchCancel=10]="TouchCancel",e))(H||{}),te=(e=>(e[e.Mouse=0]="Mouse",e[e.Pen=1]="Pen",e[e.Touch=2]="Touch",e))(te||{}),ge=(e=>(e[e["2D"]=0]="2D",e[e.WebGL=1]="WebGL",e[e.WebGL2=2]="WebGL2",e))(ge||{}),de=(e=>(e[e.Play=0]="Play",e[e.Pause=1]="Pause",e[e.Seeked=2]="Seeked",e[e.VolumeChange=3]="VolumeChange",e[e.RateChange=4]="RateChange",e))(de||{}),A=(e=>(e[e.Document=0]="Document",e[e.DocumentType=1]="DocumentType",e[e.Element=2]="Element",e[e.Text=3]="Text",e[e.CDATA=4]="CDATA",e[e.Comment=5]="Comment",e))(A||{});const mt={Node:["childNodes","parentNode","parentElement","textContent","ownerDocument","firstChild","lastChild","nextSibling","previousSibling"],ShadowRoot:["host","styleSheets"],Element:["shadowRoot","querySelector","querySelectorAll"],MutationObserver:[]},gt={Node:["contains","getRootNode"],ShadowRoot:["getSelection"],Element:[],MutationObserver:["constructor"]},we={},Ze={};let yt=0;const dr=()=>!!globalThis.Zone;function nt(e){if(we[e])return we[e];const t=globalThis[e],r=t.prototype,n=e in mt?mt[e]:void 0,o=!!(n&&n.every(c=>{var i,u;return!!((u=(i=Object.getOwnPropertyDescriptor(r,c))==null?void 0:i.get)!=null&&u.toString().includes("[native code]"))})),s=e in gt?gt[e]:void 0,a=!!(s&&s.every(c=>{var i;return typeof r[c]=="function"&&((i=r[c])==null?void 0:i.toString().includes("[native code]"))}));if(o&&a&&!dr())return we[e]=t.prototype,t.prototype;try{const c=document.createElement("iframe");c.style.display="none",document.body.appendChild(c);const i=c.contentWindow;if(!i)return t.prototype;const u=i[e].prototype;if(!u)return c.remove(),r;const d=navigator.userAgent;return d.includes("Safari")&&!d.includes("Chrome")?(c.classList.add("rr-block"),c.setAttribute("__rrwebUntaintedMutationObserver",""),Ze[e]=()=>c.remove()):c.remove(),we[e]=u}catch(c){return r}}const qe={};function G(e,t,r){var n,o;const s=(n=qe[e])==null?void 0:n[r];if(s)return s.call(t);const a=nt(e),c=(o=Object.getOwnPropertyDescriptor(a,r))==null?void 0:o.get;return c?((qe[e]||(qe[e]={}))[r]=c,c.call(t)):t[r]}const Xe={};function Tt(e,t,r){const n=`${e}.${String(r)}`;if(Xe[n])return Xe[n].bind(t);const s=nt(e)[r];return typeof s!="function"?t[r]:(Xe[n]=s,s.bind(t))}function ur(e){return G("Node",e,"ownerDocument")}function hr(e){return G("Node",e,"childNodes")}function fr(e){return G("Node",e,"parentNode")}function pr(e){return G("Node",e,"parentElement")}function mr(e){return G("Node",e,"textContent")}function gr(e){return G("Node",e,"firstChild")}function yr(e){return G("Node",e,"lastChild")}function Sr(e){return G("Node",e,"nextSibling")}function br(e){return G("Node",e,"previousSibling")}function wr(e,t){return Tt("Node",e,"contains")(t)}function Cr(e){return Tt("Node",e,"getRootNode")()}function Mr(e){return!e||!("host"in e)?null:G("ShadowRoot",e,"host")}function vr(e){return e.styleSheets}function Ir(e){return!e||!("shadowRoot"in e)?null:G("Element",e,"shadowRoot")}function Rr(e,t){return G("Element",e,"querySelector")(t)}function Or(e,t){return G("Element",e,"querySelectorAll")(t)}function Dt(){const e=nt("MutationObserver");yt++;let t=!1;return[e.constructor,()=>{if(t||(t=!0,--yt!==0))return;const r=Ze.MutationObserver;if(r)try{r()}finally{delete we.MutationObserver,delete Ze.MutationObserver}}]}let Ie=Date.now;/[1-9][0-9]{12}/.test(Date.now().toString())||(Ie=()=>new Date().getTime());function ae(e,t,r){try{if(!(t in e))return()=>{};const n=e[t],o=r(n);return typeof o=="function"&&(o.prototype=o.prototype||{},Object.defineProperties(o,{__rrweb_original__:{enumerable:!1,value:n}})),e[t]=o,()=>{e[t]=n}}catch(n){return()=>{}}}const b={ownerDocument:ur,childNodes:hr,parentNode:fr,parentElement:pr,textContent:mr,firstChild:gr,lastChild:yr,nextSibling:Sr,previousSibling:br,contains:wr,getRootNode:Cr,host:Mr,styleSheets:vr,shadowRoot:Ir,querySelector:Rr,querySelectorAll:Or,nowTimestamp:Ie,mutationObserverCtor:Dt,patch:ae};function xt(e){return e.nodeType===e.ELEMENT_NODE}function Ce(e){const t=e&&"host"in e&&"mode"in e&&b.host(e)||null;return!!(t&&"shadowRoot"in t&&b.shadowRoot(t)===e)}function Me(e){return Object.prototype.toString.call(e)==="[object ShadowRoot]"}function Nr(e){return e.includes(" background-clip: text;")&&!e.includes(" -webkit-background-clip: text;")&&(e=e.replace(/\sbackground-clip:\s*text;/g," -webkit-background-clip: text; background-clip: text;")),e}function Er(e){const{cssText:t}=e;if(t.split('"').length<3)return t;const r=["@import",`url(${JSON.stringify(e.href)})`];return e.layerName===""?r.push("layer"):e.layerName&&r.push(`layer(${e.layerName})`),e.supportsText&&r.push(`supports(${e.supportsText})`),e.media.length&&r.push(e.media.mediaText),r.join(" ")+";"}function Qe(e){try{const t=e.rules||e.cssRules;if(!t)return null;let r=e.href;!r&&e.ownerNode&&(r=e.ownerNode.baseURI);const n=Array.from(t,o=>Lt(o,r)).join("");return Nr(n)}catch(t){return null}}function Lt(e,t){if(Tr(e)){let r;try{r=Qe(e.styleSheet)||Er(e)}catch(n){r=e.cssText}return e.styleSheet.href?Ue(r,e.styleSheet.href):r}else{let r=e.cssText;return Dr(e)&&e.selectorText.includes(":")&&(r=kr(r)),t?Ue(r,t):r}}function kr(e){const t=/(\[(?:[\w-]+)[^\\])(:(?:[\w-]+)\])/gm;return e.replace(t,"$1\\$2")}function Tr(e){return"styleSheet"in e}function Dr(e){return"selectorText"in e}class At{constructor(){g(this,"idNodeMap",new Map),g(this,"nodeMetaMap",new WeakMap)}getId(t){var r;if(!t)return-1;const n=(r=this.getMeta(t))==null?void 0:r.id;return n!=null?n:-1}getNode(t){return this.idNodeMap.get(t)||null}getIds(){return Array.from(this.idNodeMap.keys())}getMeta(t){return this.nodeMetaMap.get(t)||null}removeNodeFromMap(t){const r=this.getId(t);this.idNodeMap.delete(r),t.childNodes&&t.childNodes.forEach(o=>this.removeNodeFromMap(o));const n=b.shadowRoot(t);n&&this.removeNodeFromMap(n)}has(t){return this.idNodeMap.has(t)}hasNode(t){return this.nodeMetaMap.has(t)}add(t,r){const n=r.id;this.idNodeMap.set(n,t),this.nodeMetaMap.set(t,r)}replace(t,r){const n=this.getNode(t);if(n){const o=this.nodeMetaMap.get(n);o&&this.nodeMetaMap.set(r,o)}this.idNodeMap.set(t,r)}reset(){this.idNodeMap=new Map,this.nodeMetaMap=new WeakMap}}function xr(){return new At}function Pe({element:e,maskInputOptions:t,tagName:r,type:n,value:o,maskInputFn:s}){let a=o||"";const c=n&&oe(n);return(t[r.toLowerCase()]||c&&t[c])&&(s?a=s(a,e):a="*".repeat(a.length)),a}function oe(e){return e.toLowerCase()}const St="__rrweb_original__";function Lr(e){const t=e.getContext("2d");if(!t)return!0;const r=50;for(let n=0;n<e.width;n+=r)for(let o=0;o<e.height;o+=r){const s=t.getImageData,a=St in s?s[St]:s;if(new Uint32Array(a.call(t,n,o,Math.min(r,e.width-n),Math.min(r,e.height-o)).data.buffer).some(i=>i!==0))return!1}return!0}function We(e){const t=e.type;return e.hasAttribute("data-rr-is-password")?"password":t?oe(t):null}function _t(e,t){var s;let r;try{r=new URL(e,t!=null?t:window.location.href)}catch(a){return null}const n=/\.([0-9a-z]+)(?:$)/i,o=r.pathname.match(n);return(s=o==null?void 0:o[1])!=null?s:null}function Ar(e){let t="";return e.indexOf("//")>-1?t=e.split("/").slice(0,3).join("/"):t=e.split("/")[0],t=t.split("?")[0],t}const _r=/url\((?:(')([^']*)'|(")(.*?)"|([^)]*))\)/gm,Fr=/^(?:[a-z+]+:)?\/\//i,Pr=/^www\..*/i,Wr=/^(data:)([^,]*),(.*)/i;function Ue(e,t){return(e||"").replace(_r,(r,n,o,s,a,c)=>{const i=o||a||c,u=n||s||"";if(!i)return r;if(Fr.test(i)||Pr.test(i))return`url(${u}${i}${u})`;if(Wr.test(i))return`url(${u}${i}${u})`;if(i[0]==="/")return`url(${u}${Ar(t)+i}${u})`;const d=i.split("#")[0],h=i.substring(d.length),p=t.split("#")[0].split("/"),f=d.split("/");p.pop();for(const m of f)m!=="."&&(m===".."?p.pop():p.push(m));return`url(${u}${p.join("/")}${h}${u})`})}const Ft="(?:/\\*[^*]*\\*/)|[\\s;]",Ur=new RegExp(`${Ft}|\\b(0)px?`,"g"),Br=new RegExp(Ft,"g");function De(e,t=!1){return t?e.replace(Br,""):e.replace(Ur,"$1")}function zr(e,t,r=!1){const n=Array.from(t.childNodes),o=[];let s=0;if(n.length>1&&e&&typeof e=="string"){let a=De(e,r);const c=a.length/e.length;for(let i=1;i<n.length;i++)if(n[i].textContent&&typeof n[i].textContent=="string"){const u=De(n[i].textContent,r),d=100;let h=3;for(;h<u.length&&(u[h].match(/[a-zA-Z0-9]/)||u.indexOf(u.substring(0,h),1)!==-1);h++);for(;h<u.length;h++){let p=u.substring(0,h),f=a.split(p),m=-1;if(f.length===2)m=f[0].length;else if(f.length>2&&f[0]===""&&n[i-1].textContent!=="")m=a.indexOf(p,1);else if(f.length===1){if(p=p.substring(0,p.length-1),f=a.split(p),f.length<=1)return o.push(e),o;h=d+1}else h===u.length-1&&(m=a.indexOf(p));if(f.length>=2&&h>d){const l=n[i-1].textContent;if(l&&typeof l=="string"){const S=De(l).length;m=a.indexOf(p,S)}m===-1&&(m=f[0].length)}if(m!==-1){let l=Math.floor(m/c);for(;l>0&&l<e.length;){if(s+=1,s>50*n.length)return o.push(e),o;const S=De(e.substring(0,l),r);if(S.length===m){o.push(e.substring(0,l)),e=e.substring(l),a=a.substring(m);break}else S.length<m?l+=Math.max(1,Math.floor((m-S.length)/c)):l-=Math.max(1,Math.floor((S.length-m)*c))}break}}}}return o.push(e),o}function Hr(e,t){return zr(e,t).join("/* rr_split */")}let Gr=1;const jr=new RegExp("[^a-z0-9-_:]"),Be=-2;function Pt(){return Gr++}function Vr(e){if(e instanceof HTMLFormElement)return"form";const t=oe(e.tagName);return jr.test(t)?"div":t}let ce,bt;const $r=/^[^ \t\n\r\u000c]+/,qr=/^[, \t\n\r\u000c]+/;function Xr(e,t){if(t.trim()==="")return t;let r=0;function n(s){let a;const c=s.exec(t.substring(r));return c?(a=c[0],r+=a.length,a):""}const o=[];for(;n(qr),!(r>=t.length);){let s=n($r);if(s.slice(-1)===",")s=he(e,s.substring(0,s.length-1)),o.push(s);else{let a="";s=he(e,s);let c=!1;for(;;){const i=t.charAt(r);if(i===""){o.push((s+a).trim());break}else if(c)i===")"&&(c=!1);else if(i===","){r+=1,o.push((s+a).trim());break}else i==="("&&(c=!0);a+=i,r+=1}}}return o.join(", ")}const wt=new WeakMap;function he(e,t){return!t||t.trim()===""?t:ot(e,t)}function Yr(e){return!!(e.tagName==="svg"||e.ownerSVGElement)}function ot(e,t){let r=wt.get(e);if(r||(r=e.createElement("a"),wt.set(e,r)),!t)t="";else if(t.startsWith("blob:")||t.startsWith("data:"))return t;return r.setAttribute("href",t),r.href}function Wt(e,t,r,n){return n&&(r==="src"||r==="href"&&!(t==="use"&&n[0]==="#")||r==="xlink:href"&&n[0]!=="#"||r==="background"&&["table","td","th"].includes(t)?he(e,n):r==="srcset"?Xr(e,n):r==="style"?Ue(n,ot(e)):t==="object"&&r==="data"?he(e,n):n)}function Ut(e,t,r){return["video","audio"].includes(e)&&oe(t)==="autoplay"}function Jr(e,t,r){try{if(typeof t=="string"){if(e.classList.contains(t))return!0}else for(let n=e.classList.length;n--;){const o=e.classList[n];if(t.test(o))return!0}if(r)return e.matches(r)}catch(n){}return!1}function ze(e,t,r){if(!e)return!1;if(e.nodeType!==e.ELEMENT_NODE)return r?ze(b.parentNode(e),t,r):!1;for(let n=e.classList.length;n--;){const o=e.classList[n];if(t.test(o))return!0}return r?ze(b.parentNode(e),t,r):!1}function Bt(e,t,r,n){let o;if(xt(e)){if(o=e,!b.childNodes(o).length)return!1}else{if(b.parentElement(e)===null)return!1;o=b.parentElement(e)}try{if(typeof t=="string"){if(n){if(o.closest(`.${t}`))return!0}else if(o.classList.contains(t))return!0}else if(ze(o,t,n))return!0;if(r){if(n){if(o.closest(r))return!0}else if(o.matches(r))return!0}}catch(s){}return!1}function Zr(e,t,r){const n=e.contentWindow;if(!n)return;let o=!1,s;try{s=n.document.readyState}catch(c){return}if(s!=="complete"){const c=setTimeout(()=>{o||(t(),o=!0)},r);e.addEventListener("load",()=>{clearTimeout(c),o=!0,t()});return}const a="about:blank";if(n.location.href!==a||e.src===a||e.src==="")return setTimeout(t,0),e.addEventListener("load",t);e.addEventListener("load",t)}function Qr(e,t,r){let n=!1,o;try{o=e.sheet}catch(a){return}if(o)return;const s=setTimeout(()=>{n||(t(),n=!0)},r);e.addEventListener("load",()=>{clearTimeout(s),n=!0,t()})}function Kr(e,t){const{doc:r,mirror:n,blockClass:o,blockSelector:s,needsMask:a,inlineStylesheet:c,maskInputOptions:i={},maskTextFn:u,maskInputFn:d,dataURLOptions:h={},inlineImages:p,recordCanvas:f,keepIframeSrcFn:m,newlyAddedElement:l=!1,cssCaptured:S=!1}=t,w=en(r,n);switch(e.nodeType){case e.DOCUMENT_NODE:return e.compatMode!=="CSS1Compat"?{type:A.Document,childNodes:[],compatMode:e.compatMode}:{type:A.Document,childNodes:[]};case e.DOCUMENT_TYPE_NODE:return{type:A.DocumentType,name:e.name,publicId:e.publicId,systemId:e.systemId,rootId:w};case e.ELEMENT_NODE:return rn(e,{doc:r,blockClass:o,blockSelector:s,inlineStylesheet:c,maskInputOptions:i,maskInputFn:d,dataURLOptions:h,inlineImages:p,recordCanvas:f,keepIframeSrcFn:m,newlyAddedElement:l,rootId:w});case e.TEXT_NODE:return tn(e,{doc:r,needsMask:a,maskTextFn:u,rootId:w,cssCaptured:S});case e.CDATA_SECTION_NODE:return{type:A.CDATA,textContent:"",rootId:w};case e.COMMENT_NODE:return{type:A.Comment,textContent:b.textContent(e)||"",rootId:w};default:return!1}}function en(e,t){if(!t.hasNode(e))return;const r=t.getId(e);return r===1?void 0:r}function tn(e,t){const{needsMask:r,maskTextFn:n,rootId:o,cssCaptured:s}=t,a=b.parentNode(e),c=a&&a.tagName;let i="";const u=c==="STYLE"?!0:void 0,d=c==="SCRIPT"?!0:void 0;return d?i="SCRIPT_PLACEHOLDER":s||(i=b.textContent(e),u&&i&&(i=Ue(i,ot(t.doc)))),!u&&!d&&i&&r&&(i=n?n(i,b.parentElement(e)):i.replace(/[\S]/g,"*")),{type:A.Text,textContent:i||"",rootId:o}}function rn(e,t){const{doc:r,blockClass:n,blockSelector:o,inlineStylesheet:s,maskInputOptions:a={},maskInputFn:c,dataURLOptions:i={},inlineImages:u,recordCanvas:d,keepIframeSrcFn:h,newlyAddedElement:p=!1,rootId:f}=t,m=Jr(e,n,o),l=Vr(e);let S={};const w=e.attributes.length;for(let y=0;y<w;y++){const M=e.attributes[y];Ut(l,M.name,M.value)||(S[M.name]=Wt(r,l,oe(M.name),M.value))}if(l==="link"&&s){const y=Array.from(r.styleSheets).find(D=>D.href===e.href);let M=null;y&&(M=Qe(y)),M&&(delete S.rel,delete S.href,S._cssText=M)}if(l==="style"&&e.sheet){let y=Qe(e.sheet);y&&(e.childNodes.length>1&&(y=Hr(y,e)),S._cssText=y)}if(["input","textarea","select"].includes(l)){const y=e.value,M=e.checked;S.type!=="radio"&&S.type!=="checkbox"&&S.type!=="submit"&&S.type!=="button"&&y?S.value=Pe({element:e,type:We(e),tagName:l,value:y,maskInputOptions:a,maskInputFn:c}):M&&(S.checked=M)}if(l==="option"&&(e.selected&&!a.select?S.selected=!0:delete S.selected),l==="dialog"&&e.open&&(S.rr_open_mode=e.matches("dialog:modal")?"modal":"non-modal"),l==="canvas"&&d){if(e.__context==="2d")Lr(e)||(S.rr_dataURL=e.toDataURL(i.type,i.quality));else if(!("__context"in e)){const y=e.toDataURL(i.type,i.quality),M=r.createElement("canvas");M.width=e.width,M.height=e.height;const D=M.toDataURL(i.type,i.quality);y!==D&&(S.rr_dataURL=y)}}if(l==="img"&&u){ce||(ce=r.createElement("canvas"),bt=ce.getContext("2d"));const y=e,M=y.currentSrc||y.getAttribute("src")||"<unknown-src>",D=y.crossOrigin,L=()=>{y.removeEventListener("load",L);try{ce.width=y.naturalWidth,ce.height=y.naturalHeight,bt.drawImage(y,0,0),S.rr_dataURL=ce.toDataURL(i.type,i.quality)}catch(W){if(y.crossOrigin!=="anonymous"){y.crossOrigin="anonymous",y.complete&&y.naturalWidth!==0?L():y.addEventListener("load",L);return}else console.warn(`Cannot inline img src=${M}! Error: ${W}`)}y.crossOrigin==="anonymous"&&(D?S.crossOrigin=D:y.removeAttribute("crossorigin"))};y.complete&&y.naturalWidth!==0?L():y.addEventListener("load",L)}if(["audio","video"].includes(l)){const y=S;y.rr_mediaState=e.paused?"paused":"played",y.rr_mediaCurrentTime=e.currentTime,y.rr_mediaPlaybackRate=e.playbackRate,y.rr_mediaMuted=e.muted,y.rr_mediaLoop=e.loop,y.rr_mediaVolume=e.volume}if(p||(e.scrollLeft&&(S.rr_scrollLeft=e.scrollLeft),e.scrollTop&&(S.rr_scrollTop=e.scrollTop)),m){const{width:y,height:M}=e.getBoundingClientRect();S={class:S.class,rr_width:`${y}px`,rr_height:`${M}px`}}l==="iframe"&&!h(S.src)&&(e.contentDocument||(S.rr_src=S.src),delete S.src);let C;try{customElements.get(l)&&(C=!0)}catch(y){}return{type:A.Element,tagName:l,attributes:S,childNodes:[],isSVG:Yr(e)||void 0,needBlock:m,rootId:f,isCustom:C}}function T(e){return e==null?"":e.toLowerCase()}function zt(e){return e===!0||e==="all"?{script:!0,comment:!0,headFavicon:!0,headWhitespace:!0,headMetaSocial:!0,headMetaRobots:!0,headMetaHttpEquiv:!0,headMetaVerification:!0,headMetaAuthorship:e==="all",headMetaDescKeywords:e==="all",headTitleMutations:e==="all"}:e||{}}function nn(e,t){if(t.comment&&e.type===A.Comment)return!0;if(e.type===A.Element){if(t.script&&(e.tagName==="script"||e.tagName==="link"&&(e.attributes.rel==="preload"&&e.attributes.as==="script"||e.attributes.rel==="modulepreload")||e.tagName==="link"&&e.attributes.rel==="prefetch"&&typeof e.attributes.href=="string"&&_t(e.attributes.href)==="js"))return!0;if(t.headFavicon&&(e.tagName==="link"&&e.attributes.rel==="shortcut icon"||e.tagName==="meta"&&(T(e.attributes.name).match(/^msapplication-tile(image|color)$/)||T(e.attributes.name)==="application-name"||T(e.attributes.rel)==="icon"||T(e.attributes.rel)==="apple-touch-icon"||T(e.attributes.rel)==="shortcut icon")))return!0;if(e.tagName==="meta"){if(t.headMetaDescKeywords&&T(e.attributes.name).match(/^description|keywords$/))return!0;if(t.headMetaSocial&&(T(e.attributes.property).match(/^(og|twitter|fb):/)||T(e.attributes.name).match(/^(og|twitter):/)||T(e.attributes.name)==="pinterest"))return!0;if(t.headMetaRobots&&(T(e.attributes.name)==="robots"||T(e.attributes.name)==="googlebot"||T(e.attributes.name)==="bingbot"))return!0;if(t.headMetaHttpEquiv&&e.attributes["http-equiv"]!==void 0)return!0;if(t.headMetaAuthorship&&(T(e.attributes.name)==="author"||T(e.attributes.name)==="generator"||T(e.attributes.name)==="framework"||T(e.attributes.name)==="publisher"||T(e.attributes.name)==="progid"||T(e.attributes.property).match(/^article:/)||T(e.attributes.property).match(/^product:/)))return!0;if(t.headMetaVerification&&(T(e.attributes.name)==="google-site-verification"||T(e.attributes.name)==="yandex-verification"||T(e.attributes.name)==="csrf-token"||T(e.attributes.name)==="p:domain_verify"||T(e.attributes.name)==="verify-v1"||T(e.attributes.name)==="verification"||T(e.attributes.name)==="shopify-checkout-api-token"))return!0}}return!1}function fe(e,t){const{doc:r,mirror:n,blockClass:o,blockSelector:s,maskTextClass:a,maskTextSelector:c,skipChild:i=!1,inlineStylesheet:u=!0,maskInputOptions:d={},maskTextFn:h,maskInputFn:p,slimDOMOptions:f,dataURLOptions:m={},inlineImages:l=!1,recordCanvas:S=!1,onSerialize:w,onIframeLoad:C,iframeLoadTimeout:y=5e3,onStylesheetLoad:M,stylesheetLoadTimeout:D=5e3,keepIframeSrcFn:L=()=>!1,newlyAddedElement:W=!1,cssCaptured:Z=!1}=t;let{needsMask:j}=t,{preserveWhiteSpace:Y=!0}=t;j||(j=Bt(e,a,c,j===void 0));const V=Kr(e,{doc:r,mirror:n,blockClass:o,blockSelector:s,needsMask:j,inlineStylesheet:u,maskInputOptions:d,maskTextFn:h,maskInputFn:p,dataURLOptions:m,inlineImages:l,recordCanvas:S,keepIframeSrcFn:L,newlyAddedElement:W,cssCaptured:Z});if(!V)return console.warn(e,"not serialized"),null;let Q;n.hasNode(e)?Q=n.getId(e):nn(V,f)||!Y&&V.type===A.Text&&!V.textContent.replace(/^\s+|\s+$/gm,"").length?Q=Be:Q=Pt();const N=Object.assign(V,{id:Q});if(n.add(e,N),Q===Be)return null;w&&w(e);let Se=!i;if(N.type===A.Element){Se=Se&&!N.needBlock,delete N.needBlock;const _=b.shadowRoot(e);_&&Me(_)&&(N.isShadowHost=!0)}if((N.type===A.Document||N.type===A.Element)&&Se){f.headWhitespace&&N.type===A.Element&&N.tagName==="head"&&(Y=!1);const _={doc:r,mirror:n,blockClass:o,blockSelector:s,needsMask:j,maskTextClass:a,maskTextSelector:c,skipChild:i,inlineStylesheet:u,maskInputOptions:d,maskTextFn:h,maskInputFn:p,slimDOMOptions:f,dataURLOptions:m,inlineImages:l,recordCanvas:S,preserveWhiteSpace:Y,onSerialize:w,onIframeLoad:C,iframeLoadTimeout:y,onStylesheetLoad:M,stylesheetLoadTimeout:D,keepIframeSrcFn:L,cssCaptured:!1};if(!(N.type===A.Element&&N.tagName==="textarea"&&N.attributes.value!==void 0)){N.type===A.Element&&N.attributes._cssText!==void 0&&typeof N.attributes._cssText=="string"&&(_.cssCaptured=!0);for(const se of Array.from(b.childNodes(e))){const K=fe(se,_);K&&N.childNodes.push(K)}}let $=null;if(xt(e)&&($=b.shadowRoot(e)))for(const se of Array.from(b.childNodes($))){const K=fe(se,_);K&&(Me($)&&(K.isShadow=!0),N.childNodes.push(K))}}const be=b.parentNode(e);return be&&Ce(be)&&Me(be)&&(N.isShadow=!0),N.type===A.Element&&N.tagName==="iframe"&&Zr(e,()=>{const _=e.contentDocument;if(_&&C){const $=fe(_,{doc:_,mirror:n,blockClass:o,blockSelector:s,needsMask:j,maskTextClass:a,maskTextSelector:c,skipChild:!1,inlineStylesheet:u,maskInputOptions:d,maskTextFn:h,maskInputFn:p,slimDOMOptions:f,dataURLOptions:m,inlineImages:l,recordCanvas:S,preserveWhiteSpace:Y,onSerialize:w,onIframeLoad:C,iframeLoadTimeout:y,onStylesheetLoad:M,stylesheetLoadTimeout:D,keepIframeSrcFn:L});$&&C(e,$)}},y),N.type===A.Element&&N.tagName==="link"&&typeof N.attributes.rel=="string"&&(N.attributes.rel==="stylesheet"||N.attributes.rel==="preload"&&typeof N.attributes.href=="string"&&_t(N.attributes.href)==="css")&&Qr(e,()=>{if(M){const _=fe(e,{doc:r,mirror:n,blockClass:o,blockSelector:s,needsMask:j,maskTextClass:a,maskTextSelector:c,skipChild:!1,inlineStylesheet:u,maskInputOptions:d,maskTextFn:h,maskInputFn:p,slimDOMOptions:f,dataURLOptions:m,inlineImages:l,recordCanvas:S,preserveWhiteSpace:Y,onSerialize:w,onIframeLoad:C,iframeLoadTimeout:y,onStylesheetLoad:M,stylesheetLoadTimeout:D,keepIframeSrcFn:L});_&&M(e,_)}},D),N}function on(e,t){const{mirror:r=new At,blockClass:n="rr-block",blockSelector:o=null,maskTextClass:s="rr-mask",maskTextSelector:a=null,inlineStylesheet:c=!0,inlineImages:i=!1,recordCanvas:u=!1,maskAllInputs:d=!1,maskTextFn:h,maskInputFn:p,slimDOM:f=!1,dataURLOptions:m,preserveWhiteSpace:l,onSerialize:S,onIframeLoad:w,iframeLoadTimeout:C,onStylesheetLoad:y,stylesheetLoadTimeout:M,keepIframeSrcFn:D=()=>!1}=t,L=d===!0?{color:!0,date:!0,"datetime-local":!0,email:!0,month:!0,number:!0,range:!0,search:!0,tel:!0,text:!0,time:!0,url:!0,week:!0,textarea:!0,select:!0,password:!0}:d===!1?{password:!0}:d,W=zt(f);return fe(e,{doc:e,mirror:r,blockClass:n,blockSelector:o,maskTextClass:s,maskTextSelector:a,skipChild:!1,inlineStylesheet:c,maskInputOptions:L,maskTextFn:h,maskInputFn:p,slimDOMOptions:W,dataURLOptions:m,inlineImages:i,recordCanvas:u,preserveWhiteSpace:l,onSerialize:S,onIframeLoad:w,iframeLoadTimeout:C,onStylesheetLoad:y,stylesheetLoadTimeout:M,keepIframeSrcFn:D,newlyAddedElement:!1})}class st{constructor(...t){g(this,"parentElement",null),g(this,"parentNode",null),g(this,"ownerDocument"),g(this,"firstChild",null),g(this,"lastChild",null),g(this,"previousSibling",null),g(this,"nextSibling",null),g(this,"ELEMENT_NODE",1),g(this,"TEXT_NODE",3),g(this,"nodeType"),g(this,"nodeName"),g(this,"RRNodeType")}get childNodes(){const t=[];let r=this.firstChild;for(;r;)t.push(r),r=r.nextSibling;return t}contains(t){if(t instanceof st){if(t.ownerDocument!==this.ownerDocument)return!1;if(t===this)return!0}else return!1;for(;t.parentNode;){if(t.parentNode===this)return!0;t=t.parentNode}return!1}appendChild(t){throw new Error("RRDomException: Failed to execute 'appendChild' on 'RRNode': This RRNode type does not support this method.")}insertBefore(t,r){throw new Error("RRDomException: Failed to execute 'insertBefore' on 'RRNode': This RRNode type does not support this method.")}removeChild(t){throw new Error("RRDomException: Failed to execute 'removeChild' on 'RRNode': This RRNode type does not support this method.")}toString(){return"RRNode"}}function P(e,t,r=document){const n={capture:!0,passive:!0};return r.addEventListener(e,t,n),()=>r.removeEventListener(e,t,n)}const ue=`Please stop import mirror directly. Instead of that,\r
now you can use replayer.getMirror() to access the mirror instance of a replayer,\r
or you can use record.mirror to access the mirror instance during recording.`;let Ct={map:{},getId(){return console.error(ue),-1},getNode(){return console.error(ue),null},removeNodeFromMap(){console.error(ue)},has(){return console.error(ue),!1},reset(){console.error(ue)}};typeof window!="undefined"&&window.Proxy&&window.Reflect&&(Ct=new Proxy(Ct,{get(e,t,r){return t==="map"&&console.error(ue),Reflect.get(e,t,r)}}));function Re(e,t,r={}){let n=null,o=0;return function(...s){const a=Date.now();!o&&r.leading===!1&&(o=a);const c=t-(a-o),i=this;c<=0||c>t?(n&&(clearTimeout(n),n=null),o=a,e.apply(i,s)):!n&&r.trailing!==!1&&(n=setTimeout(()=>{o=r.leading===!1?0:Date.now(),n=null,e.apply(i,s)},c))}}function Ge(e,t,r,n,o=window){const s=o.Object.getOwnPropertyDescriptor(e,t);return o.Object.defineProperty(e,t,n?r:{set(a){setTimeout(()=>{r.set.call(this,a)},0),s&&s.set&&s.set.call(this,a)}}),()=>Ge(e,t,s||{},!0)}function Ht(e){var t,r,n,o;const s=e.document;return{left:s.scrollingElement?s.scrollingElement.scrollLeft:e.pageXOffset!==void 0?e.pageXOffset:s.documentElement.scrollLeft||(s==null?void 0:s.body)&&((t=b.parentElement(s.body))==null?void 0:t.scrollLeft)||((r=s==null?void 0:s.body)==null?void 0:r.scrollLeft)||0,top:s.scrollingElement?s.scrollingElement.scrollTop:e.pageYOffset!==void 0?e.pageYOffset:(s==null?void 0:s.documentElement.scrollTop)||(s==null?void 0:s.body)&&((n=b.parentElement(s.body))==null?void 0:n.scrollTop)||((o=s==null?void 0:s.body)==null?void 0:o.scrollTop)||0}}function Gt(){return window.innerHeight||document.documentElement&&document.documentElement.clientHeight||document.body&&document.body.clientHeight}function jt(){return window.innerWidth||document.documentElement&&document.documentElement.clientWidth||document.body&&document.body.clientWidth}function Vt(e){return e?e.nodeType===e.ELEMENT_NODE?e:b.parentElement(e):null}function U(e,t,r,n){if(!e)return!1;const o=Vt(e);if(!o)return!1;try{if(typeof t=="string"){if(o.classList.contains(t)||n&&o.closest("."+t)!==null)return!0}else if(ze(o,t,n))return!0}catch(s){}return!!(r&&(o.matches(r)||n&&o.closest(r)!==null))}function sn(e,t){return t.getId(e)!==-1}function Ye(e,t,r){return e.tagName==="TITLE"&&r.headTitleMutations?!0:t.getId(e)===Be}function $t(e,t){if(Ce(e))return!1;const r=t.getId(e);if(!t.has(r))return!0;const n=b.parentNode(e);return n&&n.nodeType===e.DOCUMENT_NODE?!1:n?$t(n,t):!0}function Ke(e){return!!e.changedTouches}function an(e=window){"NodeList"in e&&!e.NodeList.prototype.forEach&&(e.NodeList.prototype.forEach=Array.prototype.forEach),"DOMTokenList"in e&&!e.DOMTokenList.prototype.forEach&&(e.DOMTokenList.prototype.forEach=Array.prototype.forEach)}function qt(e,t){return!!(e.nodeName==="IFRAME"&&t.getMeta(e))}function Xt(e,t){return!!(e.nodeName==="LINK"&&e.nodeType===e.ELEMENT_NODE&&e.getAttribute&&e.getAttribute("rel")==="stylesheet"&&t.getMeta(e))}function et(e){return e?e instanceof st&&"shadowRoot"in e?!!e.shadowRoot:!!b.shadowRoot(e):!1}class ln{constructor(){g(this,"id",1),g(this,"styleIDMap",new WeakMap),g(this,"idStyleMap",new Map)}getId(t){var r;return(r=this.styleIDMap.get(t))!=null?r:-1}has(t){return this.styleIDMap.has(t)}add(t,r){if(this.has(t))return this.getId(t);let n;return r===void 0?n=this.id++:n=r,this.styleIDMap.set(t,n),this.idStyleMap.set(n,t),n}getStyle(t){return this.idStyleMap.get(t)||null}reset(){this.styleIDMap=new WeakMap,this.idStyleMap=new Map,this.id=1}generateId(){return this.id++}}function Yt(e){var t;let r=null;return"getRootNode"in e&&((t=b.getRootNode(e))==null?void 0:t.nodeType)===Node.DOCUMENT_FRAGMENT_NODE&&b.host(b.getRootNode(e))&&(r=b.host(b.getRootNode(e))),r}function cn(e){let t=e,r;for(;r=Yt(t);)t=r;return t}function dn(e){const t=b.ownerDocument(e);if(!t)return!1;const r=cn(e);return b.contains(t,r)}function tt(e){const t=b.ownerDocument(e);return t?b.contains(t,e)||dn(e):!1}const Mt=(e,t)=>`${e}@${t}`;class un{constructor(){g(this,"frozen",!1),g(this,"locked",!1),g(this,"texts",[]),g(this,"attributes",[]),g(this,"attributeMap",new WeakMap),g(this,"removes",[]),g(this,"mapRemoves",[]),g(this,"movedMap",{}),g(this,"addedSet",new Set),g(this,"movedSet",new Set),g(this,"droppedSet",new Set),g(this,"removesSubTreeCache",new Set),g(this,"mutationCb"),g(this,"blockClass"),g(this,"blockSelector"),g(this,"maskTextClass"),g(this,"maskTextSelector"),g(this,"inlineStylesheet"),g(this,"maskInputOptions"),g(this,"maskTextFn"),g(this,"maskInputFn"),g(this,"keepIframeSrcFn"),g(this,"recordCanvas"),g(this,"inlineImages"),g(this,"slimDOMOptions"),g(this,"dataURLOptions"),g(this,"doc"),g(this,"mirror"),g(this,"iframeManager"),g(this,"stylesheetManager"),g(this,"shadowDomManager"),g(this,"processedNodeManager"),g(this,"unattachedDoc"),g(this,"processMutations",t=>{t.forEach(this.processMutation),this.emit()}),g(this,"emit",()=>{if(this.frozen||this.locked)return;const t=[],r=new Set;for(;this.mapRemoves.length;)this.mirror.removeNodeFromMap(this.mapRemoves.shift());for(const p of this.movedSet){const f=b.parentNode(p);this.removesSubTreeCache.has(f)&&!this.movedSet.has(f)||this.addedSet.add(p)}let n=null,o=null,s=-1,a=null,c=!1;const i=new Set,u=this.addedSet.values();let d=u.next();for(;this.addedSet.size;){if(n!==null&&this.addedSet.has(b.previousSibling(n)))a=n,n=b.previousSibling(n);else{for(this.addedSet.has(d.value)||(d=u.next()),n=d.value;;){if(o=b.parentNode(n),this.addedSet.has(o)){n=o;continue}break}if(i.has(o))o=null;else if(o){if(tt(o)?(c=vt(this.droppedSet,o)||this.removesSubTreeCache.has(o),c&&vt(this.movedSet,n)&&(c=!1)):c=!0,this.addedSet.has(b.lastChild(o)))n=b.lastChild(o),a=null;else for(;;){if(a=b.nextSibling(n),this.addedSet.has(a)){n=a;continue}break}if(s=Ce(o)?this.mirror.getId(Yt(n)):this.mirror.getId(o),s===-1&&o.nodeType===Node.DOCUMENT_FRAGMENT_NODE){const l=b.host(o);s=this.mirror.getId(l)}}}if(this.addedSet.delete(n),!o||s===-1){i.add(n);continue}else if(c){this.droppedSet.add(n);continue}let p=!1;if(n.nodeType===Node.TEXT_NODE){const l=o.tagName;if(l==="TEXTAREA")continue;l==="STYLE"&&r.has(s)&&(p=!0)}let f=a?this.mirror.getId(a):null;for(;f===Be;)a=a&&b.nextSibling(a),f=a&&this.mirror.getId(a);if(f===-1){console.warn("Couldn't record new node. Couldn't find mirror id for nextSibling:",a),n=null;continue}const m=fe(n,{doc:this.doc,mirror:this.mirror,blockClass:this.blockClass,blockSelector:this.blockSelector,maskTextClass:this.maskTextClass,maskTextSelector:this.maskTextSelector,skipChild:!0,newlyAddedElement:!0,inlineStylesheet:this.inlineStylesheet,maskInputOptions:this.maskInputOptions,maskTextFn:this.maskTextFn,maskInputFn:this.maskInputFn,slimDOMOptions:this.slimDOMOptions,dataURLOptions:this.dataURLOptions,recordCanvas:this.recordCanvas,inlineImages:this.inlineImages,onSerialize:l=>{qt(l,this.mirror)&&this.iframeManager.addIframe(l),Xt(l,this.mirror)&&this.stylesheetManager.trackLinkElement(l),et(n)&&this.shadowDomManager.addShadowRoot(b.shadowRoot(n),this.doc)},onIframeLoad:(l,S)=>{this.iframeManager.attachIframe(l,S),this.shadowDomManager.observeAttachShadow(l)},onStylesheetLoad:(l,S)=>{this.stylesheetManager.attachLinkElement(l,S)},cssCaptured:p});m&&(t.push({parentId:s,nextId:f,node:m}),r.add(m.id))}const h={texts:this.texts.map(p=>{const f=p.node,m=b.parentNode(f);return m&&m.tagName==="TEXTAREA"&&this.genTextAreaValueMutation(m),{id:this.mirror.getId(f),value:p.value}}).filter(p=>!r.has(p.id)).filter(p=>this.mirror.has(p.id)),attributes:this.attributes.map(p=>{const{attributes:f}=p;if(typeof f.style=="string"){const m=JSON.stringify(p.styleDiff),l=JSON.stringify(p._unchangedStyles);m.length<f.style.length&&(m+l).split("var(").length===f.style.split("var(").length&&(f.style=p.styleDiff)}return{id:this.mirror.getId(p.node),attributes:f}}).filter(p=>!r.has(p.id)).filter(p=>this.mirror.has(p.id)),removes:this.removes,adds:t};!h.texts.length&&!h.attributes.length&&!h.removes.length&&!h.adds.length||(this.texts=[],this.attributes=[],this.attributeMap=new WeakMap,this.removes=[],this.addedSet=new Set,this.movedSet=new Set,this.droppedSet=new Set,this.removesSubTreeCache=new Set,this.movedMap={},this.mutationCb(h))}),g(this,"genTextAreaValueMutation",t=>{let r=this.attributeMap.get(t);r||(r={node:t,attributes:{},styleDiff:{},_unchangedStyles:{}},this.attributes.push(r),this.attributeMap.set(t,r));const n=Array.from(b.childNodes(t),o=>b.textContent(o)||"").join("");r.attributes.value=Pe({element:t,maskInputOptions:this.maskInputOptions,tagName:t.tagName,type:We(t),value:n,maskInputFn:this.maskInputFn})}),g(this,"processMutation",t=>{if(!Ye(t.target,this.mirror,this.slimDOMOptions))switch(t.type){case"characterData":{const r=b.textContent(t.target);!U(t.target,this.blockClass,this.blockSelector,!1)&&r!==t.oldValue&&this.texts.push({value:Bt(t.target,this.maskTextClass,this.maskTextSelector,!0)&&r?this.maskTextFn?this.maskTextFn(r,Vt(t.target)):r.replace(/[\S]/g,"*"):r,node:t.target});break}case"attributes":{const r=t.target,n=oe(r.tagName);let o=t.attributeName,s=t.target.getAttribute(o);if(o==="value"){const c=We(r);s=Pe({element:r,maskInputOptions:this.maskInputOptions,tagName:r.tagName,type:c,value:s,maskInputFn:this.maskInputFn})}if(U(t.target,this.blockClass,this.blockSelector,!1)||s===t.oldValue)return;let a=this.attributeMap.get(t.target);if(n==="iframe"&&o==="src"&&!this.keepIframeSrcFn(s))if(!r.contentDocument)o="rr_src";else return;if(a||(a={node:t.target,attributes:{},styleDiff:{},_unchangedStyles:{}},this.attributes.push(a),this.attributeMap.set(t.target,a)),o==="type"&&n==="input"&&(t.oldValue||"").toLowerCase()==="password"&&r.setAttribute("data-rr-is-password","true"),!Ut(n,o))if(a.attributes[o]=Wt(this.doc,n,oe(o),s),o==="style"){if(!this.unattachedDoc)try{this.unattachedDoc=document.implementation.createHTMLDocument()}catch(i){this.unattachedDoc=this.doc}const c=this.unattachedDoc.createElement("span");t.oldValue&&c.setAttribute("style",t.oldValue);for(const i of Array.from(r.style)){const u=r.style.getPropertyValue(i),d=r.style.getPropertyPriority(i);u!==c.style.getPropertyValue(i)||d!==c.style.getPropertyPriority(i)?d===""?a.styleDiff[i]=u:a.styleDiff[i]=[u,d]:a._unchangedStyles[i]=[u,d]}for(const i of Array.from(c.style))r.style.getPropertyValue(i)===""&&(a.styleDiff[i]=!1)}else o==="open"&&r.tagName==="DIALOG"&&(r.matches("dialog:modal")?a.attributes.rr_open_mode="modal":a.attributes.rr_open_mode="non-modal");break}case"childList":{if(U(t.target,this.blockClass,this.blockSelector,!0))return;if(t.target.tagName==="TEXTAREA"){this.genTextAreaValueMutation(t.target);return}t.addedNodes.forEach(r=>this.genAdds(r,t.target)),t.removedNodes.forEach(r=>{tt(r)||this.shadowDomManager.removeShadowRootsIn(r);const n=this.mirror.getId(r),o=Ce(t.target)?this.mirror.getId(b.host(t.target)):this.mirror.getId(t.target);U(t.target,this.blockClass,this.blockSelector,!1)||Ye(r,this.mirror,this.slimDOMOptions)||!sn(r,this.mirror)||(this.addedSet.has(r)?(rt(this.addedSet,r),this.droppedSet.add(r)):this.addedSet.has(t.target)&&n===-1||$t(t.target,this.mirror)||(this.movedSet.has(r)&&this.movedMap[Mt(n,o)]?rt(this.movedSet,r):(this.removes.push({parentId:o,id:n,isShadow:Ce(t.target)&&Me(t.target)?!0:void 0}),hn(r,this.removesSubTreeCache))),this.mapRemoves.push(r))});break}}}),g(this,"genAdds",(t,r)=>{if(!this.processedNodeManager.inOtherBuffer(t,this)&&!(this.addedSet.has(t)||this.movedSet.has(t))){if(this.mirror.hasNode(t)){if(Ye(t,this.mirror,this.slimDOMOptions))return;this.movedSet.add(t);let n=null;r&&this.mirror.hasNode(r)&&(n=this.mirror.getId(r)),n&&n!==-1&&(this.movedMap[Mt(this.mirror.getId(t),n)]=!0)}else this.addedSet.add(t),this.droppedSet.delete(t);U(t,this.blockClass,this.blockSelector,!1)||(b.childNodes(t).forEach(n=>this.genAdds(n)),et(t)&&b.childNodes(b.shadowRoot(t)).forEach(n=>{this.processedNodeManager.add(n,this),this.genAdds(n,t)}))}})}init(t){["mutationCb","blockClass","blockSelector","maskTextClass","maskTextSelector","inlineStylesheet","maskInputOptions","maskTextFn","maskInputFn","keepIframeSrcFn","recordCanvas","inlineImages","slimDOMOptions","dataURLOptions","doc","mirror","iframeManager","stylesheetManager","shadowDomManager","processedNodeManager"].forEach(r=>{this[r]=t[r]})}freeze(){this.frozen=!0}unfreeze(){this.frozen=!1,this.emit()}isFrozen(){return this.frozen}lock(){this.locked=!0}unlock(){this.locked=!1,this.emit()}}function rt(e,t){e.delete(t),b.childNodes(t).forEach(r=>rt(e,r))}function hn(e,t){const r=[e];for(;r.length;){const n=r.pop();t.has(n)||(t.add(n),b.childNodes(n).forEach(o=>r.push(o)))}}function vt(e,t){return e.size===0?!1:Jt(e,t)}function Jt(e,t){if(e.has(t))return!0;const r=b.parentNode(t);return r?Jt(e,r):!1}let ve;function fn(e){ve=e}function pn(){ve=void 0}const O=e=>ve?(...r)=>{try{return e(...r)}catch(n){if(ve&&ve(n)===!0)return;throw n}}:e,me=new Set;function Ne(e){try{if("composedPath"in e){const t=e.composedPath();if(t.length)return t[0]}else if("path"in e&&e.path.length)return e.path[0]}catch(t){}return e&&e.target}function Zt(e,t){const r=new un;me.add(r),r.init(e);const[n,o]=Dt(),s=new n(O(r.processMutations.bind(r)));return s.observe(t,{attributes:!0,attributeOldValue:!0,characterData:!0,characterDataOldValue:!0,childList:!0,subtree:!0}),()=>{s.disconnect(),me.delete(r),o()}}function mn({mousemoveCb:e,sampling:t,doc:r,mirror:n}){if(t.mousemove===!1)return()=>{};const o=typeof t.mousemove=="number"?t.mousemove:50,s=typeof t.mousemoveCallback=="number"?t.mousemoveCallback:500;let a=[],c;const i=Re(O(h=>{const p=Date.now()-c;e(a.map(f=>(f.timeOffset-=p,f)),h),a=[],c=null}),s),u=O(Re(O(h=>{const p=Ne(h),{clientX:f,clientY:m}=Ke(h)?h.changedTouches[0]:h;c||(c=Ie()),a.push({x:f,y:m,id:n.getId(p),timeOffset:Ie()-c}),i(typeof DragEvent!="undefined"&&h instanceof DragEvent?R.Drag:h instanceof MouseEvent?R.MouseMove:R.TouchMove)}),o,{trailing:!1})),d=[P("mousemove",u,r),P("touchmove",u,r),P("drag",u,r)];return O(()=>{d.forEach(h=>h())})}function gn({mouseInteractionCb:e,doc:t,mirror:r,blockClass:n,blockSelector:o,sampling:s}){if(s.mouseInteraction===!1)return()=>{};const a=s.mouseInteraction===!0||s.mouseInteraction===void 0?{}:s.mouseInteraction,c=[];let i=null;const u=d=>h=>{const p=Ne(h);if(U(p,n,o,!0))return;let f=null,m=d;if("pointerType"in h){switch(h.pointerType){case"mouse":f=te.Mouse;break;case"touch":f=te.Touch;break;case"pen":f=te.Pen;break}f===te.Touch?H[d]===H.MouseDown?m="TouchStart":H[d]===H.MouseUp&&(m="TouchEnd"):te.Pen}else Ke(h)&&(f=te.Touch);f!==null?(i=f,(m.startsWith("Touch")&&f===te.Touch||m.startsWith("Mouse")&&f===te.Mouse)&&(f=null)):H[d]===H.Click&&(f=i,i=null);const l=Ke(h)?h.changedTouches[0]:h;if(!l)return;const S=r.getId(p),{clientX:w,clientY:C}=l;O(e)(F({type:H[m],id:S,x:w,y:C},f!==null&&{pointerType:f}))};return Object.keys(H).filter(d=>Number.isNaN(Number(d))&&!d.endsWith("_Departed")&&a[d]!==!1).forEach(d=>{let h=oe(d);const p=u(d);if(window.PointerEvent)switch(H[d]){case H.MouseDown:case H.MouseUp:h=h.replace("mouse","pointer");break;case H.TouchStart:case H.TouchEnd:return}c.push(P(h,p,t))}),O(()=>{c.forEach(d=>d())})}function Qt({scrollCb:e,doc:t,mirror:r,blockClass:n,blockSelector:o,sampling:s}){const a=O(Re(O(c=>{const i=Ne(c);if(!i||U(i,n,o,!0))return;const u=r.getId(i);if(i===t&&t.defaultView){const d=Ht(t.defaultView);e({id:u,x:d.left,y:d.top})}else e({id:u,x:i.scrollLeft,y:i.scrollTop})}),s.scroll||100));return P("scroll",a,t)}function yn({viewportResizeCb:e},{win:t}){let r=-1,n=-1;const o=O(Re(O(()=>{const s=Gt(),a=jt();(r!==s||n!==a)&&(e({width:Number(a),height:Number(s)}),r=s,n=a)}),200));return P("resize",o,t)}const Sn=["INPUT","TEXTAREA","SELECT"],It=new WeakMap;function bn({inputCb:e,doc:t,mirror:r,blockClass:n,blockSelector:o,ignoreClass:s,ignoreSelector:a,maskInputOptions:c,maskInputFn:i,sampling:u,userTriggeredOnInput:d}){function h(C){let y=Ne(C);const M=C.isTrusted,D=y&&y.tagName;if(y&&D==="OPTION"&&(y=b.parentElement(y)),!y||!D||Sn.indexOf(D)<0||U(y,n,o,!0)||y.classList.contains(s)||a&&y.matches(a))return;let L=y.value,W=!1;const Z=We(y)||"";Z==="radio"||Z==="checkbox"?W=y.checked:(c[D.toLowerCase()]||c[Z])&&(L=Pe({element:y,maskInputOptions:c,tagName:D,type:Z,value:L,maskInputFn:i})),p(y,d?{text:L,isChecked:W,userTriggered:M}:{text:L,isChecked:W});const j=y.name;Z==="radio"&&j&&W&&t.querySelectorAll(`input[type="radio"][name="${j}"]`).forEach(Y=>{if(Y!==y){const V=Y.value;p(Y,d?{text:V,isChecked:!W,userTriggered:!1}:{text:V,isChecked:!W})}})}function p(C,y){const M=It.get(C);if(!M||M.text!==y.text||M.isChecked!==y.isChecked){It.set(C,y);const D=r.getId(C);O(e)(Te(F({},y),{id:D}))}}const m=(u.input==="last"?["change"]:["input","change"]).map(C=>P(C,O(h),t)),l=t.defaultView;if(!l)return()=>{m.forEach(C=>C())};const S=l.Object.getOwnPropertyDescriptor(l.HTMLInputElement.prototype,"value"),w=[[l.HTMLInputElement.prototype,"value"],[l.HTMLInputElement.prototype,"checked"],[l.HTMLSelectElement.prototype,"value"],[l.HTMLTextAreaElement.prototype,"value"],[l.HTMLSelectElement.prototype,"selectedIndex"],[l.HTMLOptionElement.prototype,"selected"]];return S&&S.set&&m.push(...w.map(C=>Ge(C[0],C[1],{set(){O(h)({target:this,isTrusted:!1})}},!1,l))),O(()=>{m.forEach(C=>C())})}function He(e){const t=[];function r(n,o){if(xe("CSSGroupingRule")&&n.parentRule instanceof CSSGroupingRule||xe("CSSMediaRule")&&n.parentRule instanceof CSSMediaRule||xe("CSSSupportsRule")&&n.parentRule instanceof CSSSupportsRule||xe("CSSConditionRule")&&n.parentRule instanceof CSSConditionRule){const a=Array.from(n.parentRule.cssRules).indexOf(n);return o.unshift(a),r(n.parentRule,o)}else if(n.parentStyleSheet){const a=Array.from(n.parentStyleSheet.cssRules).indexOf(n);o.unshift(a)}return o}return r(e,t)}function ne(e,t,r){let n,o;return e?(e.ownerNode?n=t.getId(e.ownerNode):o=r.getId(e),{styleId:o,id:n}):{}}function wn({styleSheetRuleCb:e,mirror:t,stylesheetManager:r},{win:n}){if(!n.CSSStyleSheet||!n.CSSStyleSheet.prototype)return()=>{};const o=n.CSSStyleSheet.prototype.insertRule;n.CSSStyleSheet.prototype.insertRule=new Proxy(o,{apply:O((d,h,p)=>{const[f,m]=p,{id:l,styleId:S}=ne(h,t,r.styleMirror);return(l&&l!==-1||S&&S!==-1)&&e({id:l,styleId:S,adds:[{rule:f,index:m}]}),d.apply(h,p)})}),n.CSSStyleSheet.prototype.addRule=function(d,h,p=this.cssRules.length){const f=`${d} { ${h} }`;return n.CSSStyleSheet.prototype.insertRule.apply(this,[f,p])};const s=n.CSSStyleSheet.prototype.deleteRule;n.CSSStyleSheet.prototype.deleteRule=new Proxy(s,{apply:O((d,h,p)=>{const[f]=p,{id:m,styleId:l}=ne(h,t,r.styleMirror);return(m&&m!==-1||l&&l!==-1)&&e({id:m,styleId:l,removes:[{index:f}]}),d.apply(h,p)})}),n.CSSStyleSheet.prototype.removeRule=function(d){return n.CSSStyleSheet.prototype.deleteRule.apply(this,[d])};let a;n.CSSStyleSheet.prototype.replace&&(a=n.CSSStyleSheet.prototype.replace,n.CSSStyleSheet.prototype.replace=new Proxy(a,{apply:O((d,h,p)=>{const[f]=p,{id:m,styleId:l}=ne(h,t,r.styleMirror);return(m&&m!==-1||l&&l!==-1)&&e({id:m,styleId:l,replace:f}),d.apply(h,p)})}));let c;n.CSSStyleSheet.prototype.replaceSync&&(c=n.CSSStyleSheet.prototype.replaceSync,n.CSSStyleSheet.prototype.replaceSync=new Proxy(c,{apply:O((d,h,p)=>{const[f]=p,{id:m,styleId:l}=ne(h,t,r.styleMirror);return(m&&m!==-1||l&&l!==-1)&&e({id:m,styleId:l,replaceSync:f}),d.apply(h,p)})}));const i={};Le("CSSGroupingRule")?i.CSSGroupingRule=n.CSSGroupingRule:(Le("CSSMediaRule")&&(i.CSSMediaRule=n.CSSMediaRule),Le("CSSConditionRule")&&(i.CSSConditionRule=n.CSSConditionRule),Le("CSSSupportsRule")&&(i.CSSSupportsRule=n.CSSSupportsRule));const u={};return Object.entries(i).forEach(([d,h])=>{u[d]={insertRule:h.prototype.insertRule,deleteRule:h.prototype.deleteRule},h.prototype.insertRule=new Proxy(u[d].insertRule,{apply:O((p,f,m)=>{const[l,S]=m,{id:w,styleId:C}=ne(f.parentStyleSheet,t,r.styleMirror);return(w&&w!==-1||C&&C!==-1)&&e({id:w,styleId:C,adds:[{rule:l,index:[...He(f),S||0]}]}),p.apply(f,m)})}),h.prototype.deleteRule=new Proxy(u[d].deleteRule,{apply:O((p,f,m)=>{const[l]=m,{id:S,styleId:w}=ne(f.parentStyleSheet,t,r.styleMirror);return(S&&S!==-1||w&&w!==-1)&&e({id:S,styleId:w,removes:[{index:[...He(f),l]}]}),p.apply(f,m)})})}),O(()=>{n.CSSStyleSheet.prototype.insertRule=o,n.CSSStyleSheet.prototype.deleteRule=s,a&&(n.CSSStyleSheet.prototype.replace=a),c&&(n.CSSStyleSheet.prototype.replaceSync=c),Object.entries(i).forEach(([d,h])=>{h.prototype.insertRule=u[d].insertRule,h.prototype.deleteRule=u[d].deleteRule})})}function Kt({mirror:e,stylesheetManager:t},r){var n,o,s;let a=null;r.nodeName==="#document"?a=e.getId(r):a=e.getId(b.host(r));const c=r.nodeName==="#document"?(n=r.defaultView)==null?void 0:n.Document:(s=(o=r.ownerDocument)==null?void 0:o.defaultView)==null?void 0:s.ShadowRoot,i=c!=null&&c.prototype?Object.getOwnPropertyDescriptor(c==null?void 0:c.prototype,"adoptedStyleSheets"):void 0;return a===null||a===-1||!c||!i?()=>{}:(Object.defineProperty(r,"adoptedStyleSheets",{configurable:i.configurable,enumerable:i.enumerable,get(){var u;return(u=i.get)==null?void 0:u.call(this)},set(u){var d;const h=(d=i.set)==null?void 0:d.call(this,u);if(a!==null&&a!==-1)try{t.adoptStyleSheets(u,a)}catch(p){}return h}}),O(()=>{Object.defineProperty(r,"adoptedStyleSheets",{configurable:i.configurable,enumerable:i.enumerable,get:i.get,set:i.set})}))}function Cn({styleDeclarationCb:e,mirror:t,ignoreCSSAttributes:r,stylesheetManager:n},{win:o}){const s=o.CSSStyleDeclaration.prototype.setProperty;o.CSSStyleDeclaration.prototype.setProperty=new Proxy(s,{apply:O((c,i,u)=>{var d;const[h,p,f]=u;if(r.has(h))return s.apply(i,[h,p,f]);const{id:m,styleId:l}=ne((d=i.parentRule)==null?void 0:d.parentStyleSheet,t,n.styleMirror);return(m&&m!==-1||l&&l!==-1)&&e({id:m,styleId:l,set:{property:h,value:p,priority:f},index:He(i.parentRule)}),c.apply(i,u)})});const a=o.CSSStyleDeclaration.prototype.removeProperty;return o.CSSStyleDeclaration.prototype.removeProperty=new Proxy(a,{apply:O((c,i,u)=>{var d;const[h]=u;if(r.has(h))return a.apply(i,[h]);const{id:p,styleId:f}=ne((d=i.parentRule)==null?void 0:d.parentStyleSheet,t,n.styleMirror);return(p&&p!==-1||f&&f!==-1)&&e({id:p,styleId:f,remove:{property:h},index:He(i.parentRule)}),c.apply(i,u)})}),O(()=>{o.CSSStyleDeclaration.prototype.setProperty=s,o.CSSStyleDeclaration.prototype.removeProperty=a})}function Mn({mediaInteractionCb:e,blockClass:t,blockSelector:r,mirror:n,sampling:o,doc:s}){const a=O(i=>Re(O(u=>{const d=Ne(u);if(!d||U(d,t,r,!0))return;const{currentTime:h,volume:p,muted:f,playbackRate:m,loop:l}=d;e({type:i,id:n.getId(d),currentTime:h,volume:p,muted:f,playbackRate:m,loop:l})}),o.media||500)),c=[P("play",a(de.Play),s),P("pause",a(de.Pause),s),P("seeked",a(de.Seeked),s),P("volumechange",a(de.VolumeChange),s),P("ratechange",a(de.RateChange),s)];return O(()=>{c.forEach(i=>i())})}function vn({fontCb:e,doc:t}){const r=t.defaultView;if(!r)return()=>{};const n=[],o=new WeakMap,s=r.FontFace;r.FontFace=function(i,u,d){const h=new s(i,u,d);return o.set(h,{family:i,buffer:typeof u!="string",descriptors:d,fontSource:typeof u=="string"?u:JSON.stringify(Array.from(new Uint8Array(u)))}),h};const a=ae(t.fonts,"add",function(c){return function(i){return setTimeout(O(()=>{const u=o.get(i);u&&(e(u),o.delete(i))}),0),c.apply(this,[i])}});return n.push(()=>{r.FontFace=s}),n.push(a),O(()=>{n.forEach(c=>c())})}function In(e){const{doc:t,mirror:r,blockClass:n,blockSelector:o,selectionCb:s}=e;let a=!0;const c=O(()=>{const i=t.getSelection();if(!i||a&&(i!=null&&i.isCollapsed))return;a=i.isCollapsed||!1;const u=[],d=i.rangeCount||0;for(let h=0;h<d;h++){const p=i.getRangeAt(h),{startContainer:f,startOffset:m,endContainer:l,endOffset:S}=p;U(f,n,o,!0)||U(l,n,o,!0)||u.push({start:r.getId(f),startOffset:m,end:r.getId(l),endOffset:S})}s({ranges:u})});return c(),P("selectionchange",c)}function Rn({doc:e,customElementCb:t}){const r=e.defaultView;return!r||!r.customElements?()=>{}:ae(r.customElements,"define",function(o){return function(s,a,c){try{t({define:{name:s}})}catch(i){console.warn(`Custom element callback failed for ${s}`)}return o.apply(this,[s,a,c])}})}function On(e,t){const{mutationCb:r,mousemoveCb:n,mouseInteractionCb:o,scrollCb:s,viewportResizeCb:a,inputCb:c,mediaInteractionCb:i,styleSheetRuleCb:u,styleDeclarationCb:d,canvasMutationCb:h,fontCb:p,selectionCb:f,customElementCb:m}=e;e.mutationCb=(...l)=>{t.mutation&&t.mutation(...l),r(...l)},e.mousemoveCb=(...l)=>{t.mousemove&&t.mousemove(...l),n(...l)},e.mouseInteractionCb=(...l)=>{t.mouseInteraction&&t.mouseInteraction(...l),o(...l)},e.scrollCb=(...l)=>{t.scroll&&t.scroll(...l),s(...l)},e.viewportResizeCb=(...l)=>{t.viewportResize&&t.viewportResize(...l),a(...l)},e.inputCb=(...l)=>{t.input&&t.input(...l),c(...l)},e.mediaInteractionCb=(...l)=>{t.mediaInteaction&&t.mediaInteaction(...l),i(...l)},e.styleSheetRuleCb=(...l)=>{t.styleSheetRule&&t.styleSheetRule(...l),u(...l)},e.styleDeclarationCb=(...l)=>{t.styleDeclaration&&t.styleDeclaration(...l),d(...l)},e.canvasMutationCb=(...l)=>{t.canvasMutation&&t.canvasMutation(...l),h(...l)},e.fontCb=(...l)=>{t.font&&t.font(...l),p(...l)},e.selectionCb=(...l)=>{t.selection&&t.selection(...l),f(...l)},e.customElementCb=(...l)=>{t.customElement&&t.customElement(...l),m(...l)}}function Nn(e,t={}){const r=e.doc.defaultView;if(!r)return()=>{};On(e,t);let n;e.recordDOM&&(n=Zt(e,e.doc));const o=mn(e),s=gn(e),a=Qt(e),c=yn(e,{win:r}),i=bn(e),u=Mn(e);let d=()=>{},h=()=>{},p=()=>{},f=()=>{};e.recordDOM&&(d=wn(e,{win:r}),h=Kt(e,e.doc),p=Cn(e,{win:r}),e.collectFonts&&(f=vn(e)));const m=In(e),l=Rn(e),S=[];for(const w of e.plugins)S.push(w.observer(w.callback,r,w.options));return O(()=>{n==null||n(),o(),s(),a(),c(),i(),u(),d(),h(),p(),f(),m(),l(),S.forEach(w=>w())})}function xe(e){return typeof window[e]!="undefined"}function Le(e){return!!(typeof window[e]!="undefined"&&window[e].prototype&&"insertRule"in window[e].prototype&&"deleteRule"in window[e].prototype)}class Rt{constructor(t){g(this,"iframeIdToRemoteIdMap",new WeakMap),g(this,"iframeRemoteIdToIdMap",new WeakMap),this.generateIdFn=t}getId(t,r,n,o){const s=n||this.getIdToRemoteIdMap(t),a=o||this.getRemoteIdToIdMap(t);let c=s.get(r);return c||(c=this.generateIdFn(),s.set(r,c),a.set(c,r)),c}getIds(t,r){const n=this.getIdToRemoteIdMap(t),o=this.getRemoteIdToIdMap(t);return r.map(s=>this.getId(t,s,n,o))}getRemoteId(t,r,n){const o=n||this.getRemoteIdToIdMap(t);if(typeof r!="number")return r;const s=o.get(r);return s||-1}getRemoteIds(t,r){const n=this.getRemoteIdToIdMap(t);return r.map(o=>this.getRemoteId(t,o,n))}reset(t){if(!t){this.iframeIdToRemoteIdMap=new WeakMap,this.iframeRemoteIdToIdMap=new WeakMap;return}this.iframeIdToRemoteIdMap.delete(t),this.iframeRemoteIdToIdMap.delete(t)}getIdToRemoteIdMap(t){let r=this.iframeIdToRemoteIdMap.get(t);return r||(r=new Map,this.iframeIdToRemoteIdMap.set(t,r)),r}getRemoteIdToIdMap(t){let r=this.iframeRemoteIdToIdMap.get(t);return r||(r=new Map,this.iframeRemoteIdToIdMap.set(t,r)),r}}class En{constructor(t){g(this,"iframes",new WeakMap),g(this,"crossOriginIframeMap",new WeakMap),g(this,"crossOriginIframeMirror",new Rt(Pt)),g(this,"crossOriginIframeStyleMirror"),g(this,"crossOriginIframeRootIdMap",new WeakMap),g(this,"mirror"),g(this,"mutationCb"),g(this,"wrappedEmit"),g(this,"loadListener"),g(this,"unloadListener"),g(this,"attachedWindows",new Map),g(this,"messageHandler",r=>this.handleMessage(r)),g(this,"stylesheetManager"),g(this,"recordCrossOriginIframes"),this.mutationCb=t.mutationCb,this.wrappedEmit=t.wrappedEmit,this.stylesheetManager=t.stylesheetManager,this.recordCrossOriginIframes=t.recordCrossOriginIframes,this.crossOriginIframeStyleMirror=new Rt(this.stylesheetManager.styleMirror.generateId.bind(this.stylesheetManager.styleMirror)),this.mirror=t.mirror,this.recordCrossOriginIframes&&window.addEventListener("message",this.messageHandler)}addIframe(t){this.iframes.set(t,!0),t.contentWindow&&this.crossOriginIframeMap.set(t.contentWindow,t)}addLoadListener(t){this.loadListener=t}addUnloadListener(t){this.unloadListener=t}attachIframe(t,r){var n;this.mutationCb({adds:[{parentId:this.mirror.getId(t),nextId:null,node:r}],removes:[],texts:[],attributes:[],isAttachIframe:!0}),this.watchIframeWindow(t),(n=this.loadListener)==null||n.call(this,t),t.contentDocument&&t.contentDocument.adoptedStyleSheets&&t.contentDocument.adoptedStyleSheets.length>0&&this.stylesheetManager.adoptStyleSheets(t.contentDocument.adoptedStyleSheets,this.mirror.getId(t.contentDocument))}destroy(){window.removeEventListener("message",this.messageHandler),this.attachedWindows.forEach(t=>t())}watchIframeWindow(t){const r=t.contentWindow;if(!r||this.attachedWindows.has(r))return;const n=[],o=()=>{this.attachedWindows.delete(r),n.forEach(s=>{try{s()}catch(a){}})};this.attachedWindows.set(r,o),this.recordCrossOriginIframes&&n.push(P("message",this.messageHandler,r)),n.push(P("pagehide",s=>{var a;if(s.persisted)return;const c=r.document;o(),(a=this.unloadListener)==null||a.call(this,c)},r))}handleMessage(t){const r=t;if(r.data.type!=="rrweb"||r.origin!==r.data.origin||!t.source)return;const o=this.crossOriginIframeMap.get(t.source);if(!o)return;const s=this.transformCrossOriginEvent(o,r.data.event);s&&this.wrappedEmit(s,r.data.isCheckout)}transformCrossOriginEvent(t,r){var n;switch(r.type){case I.FullSnapshot:{this.crossOriginIframeMirror.reset(t),this.crossOriginIframeStyleMirror.reset(t),this.replaceIdOnNode(r.data.node,t);const o=r.data.node.id;return this.crossOriginIframeRootIdMap.set(t,o),this.patchRootIdOnNode(r.data.node,o),{timestamp:r.timestamp,type:I.IncrementalSnapshot,data:{source:R.Mutation,adds:[{parentId:this.mirror.getId(t),nextId:null,node:r.data.node}],removes:[],texts:[],attributes:[],isAttachIframe:!0}}}case I.Meta:case I.Load:case I.DomContentLoaded:return!1;case I.Annotation:case I.Plugin:return r;case I.Custom:return this.replaceIds(r.data.payload,t,["id","parentId","previousId","nextId"]),r;case I.IncrementalSnapshot:switch(r.data.source){case R.Mutation:return r.data.adds.forEach(o=>{this.replaceIds(o,t,["parentId","nextId","previousId"]),this.replaceIdOnNode(o.node,t);const s=this.crossOriginIframeRootIdMap.get(t);s&&this.patchRootIdOnNode(o.node,s)}),r.data.removes.forEach(o=>{this.replaceIds(o,t,["parentId","id"])}),r.data.attributes.forEach(o=>{this.replaceIds(o,t,["id"])}),r.data.texts.forEach(o=>{this.replaceIds(o,t,["id"])}),r;case R.Drag:case R.TouchMove:case R.MouseMove:return r.data.positions.forEach(o=>{this.replaceIds(o,t,["id"])}),r;case R.ViewportResize:return!1;case R.MediaInteraction:case R.MouseInteraction:case R.Scroll:case R.CanvasMutation:case R.Input:return this.replaceIds(r.data,t,["id"]),r;case R.StyleSheetRule:case R.StyleDeclaration:return this.replaceIds(r.data,t,["id"]),this.replaceStyleIds(r.data,t,["styleId"]),r;case R.Font:return r;case R.Selection:return r.data.ranges.forEach(o=>{this.replaceIds(o,t,["start","end"])}),r;case R.AdoptedStyleSheet:return this.replaceIds(r.data,t,["id"]),this.replaceStyleIds(r.data,t,["styleIds"]),(n=r.data.styles)==null||n.forEach(o=>{this.replaceStyleIds(o,t,["styleId"])}),r}}return!1}replace(t,r,n,o){for(const s of o)!Array.isArray(r[s])&&typeof r[s]!="number"||(Array.isArray(r[s])?r[s]=t.getIds(n,r[s]):r[s]=t.getId(n,r[s]));return r}replaceIds(t,r,n){return this.replace(this.crossOriginIframeMirror,t,r,n)}replaceStyleIds(t,r,n){return this.replace(this.crossOriginIframeStyleMirror,t,r,n)}replaceIdOnNode(t,r){this.replaceIds(t,r,["id","rootId"]),"childNodes"in t&&t.childNodes.forEach(n=>{this.replaceIdOnNode(n,r)})}patchRootIdOnNode(t,r){t.type!==A.Document&&!t.rootId&&(t.rootId=r),"childNodes"in t&&t.childNodes.forEach(n=>{this.patchRootIdOnNode(n,r)})}}class kn{constructor(t){g(this,"shadowDoms",new Map),g(this,"mutationCb"),g(this,"scrollCb"),g(this,"bypassOptions"),g(this,"mirror"),g(this,"restoreHandlers",[]),this.mutationCb=t.mutationCb,this.scrollCb=t.scrollCb,this.bypassOptions=t.bypassOptions,this.mirror=t.mirror,this.init()}init(){this.reset(),this.patchAttachShadow(Element,document)}addShadowRoot(t,r){if(!Me(t)||this.shadowDoms.has(t))return;const n=[];this.shadowDoms.set(t,n);const o=Zt(Te(F({},this.bypassOptions),{doc:r,mutationCb:this.mutationCb,mirror:this.mirror,shadowDomManager:this}),t);n.push(o),n.push(Qt(Te(F({},this.bypassOptions),{scrollCb:this.scrollCb,doc:t,mirror:this.mirror}))),setTimeout(()=>{this.shadowDoms.get(t)===n&&(t.adoptedStyleSheets&&t.adoptedStyleSheets.length>0&&this.bypassOptions.stylesheetManager.adoptStyleSheets(t.adoptedStyleSheets,this.mirror.getId(b.host(t))),n.push(Kt({mirror:this.mirror,stylesheetManager:this.bypassOptions.stylesheetManager},t)))},0)}removeShadowRootsIn(t){if(this.shadowDoms.size===0)return;const r=b.shadowRoot(t);r&&(this.shadowDoms.has(r)&&this.removeShadowRoot(r),this.removeShadowRootsIn(r)),b.childNodes(t).forEach(n=>this.removeShadowRootsIn(n))}removeShadowRoot(t){const r=this.shadowDoms.get(t);this.shadowDoms.delete(t),r==null||r.forEach(Je)}observeAttachShadow(t){!t.contentWindow||!t.contentDocument||this.patchAttachShadow(t.contentWindow.Element,t.contentDocument)}patchAttachShadow(t,r){const n=this;this.restoreHandlers.push(ae(t.prototype,"attachShadow",function(o){return function(s){const a=o.call(this,s),c=b.shadowRoot(this);return c&&tt(this)&&n.addShadowRoot(c,r),a}}))}reset(){this.restoreHandlers.forEach(Je),this.restoreHandlers=[];const t=this.shadowDoms;this.shadowDoms=new Map,t.forEach(r=>r.forEach(Je))}}function Je(e){try{e()}catch(t){}}var pe="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/",Tn=typeof Uint8Array=="undefined"?[]:new Uint8Array(256);for(var Ae=0;Ae<pe.length;Ae++)Tn[pe.charCodeAt(Ae)]=Ae;var Dn=function(e){var t=new Uint8Array(e),r,n=t.length,o="";for(r=0;r<n;r+=3)o+=pe[t[r]>>2],o+=pe[(t[r]&3)<<4|t[r+1]>>4],o+=pe[(t[r+1]&15)<<2|t[r+2]>>6],o+=pe[t[r+2]&63];return n%3===2?o=o.substring(0,o.length-1)+"=":n%3===1&&(o=o.substring(0,o.length-2)+"=="),o};const Ot=new Map;function xn(e,t){let r=Ot.get(e);return r||(r=new Map,Ot.set(e,r)),r.has(t)||r.set(t,[]),r.get(t)}const er=(e,t,r)=>{if(!e||!(rr(e,t)||typeof e=="object"))return;const n=e.constructor.name,o=xn(r,n);let s=o.indexOf(e);return s===-1&&(s=o.length,o.push(e)),s};function _e(e,t,r){if(e instanceof Array)return e.map(n=>_e(n,t,r));if(e===null)return e;if(e instanceof Float32Array||e instanceof Float64Array||e instanceof Int32Array||e instanceof Uint32Array||e instanceof Uint8Array||e instanceof Uint16Array||e instanceof Int16Array||e instanceof Int8Array||e instanceof Uint8ClampedArray)return{rr_type:e.constructor.name,args:[Object.values(e)]};if(e instanceof ArrayBuffer){const n=e.constructor.name,o=Dn(e);return{rr_type:n,base64:o}}else{if(e instanceof DataView)return{rr_type:e.constructor.name,args:[_e(e.buffer,t,r),e.byteOffset,e.byteLength]};if(e instanceof HTMLImageElement){const n=e.constructor.name,{src:o}=e;return{rr_type:n,src:o}}else if(e instanceof HTMLCanvasElement){const n="HTMLImageElement",o=e.toDataURL();return{rr_type:n,src:o}}else{if(e instanceof ImageData)return{rr_type:e.constructor.name,args:[_e(e.data,t,r),e.width,e.height]};if(rr(e,t)||typeof e=="object"){const n=e.constructor.name,o=er(e,t,r);return{rr_type:n,index:o}}}}return e}const tr=(e,t,r)=>e.map(n=>_e(n,t,r)),rr=(e,t)=>!!["WebGLActiveInfo","WebGLBuffer","WebGLFramebuffer","WebGLProgram","WebGLRenderbuffer","WebGLShader","WebGLShaderPrecisionFormat","WebGLTexture","WebGLUniformLocation","WebGLVertexArrayObject","WebGLVertexArrayObjectOES"].filter(o=>typeof t[o]=="function").find(o=>e instanceof t[o]);function Ln(e,t,r,n){const o=[],s=Object.getOwnPropertyNames(t.CanvasRenderingContext2D.prototype);for(const a of s)try{if(typeof t.CanvasRenderingContext2D.prototype[a]!="function")continue;const c=ae(t.CanvasRenderingContext2D.prototype,a,function(i){return function(...u){return U(this.canvas,r,n,!0)||setTimeout(()=>{const d=tr(u,t,this);e(this.canvas,{type:ge["2D"],property:a,args:d})},0),i.apply(this,u)}});o.push(c)}catch(c){const i=Ge(t.CanvasRenderingContext2D.prototype,a,{set(u){e(this.canvas,{type:ge["2D"],property:a,args:[u],setter:!0})}});o.push(i)}return()=>{o.forEach(a=>a())}}function An(e){return e==="experimental-webgl"?"webgl":e}function Nt(e,t,r,n){const o=[];try{const s=ae(e.HTMLCanvasElement.prototype,"getContext",function(a){return function(c,...i){if(!U(this,t,r,!0)){const u=An(c);if("__context"in this||(this.__context=u),n&&["webgl","webgl2"].includes(u))if(i[0]&&typeof i[0]=="object"){const d=i[0];d.preserveDrawingBuffer||(d.preserveDrawingBuffer=!0)}else i.splice(0,1,{preserveDrawingBuffer:!0})}return a.apply(this,[c,...i])}});o.push(s)}catch(s){console.error("failed to patch HTMLCanvasElement.prototype.getContext")}return()=>{o.forEach(s=>s())}}function Et(e,t,r,n,o,s){const a=[],c=Object.getOwnPropertyNames(e);for(const i of c)if(!["isContextLost","canvas","drawingBufferWidth","drawingBufferHeight"].includes(i))try{if(typeof e[i]!="function")continue;const u=ae(e,i,function(d){return function(...h){const p=d.apply(this,h);if(er(p,s,this),"tagName"in this.canvas&&!U(this.canvas,n,o,!0)){const f=tr(h,s,this),m={type:t,property:i,args:f};r(this.canvas,m)}return p}});a.push(u)}catch(u){const d=Ge(e,i,{set(h){r(this.canvas,{type:t,property:i,args:[h],setter:!0})}});a.push(d)}return a}function _n(e,t,r,n){const o=[];return typeof t.WebGLRenderingContext!="undefined"&&o.push(...Et(t.WebGLRenderingContext.prototype,ge.WebGL,e,r,n,t)),typeof t.WebGL2RenderingContext!="undefined"&&o.push(...Et(t.WebGL2RenderingContext.prototype,ge.WebGL2,e,r,n,t)),()=>{o.forEach(s=>s())}}const nr=`(function() {
  "use strict";
  var chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  var lookup = typeof Uint8Array === "undefined" ? [] : new Uint8Array(256);
  for (var i = 0; i < chars.length; i++) {
    lookup[chars.charCodeAt(i)] = i;
  }
  var encode = function(arraybuffer) {
    var bytes = new Uint8Array(arraybuffer), i2, len = bytes.length, base64 = "";
    for (i2 = 0; i2 < len; i2 += 3) {
      base64 += chars[bytes[i2] >> 2];
      base64 += chars[(bytes[i2] & 3) << 4 | bytes[i2 + 1] >> 4];
      base64 += chars[(bytes[i2 + 1] & 15) << 2 | bytes[i2 + 2] >> 6];
      base64 += chars[bytes[i2 + 2] & 63];
    }
    if (len % 3 === 2) {
      base64 = base64.substring(0, base64.length - 1) + "=";
    } else if (len % 3 === 1) {
      base64 = base64.substring(0, base64.length - 2) + "==";
    }
    return base64;
  };
  const lastBlobMap = /* @__PURE__ */ new Map();
  const transparentBlobMap = /* @__PURE__ */ new Map();
  async function getTransparentBlobFor(width, height, dataURLOptions) {
    const id = \`\${width}-\${height}\`;
    if ("OffscreenCanvas" in globalThis) {
      if (transparentBlobMap.has(id)) return transparentBlobMap.get(id);
      const offscreen = new OffscreenCanvas(width, height);
      offscreen.getContext("2d");
      const blob = await offscreen.convertToBlob(dataURLOptions);
      const arrayBuffer = await blob.arrayBuffer();
      const base64 = encode(arrayBuffer);
      transparentBlobMap.set(id, base64);
      return base64;
    } else {
      return "";
    }
  }
  const worker = self;
  worker.onmessage = async function(e) {
    if ("OffscreenCanvas" in globalThis) {
      const { id, bitmap, width, height, dataURLOptions } = e.data;
      const transparentBase64 = getTransparentBlobFor(
        width,
        height,
        dataURLOptions
      );
      const offscreen = new OffscreenCanvas(width, height);
      const ctx = offscreen.getContext("2d");
      ctx.drawImage(bitmap, 0, 0);
      bitmap.close();
      const blob = await offscreen.convertToBlob(dataURLOptions);
      const type = blob.type;
      const arrayBuffer = await blob.arrayBuffer();
      const base64 = encode(arrayBuffer);
      if (!lastBlobMap.has(id) && await transparentBase64 === base64) {
        lastBlobMap.set(id, base64);
        return worker.postMessage({ id });
      }
      if (lastBlobMap.get(id) === base64) return worker.postMessage({ id });
      worker.postMessage({
        id,
        type,
        base64,
        width,
        height
      });
      lastBlobMap.set(id, base64);
    } else {
      return worker.postMessage({ id: e.data.id });
    }
  };
})();
//# sourceMappingURL=image-bitmap-data-url-worker-IJpC7g_b.js.map
`,kt=typeof self!="undefined"&&self.Blob&&new Blob([nr],{type:"text/javascript;charset=utf-8"});function Fn(e){let t;try{if(t=kt&&(self.URL||self.webkitURL).createObjectURL(kt),!t)throw"";const r=new Worker(t,{name:e==null?void 0:e.name});return r.addEventListener("error",()=>{(self.URL||self.webkitURL).revokeObjectURL(t)}),r}catch(r){return new Worker("data:text/javascript;charset=utf-8,"+encodeURIComponent(nr),{name:e==null?void 0:e.name})}finally{t&&(self.URL||self.webkitURL).revokeObjectURL(t)}}class Pn{constructor(t){g(this,"pendingCanvasMutations",new Map),g(this,"rafStamps",{latestId:0,invokeId:null}),g(this,"mirror"),g(this,"mutationCb"),g(this,"resetObservers"),g(this,"frozen",!1),g(this,"locked",!1),g(this,"processMutation",(i,u)=>{(this.rafStamps.invokeId&&this.rafStamps.latestId!==this.rafStamps.invokeId||!this.rafStamps.invokeId)&&(this.rafStamps.invokeId=this.rafStamps.latestId),this.pendingCanvasMutations.has(i)||this.pendingCanvasMutations.set(i,[]),this.pendingCanvasMutations.get(i).push(u)});const{sampling:r="all",win:n,blockClass:o,blockSelector:s,recordCanvas:a,dataURLOptions:c}=t;this.mutationCb=t.mutationCb,this.mirror=t.mirror,a&&r==="all"&&this.initCanvasMutationObserver(n,o,s),a&&typeof r=="number"&&this.initCanvasFPSObserver(r,n,o,s,{dataURLOptions:c})}reset(){this.pendingCanvasMutations.clear(),this.resetObservers&&this.resetObservers()}freeze(){this.frozen=!0}unfreeze(){this.frozen=!1}lock(){this.locked=!0}unlock(){this.locked=!1}initCanvasFPSObserver(t,r,n,o,s){const a=Nt(r,n,o,!0),c=new Map,i=new Fn;i.onmessage=m=>{const{id:l}=m.data;if(c.set(l,!1),!("base64"in m.data))return;const{base64:S,type:w,width:C,height:y}=m.data;this.mutationCb({id:l,type:ge["2D"],commands:[{property:"clearRect",args:[0,0,C,y]},{property:"drawImage",args:[{rr_type:"ImageBitmap",args:[{rr_type:"Blob",data:[{rr_type:"ArrayBuffer",base64:S}],type:w}]},0,0]}]})};const u=1e3/t;let d=0,h;const p=()=>{const m=[];return r.document.querySelectorAll("canvas").forEach(l=>{U(l,n,o,!0)||m.push(l)}),m},f=m=>{if(d&&m-d<u){h=requestAnimationFrame(f);return}d=m,p().forEach(async l=>{var S;const w=this.mirror.getId(l);if(c.get(w)||l.width===0||l.height===0)return;if(c.set(w,!0),["webgl","webgl2"].includes(l.__context)){const y=l.getContext(l.__context);((S=y==null?void 0:y.getContextAttributes())==null?void 0:S.preserveDrawingBuffer)===!1&&y.clear(y.COLOR_BUFFER_BIT)}const C=await createImageBitmap(l);i.postMessage({id:w,bitmap:C,width:l.width,height:l.height,dataURLOptions:s.dataURLOptions},[C])}),h=requestAnimationFrame(f)};h=requestAnimationFrame(f),this.resetObservers=()=>{a(),cancelAnimationFrame(h)}}initCanvasMutationObserver(t,r,n){this.startRAFTimestamping(),this.startPendingCanvasMutationFlusher();const o=Nt(t,r,n,!1),s=Ln(this.processMutation.bind(this),t,r,n),a=_n(this.processMutation.bind(this),t,r,n);this.resetObservers=()=>{o(),s(),a()}}startPendingCanvasMutationFlusher(){requestAnimationFrame(()=>this.flushPendingCanvasMutations())}startRAFTimestamping(){const t=r=>{this.rafStamps.latestId=r,requestAnimationFrame(t)};requestAnimationFrame(t)}flushPendingCanvasMutations(){this.pendingCanvasMutations.forEach((t,r)=>{const n=this.mirror.getId(r);this.flushPendingCanvasMutationFor(r,n)}),requestAnimationFrame(()=>this.flushPendingCanvasMutations())}flushPendingCanvasMutationFor(t,r){if(this.frozen||this.locked)return;const n=this.pendingCanvasMutations.get(t);if(!n||r===-1)return;const o=n.map(a=>{const u=a,{type:c}=u;return ft(u,["type"])}),{type:s}=n[0];this.mutationCb({id:r,type:s,commands:o}),this.pendingCanvasMutations.delete(t)}}class Wn{constructor(t){g(this,"trackedLinkElements",new WeakSet),g(this,"mutationCb"),g(this,"adoptedStyleSheetCb"),g(this,"styleMirror",new ln),this.mutationCb=t.mutationCb,this.adoptedStyleSheetCb=t.adoptedStyleSheetCb}attachLinkElement(t,r){"_cssText"in r.attributes&&this.mutationCb({adds:[],removes:[],texts:[],attributes:[{id:r.id,attributes:r.attributes}]}),this.trackLinkElement(t)}trackLinkElement(t){this.trackedLinkElements.has(t)||(this.trackedLinkElements.add(t),this.trackStylesheetInLinkElement(t))}adoptStyleSheets(t,r){if(t.length===0)return;const n={id:r,styleIds:[]},o=[];for(const s of t){let a;this.styleMirror.has(s)?a=this.styleMirror.getId(s):(a=this.styleMirror.add(s),o.push({styleId:a,rules:Array.from(s.rules||CSSRule,(c,i)=>({rule:Lt(c,s.href),index:i}))})),n.styleIds.push(a)}o.length>0&&(n.styles=o),this.adoptedStyleSheetCb(n)}reset(){this.styleMirror.reset(),this.trackedLinkElements=new WeakSet}trackStylesheetInLinkElement(t){}}class Un{constructor(){g(this,"nodeMap",new WeakMap),g(this,"active",!1)}inOtherBuffer(t,r){const n=this.nodeMap.get(t);return n&&Array.from(n).some(o=>o!==r)}add(t,r){this.active||(this.active=!0,requestAnimationFrame(()=>{this.nodeMap=new WeakMap,this.active=!1})),this.nodeMap.set(t,(this.nodeMap.get(t)||new Set).add(r))}destroy(){}}let x,Fe,re,Oe=!1;try{if(Array.from([1],e=>e*2)[0]!==2){const e=document.createElement("iframe");document.body.appendChild(e),Array.from=((pt=e.contentWindow)==null?void 0:pt.Array.from)||Array.from,document.body.removeChild(e)}}catch(e){console.debug("Unable to override Array.from",e)}const X=xr();function ye(e={}){const{emit:t,checkoutEveryNms:r,checkoutEveryNth:n,blockClass:o="rr-block",blockSelector:s=null,ignoreClass:a="rr-ignore",ignoreSelector:c=null,maskTextClass:i="rr-mask",maskTextSelector:u=null,inlineStylesheet:d=!0,maskAllInputs:h,maskInputOptions:p,slimDOMOptions:f,maskInputFn:m,maskTextFn:l,hooks:S,packFn:w,sampling:C={},dataURLOptions:y={},mousemoveWait:M,recordDOM:D=!0,recordCanvas:L=!1,recordCrossOriginIframes:W=!1,recordAfter:Z=e.recordAfter==="DOMContentLoaded"?e.recordAfter:"load",userTriggeredOnInput:j=!1,collectFonts:Y=!1,inlineImages:V=!1,plugins:Q,keepIframeSrcFn:N=()=>!1,ignoreCSSAttributes:Se=new Set([]),errorHandler:be}=e;fn(be);const _=W?window.parent===window:!0;let $=!1;if(!_)try{window.parent.document&&($=!1)}catch(E){$=!0}if(_&&!t)throw new Error("emit function is required");if(!_&&!$)return()=>{};M!==void 0&&C.mousemove===void 0&&(C.mousemove=M),X.reset();const se=h===!0?{color:!0,date:!0,"datetime-local":!0,email:!0,month:!0,number:!0,range:!0,search:!0,tel:!0,text:!0,time:!0,url:!0,week:!0,textarea:!0,select:!0,password:!0}:p!==void 0?p:{password:!0},K=zt(f);an();let it,je=0;const at=E=>{for(const J of Q||[])J.eventProcessor&&(E=J.eventProcessor(E));return w&&!$&&(E=w(E)),E};x=(E,J)=>{const v=E;if(v.timestamp=Ie(),v.type!==I.FullSnapshot&&!(v.type===I.IncrementalSnapshot&&v.data.source===R.Mutation)){re.unfreeze();for(const B of me)if(B.isFrozen())B.unfreeze();else break}if(_)t==null||t(at(v),J);else if($){const B={type:"rrweb",event:at(v),origin:window.location.origin,isCheckout:J};window.parent.postMessage(B,"*")}if(v.type===I.FullSnapshot)it=v,je=0;else if(v.type===I.IncrementalSnapshot){if(v.data.source===R.Mutation&&v.data.isAttachIframe)return;je++;const B=n&&je>=n,q=r&&v.timestamp-it.timestamp>r;(B||q)&&Fe(!0)}};const Ee=E=>{x({type:I.IncrementalSnapshot,data:F({source:R.Mutation},E)})},lt=E=>x({type:I.IncrementalSnapshot,data:F({source:R.Scroll},E)}),ct=E=>x({type:I.IncrementalSnapshot,data:F({source:R.CanvasMutation},E)}),or=E=>x({type:I.IncrementalSnapshot,data:F({source:R.AdoptedStyleSheet},E)}),ie=new Wn({mutationCb:Ee,adoptedStyleSheetCb:or}),ee=new En({mirror:X,mutationCb:Ee,stylesheetManager:ie,recordCrossOriginIframes:W,wrappedEmit:x});for(const E of Q||[])E.getMirror&&E.getMirror({nodeMirror:X,crossOriginIframeMirror:ee.crossOriginIframeMirror,crossOriginIframeStyleMirror:ee.crossOriginIframeStyleMirror});const Ve=new Un;re=new Pn({recordCanvas:L,mutationCb:ct,win:window,blockClass:o,blockSelector:s,mirror:X,sampling:C.canvas,dataURLOptions:y});const le=new kn({mutationCb:Ee,scrollCb:lt,bypassOptions:{blockClass:o,blockSelector:s,maskTextClass:i,maskTextSelector:u,inlineStylesheet:d,maskInputOptions:se,dataURLOptions:y,maskTextFn:l,maskInputFn:m,recordCanvas:L,inlineImages:V,sampling:C,slimDOMOptions:K,iframeManager:ee,stylesheetManager:ie,canvasManager:re,keepIframeSrcFn:N,processedNodeManager:Ve},mirror:X});Fe=(E=!1)=>{if(!D)return;x({type:I.Meta,data:{href:window.location.href,width:jt(),height:Gt()}},E),ie.reset(),le.init(),re.lock(),me.forEach(v=>v.lock());const J=on(document,{mirror:X,blockClass:o,blockSelector:s,maskTextClass:i,maskTextSelector:u,inlineStylesheet:d,maskAllInputs:se,maskTextFn:l,maskInputFn:m,slimDOM:K,dataURLOptions:y,recordCanvas:L,inlineImages:V,onSerialize:v=>{qt(v,X)&&ee.addIframe(v),Xt(v,X)&&ie.trackLinkElement(v),et(v)&&le.addShadowRoot(b.shadowRoot(v),document)},onIframeLoad:(v,B)=>{ee.attachIframe(v,B),le.observeAttachShadow(v)},onStylesheetLoad:(v,B)=>{ie.attachLinkElement(v,B)},keepIframeSrcFn:N});if(!J)return console.warn("Failed to snapshot the document");x({type:I.FullSnapshot,data:{node:J,initialOffset:Ht(window)}},E),re.unlock(),me.forEach(v=>v.unlock()),document.adoptedStyleSheets&&document.adoptedStyleSheets.length>0&&ie.adoptStyleSheets(document.adoptedStyleSheets,X.getId(document))};try{const E=[],J=q=>{var z;return O(Nn)({mutationCb:Ee,mousemoveCb:(k,$e)=>x({type:I.IncrementalSnapshot,data:{source:$e,positions:k}}),mouseInteractionCb:k=>x({type:I.IncrementalSnapshot,data:F({source:R.MouseInteraction},k)}),scrollCb:lt,viewportResizeCb:k=>x({type:I.IncrementalSnapshot,data:F({source:R.ViewportResize},k)}),inputCb:k=>x({type:I.IncrementalSnapshot,data:F({source:R.Input},k)}),mediaInteractionCb:k=>x({type:I.IncrementalSnapshot,data:F({source:R.MediaInteraction},k)}),styleSheetRuleCb:k=>x({type:I.IncrementalSnapshot,data:F({source:R.StyleSheetRule},k)}),styleDeclarationCb:k=>x({type:I.IncrementalSnapshot,data:F({source:R.StyleDeclaration},k)}),canvasMutationCb:ct,fontCb:k=>x({type:I.IncrementalSnapshot,data:F({source:R.Font},k)}),selectionCb:k=>{x({type:I.IncrementalSnapshot,data:F({source:R.Selection},k)})},customElementCb:k=>{x({type:I.IncrementalSnapshot,data:F({source:R.CustomElement},k)})},blockClass:o,ignoreClass:a,ignoreSelector:c,maskTextClass:i,maskTextSelector:u,maskInputOptions:se,inlineStylesheet:d,sampling:C,recordDOM:D,recordCanvas:L,inlineImages:V,userTriggeredOnInput:j,collectFonts:Y,doc:q,maskInputFn:m,maskTextFn:l,keepIframeSrcFn:N,blockSelector:s,slimDOMOptions:K,dataURLOptions:y,mirror:X,iframeManager:ee,stylesheetManager:ie,shadowDomManager:le,processedNodeManager:Ve,canvasManager:re,ignoreCSSAttributes:Se,plugins:((z=Q==null?void 0:Q.filter(k=>k.observer))==null?void 0:z.map(k=>({observer:k.observer,options:k.options,callback:$e=>x({type:I.Plugin,data:{plugin:k.name,payload:$e}})})))||[]},S)},v=new Map;ee.addLoadListener(q=>{try{const z=q.contentDocument;if(v.has(z))return;v.set(z,J(z))}catch(z){console.warn(z)}}),ee.addUnloadListener(q=>{const z=v.get(q);z&&(v.delete(q),z(),le.removeShadowRootsIn(q),X.removeNodeFromMap(q))});const B=()=>{Fe(),E.push(J(document)),Oe=!0};return["interactive","complete"].includes(document.readyState)?B():(E.push(P("DOMContentLoaded",()=>{x({type:I.DomContentLoaded,data:{}}),Z==="DOMContentLoaded"&&B()})),E.push(P("load",()=>{x({type:I.Load,data:{}}),Z==="load"&&B()},window))),()=>{[...E,...v.values()].forEach(q=>{try{q()}catch(z){String(z).toLowerCase().includes("cross-origin")||console.warn(z)}}),v.clear(),ee.destroy(),Ve.destroy(),le.reset(),re.reset(),Oe=!1,pn()}}catch(E){console.warn(E)}}ye.addCustomEvent=(e,t)=>{if(!Oe)throw new Error("please add custom event after start recording");x({type:I.Custom,data:{tag:e,payload:t}})};ye.addAnnotation=e=>{if(!Oe)throw new Error("please add annotation after recording started");x({type:I.Annotation,data:e})};ye.freezePage=()=>{re.freeze(),me.forEach(e=>e.freeze())};ye.takeFullSnapshot=e=>{if(!Oe)throw new Error("please take full snapshot after start recording");Fe(e)};ye.mirror=X;exports.record=ye;
if (typeof module.exports == "object" && typeof exports == "object") {
  var __cp = (to, from, except, desc) => {
    if ((from && typeof from === "object") || typeof from === "function") {
      for (let key of Object.getOwnPropertyNames(from)) {
        if (!Object.prototype.hasOwnProperty.call(to, key) && key !== except)
        Object.defineProperty(to, key, {
          get: () => from[key],
          enumerable: !(desc = Object.getOwnPropertyDescriptor(from, key)) || desc.enumerable,
        });
      }
    }
    return to;
  };
  module.exports = __cp(module.exports, exports);
}
return module.exports;
}))
  C.rrweb = this.rrwebRecord
  }).call(SCOPE)
  // ---- static/src/botd.js
  ;(function () {
/*
 * BotD, vendored for Agent Cake's page script (S1.3).
 * Source: @fingerprintjs/botd 2.0.0 on npm, dist/botd.esm.js (sha256 f438ed251dc7414ece9d4a2b6941441ad9ffae1a1905817f5f0c7366e701dd86);
 * the same 19 sources and detectors as github.com/fingerprintjs/BotD at commit 193c471a (package version 2.0.0).
 * Licence: MIT, Copyright (c) 2025 FingerprintJS, Inc (full text: botd.LICENSE.txt, also bundled into cake.js).
 * Changes from the npm file, and nothing else:
 *   1. removed monitor() and load()'s `monitoring` option: the original sends a usage request to FingerprintJS's
 *      monitoring host on 1 in 1,000 loads; cake.js sends nothing anywhere but to cake (G13);
 *   2. removed the trailing `export { ... }` statement: build_js.py concatenates this file into cake.js inside a
 *      function and hands load() to cake's parts directly.
 */
/**
 * Fingerprint BotD v2.0.0 - Copyright (c) FingerprintJS, Inc, 2025 (https://fingerprint.com)
 * Licensed under the MIT (http://www.opensource.org/licenses/mit-license.php) license.
 */

var version = "2.0.0";

/**
 * Enum for types of bots.
 * Specific types of bots come first, followed by automation technologies.
 *
 * @readonly
 * @enum {string}
 */
const BotKind = {
    // Object is used instead of Typescript enum to avoid emitting IIFE which might be affected by further tree-shaking.
    // See example of compiled enums https://stackoverflow.com/q/47363996)
    Awesomium: 'awesomium',
    Cef: 'cef',
    CefSharp: 'cefsharp',
    CoachJS: 'coachjs',
    Electron: 'electron',
    FMiner: 'fminer',
    Geb: 'geb',
    NightmareJS: 'nightmarejs',
    Phantomas: 'phantomas',
    PhantomJS: 'phantomjs',
    Rhino: 'rhino',
    Selenium: 'selenium',
    Sequentum: 'sequentum',
    SlimerJS: 'slimerjs',
    WebDriverIO: 'webdriverio',
    WebDriver: 'webdriver',
    HeadlessChrome: 'headless_chrome',
    Unknown: 'unknown',
};
/**
 * Bot detection error.
 */
class BotdError extends Error {
    /**
     * Creates a new BotdError.
     *
     * @class
     */
    constructor(state, message) {
        super(message);
        this.state = state;
        this.name = 'BotdError';
        Object.setPrototypeOf(this, BotdError.prototype);
    }
}

function detect(components, detectors) {
    const detections = {};
    let finalDetection = {
        bot: false,
    };
    for (const detectorName in detectors) {
        const detector = detectors[detectorName];
        const detectorRes = detector(components);
        let detection = { bot: false };
        if (typeof detectorRes === 'string') {
            detection = { bot: true, botKind: detectorRes };
        }
        else if (detectorRes) {
            detection = { bot: true, botKind: BotKind.Unknown };
        }
        detections[detectorName] = detection;
        if (detection.bot) {
            finalDetection = detection;
        }
    }
    return [detections, finalDetection];
}
async function collect(sources) {
    const components = {};
    const sourcesKeys = Object.keys(sources);
    await Promise.all(sourcesKeys.map(async (sourceKey) => {
        const res = sources[sourceKey];
        try {
            components[sourceKey] = {
                value: await res(),
                state: 0 /* State.Success */,
            };
        }
        catch (error) {
            if (error instanceof BotdError) {
                components[sourceKey] = {
                    state: error.state,
                    error: `${error.name}: ${error.message}`,
                };
            }
            else {
                components[sourceKey] = {
                    state: -3 /* State.UnexpectedBehaviour */,
                    error: error instanceof Error ? `${error.name}: ${error.message}` : String(error),
                };
            }
        }
    }));
    return components;
}

function detectAppVersion({ appVersion }) {
    if (appVersion.state !== 0 /* State.Success */)
        return false;
    if (/headless/i.test(appVersion.value))
        return BotKind.HeadlessChrome;
    if (/electron/i.test(appVersion.value))
        return BotKind.Electron;
    if (/slimerjs/i.test(appVersion.value))
        return BotKind.SlimerJS;
}

function arrayIncludes(arr, value) {
    return arr.indexOf(value) !== -1;
}
function strIncludes(str, value) {
    return str.indexOf(value) !== -1;
}
function arrayFind(array, callback) {
    if ('find' in array)
        return array.find(callback);
    for (let i = 0; i < array.length; i++) {
        if (callback(array[i], i, array))
            return array[i];
    }
    return undefined;
}

function getObjectProps(obj) {
    return Object.getOwnPropertyNames(obj);
}
function includes(arr, ...keys) {
    for (const key of keys) {
        if (typeof key === 'string') {
            if (arrayIncludes(arr, key))
                return true;
        }
        else {
            const match = arrayFind(arr, (value) => key.test(value));
            if (match != null)
                return true;
        }
    }
    return false;
}
function countTruthy(values) {
    return values.reduce((sum, value) => sum + (value ? 1 : 0), 0);
}

function detectDocumentAttributes({ documentElementKeys }) {
    if (documentElementKeys.state !== 0 /* State.Success */)
        return false;
    if (includes(documentElementKeys.value, 'selenium', 'webdriver', 'driver')) {
        return BotKind.Selenium;
    }
}

function detectErrorTrace({ errorTrace }) {
    if (errorTrace.state !== 0 /* State.Success */)
        return false;
    if (/PhantomJS/i.test(errorTrace.value))
        return BotKind.PhantomJS;
}

function detectEvalLengthInconsistency({ evalLength, browserKind, browserEngineKind, }) {
    if (evalLength.state !== 0 /* State.Success */ ||
        browserKind.state !== 0 /* State.Success */ ||
        browserEngineKind.state !== 0 /* State.Success */)
        return;
    const length = evalLength.value;
    if (browserEngineKind.value === "unknown" /* BrowserEngineKind.Unknown */)
        return false;
    return ((length === 37 && !arrayIncludes(["webkit" /* BrowserEngineKind.Webkit */, "gecko" /* BrowserEngineKind.Gecko */], browserEngineKind.value)) ||
        (length === 39 && !arrayIncludes(["internet_explorer" /* BrowserKind.IE */], browserKind.value)) ||
        (length === 33 && !arrayIncludes(["chromium" /* BrowserEngineKind.Chromium */], browserEngineKind.value)));
}

function detectFunctionBind({ functionBind }) {
    if (functionBind.state === -2 /* State.NotFunction */)
        return BotKind.PhantomJS;
}

function detectLanguagesLengthInconsistency({ languages }) {
    if (languages.state === 0 /* State.Success */ && languages.value.length === 0) {
        return BotKind.HeadlessChrome;
    }
}

function detectMimeTypesConsistent({ mimeTypesConsistent }) {
    if (mimeTypesConsistent.state === 0 /* State.Success */ && !mimeTypesConsistent.value) {
        return BotKind.Unknown;
    }
}

function detectNotificationPermissions({ notificationPermissions, browserKind, }) {
    if (browserKind.state !== 0 /* State.Success */ || browserKind.value !== "chrome" /* BrowserKind.Chrome */)
        return false;
    if (notificationPermissions.state === 0 /* State.Success */ && notificationPermissions.value) {
        return BotKind.HeadlessChrome;
    }
}

function detectPluginsArray({ pluginsArray }) {
    if (pluginsArray.state === 0 /* State.Success */ && !pluginsArray.value)
        return BotKind.HeadlessChrome;
}

function detectPluginsLengthInconsistency({ pluginsLength, android, browserKind, browserEngineKind, }) {
    if (pluginsLength.state !== 0 /* State.Success */ ||
        android.state !== 0 /* State.Success */ ||
        browserKind.state !== 0 /* State.Success */ ||
        browserEngineKind.state !== 0 /* State.Success */)
        return;
    if (browserKind.value !== "chrome" /* BrowserKind.Chrome */ ||
        android.value ||
        browserEngineKind.value !== "chromium" /* BrowserEngineKind.Chromium */)
        return;
    if (pluginsLength.value === 0)
        return BotKind.HeadlessChrome;
}

function detectProcess({ process }) {
    var _a;
    if (process.state !== 0 /* State.Success */)
        return false;
    if (process.value.type === 'renderer' || ((_a = process.value.versions) === null || _a === void 0 ? void 0 : _a.electron) != null)
        return BotKind.Electron;
}

function detectProductSub({ productSub, browserKind }) {
    if (productSub.state !== 0 /* State.Success */ || browserKind.state !== 0 /* State.Success */)
        return false;
    if ((browserKind.value === "chrome" /* BrowserKind.Chrome */ ||
        browserKind.value === "safari" /* BrowserKind.Safari */ ||
        browserKind.value === "opera" /* BrowserKind.Opera */ ||
        browserKind.value === "wechat" /* BrowserKind.WeChat */) &&
        productSub.value !== '20030107')
        return BotKind.Unknown;
}

function detectUserAgent({ userAgent }) {
    if (userAgent.state !== 0 /* State.Success */)
        return false;
    if (/PhantomJS/i.test(userAgent.value))
        return BotKind.PhantomJS;
    if (/Headless/i.test(userAgent.value))
        return BotKind.HeadlessChrome;
    if (/Electron/i.test(userAgent.value))
        return BotKind.Electron;
    if (/slimerjs/i.test(userAgent.value))
        return BotKind.SlimerJS;
}

function detectWebDriver({ webDriver }) {
    if (webDriver.state === 0 /* State.Success */ && webDriver.value)
        return BotKind.HeadlessChrome;
}

function detectWebGL({ webGL }) {
    if (webGL.state === 0 /* State.Success */) {
        const { vendor, renderer } = webGL.value;
        if (vendor == 'Brian Paul' && renderer == 'Mesa OffScreen') {
            return BotKind.HeadlessChrome;
        }
    }
}

function detectWindowExternal({ windowExternal }) {
    if (windowExternal.state !== 0 /* State.Success */)
        return false;
    if (/Sequentum/i.test(windowExternal.value))
        return BotKind.Sequentum;
}

function detectWindowSize({ windowSize, documentFocus }) {
    if (windowSize.state !== 0 /* State.Success */ || documentFocus.state !== 0 /* State.Success */)
        return false;
    const { outerWidth, outerHeight } = windowSize.value;
    // When a page is opened in a new tab without focusing it right away, the window outer size is 0x0
    if (!documentFocus.value)
        return;
    if (outerWidth === 0 && outerHeight === 0)
        return BotKind.HeadlessChrome;
}

function detectDistinctiveProperties({ distinctiveProps }) {
    if (distinctiveProps.state !== 0 /* State.Success */)
        return false;
    const value = distinctiveProps.value;
    let bot;
    for (bot in value)
        if (value[bot])
            return bot;
}

// eslint-disable-next-line @typescript-eslint/explicit-module-boundary-types
const detectors = {
    detectAppVersion,
    detectDocumentAttributes,
    detectErrorTrace,
    detectEvalLengthInconsistency,
    detectFunctionBind,
    detectLanguagesLengthInconsistency,
    detectNotificationPermissions,
    detectPluginsArray,
    detectPluginsLengthInconsistency,
    detectProcess,
    detectUserAgent,
    detectWebDriver,
    detectWebGL,
    detectWindowExternal,
    detectWindowSize,
    detectMimeTypesConsistent,
    detectProductSub,
    detectDistinctiveProperties,
};

function getAppVersion() {
    const appVersion = navigator.appVersion;
    if (appVersion == undefined) {
        throw new BotdError(-1 /* State.Undefined */, 'navigator.appVersion is undefined');
    }
    return appVersion;
}

function getDocumentElementKeys() {
    if (document.documentElement === undefined) {
        throw new BotdError(-1 /* State.Undefined */, 'document.documentElement is undefined');
    }
    const { documentElement } = document;
    if (typeof documentElement.getAttributeNames !== 'function') {
        throw new BotdError(-2 /* State.NotFunction */, 'document.documentElement.getAttributeNames is not a function');
    }
    return documentElement.getAttributeNames();
}

function getErrorTrace() {
    try {
        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
        // @ts-ignore
        null[0]();
    }
    catch (error) {
        if (error instanceof Error && error['stack'] != null) {
            return error.stack.toString();
        }
    }
    throw new BotdError(-3 /* State.UnexpectedBehaviour */, 'errorTrace signal unexpected behaviour');
}

function getEvalLength() {
    return eval.toString().length;
}

function getFunctionBind() {
    if (Function.prototype.bind === undefined) {
        throw new BotdError(-2 /* State.NotFunction */, 'Function.prototype.bind is undefined');
    }
    return Function.prototype.bind.toString();
}

function getBrowserEngineKind() {
    var _a, _b;
    // Based on research in October 2020. Tested to detect Chromium 42-86.
    const w = window;
    const n = navigator;
    if (countTruthy([
        'webkitPersistentStorage' in n,
        'webkitTemporaryStorage' in n,
        n.vendor.indexOf('Google') === 0,
        'webkitResolveLocalFileSystemURL' in w,
        'BatteryManager' in w,
        'webkitMediaStream' in w,
        'webkitSpeechGrammar' in w,
    ]) >= 5) {
        return "chromium" /* BrowserEngineKind.Chromium */;
    }
    if (countTruthy([
        'ApplePayError' in w,
        'CSSPrimitiveValue' in w,
        'Counter' in w,
        n.vendor.indexOf('Apple') === 0,
        'getStorageUpdates' in n,
        'WebKitMediaKeys' in w,
    ]) >= 4) {
        return "webkit" /* BrowserEngineKind.Webkit */;
    }
    if (countTruthy([
        'buildID' in navigator,
        'MozAppearance' in ((_b = (_a = document.documentElement) === null || _a === void 0 ? void 0 : _a.style) !== null && _b !== void 0 ? _b : {}),
        'onmozfullscreenchange' in w,
        'mozInnerScreenX' in w,
        'CSSMozDocumentRule' in w,
        'CanvasCaptureMediaStream' in w,
    ]) >= 4) {
        return "gecko" /* BrowserEngineKind.Gecko */;
    }
    return "unknown" /* BrowserEngineKind.Unknown */;
}
function getBrowserKind() {
    var _a;
    const userAgent = (_a = navigator.userAgent) === null || _a === void 0 ? void 0 : _a.toLowerCase();
    if (strIncludes(userAgent, 'edg/')) {
        return "edge" /* BrowserKind.Edge */;
    }
    else if (strIncludes(userAgent, 'trident') || strIncludes(userAgent, 'msie')) {
        return "internet_explorer" /* BrowserKind.IE */;
    }
    else if (strIncludes(userAgent, 'wechat')) {
        return "wechat" /* BrowserKind.WeChat */;
    }
    else if (strIncludes(userAgent, 'firefox')) {
        return "firefox" /* BrowserKind.Firefox */;
    }
    else if (strIncludes(userAgent, 'opera') || strIncludes(userAgent, 'opr')) {
        return "opera" /* BrowserKind.Opera */;
    }
    else if (strIncludes(userAgent, 'chrome')) {
        return "chrome" /* BrowserKind.Chrome */;
    }
    else if (strIncludes(userAgent, 'safari')) {
        return "safari" /* BrowserKind.Safari */;
    }
    else {
        return "unknown" /* BrowserKind.Unknown */;
    }
}
// Source: https://github.com/fingerprintjs/fingerprintjs/blob/master/src/utils/browser.ts#L223
function isAndroid() {
    const browserEngineKind = getBrowserEngineKind();
    const isItChromium = browserEngineKind === "chromium" /* BrowserEngineKind.Chromium */;
    const isItGecko = browserEngineKind === "gecko" /* BrowserEngineKind.Gecko */;
    const w = window;
    const n = navigator;
    const c = 'connection';
    // Chrome removes all words "Android" from `navigator` when desktop version is requested
    // Firefox keeps "Android" in `navigator.appVersion` when desktop version is requested
    if (isItChromium) {
        return (countTruthy([
            !('SharedWorker' in w),
            // `typechange` is deprecated, but it's still present on Android (tested on Chrome Mobile 117)
            // Removal proposal https://bugs.chromium.org/p/chromium/issues/detail?id=699892
            // Note: this expression returns true on ChromeOS, so additional detectors are required to avoid false-positives
            n[c] && 'ontypechange' in n[c],
            !('sinkId' in new Audio()),
        ]) >= 2);
    }
    else if (isItGecko) {
        return countTruthy(['onorientationchange' in w, 'orientation' in w, /android/i.test(n.appVersion)]) >= 2;
    }
    else {
        // Only 2 browser engines are presented on Android.
        // Actually, there is also Android 4.1 browser, but it's not worth detecting it at the moment.
        return false;
    }
}
function getDocumentFocus() {
    if (document.hasFocus === undefined) {
        return false;
    }
    return document.hasFocus();
}
function isChromium86OrNewer() {
    // Checked in Chrome 85 vs Chrome 86 both on desktop and Android. Checked in macOS Chrome 128, Android Chrome 127.
    const w = window;
    return (countTruthy([
        !('MediaSettingsRange' in w),
        'RTCEncodedAudioFrame' in w,
        '' + w.Intl === '[object Intl]',
        '' + w.Reflect === '[object Reflect]',
    ]) >= 3);
}

function getLanguages() {
    const n = navigator;
    const result = [];
    const language = n.language || n.userLanguage || n.browserLanguage || n.systemLanguage;
    if (language !== undefined) {
        result.push([language]);
    }
    if (Array.isArray(n.languages)) {
        const browserEngine = getBrowserEngineKind();
        // Starting from Chromium 86, there is only a single value in `navigator.language` in Incognito mode:
        // the value of `navigator.language`. Therefore, the value is ignored in this browser.
        if (!(browserEngine === "chromium" /* BrowserEngineKind.Chromium */ && isChromium86OrNewer())) {
            result.push(n.languages);
        }
    }
    else if (typeof n.languages === 'string') {
        const languages = n.languages;
        if (languages) {
            result.push(languages.split(','));
        }
    }
    return result;
}

function areMimeTypesConsistent() {
    if (navigator.mimeTypes === undefined) {
        throw new BotdError(-1 /* State.Undefined */, 'navigator.mimeTypes is undefined');
    }
    const { mimeTypes } = navigator;
    let isConsistent = Object.getPrototypeOf(mimeTypes) === MimeTypeArray.prototype;
    for (let i = 0; i < mimeTypes.length; i++) {
        isConsistent && (isConsistent = Object.getPrototypeOf(mimeTypes[i]) === MimeType.prototype);
    }
    return isConsistent;
}

async function getNotificationPermissions() {
    if (window.Notification === undefined) {
        throw new BotdError(-1 /* State.Undefined */, 'window.Notification is undefined');
    }
    if (navigator.permissions === undefined) {
        throw new BotdError(-1 /* State.Undefined */, 'navigator.permissions is undefined');
    }
    const { permissions } = navigator;
    if (typeof permissions.query !== 'function') {
        throw new BotdError(-2 /* State.NotFunction */, 'navigator.permissions.query is not a function');
    }
    try {
        const permissionStatus = await permissions.query({ name: 'notifications' });
        return window.Notification.permission === 'denied' && permissionStatus.state === 'prompt';
    }
    catch (e) {
        throw new BotdError(-3 /* State.UnexpectedBehaviour */, 'notificationPermissions signal unexpected behaviour');
    }
}

function getPluginsArray() {
    if (navigator.plugins === undefined) {
        throw new BotdError(-1 /* State.Undefined */, 'navigator.plugins is undefined');
    }
    if (window.PluginArray === undefined) {
        throw new BotdError(-1 /* State.Undefined */, 'window.PluginArray is undefined');
    }
    return navigator.plugins instanceof PluginArray;
}

function getPluginsLength() {
    if (navigator.plugins === undefined) {
        throw new BotdError(-1 /* State.Undefined */, 'navigator.plugins is undefined');
    }
    if (navigator.plugins.length === undefined) {
        throw new BotdError(-3 /* State.UnexpectedBehaviour */, 'navigator.plugins.length is undefined');
    }
    return navigator.plugins.length;
}

function getProcess() {
    const { process } = window;
    const errorPrefix = 'window.process is';
    if (process === undefined) {
        throw new BotdError(-1 /* State.Undefined */, `${errorPrefix} undefined`);
    }
    if (process && typeof process !== 'object') {
        throw new BotdError(-3 /* State.UnexpectedBehaviour */, `${errorPrefix} not an object`);
    }
    return process;
}

function getProductSub() {
    const { productSub } = navigator;
    if (productSub === undefined) {
        throw new BotdError(-1 /* State.Undefined */, 'navigator.productSub is undefined');
    }
    return productSub;
}

function getRTT() {
    if (navigator.connection === undefined) {
        throw new BotdError(-1 /* State.Undefined */, 'navigator.connection is undefined');
    }
    if (navigator.connection.rtt === undefined) {
        throw new BotdError(-1 /* State.Undefined */, 'navigator.connection.rtt is undefined');
    }
    return navigator.connection.rtt;
}

function getUserAgent() {
    return navigator.userAgent;
}

function getWebDriver() {
    if (navigator.webdriver == undefined) {
        throw new BotdError(-1 /* State.Undefined */, 'navigator.webdriver is undefined');
    }
    return navigator.webdriver;
}

function getWebGL() {
    const canvasElement = document.createElement('canvas');
    if (typeof canvasElement.getContext !== 'function') {
        throw new BotdError(-2 /* State.NotFunction */, 'HTMLCanvasElement.getContext is not a function');
    }
    const webGLContext = canvasElement.getContext('webgl');
    if (webGLContext === null) {
        throw new BotdError(-4 /* State.Null */, 'WebGLRenderingContext is null');
    }
    if (typeof webGLContext.getParameter !== 'function') {
        throw new BotdError(-2 /* State.NotFunction */, 'WebGLRenderingContext.getParameter is not a function');
    }
    const vendor = webGLContext.getParameter(webGLContext.VENDOR);
    const renderer = webGLContext.getParameter(webGLContext.RENDERER);
    return { vendor: vendor, renderer: renderer };
}

function getWindowExternal() {
    if (window.external === undefined) {
        throw new BotdError(-1 /* State.Undefined */, 'window.external is undefined');
    }
    const { external } = window;
    if (typeof external.toString !== 'function') {
        throw new BotdError(-2 /* State.NotFunction */, 'window.external.toString is not a function');
    }
    return external.toString();
}

function getWindowSize() {
    return {
        outerWidth: window.outerWidth,
        outerHeight: window.outerHeight,
        innerWidth: window.innerWidth,
        innerHeight: window.innerHeight,
    };
}

function checkDistinctiveProperties() {
    // The order in the following list matters, because specific types of bots come first, followed by automation technologies.
    const distinctivePropsList = {
        [BotKind.Awesomium]: {
            window: ['awesomium'],
        },
        [BotKind.Cef]: {
            window: ['RunPerfTest'],
        },
        [BotKind.CefSharp]: {
            window: ['CefSharp'],
        },
        [BotKind.CoachJS]: {
            window: ['emit'],
        },
        [BotKind.FMiner]: {
            window: ['fmget_targets'],
        },
        [BotKind.Geb]: {
            window: ['geb'],
        },
        [BotKind.NightmareJS]: {
            window: ['__nightmare', 'nightmare'],
        },
        [BotKind.Phantomas]: {
            window: ['__phantomas'],
        },
        [BotKind.PhantomJS]: {
            window: ['callPhantom', '_phantom'],
        },
        [BotKind.Rhino]: {
            window: ['spawn'],
        },
        [BotKind.Selenium]: {
            window: ['_Selenium_IDE_Recorder', '_selenium', 'calledSelenium', /^([a-z]){3}_.*_(Array|Promise|Symbol)$/],
            document: ['__selenium_evaluate', 'selenium-evaluate', '__selenium_unwrapped'],
        },
        [BotKind.WebDriverIO]: {
            window: ['wdioElectron'],
        },
        [BotKind.WebDriver]: {
            window: [
                'webdriver',
                '__webdriverFunc',
                '__lastWatirAlert',
                '__lastWatirConfirm',
                '__lastWatirPrompt',
                '_WEBDRIVER_ELEM_CACHE',
                'ChromeDriverw',
            ],
            document: [
                '__webdriver_script_fn',
                '__driver_evaluate',
                '__webdriver_evaluate',
                '__fxdriver_evaluate',
                '__driver_unwrapped',
                '__webdriver_unwrapped',
                '__fxdriver_unwrapped',
                '__webdriver_script_fn',
                '__webdriver_script_func',
                '__webdriver_script_function',
                '$cdc_asdjflasutopfhvcZLmcf',
                '$cdc_asdjflasutopfhvcZLmcfl_',
                '$chrome_asyncScriptInfo',
                '__$webdriverAsyncExecutor',
            ],
        },
        [BotKind.HeadlessChrome]: {
            window: ['domAutomation', 'domAutomationController'],
        },
    };
    let botName;
    const result = {};
    const windowProps = getObjectProps(window);
    let documentProps = [];
    if (window.document !== undefined)
        documentProps = getObjectProps(window.document);
    for (botName in distinctivePropsList) {
        const props = distinctivePropsList[botName];
        if (props !== undefined) {
            const windowContains = props.window === undefined ? false : includes(windowProps, ...props.window);
            const documentContains = props.document === undefined || !documentProps.length ? false : includes(documentProps, ...props.document);
            result[botName] = windowContains || documentContains;
        }
    }
    return result;
}

const sources = {
    android: isAndroid,
    browserKind: getBrowserKind,
    browserEngineKind: getBrowserEngineKind,
    documentFocus: getDocumentFocus,
    userAgent: getUserAgent,
    appVersion: getAppVersion,
    rtt: getRTT,
    windowSize: getWindowSize,
    pluginsLength: getPluginsLength,
    pluginsArray: getPluginsArray,
    errorTrace: getErrorTrace,
    productSub: getProductSub,
    windowExternal: getWindowExternal,
    mimeTypesConsistent: areMimeTypesConsistent,
    evalLength: getEvalLength,
    webGL: getWebGL,
    webDriver: getWebDriver,
    languages: getLanguages,
    notificationPermissions: getNotificationPermissions,
    documentElementKeys: getDocumentElementKeys,
    functionBind: getFunctionBind,
    process: getProcess,
    distinctiveProps: checkDistinctiveProperties,
};

/**
 * Class representing a bot detector.
 *
 * @class
 * @implements {BotDetectorInterface}
 */
class BotDetector {
    constructor() {
        this.components = undefined;
        this.detections = undefined;
    }
    getComponents() {
        return this.components;
    }
    getDetections() {
        return this.detections;
    }
    /**
     * @inheritdoc
     */
    detect() {
        if (this.components === undefined) {
            throw new Error("BotDetector.detect can't be called before BotDetector.collect");
        }
        const [detections, finalDetection] = detect(this.components, detectors);
        this.detections = detections;
        return finalDetection;
    }
    /**
     * @inheritdoc
     */
    async collect() {
        this.components = await collect(sources);
        return this.components;
    }
}

async function load() {
    const detector = new BotDetector();
    await detector.collect();
    return detector;
}
var index = { load };
  C.botdLoad = load
  }).call(SCOPE)
  // ---- static/src/botscent.js (started by cake.js)
  C.startBotscent = function () {
(function(){let e=`1.2.0`,t=[`signer.web-bot-auth.verified`,`signer.edge-verified-bot`,`signer.web-bot-auth.declared`,`ua.declared-agent-token`,`ua.page-declared-engine`,`browser.webdriver-flag`,`ua.headless-chrome`,`muse.cloud-browser.password-manager`,`instinct.credentials.wrappers`,`instinct.geetest.accessor-pair`,`grok.cloud-computer.environment`,`codex.prompt.anonymous-native`,`codex.keyboard.empty-layout-map`,`codex.overlay.shadow-root`,`chatgpt.badge.active`,`claude.marker.active`,`hidden.input.focus-emulated`,`hidden.input.trusted-pointerdown`],n=Object.freeze({type:`human`,reasons:Object.freeze([])}),r=new Map(t.map((e,t)=>[e,t]));function i(e){let t=/* @__PURE__ */ new Set,n=[],i=[];for(let a of e)t.has(a)||(t.add(a),(r.has(a)?n:i).push(a));return n.sort((e,t)=>r.get(e)-r.get(t)),[...n,...i]}function a(e){let t=/* @__PURE__ */ new Set,n=/* @__PURE__ */ new Set;for(let r of e)r.name&&(r.source===`declaration`?t:n).add(r.name);let r=t.size?t:n;return r.size===1?[...r][0]:void 0}function o(e,t){if(e.length===0)return n;let r=Object.freeze([...e]);return Object.freeze(t?{type:`agent`,agent_name:t,reasons:r}:{type:`agent`,reasons:r})}function s(e){return e.length===0?n:o(i(e.map(e=>e.reason)),a(e))}let c=/^([0-9]{1,3})(?:\.[0-9]{1,3})?;([a-z0-9-]{0,64});([0-9]{0,15});([a-z0-9._-]{1,80}(?:,[a-z0-9._-]{1,80})*)(?:;[\x21-\x3a\x3c-\x7e]*)*$/,l=/^[a-z0-9-]{1,64}$/,u=/^[a-z0-9._-]{1,80}$/;function d(e,t){if(e.type!==`agent`)return null;let n=`1;${e.agent_name&&l.test(e.agent_name)?e.agent_name:``};${typeof t==`number`&&Number.isFinite(t)&&t>=0?String(Math.floor(t)).slice(0,15):``};`,r=``;for(let t of e.reasons){if(!u.test(t))continue;let e=r?`${r},${t}`:t;if(n.length+e.length>256)break;r=e}return r?n+r:null}function f(e){if(typeof e!=`string`||e.length>256)return null;let t=c.exec(e);if(!t||Number(t[1])!==1)return null;let n={reasons:[...new Set(t[4].split(`,`))]};return t[2]&&(n.name=t[2]),t[3]&&(n.time=Number(t[3])),n}function p(e){try{return new URL(String(e),location.href).origin===location.origin}catch{return!1}}function m(e,t){if(e.type!==`agent`||!p(t))return{};let n=d(e);return n?{"Botscent-Report":n}:{}}function h(e){let t=/* @__PURE__ */ new WeakMap,n=e=>{e.target&&t.set(e.target,e)},r=n=>{try{let r=n.target;if(!(r instanceof HTMLFormElement))return;let i=t.get(r);if(!i||i.currentTarget||(t.delete(r),i.defaultPrevented)||!r.hasAttribute(`data-botscent-field`)&&!r.querySelector(`[data-botscent-field]`))return;let a=i.submitter,o=a?.hasAttribute(`formmethod`)?a.formMethod:r.method,s=a?.hasAttribute(`formaction`)?a.formAction:r.action;if(o.toLowerCase()!==`post`||!p(s))return;let c=d(e());c&&n.formData.set(`botscent`,c)}catch{}};return document.addEventListener(`submit`,n,!0),document.addEventListener(`formdata`,r,!0),()=>{document.removeEventListener(`submit`,n,!0),document.removeEventListener(`formdata`,r,!0)}}let g=[[/^Kitesurf\//,`cloudflare-browser-run`],[/(?:^|[ \t;(,+])Cursor\//,`cursor-browser`]],_={"Cloudflare Workers":`cloudflare-browser-run`},v={webdriver:`browser.webdriver-flag`,declared:`ua.page-declared-engine`,muse:`muse.cloud-browser.password-manager`,grok:`grok.cloud-computer.environment`,wrappers:`instinct.credentials.wrappers`,geetest:`instinct.geetest.accessor-pair`,prompt:`codex.prompt.anonymous-native`,keyboard:`codex.keyboard.empty-layout-map`,overlay:`codex.overlay.shadow-root`,badge:`chatgpt.badge.active`,claude:`claude.marker.active`,focus:`hidden.input.focus-emulated`,pointerdown:`hidden.input.trusted-pointerdown`},y=e=>e.every(e=>e.status===`ok`&&e.own&&e.accessor&&e.configurable===!1&&e.enumerable&&e.getter&&e.setter),b=(e,t)=>e===`Linux x86_64`&&Number(/\bChrome\/(\d+)/.exec(t)?.[1]??0)>=139,x=e=>!!e?.includes(`SwiftShader`),S=(e,t)=>e.filter(Boolean).length>=5&&x(t);function C(e){let t=e=>e.status===`ok`&&!!e.own&&!!e.configurable&&!!e.writable&&!e.accessor&&e.function?.name===``&&e.function.length===1&&e.function.nativeLike===!1;return t(e[0])&&t(e[1])&&e.slice(2).every(e=>e.function?.nativeLike===!0)}let w=(e,t)=>[e,t].every(e=>e.present&&e.own&&e.getter&&e.setter&&e.enumerable===!1&&e.configurable),T=e=>!!e&&e.fnName===``&&e.nativeLike===!0&&e.sourceLength===29&&e.fnLength===0,E=e=>!e.idKnown&&e.openShadowRoot&&e.parent===`html`&&(e.position===`fixed`||e.position===`absolute`||e.position===`sticky`)&&e.zIndex===`2147483647`&&e.pointerEvents===`none`,D={[v.muse]:`muse`,[v.grok]:`grok-bot`,[v.wrappers]:`instinct`,[v.geetest]:`instinct`,[v.prompt]:`codex-browser`,[v.keyboard]:`codex-browser`,[v.overlay]:`codex-browser`,[v.badge]:`chatgpt-chrome`,[v.claude]:`claude-chrome`};function O(e,t){let n=[],r=e=>n.push({reason:e,name:D[e],source:`shape`});e.has(v.webdriver)&&n.push({reason:v.webdriver}),e.has(v.declared)&&n.push(t?{reason:v.declared,name:t,source:`declaration`}:{reason:v.declared}),e.has(v.muse)&&r(v.muse),e.has(v.wrappers)&&e.has(v.geetest)&&(r(v.wrappers),r(v.geetest)),e.has(v.grok)&&r(v.grok);let i=[v.prompt,v.keyboard,v.overlay].filter(t=>e.has(t));return i.length>=2&&i.forEach(r),e.has(v.badge)&&r(v.badge),e.has(v.claude)&&r(v.claude),e.has(v.focus)&&n.push({reason:v.focus}),e.has(v.pointerdown)&&n.push({reason:v.pointerdown}),n}function k(e,t){let n=[v.wrappers,v.geetest];if(n.includes(t)&&!n.every(t=>e.has(t)))return`; counts only with ${n.find(e=>e!==t)}`;let r=[v.prompt,v.keyboard,v.overlay],i=r.filter(t=>e.has(t)).length;return r.includes(t)&&i<2?`; Codex shell ${i} of 3, counts at 2`:``}let A=/\{\s*\[native code\]\s*\}/,j=Function.prototype.toString;function M(e,t){let n=e;for(let e=0;n&&e<4;e++,n=Object.getPrototypeOf(n)){let r=Object.getOwnPropertyDescriptor(n,t);if(!r)continue;let i=r.value;return{status:`ok`,own:e===0,configurable:r.configurable,enumerable:r.enumerable,writable:typeof r.writable==`boolean`?r.writable:null,accessor:!(`value`in r),getter:typeof r.get==`function`,setter:typeof r.set==`function`,function:typeof i==`function`?{name:typeof i.name==`string`?i.name:null,length:typeof i.length==`number`?i.length:null,nativeLike:A.test(j.call(i))}:null}}return{status:`unsupported`}}function N(e){let t=Object.getOwnPropertyDescriptor(window,e);return t?{present:!0,own:!0,accessor:!(`value`in t),enumerable:t.enumerable,configurable:t.configurable,getter:typeof t.get==`function`,setter:typeof t.set==`function`}:{present:e in window,own:!1}}function P(e,t){let n=Object.getOwnPropertyDescriptor(e,t);if(!n)return null;let r=`value`in n?n.value:n.get;if(typeof r!=`function`)return{fnName:null,nativeLike:null,sourceLength:null,fnLength:null};let i=j.call(r);return{fnName:String(r.name),nativeLike:A.test(i),sourceLength:i.length,fnLength:r.length}}let F=[`claude-agent-glow-border`,`claude-agent-glow-border-inner`,`claude-agent-stop-container`,`claude-agent-stop-button`,`claude-phantom-cursor`,`claude-static-indicator-container`],I=[...F,`claude-agent-animation-styles`,`codex-agent-overlay-root`];function L(e){let t=getComputedStyle(e),n=e.parentNode?.nodeName;return{idKnown:!!e.id&&I.includes(e.id),openShadowRoot:!!e.shadowRoot,parent:n===`BODY`?`body`:n===`HEAD`?`head`:`html`,position:t.position,zIndex:t.zIndex,pointerEvents:t.pointerEvents}}function R(){let e=document.createElement(`canvas`).getContext(`webgl`);if(!e)return null;try{let t=e.getExtension(`WEBGL_debug_renderer_info`);return t?String(e.getParameter(t.UNMASKED_RENDERER_WEBGL)):null}finally{e.getExtension(`WEBGL_lose_context`)?.loseContext()}}let z=`mmmmmmmmmmlli0123456789`;function B(e){let t=document.createElement(`canvas`).getContext(`2d`);return t?[`monospace`,`serif`,`sans-serif`].some(n=>{t.font=`32px ${n}`;let r=t.measureText(z).width;return t.font=`32px "${e}",${n}`,t.measureText(z).width!==r}):!1}let V=[1500,5e3];function H(e){let t=!0,n=(n,r)=>{try{let i=r();i instanceof Promise?(e.status(n,`pending`),i.then(r=>t&&(r&&e.hold(r),e.status(n,`ok`)),()=>t&&e.status(n,`failed`))):e.status(n,i===!1?`unsupported`:`ok`)}catch{e.status(n,`failed`)}},r=()=>n(`navigator`,()=>{navigator.webdriver===!0&&e.hold(v.webdriver);let t=navigator.userAgent;for(let[e,n]of g)e.test(t)&&i(n);Object.hasOwn(_,navigator.platform)&&i(_[navigator.platform])}),i=t=>{e.declare(t),e.hold(v.declared)},a=!1,o,s=()=>o===void 0?o=R():o,c=()=>n(`credentials`,()=>{let r=navigator.credentials,i=window.PublicKeyCredential;if(!r||!i)return!1;let o=[M(r,`get`),M(r,`create`),M(i,`getClientCapabilities`),M(i,`isUserVerifyingPlatformAuthenticatorAvailable`),M(i,`isConditionalMediationAvailable`)];!a&&y(o)&&b(navigator.platform,navigator.userAgent)&&(a=!0,setTimeout(()=>n(`renderer`,()=>void(t&&x(s())&&e.hold(v.muse))))),C(o)&&e.hold(v.wrappers)}),l=()=>n(`geetest`,()=>{w(N(`initGeetest`),N(`initGeetest4`))&&e.hold(v.geetest)}),u=()=>n(`prompt`,()=>{T(P(window,`prompt`))&&e.hold(v.prompt)}),d=()=>n(`computer`,()=>{if(!b(navigator.platform,navigator.userAgent))return;let e=navigator.userAgentData?.brands??[],t=[screen.width===1280&&screen.height===800,B(`Ubuntu`),B(`Droid Sans`),!1,!1,e.some(e=>e.brand===`Google Chrome`)];if(t.filter(Boolean).length<3||(t[4]=B(`Cambria`),t.filter(Boolean).length<4))return;let n=window.PublicKeyCredential;return typeof n?.isConditionalMediationAvailable==`function`&&n.isConditionalMediationAvailable().then(e=>(t[3]=e===!1,S(t,t.filter(Boolean).length>=5?s():null)&&v.grok))}),f=()=>n(`keyboard`,()=>{let e=navigator.keyboard;return typeof e?.getLayoutMap==`function`&&e.getLayoutMap().then(e=>e?.size===0&&v.keyboard)}),p=()=>n(`overlay`,()=>{for(let t of Array.from(document.documentElement.children))t.nodeName!==`HEAD`&&t.nodeName!==`BODY`&&t.shadowRoot&&E(L(t))&&e.hold(v.overlay)}),m=()=>n(`markers`,()=>{let t=document.head;t&&(t.querySelector(`[data-codex-favicon-badge]`)||Array.from(t.querySelectorAll(`link[rel~="icon"]`)).some(e=>(e.getAttribute(`href`)??``).includes(`data-codex-favicon-badge`)))&&e.hold(v.badge);for(let t of F)if(document.getElementById(t)){e.hold(v.claude);break}}),h=()=>{c(),l(),u(),p(),m()};r(),f(),h();let D=V.map(e=>setTimeout(h,e)),O=window.requestIdleCallback,k=typeof O==`function`?O(()=>t&&d(),{timeout:300}):void 0;k===void 0&&D.push(setTimeout(d,300));let A=setInterval(()=>{document.visibilityState===`visible`&&(p(),m())},5e3),j,I=()=>{j===void 0&&(j=setTimeout(()=>{j=void 0,p(),m()},250))},z,H=/* @__PURE__ */ new Set,U=()=>{if(!z)return;let e=[[document.documentElement,{childList:!0}],[document.body,{childList:!0}],[document.head,{childList:!0,subtree:!0,attributes:!0,attributeFilter:[`href`,`data-codex-favicon-badge`]}]];for(let[t,n]of e)t&&!H.has(t)&&(H.add(t),z.observe(t,n))};try{z=new MutationObserver(()=>{U(),I()}),U(),e.status(`dom`,`ok`)}catch{e.status(`dom`,`failed`)}let W=-1/0,G=t=>{if(!t.isTrusted)return;document.visibilityState===`hidden`&&(t.type===`pointerdown`&&e.hold(v.pointerdown),document.hasFocus()&&e.hold(v.focus));let n=performance.now();(t.type===`pointerdown`||t.type===`keydown`)&&n-W>=300&&(W=n,m())},K=[`pointerdown`,`keydown`,`wheel`,`input`];for(let e of K)document.addEventListener(e,G,{capture:!0,passive:!0});return e.status(`input`,`ok`),()=>{t=!1,D.forEach(clearTimeout),k!==void 0&&window.cancelIdleCallback?.(k),clearInterval(A),j!==void 0&&clearTimeout(j),z?.disconnect();for(let e of K)document.removeEventListener(e,G,{capture:!0})}}function U(){let e=performance.getEntriesByType?.(`navigation`)[0];if(!e||!Array.isArray(e.serverTiming))return{status:`unsupported`,evidence:[],note:``};let t=e.serverTiming.filter(e=>e.name===`botscent`);if(t.length===0)return{status:`absent`,evidence:[],note:``};if(t.length>1)return{status:`rejected`,evidence:[],note:`${t.length} entries`};let n=f(t[0].description);if(!n||n.time===void 0)return{status:`rejected`,evidence:[],note:`malformed`};let r=n.time-performance.timeOrigin;if(r<-1e4||r>12e4)return{status:`rejected`,evidence:[],note:`stale ${Math.round(r)} ms`};let i=n.name;return{status:`received`,evidence:n.reasons.map(e=>i?{reason:e,name:i,source:`declaration`}:{reason:e}),note:`${i??`(unnamed)`} [${n.reasons}], server time ${r<0?``:`+`}${Math.round(r)} ms from navigation start`}}let W=Symbol.for(`botscent`);function G(){if(typeof document>`u`||typeof window>`u`)return null;let e=globalThis;return e[W]??(e[W]=q())}let K=(e,t)=>e.length===t.length&&e.every((e,n)=>e===t[n]);function q(){let t=/* @__PURE__ */ new Set,r,i=[],a=n,o=null,c=!1,l=null,u=/* @__PURE__ */ new Set,d={version:e,started:!1,startedAt:null,probes:{},transport:`pending`},f=()=>Math.round(performance.now());function p(){if(c)return;let e=s([...i,...O(t,r)]);if(!(e.type===a.type&&e.agent_name===a.agent_name&&K(e.reasons,a.reasons))){a=K(e.reasons,a.reasons)?Object.freeze({...e,reasons:a.reasons}):e,l?.(`verdict ${a.type} ${a.agent_name??`(unnamed)`} [${a.reasons.join(`, `)}] at ${f()} ms`);for(let e of[...u])try{e(a)}catch{}try{window.dispatchEvent(new CustomEvent(`botscent`,{detail:a}))}catch{}}}function m(n={}){if(n.debug&&!l&&(l=e=>console.debug(`[botscent] ${e}`)),o||c)return g;c=!0,d.started=!0,d.startedAt=f(),l?.(`started ${e} at ${d.startedAt} ms`);try{let e=U();d.transport=e.status,i=e.evidence,l?.(`transport ${e.status}${e.note?`: ${e.note}`:``}`)}catch{d.transport=`unsupported`}let s=h(()=>a),u=()=>{};try{u=H({hold(e){t.has(e)||(t.add(e),l?.(`held ${e} at ${f()} ms${k(t,e)}`),p())},declare(e){r??(r=e)},status(e,t){d.probes[e]!==t&&(t!==`ok`||d.probes[e]===`pending`)&&l?.(`probe ${e}: ${t}`),d.probes[e]=t}})}catch{d.probes.observe=`failed`}return o=()=>{u(),s()},c=!1,p(),g}function g(){o?.(),o=null,d.started=!1,l?.(`stopped; evidence kept`)}return{version:e,verdict:()=>a,subscribe(e){return u.add(e),()=>u.delete(e)},diagnostics:()=>({...d,probes:{...d.probes}}),start:m}}function J(e){return G()?.start(e)??(()=>{})}function Y(){return G()?.verdict()??n}function X(e){return G()?.subscribe(e)??(()=>{})}function Z(e){return G()?m(Y(),e):{}}function Q(){return G()?.diagnostics()??{version:``,started:!1,startedAt:null,probes:{},transport:`unsupported`}}let $=document.currentScript;window.botscent={verdict:Y,subscribe:X,reportHeaders:Z,diagnostics:Q,start:J,VERSION:e},J({debug:!!$&&$.hasAttribute(`data-debug`)})})();
  }
  // ---- static/src/util.js
  ;(function () {
// Agent Cake page script, part: small shared helpers (plan step S1.3).
//
// build_js.py concatenates the parts in agentcake/static/src/ into agentcake/static/cake.js, each inside its own
// function, and gives them in the enclosing scope:
//   C        the parts' private namespace (never a global; parts talk to each other only through it)
//   CFG      the "script" object of agentcake/data/cakejs.json (every number and name the script uses)
//   RUNTIME  values cake fills in when it serves cake.js (site key, settings the site owner turned on)
//   TAG      this <script> element, read while the script first runs
//   BUILD    a short hash of the sources, sent with every page so data can be traced to the script that made it
//   STARTED  performance.now() when cake.js began to run
//
// The helpers here read clocks and sessionStorage and keep the list of everything stop() must undo.

var HEX_RADIX = 16 // protocol: hexadecimal digits of an id
var HEX_DIGITS_PER_BYTE = 2 // protocol: one byte is two hexadecimal digits

// Event timestamps are relative to the page's time origin; cake wants epoch milliseconds that compare across pages.
var timeOrigin = performance.timeOrigin || Date.now() - performance.now()

C.off = false

/** Epoch milliseconds for a performance timestamp (event.timeStamp, performance.now()), to CFG.time_precision. */
C.epoch = function (ts) {
  return Math.round((timeOrigin + ts) * CFG.time_precision) / CFG.time_precision
}

C.now = function () {
  return C.epoch(performance.now())
}

/** A coordinate or size rounded the same way as times (the lab recorded both at this precision). */
C.round = function (value) {
  return Math.round(value * CFG.time_precision) / CFG.time_precision
}

/** fn's value, or why it failed: a probe that throws records the reason instead of breaking the page. */
C.safe = function (fn) {
  try {
    return fn()
  } catch (e) {
    return 'error: ' + (e && e.message)
  }
}

/** A random hexadecimal id for a visit or a page view. Nothing about the device or the time goes into it. */
C.randomId = function () {
  if (window.crypto && crypto.randomUUID) return crypto.randomUUID().replace(/-/g, '')
  var bytes = crypto.getRandomValues(new Uint8Array(CFG.id_bytes))
  return Array.prototype.map
    .call(bytes, function (b) {
      return b.toString(HEX_RADIX).padStart(HEX_DIGITS_PER_BYTE, '0')
    })
    .join('')
}

// sessionStorage can be missing or throw (private windows, storage turned off). Then cake.js keeps working without
// it: a page simply starts a new visit id and nothing is parked for the next page.
C.store = {
  get: function (key) {
    try {
      return sessionStorage.getItem(key)
    } catch (e) {
      return null
    }
  },
  set: function (key, value) {
    try {
      sessionStorage.setItem(key, value)
      return true
    } catch (e) {
      return false
    }
  },
  remove: function (key) {
    try {
      sessionStorage.removeItem(key)
    } catch (e) {
      return false
    }
    return true
  }
}

/** Records one of cake.js's own failures (where, and the message only) so a broken probe shows up in cake. */
C.fault = function (where, error) {
  if (!C.push) return
  var message = String((error && error.message) || error).slice(0, CFG.limits.error_chars)
  C.push('x', { t: C.now(), ty: 'err', where: where, msg: message })
}

// Everything that has to be undone when the visitor says no (window.cake.stop()): listeners, timers, observers,
// the recorder. Each part registers its own undo here.
var undo = []

C.onStop = function (fn) {
  undo.push(fn)
}

C.listen = function (target, type, fn, options) {
  target.addEventListener(type, fn, options)
  C.onStop(function () {
    target.removeEventListener(type, fn, options)
  })
}

C.every = function (fn, ms) {
  var id = setInterval(fn, ms)
  C.onStop(function () {
    clearInterval(id)
  })
}

C.later = function (fn, ms) {
  var id = setTimeout(function () {
    if (!C.off) fn()
  }, ms)
  C.onStop(function () {
    clearTimeout(id)
  })
}

C.stopAll = function () {
  C.off = true
  undo.splice(0).forEach(function (fn) {
    try {
      fn()
    } catch (e) {
      // Stopping must finish even if one recorder fails to stop; nothing is sent any more, so there is no one to tell.
      return
    }
  })
}
  }).call(SCOPE)
  // ---- static/src/schedule.js
  ;(function () {
// Agent Cake page script, part: running the detectors after the page has loaded, a little at a time (plan step S1.3).
//
// A site that adds cake.js must not get slower. So only what has to see the page from its first moment runs when
// cake.js starts (the input listeners, the replay's first snapshot); every detector waits for the page's load event
// and then runs as one task per idle period of the browser (requestIdleCallback, or a timer where there is none),
// each task well under a long task (50 ms). The tasks' times go to cake in a "tasks" record: how long each took
// ("start" is cake.js's own first task from its first line, after the browser compiled it; "rrweb" the first
// snapshot) and how long after load the last one finished.

var tasks = []
var took = {}
var loadedAt = null
var scheduled = false

function nextTask() {
  scheduled = false
  if (C.off || !tasks.length) return
  var task = tasks.shift()
  var started = performance.now()
  try {
    task.run()
  } catch (e) {
    C.fault(task.name, e)
  }
  took[task.name] = C.round(performance.now() - started)
  schedule()
}

function schedule() {
  if (scheduled || loadedAt === null || !tasks.length) return
  scheduled = true
  if (window.requestIdleCallback) requestIdleCallback(nextTask, { timeout: CFG.idle_timeout_ms })
  else C.later(nextTask, CFG.idle_gap_ms)
}

function loaded() {
  loadedAt = performance.now()
  schedule()
}

C.schedule = {
  /** Starts the queue at the page's load event (at once if the page has loaded already). */
  start: function () {
    if (document.readyState === 'complete') loaded()
    else C.listen(window, 'load', loaded, { once: true })
  },
  /** Queues fn to run in an idle period after load, after the tasks queued before it. */
  afterLoad: function (name, fn) {
    tasks.push({ name: name, run: fn })
    schedule()
  },
  /** Notes the time (ms) of a task that ran outside the queue. */
  took: function (name, ms) {
    took[name] = C.round(ms)
  },
  /** The "tasks" record: each task's time (ms) and how long after load this record was made. */
  report: function () {
    var longest = 0
    Object.keys(took).forEach(function (name) {
      longest = Math.max(longest, took[name])
    })
    var afterLoad = loadedAt === null ? null : C.round(performance.now() - loadedAt)
    return { t: C.now(), ty: 'tasks', after_load_ms: afterLoad, took_ms: took, longest_ms: longest }
  }
}
  }).call(SCOPE)
  // ---- static/src/transport.js
  ;(function () {
// Agent Cake page script, part: batches, sequence numbers and sending (plan step S1.3; format: docs/collect-format.md).
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
  }).call(SCOPE)
  // ---- static/src/edge_token.js
  ;(function () {
// Agent Cake page script, part: the server-half token (plan steps S1.3, S4.2).
//
// As in cake 0.3.3: the site's server (its cake middleware) puts a signed token in
// the Server-Timing header of the response that opened this page (`Server-Timing: cake;desc="c1.<body>.<sig>"`).
// cake.js reads it from the page's navigation entry and sends it with every batch of this page until cake has
// accepted one batch that carried it (a 2xx answer). The token is signed by the server and never opened here.
// A single-page app's route change (history.pushState) stays in this page view, whose token went already. A page the
// browser shows from its cache carries the token stored with it (after a 304, the 304's own new one; going back to a
// stored page, that page's earlier one): it goes all the same, and collect answers reuse and keeps it once (S4.2,
// checked in Chromium, WebKit and Firefox). A page the back-forward cache restores is the same page view: nothing new.

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
  }).call(SCOPE)
  // ---- static/src/raw.js
  ;(function () {
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
  }).call(SCOPE)
  // ---- static/src/replay.js
  ;(function () {
// Agent Cake page script, part: the session replay recorder (plan step S1.3), stream "e".
//
// rrweb's record (bundled into cake.js unchanged, see THIRD_PARTY.md) with the privacy rules of
// agentcake/data/privacy.json (plan step S1.4): every input masked (the replay keeps its length), text typed into
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
  }).call(SCOPE)
  // ---- static/src/automation.js
  ;(function () {
// Agent Cake page script, part: probes for a browser driven over the DevTools protocol (plan step S1.3), stream "x".
//
// The ideas of these checks come from rebrowser-bot-detector (github.com/rebrowser/rebrowser-bot-detector, commit
// 55fa59b); the code is our own. That repository declares MIT in its package.json but has no licence file, so none of
// its code is used (our rule: no code without a licence). The ideas:
//   1. A DevTools-protocol client with the Runtime domain on (Puppeteer, Playwright) has console messages serialised
//      at once, so a logged error is formatted right away: Error.prepareStackTrace runs for it and its name is read
//      more often (research lab, 11/11: per round 1 formatting and 3 name reads for Playwright, 0 and 1 for Claude in
//      Chrome).
//   2. Chrome ignores a burst of same-document history updates beyond its IPC flooding limit, unless it was started
//      with --disable-ipc-flooding-protection, as Puppeteer and Playwright start it.
//   3. A document the automation tool served itself has a navigation entry no network or service worker made.
//   4. Code a DevTools client evaluates in the page leaves its own frames on the call stack (Puppeteer's pptr: URLs,
//      Playwright's UtilityScript), visible from inside the page's DOM lookups. Off unless the site owner turns it
//      on, since it wraps the site's own DOM methods.
// Field names follow the research lab's (runtimeEnableLeak, ipcFlooding.all300, …): cake's environment rules (S3.3)
// read them.

// ---------------------------------------------------------------- 1. the logged-error probe
var leak = { rounds: 0, prepareStackTraceCount: 0, nameGetterCount: 0, stackLookupCount: 0, firstHitRound: null }

// V8's own format, for any other error formatted while the counting hook is in place.
function plainStack(error, callSites) {
  return [String(error)]
    .concat(
      callSites.map(function (site) {
        return '    at ' + site
      })
    )
    .join('\n')
}

function countFormatting() {
  var own = Object.getOwnPropertyDescriptor(Error, 'prepareStackTrace')
  if (own && !own.configurable) return // the page fixed it: this round cannot see formatting
  var watched = new Error(CFG.env.cdp_message)
  var outer = Error.prepareStackTrace
  Object.defineProperty(Error, 'prepareStackTrace', {
    configurable: true,
    writable: true,
    value: function (error, callSites) {
      if (error === watched) leak.prepareStackTraceCount++
      return outer ? outer(error, callSites) : plainStack(error, callSites)
    }
  })
  try {
    console.debug(watched)
  } finally {
    if (own) Object.defineProperty(Error, 'prepareStackTrace', own)
    else delete Error.prepareStackTrace
  }
}

function countReads(property, field) {
  var watched = new Error(CFG.env.cdp_message)
  var value = property === 'name' ? watched.name : ''
  Object.defineProperty(watched, property, {
    configurable: true,
    get: function () {
      leak[field]++
      return value
    }
  })
  console.debug(watched)
}

function probeRound() {
  leak.rounds++
  countFormatting()
  countReads('name', 'nameGetterCount')
  countReads('stack', 'stackLookupCount')
  var nameReadsPerRound = leak.nameGetterCount / leak.rounds
  var seen = leak.prepareStackTraceCount > 0 || leak.stackLookupCount > 0
  seen = seen || nameReadsPerRound > CFG.env.cdp_name_lookups_per_round
  if (seen && leak.firstHitRound === null) leak.firstHitRound = leak.rounds
  if (!seen && leak.rounds < CFG.env.cdp_rounds) {
    C.later(probeRound, CFG.env.cdp_round_ms)
    return
  }
  var copy = {}
  Object.keys(leak).forEach(function (key) {
    copy[key] = leak[key]
  })
  C.push('x', { t: C.now(), ty: 'cdp', runtimeEnableLeak: copy })
}

// ---------------------------------------------------------------- 2. history writes in a hidden frame
// A burst of history writes makes Chrome's browser process queue them, and any synchronous call into it meanwhile
// (navigator.plugins, Notification.permission, the site's own document.cookie) waits, ~0.1 s for 300 at once. So
// the writes go in short bursts (CFG.env.frame_burst_writes every frame_burst_gap_ms), still well inside Chrome's
// counting window, and cake_main.js runs this once per visit, when idle. The frame is marked, so raw.js does not
// report it and rrweb records only an empty placeholder for it; calls done(record) when finished.
function frameChecks(done) {
  var frame = document.createElement('iframe')
  frame.setAttribute(CFG.env.probe_attr, '')
  frame.style.display = 'none'
  var record = { ty: 'frames' }
  var finish = function () {
    frame.remove()
    record.t = C.now()
    done(record)
  }
  try {
    ;(document.body || document.documentElement).appendChild(frame)
    record.iframeSharesRealm = frame.contentWindow.Navigator === window.Navigator
  } catch (e) {
    record.error = String(e)
    finish()
    return
  }
  var frameHistory = frame.contentWindow.history
  var target = CFG.env.frame_history_writes
  var written = 0
  var stoppedBy = null
  record.longest_burst_ms = 0
  var burst = function () {
    var started = performance.now()
    var until = Math.min(written + CFG.env.frame_burst_writes, target)
    while (written < until && stoppedBy === null) {
      try {
        frameHistory.replaceState({ n: written + 1 }, '')
        written++
      } catch (e) {
        stoppedBy = String(e.name || e)
      }
    }
    record.longest_burst_ms = Math.max(record.longest_burst_ms, C.round(performance.now() - started))
    if (written < target && stoppedBy === null) {
      C.later(burst, CFG.env.frame_burst_gap_ms)
      return
    }
    // A throttled write is dropped without an error: the state shows how many went through.
    var applied = frameHistory.state ? frameHistory.state.n : null
    record.ipcFlooding = { applied: applied, error: stoppedBy, all300: applied === target }
    finish()
  }
  burst()
}

// ---------------------------------------------------------------- 3. how the document arrived
function documentInterception() {
  var nav = performance.getEntriesByType('navigation')[0]
  if (!nav) return null
  var noHop = nav.nextHopProtocol === ''
  var noWorker = nav.workerStart === 0 && (nav.deliveryType || '') === ''
  return {
    nextHopProtocol: nav.nextHopProtocol,
    transferSize: nav.transferSize,
    deliveryType: nav.deliveryType,
    workerStart: nav.workerStart,
    intercepted: noHop && noWorker && nav.transferSize > 0
  }
}

// ---------------------------------------------------------------- 4. who calls the page's DOM lookups
var hookHits = []
var lookups = { checked: 0, total: 0 }

function noteLookup(method, argument) {
  lookups.total++
  if (lookups.checked >= CFG.env.hook.checks_max || hookHits.length >= CFG.env.hook.hits_max) return
  lookups.checked++
  var stack = String(new Error(CFG.env.cdp_message).stack || '')
  var hit = { fn: method, arg: String(argument).slice(0, CFG.env.hook.arg_chars), t: C.now() }
  var found = false
  Object.keys(CFG.env.hook.markers).forEach(function (flag) {
    hit[flag] = stack.indexOf(CFG.env.hook.markers[flag]) >= 0
    found = found || hit[flag]
  })
  if (!found) return
  hit.stack = stack.split('\n').slice(1, CFG.env.hook.stack_frames + 1).join(' | ').slice(0, CFG.env.stack_chars)
  hookHits.push(hit)
}

function watchDomLookups() {
  CFG.env.hook.methods.forEach(function (method) {
    var original = document[method]
    if (typeof original !== 'function') return
    var hadOwn = Object.prototype.hasOwnProperty.call(document, method)
    document[method] = function () {
      noteLookup(method, arguments[0])
      return original.apply(this, arguments)
    }
    C.onStop(function () {
      if (hadOwn) document[method] = original
      else delete document[method]
    })
  })
}

C.automation = {
  start: function (watchDom) {
    if (watchDom) watchDomLookups()
  },
  probe: probeRound,
  frameChecks: frameChecks,
  documentInterception: documentInterception,
  /** What the DOM lookups showed so far (only when the site owner turned the watch on). */
  lookups: function () {
    return hookHits.length || lookups.total ? { hookHits: hookHits.slice(), lookups: lookups } : {}
  }
}
  }).call(SCOPE)
  // ---- static/src/env.js
  ;(function () {
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
  }).call(SCOPE)
  // ---- static/src/probes.js
  ;(function () {
// Agent Cake page script, part: the asynchronous environment probes of a page view (plan step S1.3), stream "x".
//
// The research lab's asynchronous checks (env.js, 11/11), in our own code: the worker-consistency and
// native-tampering ideas come from rebrowser-bot-detector (no code of it is used, see automation.js). Added: the
// media-device counts (signal sig-040, and the evaluation's superline comparison) and a font check (sig-030, with
// botscent's width-measuring idea). Every probe has a time limit; all results go to cake in one
// record. Nothing here asks the visitor for a permission: enumerateDevices without a grant gives kinds, no labels,
// and only the counts per kind are kept.

function withTimeout(promise) {
  return new Promise(function (resolve) {
    var timer = setTimeout(function () {
      resolve({ error: 'timeout' })
    }, CFG.probes.timeout_ms)
    promise.then(
      function (value) {
        clearTimeout(timer)
        resolve(value)
      },
      function (e) {
        clearTimeout(timer)
        resolve({ error: String((e && e.message) || e) })
      }
    )
  })
}

// Read in the page and in a worker: automation that patches navigator in the page often forgets workers.
function navigatorFacts() {
  return {
    userAgent: navigator.userAgent,
    platform: navigator.platform,
    languages: navigator.languages,
    hardwareConcurrency: navigator.hardwareConcurrency,
    brands: navigator.userAgentData && navigator.userAgentData.brands
  }
}

function comparable(key, value) {
  if (key !== 'brands' || !value) return JSON.stringify(value)
  return JSON.stringify(
    value
      .map(function (b) {
        return b.brand + '/' + b.version
      })
      .sort()
  )
}

function workerConsistency() {
  return new Promise(function (resolve, reject) {
    var source = 'var navigatorFacts = ' + navigatorFacts.toString() + '; postMessage(navigatorFacts())'
    var url = URL.createObjectURL(new Blob([source], { type: 'text/javascript' }))
    var worker = new Worker(url)
    var finish = function () {
      worker.terminate()
      URL.revokeObjectURL(url)
    }
    worker.onmessage = function (e) {
      finish()
      var page = navigatorFacts()
      var differs = Object.keys(page).filter(function (key) {
        var mine = page[key]
        var theirs = e.data[key]
        return mine != null && theirs != null && comparable(key, mine) !== comparable(key, theirs)
      })
      resolve({ differs: differs, worker: e.data })
    }
    worker.onerror = function (e) {
      finish()
      reject(new Error(e.message || 'worker error'))
    }
  })
}

// Native functions and getters that stealth tools replace: not native source any more, or a prototype of their own.
function nativeTampering() {
  var targets = {}
  var getters = CFG.probes.native_getters
  Object.keys(getters).forEach(function (owner) {
    var proto = window[owner] && window[owner].prototype
    getters[owner].forEach(function (name) {
      var d = proto && Object.getOwnPropertyDescriptor(proto, name)
      targets[owner + '.' + name] = d && d.get
    })
  })
  var methods = CFG.probes.native_methods
  Object.keys(methods).forEach(function (owner) {
    var proto = window[owner] && window[owner].prototype
    methods[owner].forEach(function (name) {
      targets[owner + '.' + name] = proto && proto[name]
    })
  })
  var tampered = {}
  Object.keys(targets).forEach(function (key) {
    var fn = targets[key]
    if (typeof fn !== 'function') return
    var reasons = []
    var source = Function.prototype.toString.call(fn)
    if (!/^function [^(]*\(\) \{\s*\[native code\]\s*\}$/.test(source)) {
      reasons.push('toString: ' + source.slice(0, CFG.probes.source_chars))
    }
    if (Object.prototype.hasOwnProperty.call(fn, 'prototype')) reasons.push('has own prototype')
    if (reasons.length) tampered[key] = reasons
  })
  return Promise.resolve({ tampered: tampered })
}

function permissionsMismatch() {
  var notification = window.Notification ? Notification.permission : null
  var answer = function (query) {
    return {
      notificationPermission: notification,
      permissionsQuery: query,
      mismatch: notification === 'denied' && query === 'prompt'
    }
  }
  if (!navigator.permissions) return Promise.resolve(answer(null))
  return navigator.permissions.query({ name: 'notifications' }).then(
    function (status) {
      return answer(status.state)
    },
    function (e) {
      return answer('error: ' + e.message)
    }
  )
}

function uaFullVersion() {
  if (!navigator.userAgentData || !navigator.userAgentData.getHighEntropyValues) return Promise.resolve(null)
  return navigator.userAgentData.getHighEntropyValues(CFG.probes.high_entropy_hints).then(function (values) {
    var brands = (values.fullVersionList || []).map(function (b) {
      return b.brand
    })
    values.chromiumWithoutGoogleChrome = brands.indexOf('Chromium') >= 0 && brands.indexOf('Google Chrome') < 0
    return values
  })
}

function mediaDeviceCounts() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return Promise.resolve(null)
  return navigator.mediaDevices.enumerateDevices().then(function (devices) {
    var counts = {}
    devices.forEach(function (device) {
      counts[device.kind] = (counts[device.kind] || 0) + 1
    })
    return counts
  })
}

// Whether a font is installed: a sample's width in that font differs from at least one generic fallback.
function hasFont(context, font) {
  return CFG.probes.font_bases.some(function (base) {
    context.font = CFG.probes.font_px + 'px ' + base
    var fallback = context.measureText(CFG.probes.font_sample).width
    context.font = CFG.probes.font_px + 'px "' + font + '",' + base
    return context.measureText(CFG.probes.font_sample).width !== fallback
  })
}

function fonts() {
  var context = document.createElement('canvas').getContext('2d')
  if (!context) return Promise.resolve(null)
  var found = {}
  CFG.probes.fonts.forEach(function (font) {
    found[font] = hasFont(context, font)
  })
  return Promise.resolve(found)
}

var PROBES = {
  permissions: permissionsMismatch,
  workerConsistency: workerConsistency,
  nativeTampering: nativeTampering,
  uaFullVersion: uaFullVersion,
  mediaDevices: mediaDeviceCounts,
  fonts: fonts
}

var results = null
var reported = false

// One record per page view: when every probe has answered, or at exit with the answers so far (the rest are listed
// as pending), so a page left quickly still reports what had finished.
function report() {
  if (reported || !results) return
  reported = true
  var record = { t: C.now(), ty: 'probes' }
  var pending = Object.keys(PROBES).filter(function (name) {
    if (name in results) record[name] = results[name]
    return !(name in results)
  })
  if (pending.length) record.pending = pending
  C.push('x', record)
}

C.probes = {
  /** Runs every probe; returns a promise that settles once the probes record has been pushed. */
  run: function () {
    results = {}
    return Promise.all(
      Object.keys(PROBES).map(function (name) {
        var answer
        try {
          answer = withTimeout(PROBES[name]())
        } catch (e) {
          answer = Promise.resolve({ error: String(e && e.message) })
        }
        return answer.then(function (value) {
          results[name] = value
        })
      })
    ).then(report)
  },
  atExit: report
}
  }).call(SCOPE)
  // ---- static/src/markers.js
  ;(function () {
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
  }).call(SCOPE)
  // ---- static/src/detectors.js
  ;(function () {
// Agent Cake page script, part: what the two bundled detectors find in the page (plan step S1.3), stream "x".
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
  }).call(SCOPE)
  // ---- static/src/cake_main.js
  ;(function () {
// Agent Cake page script, part: start, stop and window.cake (plan steps S1.3, S1.4).
//
// As in cake 0.3.3, a site adds one line:
// <script src="https://<cake>/cake.js" data-site="<key>" defer></script>.
// cake.js sends to the address it was loaded from (…/cake.js → …/collect) and keeps the visit id in sessionStorage
// (a visit ends with the tab).
// Consent, as PostHog 1.0 left it to the site (plan step S1.4, GOAL G12): a site that asks first either adds the tag
// only after the visitor agreed, or adds it with data-consent="required" and calls window.cake.start() once they
// agree; until then cake.js does nothing at all (no listener, no storage, no request). window.cake.stop() (the
// visitor said no) ends recording and sending on this page for good, drops what was not sent yet and forgets the
// visit id. A site whose consent code runs before cake.js has loaded can queue the calls:
// window.cake = window.cake || []; window.cake.push('start').
// A site must not get slower for having cake.js: when it starts, it only reads its settings and hooks its
// listeners; the replay's first snapshot is the next task; every detector waits for the page's load event and runs
// as one task per idle period (schedule.js).

var settings = {}
Object.keys(CFG.defaults).forEach(function (key) {
  settings[key] = key in RUNTIME ? RUNTIME[key] : CFG.defaults[key]
})

// What is never recorded (plan step S5.5): privacy.json's private elements, and the parts of the page the site owner
// lists in AgentCake's settings (hide_selectors). A list this browser cannot read is left out, and said so in the
// upload's faults, rather than stopping the recorders; AgentCake's settings page saves only lists a browser reads.
C.privateSelector = (function (owned) {
  if (!owned) return CFG.privacy.private_selector
  try {
    document.createDocumentFragment().querySelector(owned)
    return CFG.privacy.private_selector + ',' + owned
  } catch (e) {
    C.fault('hide_selectors', e)
    return CFG.privacy.private_selector
  }
})(settings.hide_selectors)

var consentRequired = !!TAG && TAG.getAttribute(CFG.attr.consent) === CFG.consent.required

function collectUrl() {
  if (!TAG || !TAG.src) return null
  try {
    return new URL(CFG.collect_path, TAG.src).href
  } catch (e) {
    return null
  }
}

function siteKey() {
  return (TAG && TAG.getAttribute(CFG.attr.site)) || RUNTIME.site_key || null
}

function visitId() {
  var id = C.store.get(CFG.storage.session)
  if (!id) {
    id = C.randomId()
    C.store.set(CFG.storage.session, id)
  }
  return id
}

function nextPageNumber() {
  var n = (Number(C.store.get(CFG.storage.page_number)) || 0) + 1
  C.store.set(CFG.storage.page_number, String(n))
  return n
}

function pageRecord() {
  var nav = C.safe(function () {
    return performance.getEntriesByType('navigation')[0]
  })
  return {
    t: C.now(),
    ty: 'page',
    n: nextPageNumber(),
    build: BUILD,
    ref: document.referrer,
    nav: nav && nav.type ? nav.type : null,
    t0: C.round(performance.timeOrigin),
    ran: C.round(performance.now()),
    prerendering: document.prerendering === true,
    vis: document.visibilityState,
    hf: document.hasFocus(),
    hist: history.length,
    hook_dom: settings.hook_dom,
    consent: consentRequired ? 'start' : 'load'
  }
}

// Each step is guarded: one recorder failing must not stop the others or break the page.
function step(name, fn) {
  try {
    return fn()
  } catch (e) {
    C.fault(name, e)
    return null
  }
}

// The frame checks (automation.js) once per visit, on the first page view that finishes them; then the tasks record.
function framesThenReport() {
  var report = function () {
    C.push('x', C.schedule.report())
    C.flush('probes')
  }
  if (C.store.get(CFG.storage.frames_done)) {
    report()
    return
  }
  C.automation.frameChecks(function (record) {
    C.push('x', record)
    C.store.set(CFG.storage.frames_done, '1')
    report()
  })
}

// The detectors, one idle task each after load. The frame checks wait for the probes and BotD, whose synchronous
// reads would otherwise wait behind the frame's history writes (automation.js).
function queueDetectors() {
  var answers = []
  C.schedule.afterLoad('parked', C.transport.resendParked)
  C.schedule.afterLoad('markers', C.markers.start)
  C.schedule.afterLoad('env', C.env.environment)
  C.schedule.afterLoad('webgl', C.env.webgl)
  C.schedule.afterLoad('tz', C.env.timeZone)
  C.schedule.afterLoad('auto', function () {
    C.env.automationTraces()
    C.flush('env')
  })
  C.schedule.afterLoad('cdp', C.automation.probe)
  C.schedule.afterLoad('botscent', C.detectors.startBotscent)
  C.schedule.afterLoad('probes', function () {
    answers.push(C.probes.run())
  })
  C.schedule.afterLoad('botd', function () {
    answers.push(C.detectors.runBotd())
    Promise.all(answers).then(function () {
      C.schedule.afterLoad('frames', framesThenReport)
    })
  })
}

var exited = false

// At exit only cheap work: the page is going and the next one is waiting for it.
function onLeave(why) {
  if (!exited) {
    exited = true
    step('globals', C.env.atExit)
    step('probes', C.probes.atExit)
    step('botscent', C.detectors.atExit)
    step('markers', C.markers.atExit)
    C.push('x', { t: C.now(), ty: 'leave', why: why })
  }
  C.flush('exit')
}

function stop() {
  if (C.off) return
  C.transport.discard()
  C.stopAll()
  C.store.remove(CFG.storage.session)
  C.store.remove(CFG.storage.page_number)
  C.store.remove(CFG.storage.frames_done)
}

function begin() {
  var url = collectUrl()
  var key = siteKey()
  if (!url || !key) return
  var header = {
    v: CFG.format_version,
    k: key,
    s: visitId(),
    pv: C.randomId(),
    ua: navigator.userAgent,
    wd: navigator.webdriver === true
  }
  step('token', C.token.read)
  step('hooks', function () {
    C.automation.start(settings.hook_dom)
  })
  C.push('x', pageRecord())
  step('raw', C.raw.listen)
  C.transport.start(url, header)
  C.listen(window, 'pagehide', function () {
    onLeave('pagehide')
  })
  C.listen(document, 'visibilitychange', function () {
    if (document.visibilityState === 'hidden') onLeave('hidden')
    else exited = false
  })
  C.listen(window, 'pageshow', function (e) {
    if (!e.persisted) return
    exited = false // back from the back-forward cache: recording goes on, the next exit is a new one
    C.push('x', { t: C.now(), ty: 'pageshow', persisted: true })
  })
  // The replay's first snapshot in a task of its own, right after this one. rrweb first, then the DOM watch: rrweb
  // adds and removes a frame of its own as it starts, which raw.js must not report.
  C.later(function () {
    var started = performance.now()
    step('rrweb', C.replay.start)
    step('dom_add', C.raw.watchDom)
    C.schedule.took('rrweb', performance.now() - started)
    C.flushSoon('start') // the page record goes now even if rrweb failed (rrweb sends its snapshot itself)
  }, 0)
  queueDetectors()
  C.schedule.start()
  C.schedule.took('start', performance.now() - STARTED)
}

var started = false

function start() {
  if (started || C.off) return
  started = true
  begin()
}

var queued = Array.isArray(window.cake) ? window.cake.slice() : []
window.cake = { stop: stop, start: start, version: BUILD }
queued.forEach(function (command) {
  if (command === CFG.consent.commands.stop) stop()
  if (command === CFG.consent.commands.start) start()
})
if (!consentRequired) start()
  }).call(SCOPE)
})()
