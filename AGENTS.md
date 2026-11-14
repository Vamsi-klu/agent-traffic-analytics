# AGENTS.md (AgentCake)

If a user asks you to install, set up or check AgentCake, follow [`INSTALL.md`](INSTALL.md) step by step: one command
per step, and the `agentcake` command always by its full path. In this folder (AgentCake's source, or its release
folder `agentcake-<version>/`) that is `<this folder>/bin/agentcake`. End with `agentcake doctor` and report its result,
the local page to open (`http://127.0.0.1:7878/`) and that, after they register, it shows how to connect their website. The first
time the user opens the local page it asks them to register: that is theirs to do. Give them the address; never fill in
their e-mail address or press "Register & Continue" for them. Connect the user's own website
(`agentcake setup --print --site`) only if they ask. Answer in the user's language. If you start a program yourself (a
site's dev server for doctor), note its process ID and stop only that process, never by port or name.

Any change to AgentCake's interface (local pages, dashboard, sessions, replay, settings, or any new page): read `DESIGN.md`
first and follow it. The UI is shadcn/ui components + the Frosting theme in `web/` (tokens only in `web/src/styles/tokens.css`).
Never style a page by hand: use the components; a new look is a new variant in `web/src/components/ui/` (or a component in
`web/src/components/cake/`) added to DESIGN.md §6 and to the component overview (`#/components`). Before you finish, pass all three:
`cd web && npm run check:ui` (rules + DESIGN.md token table), the component overview, and `npm run build && npm run visual`
(pixel diff against `web/visual/baseline/`; if the change is intended, run `npm run visual:update` and commit the new baseline).
