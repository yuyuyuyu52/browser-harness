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


_DESCRIBE_JS = """
(function(maxItems) {
  const SEL = 'a, button, input, select, textarea, [role="button"], [onclick]';
  const els = document.querySelectorAll(SEL);
  const items = [];
  for (const el of els) {
    if (items.length >= maxItems) break;
    const style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) continue;
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
      selector = '[data-testid="' + CSS.escape(el.getAttribute('data-testid')) + '"]';
    } else if (el.getAttribute('aria-label')) {
      selector = tag + '[aria-label="' + CSS.escape(el.getAttribute('aria-label')) + '"]';
    } else if (el.name) {
      selector = tag + '[name="' + CSS.escape(el.name) + '"]';
    } else if (tag === 'a' && el.getAttribute('href')) {
      const href = el.getAttribute('href');
      if (href.length < 100) selector = 'a[href="' + CSS.escape(href) + '"]';
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
    _ensure_ready()
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
    visible = items[:max_items]
    _write_cache(visible)

    groups = {}
    for i, it in enumerate(visible):
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


def page_text(max_length=3000):
    _ensure_ready()
    raw = js("document.body.innerText") or ""
    if len(raw) > max_length:
        return raw[:max_length] + f"\n\n...truncated ({len(raw) - max_length} chars remaining, use page_text(max_length={len(raw)}) to see all)"
    return raw


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
        return f"error | selector '{selector}' not found. use describe_page() to see available elements"
    r = json.loads(result)
    if r.get("error"):
        return f"error | selector '{selector}' not found. use describe_page() to see available elements"
    return f"clicked '{r['label']}' ({r['selector']})"


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
        return f"error | no clickable element with text '{text}' found. use describe_page() to see available elements"
    r = json.loads(result)
    if r.get("error"):
        return f"error | no clickable element with text '{text}' found. use describe_page() to see available elements"
    return f"clicked '{r['label']}' ({r['tag']})"


def click_item(index):
    _ensure_ready()
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


def fill_item(index, text):
    _ensure_ready()
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


def select_option(selector, value):
    _ensure_ready()
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
    _ensure_ready()
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


def go(url):
    _ensure_ready()
    new_tab(url)
    wait_for_load()
    return status()


def back():
    _ensure_ready()
    js("history.back()")
    wait_for_load()
    return status()
