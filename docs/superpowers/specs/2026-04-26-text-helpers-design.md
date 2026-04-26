# text_helpers.py — Pure-Text LLM Layer for browser-harness

## Problem

browser-harness assumes a multimodal LLM: its core loop is `screenshot() → look → click(x, y)`. Pure-text LLMs cannot see screenshots, so they:

1. Fail at connecting — don't know which function to call, can't interpret error messages, can't recover from stale sessions.
2. Fail at interacting — coordinate-based clicking is unusable without vision; they guess selectors or hallucinate coordinates.

## Solution

Add `text_helpers.py` — a new file that provides text-only-friendly functions built on top of existing `helpers.py`. No existing files are modified except `run.py` (one import line added).

## Design Constraints

- Zero changes to `helpers.py`, `daemon.py`, `admin.py`.
- Both APIs coexist: multimodal LLMs keep using `screenshot()` + `click(x, y)`, text LLMs use the new functions.
- No retry framework, no manager layer, no config system (per project's design constraints).
- All return values are plain strings, never raw CDP JSON.

---

## 1. Connection Layer

### `auto_connect() -> str`

One function handles daemon startup, tab attachment, and health verification. Automatic recovery (up to 2 rounds):

1. Daemon not running → `ensure_daemon()`
2. No real tab → `ensure_real_tab()`, or `new_tab("about:blank")` if zero tabs exist
3. Stale session → `restart_daemon()` + reconnect

Returns:
```
"connected | tab: GitHub - browser-harness | https://github.com/browser-use/browser-harness"
```

On failure:
```
"error | Chrome not running, please start Chrome first"
"error | enable remote debugging at chrome://inspect/#remote-debugging"
```

### `status() -> str`

Lightweight check, no recovery:
```
"connected | tab: Google | https://www.google.com | 1280x720"
"disconnected | daemon not running"
"disconnected | no real tab attached"
```

---

## 2. Page Perception Layer

### `describe_page(max_items=50) -> str`

Returns a structured text description of all interactive elements on the page.

```
page: GitHub - browser-harness
url: https://github.com/browser-use/browser-harness
viewport: 1280x720 | scroll: 0/3200

[buttons]
  #0 "Sign in" selector="a[href='/login']"
  #1 "Star" selector="button.js-toggler-target"

[inputs]
  #4 placeholder="Search or jump to..." selector="input[name='q']"

[links]
  #5 "Issues (12)" selector="a#issues-tab"
  ...truncated (38 more, use describe_page(max_items=100) to see all)
```

Implementation: `js()` executes a DOM traversal script collecting all `<a>`, `<button>`, `<input>`, `<select>`, `<textarea>`, `[role=button]`, `[onclick]` elements. For each element it extracts:

- Visible text / placeholder / aria-label
- A stable CSS selector (prefer `data-*`, `id`, `aria-*`; fallback to `:nth-of-type`)
- Visibility check (skip `display:none` / `visibility:hidden`)

Items are numbered (`#0`, `#1`...) for use with `click_item()` / `fill_item()`.

The last `describe_page()` result is cached to `/tmp/bu-describe-cache.json` so `click_item(n)` can reference it across separate `browser-harness` invocations (each invocation is a new process). Calling `describe_page()` again refreshes the cache. The cache stores each item's selector, so `click_item(3)` looks up the selector from the cache file and clicks it.

### `page_text(max_length=3000) -> str`

Extracts page body text (reader-mode style) via `document.body.innerText`, truncated to `max_length`. For data extraction tasks.

---

## 3. Action Layer

All actions use DOM events (not coordinates). All return plain-text confirmation or error with recovery hint.

### Clicking

```python
click_item(index)                  # by describe_page() index
click_text("Sign in")              # fuzzy match visible text on clickable elements
click_selector("button.submit")    # exact CSS selector
```

Implementation: DOM query → `element.scrollIntoView()` → `element.click()`.

`click_item(index)` reads the cached `/tmp/bu-describe-cache.json` from the last `describe_page()` call; auto-calls `describe_page()` if no cache exists or cache is stale (>60s).

Return examples:
```
"clicked 'Sign in' (a[href='/login'])"
"error | no clickable element with text 'xxx' found. use describe_page() to see available elements"
```

### Form Input

```python
fill(selector, text)               # focus → clear → set value → dispatch events
fill_item(index, text)             # by describe_page() index
select_option(selector, value)     # <select> dropdown
check(selector, checked=True)      # checkbox / radio
```

`fill` implementation: `element.focus()` → `element.value = ""` → `element.value = text` → dispatch `InputEvent` + `change`. Uses DOM assignment + manual event dispatch rather than `type_text()` to avoid the need for correct focus management.

### Navigation

```python
go(url)        # new_tab(url) + wait_for_load() + return status()
back()         # history.back() + wait_for_load()
```

`go()` wraps the three steps LLMs most often get wrong into one call.

---

## 4. Integration

### File Changes

| File | Change |
|------|--------|
| `text_helpers.py` | **New file** — all functions above |
| `run.py` | Add `from text_helpers import *` |
| `helpers.py` | No change |
| `daemon.py` | No change |
| `admin.py` | No change |
| `SKILL.md` | No change |

### Internal Dependencies

`text_helpers.py` imports from `helpers.py` and `admin.py`:

```python
from helpers import (cdp, js, goto, new_tab, switch_tab, list_tabs,
                     current_tab, ensure_real_tab, wait_for_load,
                     page_info, scroll, type_text, press_key,
                     click as raw_click)
from admin import ensure_daemon, restart_daemon, daemon_alive
```

### Usage Pattern

Text-LLM workflow replaces `screenshot()` with `describe_page()`:

```bash
browser-harness <<'PY'
auto_connect()
go("https://github.com")
print(describe_page())
PY

browser-harness <<'PY'
fill_item(4, "browser-harness")
press_key("Enter")
print(describe_page())
PY
```

### What This Does NOT Do

- Does not change SKILL.md (that's the multimodal guide)
- Does not change daemon.py (communication layer is fine)
- Does not add a retry framework (violates "no manager layer" principle; recovery in `auto_connect()` is local, not a framework)
- Does not add a new CLI entry point
