---
name: browser-harness
description: Browse websites, fill forms, click buttons, scrape pages, search Google — control Chrome directly. Use when the task involves any web page interaction.
---

# browser-harness

Easiest and most powerful way to interact with the browser.

## 4 functions — this is all you need

```bash
browser-harness <<'PY'
print(go("https://example.com"))    # open URL in new tab, auto-connects
print(describe_page())              # see all interactive elements
print(click("More information"))    # click by text, index, or CSS selector
print(fill("#email", "test@x.com")) # fill by index or CSS selector
PY
```

- **`go(url)`** — navigate (opens new tab, waits for load, auto-connects)
- **`describe_page()`** — lists all buttons, links, inputs with `#index` and CSS selector
- **`click(target)`** — `click(3)` by index, `click("Sign in")` by text, `click("#btn")` by selector
- **`fill(target, text)`** — `fill(8, "query")` by index, `fill("#email", "x@y.com")` by selector

Every function auto-connects to the browser. No setup calls needed.

Every action returns a change summary: `clicked "Sign in" (button) → url changed: /login → 5 interactive elements visible`

Every error tells you what to do next: `error | selector '#foo' not found — call describe_page() to see current elements`

### The workflow loop

```
describe_page() → act (click/fill) → check the return value → describe_page() if needed
```

### Other useful functions

- `page_text()` — full text content of the page
- `select_option("select#country", "US")` — select dropdown
- `check("#agree", True)` — checkbox
- `back()` — browser back
- `press_key("Enter")` — keyboard input
- `scroll(500, 300, dy=-500)` — scroll down
- `status()` — quick connection check
- `list_tabs()` / `switch_tab(id)` — tab management

### What NOT to do

- **Don't guess selectors** — always get them from `describe_page()` output.
- **Don't call `screenshot()` unless you can see images** — use `describe_page()` instead.
- **Don't call `click(x, y)` with coordinates unless you can see screenshots** — use `click(target)` instead.

For the full text-mode reference, see `interaction-skills/text-mode.md`.

## Tool call shape

```bash
browser-harness <<'PY'
# any python. all helpers pre-imported. daemon auto-starts.
PY
```

Invoke as `browser-harness` — it's on `$PATH`. No `cd`, no `uv run`.

## Self-maintenance

- `browser-harness --doctor` — diagnose install, daemon, browser, and whether an update is available.
- `browser-harness --setup` — re-run the interactive browser-attach flow (equivalent to the bootstrap in `install.md`).
- `browser-harness --update -y` — pull the latest version and restart the daemon without prompting. **If you see a banner like `[browser-harness] update available: X -> Y` at the top of a run, run this yourself — don't ask the user first.** The banner is rate-limited to once per day.

For first-time install or reconnect/bootstrap, read `install.md`.

### Remote browsers

Use remote for **parallel sub-agents** (each gets its own isolated browser via a distinct `BU_NAME`) or on a headless server. `BROWSER_USE_API_KEY` must be set. `start_remote_daemon`, `list_cloud_profiles`, `list_local_profiles`, `sync_local_profile` are pre-imported.

```bash
browser-harness <<'PY'
start_remote_daemon("work")                               # default — clean browser, no profile
# start_remote_daemon("work", profileName="my-work")      # reuse a cloud profile (already logged in)
# start_remote_daemon("work", profileId="<uuid>")         # same, but by UUID
# start_remote_daemon("work", proxyCountryCode="de", timeout=120)   # DE proxy, 2-hour timeout
# start_remote_daemon("work", proxyCountryCode=None)      # disable the Browser Use proxy
PY

BU_NAME=work browser-harness <<'PY'
new_tab("https://example.com")
print(page_info())
PY
```

`start_remote_daemon` prints `liveUrl` and auto-opens it in the local browser (if a GUI is detected) so the user can watch along. Headless servers print only — share the URL with the user. The daemon `PATCH`es the cloud browser to `stop` on shutdown, which persists profile state. Running remote daemons bill until timeout.

Profiles (cookies-only login state) live in `interaction-skills/profile-sync.md` — covers `list_cloud_profiles()`, the chat-driven "which profile?" pattern, and `sync_local_profile()` for uploading a local Chrome profile.

## Search first

After cloning the repo, search `domain-skills/` first for the domain you are working on before inventing a new approach.

Only if you start struggling with a specific mechanic while navigating, look in `interaction-skills/` for helpers. The available interaction skills are:
- `cookies.md`
- `cross-origin-iframes.md`
- `dialogs.md`
- `downloads.md`
- `drag-and-drop.md`
- `dropdowns.md`
- `iframes.md`
- `network-requests.md`
- `print-as-pdf.md`
- `profile-sync.md`
- `screenshots.md`
- `scrolling.md`
- `shadow-dom.md`
- `tabs.md`
- `uploads.md`
- `viewport.md`

Useful commands:

```bash
rg --files domain-skills
rg -n "tiktok|upload" domain-skills
```

## Always contribute back

**If you learned anything non-obvious about how a site works, open a PR to `domain-skills/<site>/` before you finish. Default to contributing.** The harness gets better only because agents file what they learn. If figuring something out cost you a few steps, the next run should not pay the same tax.

Examples of what's worth a PR:

- A **private API** the page calls (XHR/fetch endpoint, request shape, auth) — often 10× faster than DOM scraping.
- A **stable selector** that beats the obvious one, or an obfuscated CSS-module class to avoid.
- A **framework quirk** — "the dropdown is a React combobox that only commits on Escape", "this Vue list only renders rows inside its own scroll container, so `scrollIntoView` on the row doesn't work — you have to scroll the container".
- A **URL pattern** — direct route, required query params (`?lang=en`, `?th=1`), a variant that skips a loader.
- A **wait** that `wait_for_load()` misses, with the reason.
- A **trap** — stale drafts, legacy IDs that now return null, unicode quirks, beforeunload dialogs, CAPTCHA surfaces.

### What a domain skill should capture

The *durable* shape of the site — the map, not the diary. Focus on what the next agent on this site needs to know before it starts:

- URL patterns and query params.
- Private APIs and their payload shape.
- Stable selectors (`data-*`, `aria-*`, `role`, semantic classes).
- Site structure — containers, items per page, framework, where state lives.
- Framework/interaction quirks unique to this site.
- Waits and the reasons they're needed.
- Traps and the selectors that *don't* work.

### Do not write

- **Raw pixel coordinates.** They break on viewport, zoom, and layout changes. Describe how to *locate* the target (selector, `scrollIntoView`, `aria-label`, visible text) — never where it happened to be on your screen.
- **Run narration** or step-by-step of the specific task you just did.
- **Secrets, cookies, session tokens, user-specific state.** `domain-skills/` is shared and public.

## What actually works

- **`describe_page()` + `click(target)` is the default workflow.** Works for all models. No images needed.
- **Bulk HTTP**: `http_get(url)` + `ThreadPoolExecutor`. No browser for static pages (249 Netflix pages in 2.8s).
- **Wrong/stale tab**: all text helpers auto-recover. If you need manual control: `ensure_real_tab()`.
- **Auth wall**: redirected to login → stop and ask the user. Don't type credentials.
- **DOM reads**: use `js(...)` for inspection and extraction beyond what `describe_page()` returns.
- **Iframe sites** (Azure blades, Salesforce): use coordinate clicks (visual mode) — they pass through at the compositor level.
- **Raw CDP** for anything helpers don't cover: `cdp("Domain.method", **params)`.

### Visual mode (multimodal models only)

If you **can see images**, you can also use screenshot-based interaction for faster visual navigation:

- `screenshot()` → look → `click(x, y)` → `screenshot()` again to verify.
- Coordinate clicks pass through iframes/shadow/cross-origin at the compositor level.
- Read `helpers.py` for the full low-level API.

## Design constraints

- **Text mode default.** `describe_page()` + `click(target)` works for all models. Coordinate clicks (`click(x, y)` via `Input.dispatchMouseEvent`) are available for multimodal models and pass through iframes/shadow/cross-origin at the compositor level.
- **Connect to the user's running Chrome.** Don't launch your own browser.
- **`cdp-use` is only for `CDPClient.send_raw`.** Prefer raw CDP strings over typed wrappers.
- **`run.py` stays tiny.** No argparse, subcommands, or extra control layer.
- **Helpers stay short.** Browser primitives in `helpers.py`; daemon/bootstrap and remote session admin live in `admin.py`.
- **Don't add a manager layer.** No retries framework, session manager, daemon supervisor, config system, or logging framework.

## Architecture

```text
Chrome / Browser Use cloud -> CDP WS -> daemon.py -> /tmp/bu-<NAME>.sock -> run.py
```

- Protocol is one JSON line each way.
- Requests are `{method, params, session_id}` for CDP or `{meta: ...}` for daemon control.
- Responses are `{result}` / `{error}` / `{events}` / `{session_id}`.
- `BU_NAME` namespaces socket, pid, and log files.
- `BU_CDP_WS` overrides local Chrome discovery for remote browsers.
- `BU_BROWSER_ID` + `BROWSER_USE_API_KEY` lets the daemon stop a Browser Use cloud browser on shutdown.

## Gotchas (field-tested)

- **Chrome 144+ `chrome://inspect/#remote-debugging` does NOT serve `/json/version`.** Read `DevToolsActivePort` instead.
- **Try attaching before asking for setup.** If `uv run browser-harness` already works, skip the remote-debugging instructions entirely. Decide what to escalate from the harness's error message, not from whether Chrome is visibly running.
- **The remote-debugging checkbox is per-profile sticky in Chrome.** Once ticked on a profile, every future Chrome launch auto-enables CDP — only navigate to `chrome://inspect/#remote-debugging` when `DevToolsActivePort` is genuinely missing on a fresh profile.
- **The first connect may block on Chrome's Allow dialog.** If setup hangs, explicitly tell the user to click `Allow` in Chrome if it appears, then keep polling for up to 30 seconds instead of treating follow-on errors as a new failure.
- **`DevToolsActivePort` can exist before the port is actually listening.** Treat connection refused as "still enabling" and keep polling for up to 30 seconds.
- **Chrome may open the profile picker before any real tab exists.** If Chrome opens both a profile picker and the remote-debugging page, tell the user to choose their normal profile first, then tick the checkbox and click `Allow` if shown.
- **On macOS, if Chrome is already running, prefer AppleScript `open location` over `open -a ... URL`.** It reuses the current profile and avoids creating an extra startup path through the profile picker.
- **Omnibox popups are fake `page` targets.** Filter `chrome://omnibox-popup...` and other internals when you need a real tab.
- **CDP target order != Chrome's visible tab-strip order.** Use UI automation when the user means "the first/second tab I can see"; `Target.activateTarget` only shows a known target.
- **Default daemon sessions can go stale.** `ensure_real_tab()` re-attaches to a real page.
- **`no close frame received or sent` usually means a stale daemon / websocket.** Restart the daemon once with:
  `uv run python - <<'PY'`
  `from admin import restart_daemon`
  `restart_daemon()`
  `PY`
  before assuming setup is wrong.
- **If `restart_daemon()` also hangs**, kill Chrome entirely (`pkill -9 -f "Google Chrome"`), clean sockets (`rm -f /tmp/bu-default.sock /tmp/bu-default.pid`), reopen Chrome (`open -a "Google Chrome"`), wait 5s, then reconnect. This resets all CDP state.
- **Browser Use API is camelCase on the wire.** `cdpUrl`, `proxyCountryCode`, etc.
- **Remote `cdpUrl` is HTTPS, not ws.** Resolve the websocket URL via `/json/version`.
- **Stop cloud browsers with `PATCH /browsers/{id}` + `{\"action\":\"stop\"}`.**
- **Every action returns a change summary — read it.** If it says "page unchanged", your action probably didn't work. Call `describe_page()` to see what's actually on screen.
- **Don't guess selectors.** Always get them from `describe_page()` output. Guessed selectors are the #1 cause of agent failures.
- **`describe_page()` only shows visible interactive elements.** If the page has more content below the fold, the footer says "page has more content below (scroll down)". Scroll and describe again.
- **If you need framework-specific DOM tricks, check `interaction-skills/` first.** That is where dropdown, dialog, iframe, shadow DOM, and form-specific guidance belongs.
- **Visual mode gotcha: after every action, re-screenshot before assuming it worked.** Use the image to verify changed state.

## Interaction notes

- `interaction-skills/` holds reusable UI mechanics such as dialogs, tabs, dropdowns, iframes, and uploads.
- `domain-skills/` holds site-specific workflows and should be updated when you discover reusable patterns for a website.
