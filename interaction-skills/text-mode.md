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
