# text_helpers.py Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `text_helpers.py` module that gives pure-text (non-multimodal) LLMs a usable API for browser-harness — auto-connect, DOM-based element discovery, text/selector-based clicking, and form filling.

**Architecture:** A single new file `text_helpers.py` that imports from existing `helpers.py` and `admin.py`. All functions return plain strings. A JSON cache file at `/tmp/bu-describe-cache.json` persists `describe_page()` results across process invocations. `run.py` gains one import line; `pyproject.toml` gains one module name.

**Tech Stack:** Python 3.11+, CDP via existing `helpers.py` primitives, `js()` for DOM traversal.

---

### Task 1: Connection Layer — `auto_connect()` and `status()`

**Files:**
- Create: `text_helpers.py`

- [ ] **Step 1: Create `text_helpers.py` with imports and `status()`**

```python
"""Text-friendly browser helpers for non-multimodal LLMs."""
import json, os, time
from pathlib import Path

from helpers import (
    cdp, js, goto, new_tab, switch_tab, list_tabs, current_tab,
    ensure_real_tab, wait_for_load, page_info, scroll, type_text,
    press_key, click as raw_click, INTERNAL,
)
from admin import ensure_daemon, restart_daemon, daemon_alive

NAME = os.environ.get("BU_NAME", "default")
CACHE_PATH = Path(f"/tmp/bu-describe-cache-{NAME}.json")
CACHE_TTL = 60


def status():
    if not daemon_alive():
        return "disconnected | daemon not running"
    try:
        info = page_info()
    except Exception:
        return "disconnected | daemon running but no tab attached"
    if "dialog" in info:
        d = info["dialog"]
        return f"connected | dialog open: {d.get('type', '?')} — {d.get('message', '')}"
    url = info.get("url", "")
    if not url or url.startswith(INTERNAL):
        return "disconnected | no real tab attached"
    title = info.get("title", "")
    w, h = info.get("w", "?"), info.get("h", "?")
    return f"connected | tab: {title} | {url} | {w}x{h}"
```

- [ ] **Step 2: Add `auto_connect()`**

Append to `text_helpers.py`:

```python
def auto_connect():
    for attempt in range(2):
        try:
            if not daemon_alive():
                ensure_daemon()
            tab = ensure_real_tab()
            if not tab:
                new_tab("about:blank")
            s = status()
            if s.startswith("connected"):
                return s
        except RuntimeError as e:
            msg = str(e)
            if attempt == 0:
                if "DevToolsActivePort not found" in msg or "chrome://inspect" in msg:
                    return f"error | enable remote debugging at chrome://inspect/#remote-debugging"
                try:
                    restart_daemon()
                except Exception:
                    pass
                continue
            if "Chrome" in msg or "DevTools" in msg:
                return f"error | Chrome not running, please start Chrome first"
            return f"error | {msg}"
        except Exception as e:
            if attempt == 0:
                try:
                    restart_daemon()
                except Exception:
                    pass
                continue
            return f"error | {e}"
    return status()
```

- [ ] **Step 3: Verify connection layer works**

Run (requires Chrome running with remote debugging enabled):

```bash
browser-harness <<'PY'
from text_helpers import auto_connect, status
print(auto_connect())
print(status())
PY
```

Expected: two lines starting with `connected | tab:`.

- [ ] **Step 4: Commit**

```bash
git add text_helpers.py
git commit -m "feat: add text_helpers.py with auto_connect() and status()"
```

---

### Task 2: Page Perception — `describe_page()` and `page_text()`

**Files:**
- Modify: `text_helpers.py`

- [ ] **Step 1: Add the DOM traversal JS and `describe_page()`**

Append to `text_helpers.py`:

```python
_DESCRIBE_JS = """
(function(maxItems) {
  const SEL = 'a, button, input, select, textarea, [role="button"], [onclick]';
  const els = document.querySelectorAll(SEL);
  const items = [];
  for (const el of els) {
    if (items.length >= maxItems) break;
    const style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') continue;
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) continue;

    const tag = el.tagName.toLowerCase();
    const type = el.type || '';
    let category = 'other';
    if (tag === 'a') category = 'link';
    else if (tag === 'button' || el.getAttribute('role') === 'button' || el.hasAttribute('onclick')) category = 'button';
    else if (tag === 'input' || tag === 'textarea') category = 'input';
    else if (tag === 'select') category = 'select';

    const text = (el.textContent || '').trim().slice(0, 80);
    const placeholder = el.placeholder || '';
    const ariaLabel = el.getAttribute('aria-label') || '';
    const label = text || ariaLabel || placeholder;

    // Build a stable selector
    let selector = '';
    if (el.id) {
      selector = '#' + CSS.escape(el.id);
    } else if (el.getAttribute('data-testid')) {
      selector = '[data-testid="' + el.getAttribute('data-testid') + '"]';
    } else if (el.getAttribute('aria-label')) {
      selector = tag + '[aria-label="' + el.getAttribute('aria-label') + '"]';
    } else if (el.name) {
      selector = tag + '[name="' + el.name + '"]';
    } else if (tag === 'a' && el.getAttribute('href')) {
      const href = el.getAttribute('href');
      if (href.length < 100) selector = 'a[href="' + href + '"]';
    }
    if (!selector) {
      const parent = el.parentElement;
      const siblings = parent ? Array.from(parent.children).filter(c => c.tagName === el.tagName) : [];
      const idx = siblings.indexOf(el) + 1;
      selector = tag + ':nth-of-type(' + idx + ')';
      if (parent && parent !== document.body) {
        let pSel = '';
        if (parent.id) pSel = '#' + CSS.escape(parent.id);
        else if (parent.className && typeof parent.className === 'string') {
          const cls = parent.className.trim().split(/\\s+/)[0];
          if (cls) pSel = parent.tagName.toLowerCase() + '.' + CSS.escape(cls);
        }
        if (pSel) selector = pSel + ' > ' + selector;
      }
    }

    items.push({category, tag, type, label, placeholder, selector});
  }
  return JSON.stringify(items);
})(%%MAX_ITEMS%%)
"""


def _write_cache(items):
    CACHE_PATH.write_text(json.dumps({"ts": time.time(), "items": items}))


def _read_cache():
    try:
        data = json.loads(CACHE_PATH.read_text())
        if time.time() - data["ts"] < CACHE_TTL:
            return data["items"]
    except (FileNotFoundError, ValueError, KeyError):
        pass
    return None


def describe_page(max_items=50):
    info = page_info()
    if "dialog" in info:
        d = info["dialog"]
        return f"dialog open: {d.get('type', '?')} — {d.get('message', '')}\nhandle it before interacting with the page"

    url = info.get("url", "")
    title = info.get("title", "")
    w, h = info.get("w", "?"), info.get("h", "?")
    sy, ph = info.get("sy", 0), info.get("ph", 0)

    script = _DESCRIBE_JS.replace("%%MAX_ITEMS%%", str(int(max_items * 2)))
    raw = js(script)
    if not raw:
        return f"page: {title}\nurl: {url}\n\n(no interactive elements found)"

    items = json.loads(raw)
    _write_cache(items)

    groups = {}
    for i, it in enumerate(items[:max_items]):
        cat = it["category"] + "s"
        groups.setdefault(cat, []).append((i, it))

    lines = [f"page: {title}", f"url: {url}", f"viewport: {w}x{h} | scroll: {sy}/{ph}", ""]
    for cat in ["buttons", "inputs", "selects", "links", "others"]:
        if cat not in groups:
            continue
        lines.append(f"[{cat}]")
        for idx, it in groups[cat]:
            label = it.get("label", "")
            sel = it.get("selector", "")
            ph = it.get("placeholder", "")
            if it["category"] == "input" and ph:
                lines.append(f'  #{idx} placeholder="{ph}" selector="{sel}"')
            elif label:
                lines.append(f'  #{idx} "{label}" selector="{sel}"')
            else:
                lines.append(f'  #{idx} ({it["tag"]}) selector="{sel}"')
        lines.append("")

    total = len(items)
    if total > max_items:
        lines.append(f"...truncated ({total - max_items} more, use describe_page(max_items={total}) to see all)")

    return "\n".join(lines)
```

- [ ] **Step 2: Add `page_text()`**

Append to `text_helpers.py`:

```python
def page_text(max_length=3000):
    raw = js("document.body.innerText") or ""
    if len(raw) > max_length:
        return raw[:max_length] + f"\n\n...truncated ({len(raw) - max_length} chars remaining, use page_text(max_length={len(raw)}) to see all)"
    return raw
```

- [ ] **Step 3: Verify page perception works**

```bash
browser-harness <<'PY'
from text_helpers import auto_connect, describe_page, page_text
auto_connect()
from helpers import new_tab, wait_for_load
new_tab("https://example.com")
wait_for_load()
print(describe_page())
print("---")
print(page_text())
PY
```

Expected: structured element list with `[links]` section containing "More information..." link, followed by `---` and the plain text of example.com.

- [ ] **Step 4: Commit**

```bash
git add text_helpers.py
git commit -m "feat: add describe_page() and page_text() for DOM-based page perception"
```

---

### Task 3: Action Layer — Clicking

**Files:**
- Modify: `text_helpers.py`

- [ ] **Step 1: Add `click_selector()`**

Append to `text_helpers.py`:

```python
def click_selector(selector):
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
        return f"error | selector '{selector}' not found. use describe_page() to see available elements"
    r = json.loads(result)
    if r.get("error"):
        return f"error | selector '{selector}' not found. use describe_page() to see available elements"
    return f"clicked '{r['label']}' ({r['selector']})"
```

- [ ] **Step 2: Add `click_text()`**

Append to `text_helpers.py`:

```python
def click_text(text):
    escaped = json.dumps(text)
    result = js(f"""
    (function() {{
        const target = {escaped}.toLowerCase();
        const SEL = 'a, button, input[type="submit"], input[type="button"], [role="button"], [onclick]';
        let best = null;
        let bestLen = Infinity;
        for (const el of document.querySelectorAll(SEL)) {{
            const style = getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') continue;
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
        return f"error | no clickable element with text '{text}' found. use describe_page() to see available elements"
    r = json.loads(result)
    if r.get("error"):
        return f"error | no clickable element with text '{text}' found. use describe_page() to see available elements"
    return f"clicked '{r['label']}' ({r['tag']})"
```

- [ ] **Step 3: Add `click_item()`**

Append to `text_helpers.py`:

```python
def click_item(index):
    cache = _read_cache()
    if cache is None:
        describe_page()
        cache = _read_cache()
    if cache is None:
        return "error | could not build element cache. use describe_page() first"
    if index < 0 or index >= len(cache):
        return f"error | index {index} out of range (0-{len(cache)-1}). use describe_page() to see available elements"
    item = cache[index]
    return click_selector(item["selector"])
```

- [ ] **Step 4: Verify clicking works**

```bash
browser-harness <<'PY'
from text_helpers import auto_connect, describe_page, click_text, click_item
auto_connect()
from helpers import new_tab, wait_for_load
new_tab("https://example.com")
wait_for_load()
print(describe_page())
PY
```

Then in a second invocation (tests cross-process cache):

```bash
browser-harness <<'PY'
from text_helpers import click_item, click_text
print(click_text("More information"))
PY
```

Expected: `clicked 'More information...' (a)` or similar.

- [ ] **Step 5: Commit**

```bash
git add text_helpers.py
git commit -m "feat: add click_text(), click_selector(), click_item() for DOM-based clicking"
```

---

### Task 4: Action Layer — Form Input

**Files:**
- Modify: `text_helpers.py`

- [ ] **Step 1: Add `fill()`**

Append to `text_helpers.py`:

```python
def fill(selector, text):
    escaped_sel = json.dumps(selector)
    escaped_val = json.dumps(text)
    result = js(f"""
    (function() {{
        const el = document.querySelector({escaped_sel});
        if (!el) return JSON.stringify({{error: "not found"}});
        el.scrollIntoView({{block: 'center'}});
        el.focus();
        el.value = '';
        el.value = {escaped_val};
        el.dispatchEvent(new Event('input', {{bubbles: true}}));
        el.dispatchEvent(new Event('change', {{bubbles: true}}));
        return JSON.stringify({{selector: {escaped_sel}, value: {escaped_val}}});
    }})()
    """)
    if not result:
        return f"error | selector '{selector}' not found. use describe_page() to see available elements"
    r = json.loads(result)
    if r.get("error"):
        return f"error | selector '{selector}' not found. use describe_page() to see available elements"
    return f"filled '{r['selector']}' with '{text}'"
```

- [ ] **Step 2: Add `fill_item()`**

Append to `text_helpers.py`:

```python
def fill_item(index, text):
    cache = _read_cache()
    if cache is None:
        describe_page()
        cache = _read_cache()
    if cache is None:
        return "error | could not build element cache. use describe_page() first"
    if index < 0 or index >= len(cache):
        return f"error | index {index} out of range (0-{len(cache)-1}). use describe_page() to see available elements"
    item = cache[index]
    return fill(item["selector"], text)
```

- [ ] **Step 3: Add `select_option()` and `check()`**

Append to `text_helpers.py`:

```python
def select_option(selector, value):
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
        return f"error | selector '{selector}' not found"
    r = json.loads(result)
    if r.get("error") == "no matching option":
        return f"error | no option '{value}' in {selector}. available: {r.get('available', '?')}"
    if r.get("error"):
        return f"error | {r['error']} for selector '{selector}'"
    return f"selected '{r['selected']}' in '{selector}'"


def check(selector, checked=True):
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
        return f"error | selector '{selector}' not found"
    r = json.loads(result)
    if r.get("error"):
        return f"error | selector '{selector}' not found"
    state = "checked" if r["checked"] else "unchecked"
    return f"{state} '{selector}'"
```

- [ ] **Step 4: Verify form input works**

```bash
browser-harness <<'PY'
from text_helpers import auto_connect, go, describe_page, fill, click_text
auto_connect()
go("https://www.google.com")
print(describe_page())
PY
```

Then:

```bash
browser-harness <<'PY'
from text_helpers import fill, describe_page
print(fill('textarea[name="q"]', 'browser-harness'))
print(describe_page())
PY
```

Expected: `filled 'textarea[name="q"]' with 'browser-harness'`.

- [ ] **Step 5: Commit**

```bash
git add text_helpers.py
git commit -m "feat: add fill(), fill_item(), select_option(), check() for form input"
```

---

### Task 5: Navigation — `go()` and `back()`

**Files:**
- Modify: `text_helpers.py`

- [ ] **Step 1: Add `go()` and `back()`**

Append to `text_helpers.py`:

```python
def go(url):
    new_tab(url)
    wait_for_load()
    return status()


def back():
    js("history.back()")
    wait_for_load()
    return status()
```

- [ ] **Step 2: Verify navigation**

```bash
browser-harness <<'PY'
from text_helpers import auto_connect, go, back
auto_connect()
print(go("https://example.com"))
print(go("https://www.google.com"))
print(back())
PY
```

Expected: three `connected | tab: ...` lines — example.com, google.com, then example.com again.

- [ ] **Step 3: Commit**

```bash
git add text_helpers.py
git commit -m "feat: add go() and back() navigation wrappers"
```

---

### Task 6: Integration — `run.py` and `pyproject.toml`

**Files:**
- Modify: `run.py:17` (add import)
- Modify: `pyproject.toml:20` (add module)

- [ ] **Step 1: Add import to `run.py`**

After the existing `from helpers import *` line (line 17), add:

```python
from text_helpers import *
```

The full imports section of `run.py` becomes:

```python
from admin import (
    _version,
    ensure_daemon,
    list_cloud_profiles,
    list_local_profiles,
    print_update_banner,
    restart_daemon,
    run_doctor,
    run_setup,
    run_update,
    start_remote_daemon,
    stop_remote_daemon,
    sync_local_profile,
)
from helpers import *
from text_helpers import *
```

- [ ] **Step 2: Add `text_helpers` to `pyproject.toml`**

Change line 20 from:

```toml
py-modules = ["run", "helpers", "daemon", "admin"]
```

to:

```toml
py-modules = ["run", "helpers", "text_helpers", "daemon", "admin"]
```

- [ ] **Step 3: Verify end-to-end usage (the target UX)**

This is how a pure-text LLM would actually use it — no imports needed:

```bash
browser-harness <<'PY'
print(auto_connect())
PY
```

```bash
browser-harness <<'PY'
print(go("https://example.com"))
PY
```

```bash
browser-harness <<'PY'
print(describe_page())
PY
```

```bash
browser-harness <<'PY'
print(click_text("More information"))
PY
```

Expected: each command succeeds with a plain-text response. No `from text_helpers import ...` needed.

- [ ] **Step 4: Verify existing helpers still work (no regressions)**

```bash
browser-harness <<'PY'
new_tab("https://example.com")
wait_for_load()
print(page_info())
print(screenshot())
PY
```

Expected: `page_info()` returns a dict, `screenshot()` returns `/tmp/shot.png`. Original API unaffected.

- [ ] **Step 5: Commit**

```bash
git add run.py pyproject.toml
git commit -m "feat: integrate text_helpers into browser-harness entrypoint"
```

---

### Task 7: Final Smoke Test

- [ ] **Step 1: Run the full text-LLM workflow end to end**

Simulate a complete pure-text-LLM session across separate process invocations:

```bash
browser-harness <<'PY'
print(auto_connect())
print(go("https://www.google.com"))
print(describe_page())
PY
```

```bash
browser-harness <<'PY'
print(fill_item(0, "browser harness github"))
print(click_text("Google Search"))
PY
```

```bash
browser-harness <<'PY'
print(describe_page())
print(page_text(500))
PY
```

Expected: navigates to Google, fills search box by index, clicks search, shows search results in text.

- [ ] **Step 2: Test error paths**

```bash
browser-harness <<'PY'
print(click_text("nonexistent button xyz"))
print(click_item(9999))
print(fill("#nonexistent", "test"))
PY
```

Expected: three `error | ...` messages with recovery hints pointing to `describe_page()`.

- [ ] **Step 3: Final commit (if any adjustments were needed)**

```bash
git add -A
git commit -m "fix: adjustments from smoke test"
```

Only if changes were made. Skip if smoke test passed cleanly.
