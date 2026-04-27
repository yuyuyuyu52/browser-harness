# text_helpers.py Stupid-Proof Enhancement

Enhance text_helpers.py in-place to make every function self-healing, auto-connecting, and guiding for agents that don't know what to do next.

## 1. Auto-connect guard

All public functions call `_ensure_ready()` at entry. It silently handles daemon startup, tab attachment, and reconnection. Agents never need to call `auto_connect()` manually.

```python
def _ensure_ready():
    if not daemon_alive():
        ensure_daemon()
    ensure_real_tab()
```

## 2. Unified click() smart dispatch

Merge `click_item`, `click_text`, `click_selector` into one `click(target)`:

- `int` → by index (from describe_page)
- string with CSS selector characters (`#`, `.`, `[`, `>`, `:`, `=`) → by CSS selector
- plain string → by visible text (fuzzy match, shortest wins)

Same for `fill(target, text)`: accepts int index or CSS selector string.

Original functions (`click_item`, `click_text`, `click_selector`, `fill_item`) remain for backward compat but are no longer documented.

## 3. Auto-verify after actions

Every write operation (click, fill, select_option, check, go, back) captures `{url, title}` before acting, waits ~0.5s after, then compares:

```
clicked "Sign in" (button) → url changed: /login → 2 inputs, 1 button visible
clicked "Menu" (button) → page unchanged
filled "#email" with "test@..." → page unchanged
go("https://example.com") → connected | tab: Example Domain | https://example.com/ | 1015x642
```

If a dialog opens after the action, report that instead.

The brief element count in the suffix comes from a lightweight JS query (count of visible interactive elements), not a full describe_page.

## 4. Compact describe_page() output

Before (grouped by category, verbose):
```
[buttons]
  #7 "Upload files or images" selector="button[aria-label=\"Upload files or images\"]"
[inputs]
  #8 placeholder="Search" selector="#APjFqb"
```

After (flat list, DOM order, inline type tag):
```
page: Google — https://www.google.com/
viewport: 1015x642 | scroll: 0/642

#0 [link] "About" → a[href="..."]
#1 [link] "Store" → a[href="..."]
#7 [button] "Upload files" → button[aria-label="Upload files or images"]
#8 [input] placeholder="Search" → #APjFqb
#12 [button] "Google Search" → input[aria-label="Google Search"]

15 elements | page has more content below (scroll down)
```

Footer line:
- Always shows total element count
- If `scrollY + viewportHeight < pageHeight`: append "page has more content below (scroll down)"
- If truncated: append "showing N of M (use describe_page(max_items=M) for all)"

## 5. Error messages = diagnosis + next step

Unified format: `error | <what happened> — <what to do next>`

Examples:
- `error | selector '#foo' not found — call describe_page() to see current elements`
- `error | index 15 out of range (0-12) — call describe_page() to refresh the element list`
- `error | no page loaded — call go(url) to navigate first`
- `error | dialog open: confirm "Delete?" — handle with js() or read interaction-skills/dialogs.md`
- `error | daemon not running, auto-start failed — check Chrome is running, then retry`

## 6. Guard rails

- `fill()` targeting a non-input/textarea/select element → `error | '#btn' is a <button>, not an input — use click() instead`
- `describe_page()` returns 0 elements → append: `no elements found — page may still be loading, try: wait_for_load() then describe_page()`
- Navigation functions already auto-wait (keep as-is)

## 7. text-mode.md doc update

Simplify to recommend only the unified API:
- `describe_page()` → `click(target)` / `fill(target, text)` → `describe_page()`
- Remove separate sections for click_item/click_text/click_selector/fill_item
- Keep troubleshooting section, updated with new error format

## What doesn't change

- `helpers.py` — low-level API for multimodal models and power users
- `daemon.py` — CDP websocket holder
- `run.py` — entrypoint
- `admin.py` — daemon lifecycle
- Original functions remain exported (backward compat), just undocumented
