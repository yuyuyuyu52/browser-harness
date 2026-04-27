# text_helpers.py Stupid-Proof Enhancement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make text_helpers.py self-healing, auto-connecting, and guiding so that even weak LLMs can drive the browser without getting stuck.

**Architecture:** Enhance text_helpers.py in-place. Add `_ensure_ready()` guard, unified `click()`/`fill()` dispatch, post-action page-change summaries, compact `describe_page()` output, and guard rails. Original functions stay for backward compat. Update text-mode.md to document only the simplified API.

**Tech Stack:** Python 3.11+, no new dependencies. All changes in `text_helpers.py` and `interaction-skills/text-mode.md`.

**Testing:** No unit tests — this project has no test infrastructure and all functions require a live browser + daemon. Verify manually: start Chrome, run `browser-harness --setup`, then run the verification script in each task's final step.

---

### Task 1: Add `_ensure_ready()` guard and internal helpers

**Files:**
- Modify: `text_helpers.py:1-15` (imports and top of file)

This task adds the auto-connect guard and two internal helpers used by later tasks: `_page_snapshot()` (captures url+title for change detection) and `_quick_count()` (lightweight element count).

- [ ] **Step 1: Add `_ensure_ready()`, `_page_snapshot()`, `_quick_count()`, and `_is_css_selector()` after the existing imports and constants**

Insert after line 15 (`CACHE_TTL = 60`):

```python
def _ensure_ready():
    if not daemon_alive():
        try:
            ensure_daemon()
        except RuntimeError:
            raise RuntimeError("error | daemon not running, auto-start failed — check Chrome is running, then retry")
    try:
        ensure_real_tab()
    except Exception:
        pass


def _page_snapshot():
    try:
        info = page_info()
        if "dialog" in info:
            d = info["dialog"]
            return {"url": "", "title": "", "dialog": f"{d.get('type', '?')}: {d.get('message', '')}"}
        return {"url": info.get("url", ""), "title": info.get("title", "")}
    except Exception:
        return {"url": "", "title": ""}


def _quick_count():
    try:
        raw = js("document.querySelectorAll('a,button,input,select,textarea,[role=\"button\"],[onclick]').length")
        return int(raw) if raw else 0
    except Exception:
        return 0


def _is_css_selector(s):
    for ch in ('#', '.', '[', '>', ':', '=', ' > ', ' ~ ', ' + '):
        if ch in s:
            return True
    return False


def _change_summary(before, after):
    parts = []
    if after.get("dialog"):
        parts.append(f"dialog opened: {after['dialog']}")
    elif before.get("url") != after.get("url"):
        parts.append(f"url changed: {after['url']}")
    elif before.get("title") != after.get("title"):
        parts.append(f"title changed: {after['title']}")
    else:
        parts.append("page unchanged")
    count = _quick_count()
    if count:
        parts.append(f"{count} interactive elements visible")
    return " → ".join(parts)
```

- [ ] **Step 2: Commit**

```bash
git add text_helpers.py
git commit -m "feat: add _ensure_ready guard and internal helpers for change detection"
```

---

### Task 2: Add `_ensure_ready()` calls to all existing public functions

**Files:**
- Modify: `text_helpers.py` — functions `status`, `auto_connect`, `describe_page`, `page_text`, `click_selector`, `click_text`, `click_item`, `fill` (the one taking selector), `fill_item`, `select_option`, `check`, `go`, `back`

Add `_ensure_ready()` as the first line of every public function **except** `auto_connect` and `status` (which handle their own connection logic). For those two, leave them as-is.

- [ ] **Step 1: Add `_ensure_ready()` to each function**

Functions to modify (add `_ensure_ready()` as first line of function body):

- `describe_page` (line ~146)
- `page_text` (line ~195)
- `click_selector` (line ~202)
- `click_text` (line ~221)
- `click_item` (line ~258)
- `fill` (the one taking selector+text, line ~271)
- `fill_item` (line ~296)
- `select_option` (line ~309)
- `check` (line ~338)
- `go` (line ~359)
- `back` (line ~365)

Example for `describe_page`:
```python
def describe_page(max_items=50):
    _ensure_ready()
    info = page_info()
    ...
```

Same pattern for every function listed above.

- [ ] **Step 2: Commit**

```bash
git add text_helpers.py
git commit -m "feat: add _ensure_ready() to all public text_helpers functions"
```

---

### Task 3: Unified `click()` smart dispatch

**Files:**
- Modify: `text_helpers.py` — add new `click()` function after the existing `click_item` function (around line ~269)

The new `click(target)` dispatches based on argument type: int → `click_item`, CSS selector string → `click_selector`, plain text → `click_text`. Wraps with before/after change detection.

- [ ] **Step 1: Rename the existing `click` import from helpers.py**

In the imports at line 6, the `click as raw_click` import already handles this — `raw_click` is the coordinate-based click from helpers.py. The new `click()` will shadow the old name only for text_helpers consumers, which is exactly what we want.

No change needed — the import already reads `click as raw_click`.

- [ ] **Step 2: Add unified `click()` after `click_item`**

Insert after the `click_item` function:

```python
def click(target):
    _ensure_ready()
    before = _page_snapshot()
    if isinstance(target, int):
        result = click_item(target)
    elif _is_css_selector(str(target)):
        result = click_selector(str(target))
    else:
        result = click_text(str(target))
    if result.startswith("error"):
        return result
    time.sleep(0.5)
    after = _page_snapshot()
    return f"{result} → {_change_summary(before, after)}"
```

- [ ] **Step 3: Commit**

```bash
git add text_helpers.py
git commit -m "feat: unified click() with smart dispatch and change detection"
```

---

### Task 4: Unified `fill()` smart dispatch

**Files:**
- Modify: `text_helpers.py` — replace existing `fill(selector, text)` function

The existing `fill(selector, text)` only accepts a CSS selector. Upgrade it to also accept an int index. Add guard rail: if the target element is not an input/textarea/select, return a clear error.

- [ ] **Step 1: Replace the `fill` function**

Replace the entire `fill(selector, text)` function (currently around line ~271) with:

```python
def fill(target, text):
    _ensure_ready()
    if isinstance(target, int):
        return fill_item(target, text)
    selector = str(target)
    escaped_sel = json.dumps(selector)
    escaped_val = json.dumps(text)
    before = _page_snapshot()
    result = js(f"""
    (function() {{
        const el = document.querySelector({escaped_sel});
        if (!el) return JSON.stringify({{error: "not found"}});
        const tag = el.tagName.toLowerCase();
        if (tag !== 'input' && tag !== 'textarea' && tag !== 'select' && !el.isContentEditable) {{
            return JSON.stringify({{error: "not an input", tag: tag}});
        }}
        el.scrollIntoView({{block: 'center'}});
        el.focus();
        el.value = '';
        el.value = {escaped_val};
        el.dispatchEvent(new InputEvent('input', {{bubbles: true}}));
        el.dispatchEvent(new Event('change', {{bubbles: true}}));
        el.dispatchEvent(new Event('blur', {{bubbles: true}}));
        return JSON.stringify({{selector: {escaped_sel}, value: {escaped_val}, tag: tag}});
    }})()
    """)
    if not result:
        return f"error | selector '{selector}' not found — call describe_page() to see current elements"
    r = json.loads(result)
    if r.get("error") == "not found":
        return f"error | selector '{selector}' not found — call describe_page() to see current elements"
    if r.get("error") == "not an input":
        return f"error | '{selector}' is a <{r.get('tag', '?')}>, not an input — use click() instead"
    time.sleep(0.3)
    after = _page_snapshot()
    summary = _change_summary(before, after)
    return f"filled '{selector}' with '{text}' → {summary}"
```

- [ ] **Step 2: Update `fill_item` to use the same guard rail**

`fill_item` delegates to the old `fill(selector, text)`, so once `fill()` is updated, `fill_item` inherits the guard rail automatically via `fill(item["selector"], text)`. But we need to make sure `fill_item` still calls `fill` with a string selector (not recurse via int). Check that `fill_item` calls `fill(item["selector"], text)` — which passes a string. No change needed to `fill_item`.

- [ ] **Step 3: Commit**

```bash
git add text_helpers.py
git commit -m "feat: unified fill() with int index support and input guard rail"
```

---

### Task 5: Add change detection to `select_option`, `check`, `go`, `back`

**Files:**
- Modify: `text_helpers.py` — functions `select_option`, `check`, `go`, `back`

Add before/after snapshot and change summary to the remaining write operations.

- [ ] **Step 1: Update `select_option`**

Add before snapshot at start, after snapshot + summary at end:

```python
def select_option(selector, value):
    _ensure_ready()
    before = _page_snapshot()
    escaped_sel = json.dumps(selector)
    escaped_val = json.dumps(value)
    result = js(f"""
    (function() {{
        const el = document.querySelector({escaped_sel});
        if (!el || el.tagName.toLowerCase() !== 'select') return JSON.stringify({{error: "not a select element"}});
        el.scrollIntoView({{block: 'center'}});
        const opts = Array.from(el.options);
        const match = opts.find(o => o.value === {escaped_val} || o.textContent.trim() === {escaped_val});
        if (!match) {{
            const available = opts.map(o => o.textContent.trim()).join(', ');
            return JSON.stringify({{error: "no matching option", available: available}});
        }}
        el.value = match.value;
        el.dispatchEvent(new Event('change', {{bubbles: true}}));
        return JSON.stringify({{selector: {escaped_sel}, selected: match.textContent.trim()}});
    }})()
    """)
    if not result:
        return f"error | selector '{selector}' not found — call describe_page() to see current elements"
    r = json.loads(result)
    if r.get("error") == "no matching option":
        return f"error | no option '{value}' in {selector}. available: {r.get('available', '?')}"
    if r.get("error"):
        return f"error | {r['error']} for selector '{selector}'"
    time.sleep(0.3)
    after = _page_snapshot()
    return f"selected '{r['selected']}' in '{selector}' → {_change_summary(before, after)}"
```

- [ ] **Step 2: Update `check`**

```python
def check(selector, checked=True):
    _ensure_ready()
    before = _page_snapshot()
    escaped_sel = json.dumps(selector)
    result = js(f"""
    (function() {{
        const el = document.querySelector({escaped_sel});
        if (!el) return JSON.stringify({{error: "not found"}});
        el.scrollIntoView({{block: 'center'}});
        el.checked = {str(checked).lower()};
        el.dispatchEvent(new Event('change', {{bubbles: true}}));
        return JSON.stringify({{selector: {escaped_sel}, checked: el.checked}});
    }})()
    """)
    if not result:
        return f"error | selector '{selector}' not found — call describe_page() to see current elements"
    r = json.loads(result)
    if r.get("error"):
        return f"error | selector '{selector}' not found — call describe_page() to see current elements"
    state = "checked" if r["checked"] else "unchecked"
    time.sleep(0.3)
    after = _page_snapshot()
    return f"{state} '{selector}' → {_change_summary(before, after)}"
```

- [ ] **Step 3: Update `go`**

```python
def go(url):
    _ensure_ready()
    new_tab(url)
    wait_for_load()
    return status()
```

`go()` already returns `status()` which includes page info. No change detection needed — the status line is sufficient.

- [ ] **Step 4: Update `back`**

```python
def back():
    _ensure_ready()
    before = _page_snapshot()
    js("history.back()")
    wait_for_load()
    after = _page_snapshot()
    return f"back → {_change_summary(before, after)}"
```

- [ ] **Step 5: Commit**

```bash
git add text_helpers.py
git commit -m "feat: add change detection to select_option, check, go, back"
```

---

### Task 6: Compact `describe_page()` output

**Files:**
- Modify: `text_helpers.py` — `describe_page` function (line ~146)

Replace the grouped category output with a flat DOM-order list and add footer hints.

- [ ] **Step 1: Replace the output formatting section of `describe_page`**

Replace the entire `describe_page` function:

```python
def describe_page(max_items=50):
    _ensure_ready()
    info = page_info()
    if "dialog" in info:
        d = info["dialog"]
        return f"error | dialog open: {d.get('type', '?')} — {d.get('message', '')}\nhandle it before interacting with the page"

    url = info.get("url", "")
    title = info.get("title", "")
    w, h = info.get("w", "?"), info.get("h", "?")
    sy, ph = info.get("sy", 0), info.get("ph", 0)

    if not url or url.startswith(INTERNAL):
        return "error | no page loaded — call go(url) to navigate first"

    script = _DESCRIBE_JS.replace("%%MAX_ITEMS%%", str(int(max_items * 2)))
    raw = js(script)
    if not raw:
        return f"page: {title} — {url}\nviewport: {w}x{h}\n\nno elements found — page may still be loading, try: wait_for_load() then describe_page()"

    items = json.loads(raw)
    visible = items[:max_items]
    _write_cache(visible)

    lines = [f"page: {title} — {url}", f"viewport: {w}x{h} | scroll: {sy}/{ph}", ""]
    for i, it in enumerate(visible):
        cat = it["category"]
        label = it.get("label", "")
        sel = it.get("selector", "")
        ph_val = it.get("placeholder", "")
        if cat == "input" and ph_val:
            lines.append(f'#{i} [{cat}] placeholder="{ph_val}" → {sel}')
        elif label:
            lines.append(f'#{i} [{cat}] "{label}" → {sel}')
        else:
            lines.append(f'#{i} [{it["tag"]}] → {sel}')

    footer_parts = [f"{len(visible)} elements"]
    total = len(items)
    if total > max_items:
        footer_parts.append(f"showing {max_items} of {total} (use describe_page(max_items={total}) for all)")
    try:
        viewport_h = int(h) if isinstance(h, int) else int(h)
        scroll_y = int(sy)
        page_h = int(ph)
        if scroll_y + viewport_h < page_h - 50:
            footer_parts.append("page has more content below (scroll down)")
    except (ValueError, TypeError):
        pass
    lines.append("")
    lines.append(" | ".join(footer_parts))

    return "\n".join(lines)
```

- [ ] **Step 2: Commit**

```bash
git add text_helpers.py
git commit -m "feat: compact describe_page output with flat list and footer hints"
```

---

### Task 7: Improve error messages across all functions

**Files:**
- Modify: `text_helpers.py` — `click_selector`, `click_text`, `click_item`

The unified `click()` and `fill()` from Tasks 3-4 already have good error messages. But the underlying `click_selector`, `click_text`, `click_item` functions still have old-style errors. Update them so even if someone calls them directly, errors are helpful.

- [ ] **Step 1: Update `click_selector` error messages**

Replace error returns in `click_selector`:

```python
def click_selector(selector):
    _ensure_ready()
    result = js(f"""
    (function() {{
        const el = document.querySelector({json.dumps(selector)});
        if (!el) return JSON.stringify({{error: true}});
        el.scrollIntoView({{block: 'center'}});
        el.click();
        const label = (el.textContent || '').trim().slice(0, 50) || el.tagName.toLowerCase();
        return JSON.stringify({{label: label, selector: {json.dumps(selector)}}});
    }})()
    """)
    if not result:
        return f"error | selector '{selector}' not found — call describe_page() to see current elements"
    r = json.loads(result)
    if r.get("error"):
        return f"error | selector '{selector}' not found — call describe_page() to see current elements"
    return f"clicked '{r['label']}' ({r['selector']})"
```

- [ ] **Step 2: Update `click_text` error messages**

Replace error returns in `click_text`:

```python
def click_text(text):
    _ensure_ready()
    escaped = json.dumps(text)
    result = js(f"""
    (function() {{
        const target = {escaped}.toLowerCase();
        const SEL = 'a, button, input[type="submit"], input[type="button"], [role="button"], [onclick]';
        let best = null;
        let bestLen = Infinity;
        for (const el of document.querySelectorAll(SEL)) {{
            const style = getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) continue;
            const t = (el.textContent || '').trim();
            if (t.toLowerCase().includes(target) && t.length < bestLen) {{
                best = el;
                bestLen = t.length;
            }}
            const aria = el.getAttribute('aria-label') || '';
            if (aria.toLowerCase().includes(target) && aria.length < bestLen) {{
                best = el;
                bestLen = aria.length;
            }}
        }}
        if (!best) return JSON.stringify({{error: true}});
        best.scrollIntoView({{block: 'center'}});
        best.click();
        const label = (best.textContent || '').trim().slice(0, 50) || best.tagName.toLowerCase();
        return JSON.stringify({{label: label, tag: best.tagName.toLowerCase()}});
    }})()
    """)
    if not result:
        return f"error | no clickable element with text '{text}' — call describe_page() to see available elements"
    r = json.loads(result)
    if r.get("error"):
        return f"error | no clickable element with text '{text}' — call describe_page() to see available elements"
    return f"clicked '{r['label']}' ({r['tag']})"
```

- [ ] **Step 3: Update `click_item` error messages**

```python
def click_item(index):
    _ensure_ready()
    cache = _read_cache()
    if cache is None:
        describe_page()
        cache = _read_cache()
    if cache is None:
        return "error | could not build element cache — call describe_page() first, then retry"
    if index < 0 or index >= len(cache):
        return f"error | index {index} out of range (0-{len(cache)-1}) — call describe_page() to see current elements"
    item = cache[index]
    return click_selector(item["selector"])
```

- [ ] **Step 4: Update `fill_item` error messages**

```python
def fill_item(index, text):
    _ensure_ready()
    cache = _read_cache()
    if cache is None:
        describe_page()
        cache = _read_cache()
    if cache is None:
        return "error | could not build element cache — call describe_page() first, then retry"
    if index < 0 or index >= len(cache):
        return f"error | index {index} out of range (0-{len(cache)-1}) — call describe_page() to see current elements"
    item = cache[index]
    return fill(item["selector"], text)
```

- [ ] **Step 5: Commit**

```bash
git add text_helpers.py
git commit -m "feat: improve error messages with next-step guidance in all functions"
```

---

### Task 8: Update `interaction-skills/text-mode.md`

**Files:**
- Modify: `interaction-skills/text-mode.md` (full rewrite)

Simplify to only recommend the unified API. Drop separate sections for click_item/click_text/click_selector/fill_item.

- [ ] **Step 1: Rewrite text-mode.md**

```markdown
# Text Mode (Non-Multimodal LLMs)

If you cannot see images, **do not use `screenshot()` or `click(x, y)`**. Use the text helpers instead — they give you the same control through DOM queries and plain-text output.

## Quick start

```python
# navigate and see what's on screen
print(go("https://example.com"))
print(describe_page())

# click by index, text, or CSS selector
click(3)
click("Sign in")
click("#submit-btn")

# fill inputs by index or selector
fill(8, "search query")
fill("#email", "test@example.com")
press_key("Enter")

# verify the result
print(describe_page())
```

No need to call `auto_connect()` — every function auto-connects.

## Core workflow

Every interaction follows the same loop:

```
describe_page() → act → describe_page() to verify
```

1. **`describe_page()`** — returns all interactive elements with numbered indices and CSS selectors. This replaces `screenshot()`.
2. **Act** — use `click(target)` or `fill(target, text)`. Target can be an index number, visible text, or CSS selector.
3. **Verify** — call `describe_page()` again. Actions also return a change summary (url changed, page unchanged, etc.) so you can often skip this step if the summary is clear.

## Navigating

```python
print(go("https://example.com"))       # open URL in new tab
print(describe_page())                  # see what's on the page
print(back())                           # browser back button
```

Use `go(url)` — it opens a new tab so you don't clobber the user's active page.

## Reading the page

```python
# interactive elements (buttons, links, inputs)
print(describe_page())

# full text content
print(page_text())

# page metadata only
print(status())
```

`describe_page()` output:

```
page: Google — https://www.google.com/
viewport: 1015x642 | scroll: 0/642

#0 [link] "About" → a[href="..."]
#7 [button] "Upload files" → button[aria-label="Upload files or images"]
#8 [input] placeholder="Search" → #APjFqb
#12 [button] "Google Search" → input[aria-label="Google Search"]

15 elements | page has more content below (scroll down)
```

## Clicking

`click(target)` figures out what you mean:

```python
click(3)              # by index from describe_page()
click("Sign in")      # by visible text (fuzzy match)
click("#submit-btn")  # by CSS selector
```

Returns a change summary: `clicked "Sign in" (button) → url changed: /login → 5 interactive elements visible`

## Filling forms

```python
fill(8, "hello world")           # by index
fill("#email", "hello@test.com") # by selector
press_key("Enter")               # submit
```

`fill()` handles focus, clearing, typing, and dispatching input/change/blur events so frameworks (React, Vue, Angular) pick up the value.

If you try to fill a non-input element, it tells you: `error | '#btn' is a <button>, not an input — use click() instead`

## Select dropdowns and checkboxes

```python
select_option("select#country", "United States")
check("#agree-tos", True)
```

## Scrolling

```python
scroll(500, 300, dy=-500)    # scroll down 500px
describe_page()              # elements update after scroll
```

If `describe_page()` says "page has more content below", scroll and describe again.

## Tab management

```python
for t in list_tabs():
    print(f"{t['title']} — {t['url']}")

switch_tab(target_id)
go("https://example.com")    # opens new tab
```

## When things go wrong

Every error tells you what to do next. Format: `error | <what happened> — <what to do>`

**Element not found:**
Call `describe_page()` to see what's actually on the page. The page may have changed.

**No elements found:**
Page might still be loading. Try `wait_for_load()` then `describe_page()`.

**Dialog open:**
`describe_page()` will report the dialog. Handle with JS or read `interaction-skills/dialogs.md`.

**Need more elements:**
```python
print(describe_page(max_items=100))
```

## What NOT to do

- **Don't call `screenshot()`** — you can't see the image.
- **Don't call `click(x, y)` with coordinates** — without screenshots, you're guessing.
- **Don't guess selectors** — always get them from `describe_page()` output.
```

- [ ] **Step 2: Commit**

```bash
git add interaction-skills/text-mode.md
git commit -m "docs: rewrite text-mode.md for unified click/fill API"
```

---

### Task 9: Update SKILL.md references

**Files:**
- Modify: `SKILL.md` — update the fast start section to reflect the simplified API

- [ ] **Step 1: Update the text-mode pointer in SKILL.md**

The existing text at line 12 already says:

> **If you cannot see images (pure-text / non-multimodal LLM), read `interaction-skills/text-mode.md` instead of this file.**

This is correct and sufficient. No change needed — text-mode.md itself now documents the unified API.

Check line 14 — it says to read `text_helpers.py`. This is still correct for power users who want to understand internals.

No code changes in this step.

- [ ] **Step 2: Verify the full flow manually**

Run with a live Chrome browser:

```bash
browser-harness <<'PY'
# Test auto-connect (no explicit auto_connect call)
print(describe_page())

# Test unified click
print(go("https://example.com"))
print(describe_page())
print(click("More information"))
print(describe_page())

# Test back with change detection
print(back())

# Test status
print(status())
PY
```

Verify:
- `describe_page()` works without prior `auto_connect()`
- Output uses the new compact format (flat list, `#N [type] "label" → selector`)
- `click("More information")` returns a change summary
- `back()` returns change summary
- No tracebacks

- [ ] **Step 3: Commit any fixups**

```bash
git add -A
git commit -m "chore: final verification and fixups"
```
