# Privacy notice template: the part about AgentCake

**This is not legal advice.** It is a starting point for the paragraph of your website's privacy notice that covers
AgentCake, written from what AgentCake records ([`PRIVACY.md`](../PRIVACY.md)). What you must tell your visitors,
whether you need their consent before recording, and how long you may keep what you record depend on the laws where
you and your visitors are. Have it checked by someone who can advise you on them.

How to use it: copy the text between the lines into your privacy notice, replace each `[bracketed]` part, and delete
the sentences that do not apply to your site (for example the server-half sentence when your server does not run
AgentCake's middleware). Keep it in step with how you set AgentCake up: if you ask visitors before recording, say
so; if you chose a retention period, give it.

---

### Telling AI agents from human visitors (AgentCake)

[Site name] uses AgentCake, a program [we run / [operator] runs for us] on [our own server / a server we control],
to find out whether a visit to this website was made by a human or by an AI agent (software that uses websites on
someone's behalf), and which agent. We use this to [understand how AI agents use our site / protect our forms and
checkout from automated use / describe the purpose]. AgentCake does not try to identify who you are.

**What is recorded during a visit** [after you agree to it in our cookie and consent settings]:

- a replay of the pages you see and how they change while you use them. Everything typed into forms is hidden: only
  the length of what was typed is kept. Password fields, payment card fields and other fields we mark as private are
  not recorded at all;
- how the mouse, finger or keyboard was used: positions and times of movements, clicks and scrolling, and for each
  key press only its time and its kind (letter, digit, space, …), never which key;
- what your browser shows about itself: its name and version, screen and window size, time zone, language, graphics
  renderer, and signs of automation software;
- the page addresses you visited during the visit and when;
- [only if your server runs AgentCake's middleware:] what our web server saw about each page request: the address
  path, the browser's name and language headers, the names of the request headers, and a code derived from your
  network (not your IP address) that cannot be turned back into your address;
- [only if your web server sends its access log to AgentCake:] what our web server logged about each page request of
  your visit: the address path, the response status, and the browser's name and language headers.

**What is not recorded**: what you type, which keys you press, passwords, card numbers, the content of private fields,
cookies, and your IP address. Our server uses your IP address for a moment to check whether it belongs to a published
network of an AI service, then discards it, keeping only codes made from it and from its network with a random key
that is replaced every [30] days: they show whether two requests came from the same network, and cannot be turned back
into your address. AgentCake sets no cookies; it keeps a random visit identifier in your browser's session storage,
which is deleted when you close the tab.

**Where it is kept, and who receives it**: on [our server in [country or region] / describe where]. AgentCake does
not send what it records about your visit to anyone else, including the makers of AgentCake: no website traffic,
session replay or usage telemetry leaves our server. [List anyone else who can access the server, such as your
hosting provider.]

**How long it is kept**: [until we delete it / for [30 / 90] days], and replays of visits made only by humans may be
removed earlier when the storage set aside for them is full.

**Your choices**: [You can refuse or withdraw your consent at any time in our cookie and consent settings; from then
on nothing more is recorded during your visit, and the identifier in your browser is deleted.] You can ask us to
delete the record of a visit: write to [contact address], saying [when you visited and which pages / the visit
identifier our consent settings show you]. We delete it from our database, the replay files, our backups made by
AgentCake and AgentCake's log files[, and from our other backups within [period]].

[Legal basis, if your law asks for one: [consent / legitimate interest in …]. Your rights under [law]: [access,
erasure, objection, complaint to [supervisory authority]].]

---

## Notes for the site owner

- **Consent**: AgentCake records nothing until the page script runs. To record only after consent, add the script
  after the visitor agreed, or add it with `data-consent="required"` and call `window.cake.start()` then; call
  `window.cake.stop()` when they refuse or withdraw (`PRIVACY.md`, "Consent").
- **Deletion requests**: `agentcake delete --session <id>` or `--visitor <visit id>` deletes a visit everywhere in
  AgentCake's data folder, while it runs. A visitor cannot read their visit identifier from your site unless your
  consent settings show it (it is `sessionStorage.cake_sid`); otherwise find the visit on the dashboard by its time and
  pages. Copies outside the data folder (your own backups and snapshots) are yours to handle.
- **Server half**: the network code is an HMAC keyed with a secret your server and AgentCake share. Whoever holds the
  secret could work out the /24 (or /48) network of a visit, not the full address (`PRIVACY.md`, "The server half").
- **Not legal advice**: this template describes what the software does; it does not say what your law requires.
