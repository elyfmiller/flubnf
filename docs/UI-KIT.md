# UI kit: explaining the console without paragraphs

A page of the console should read as headings, labels, values, controls and badges. The explanations still matter, so they move into the interface: a "?" beside the thing it explains, a badge that states a status in a word, a unit beside a number, an empty state with one action. This page is the kit that does it, the rules for choosing a component, and the conventions for a tab's own styles.

The kit is three files, shared by every tab:

| File | Holds |
|---|---|
| `app/ui/templates/_tips.html` | the Jinja macros: `{% import "_tips.html" as tips %}` |
| `app/ui/static/ui-kit.css` | their styles, linked by `base.html` right after `nau.css`; every class starts `uk-` |
| `app/ui/static/tips.js` | tooltip and toggletip behavior, and `window.FluBNFUI` for page scripts |

A tab uses the kit as it is and never restyles a `uk-` class. A component a tab needs and the kit lacks starts as a class with the tab's prefix in the tab's own stylesheet, and is proposed for the kit from there.

## Deciding what to do with a sentence

Every loose explanatory sentence (a `p.hint` under a heading, a `.sub` line, a sentence in a table cell, a paragraph above a form, a legend written out in words) gets one decision:

| Decision | When | With |
|---|---|---|
| **MOVE** | the text explains something the reader may want to know | a "?" beside the thing: `tips.tip`, `tips.label`, `tips.heading`; a `tips.toggletip` when it holds links, a list or several lines |
| **REPLACE** | a UI element can say it without prose | `tips.badge` for a status, `tips.stat` for a number and its unit, `tips.legend` for colors, `tips.empty` for "nothing here yet", `tips.reason_button` for "why is this off", `tips.stepper` for a sequence, `tips.meta` for a line of facts, a placeholder or a unit affix for a field |
| **KEEP** | the user must act on it now: an error, a warning, a blocking problem, a due date | `tips.alert`, one short line, the details in its tip |
| **DELETE** | it repeats what the page already shows | nothing |

The target is at most one short visible line of prose per card, and usually none.

When text moves, every fact, number and rule in it moves word for word: a tip can hold rich text (a call block), so nothing the text said is lost. Ids, names, `data-*` hooks, form field names and anything a script or a test reads stay as they are. The tests read the templates as text: search `app/tests` and `tests` for a sentence before changing it, and change a test only where it pins wording you deliberately changed.

## Components

Each macro whose explainer can be rich text (links, bold, line breaks) takes it as a call block, as `tip` always has:

```jinja
{% call tips.badge("warn", "not archived", id="live-newer") %}Real-time runs for
<span class="wk">{{ live_week }}</span> read target-data.{% endcall %}
```

A plain string argument is escaped; markup built in the template (`{% set t %}...{% endset %}`) or passed from Python as `Markup` is not. Ids belong to the caller and must be unique on the page: a tip's box is `tip-<id>`, a toggletip's panel `tt-<id>`.

### Tip: `tips.tip(id, label, text="")`

The "?" button beside a setting, a heading or a value. The tooltip shows on hover, on keyboard focus and on click or tap; Escape hides it. The button is named "About <label>" and described by the tooltip, so a screen reader reads the explanation on focus. Use it for a sentence or two of plain explanation. A tooltip is never interactive: a link inside one cannot be reached by keyboard, so an explanation with links is a toggletip.

```jinja
{{ tips.tip("archive", "the archive", "Each dot is one week's snapshot as the runs fit it.") }}
```

### Field hint: `tips.label(text, id, tiptext, for_="")`

A form label with its "?" on the same line. A hint under a field (`<p class="hint">` after an input) becomes the label's tip. Short format hints that help while typing ("YYYY-MM-DD", "model name") belong in the field's `placeholder`; a unit belongs beside the field:

```jinja
{{ tips.label("Shard width", "rt-width", "Parallel runners; the default suits this machine.", for_="rt-width-in") }}
<span class="uk-affix"><input type="number" id="rt-width-in" name="width"><span>runners</span></span>
```

### Heading: `tips.heading(text, id="", tiptext="", level=2, after="", aside="", cls="", rich=False, tip_label="")`

A section title with its explainer beside it. It replaces the subtext line under a card's `h2`. The "?" sits after the heading element, not inside it, so the heading's accessible name is the title alone. `after` is markup after the tip (a badge, a count); `aside` is markup pushed to the right edge (an action). `rich=True` makes the explainer a toggletip. The heading gets `id="h-<id>"`. At `level=3` it is a sub-heading inside a card, drawn at one size on every tab; a tab's `cls` sets its spacing only.

```jinja
{{ tips.heading("Run ledger", "st-ledger", "Elapsed is wall time; a dash: recorded before timing existed.",
                after=tips.badge("neutral", ledger | length ~ " runs")) }}
```

Inside a `<summary>` (whose content may not hold a `<div>`), keep the plain `<h2>` and put `tips.tip` after it.

### Toggletip: `tips.toggletip(id, label, text="", title="")`

An "i" button that opens a panel on click (Enter or Space from the keyboard) and keeps it open: for explanations too long or too rich for a tooltip, with links, lists or several lines. The button carries `aria-expanded` and `aria-controls`; the panel is ordinary content (never `role="tooltip"`), so Tab moves from the button into its links. Escape, a click outside or focus leaving it closes it, and Escape returns focus to the button; an Escape that closes a panel or hides a tip goes no further, so the menu around it stays open until a second Escape. A panel taller than the window scrolls inside itself, kept in view. Without script the panel shows, in the flow under its button (so a card never clips it), while focus is inside the toggletip. Put one line per `<span class="uk-tt-line">`; a list needs the toggletip outside any `<p>` (a `<ul>` closes an open `<p>`).

```jinja
{% call tips.toggletip("out-files", "these files", title="Submission files") %}
 <span class="uk-tt-line">Each model's file is named &lt;reference date&gt;-&lt;team&gt;-&lt;model&gt;.csv.</span>
 <span class="uk-tt-line">Rules: <a href="/methods#policies">Methods</a>.</span>
{% endcall %}
```

### Badge: `tips.badge(state, text, tiptext="", id="", icon_name="")`

A status in an icon and a word, never in color alone. `state` is `ok`, `warn`, `error`, `info`, `neutral` or `pending`; each has its own icon shape (check, triangle, octagon, circle, dot, clock), so the states differ in the color-vision mode and in grayscale too. With a tip, the "?" follows the badge, the two held together in one `uk-badge-pair` so a wrapping line never leaves the "?" on its own. It replaces status sentences ("the hub clone is up to date") and `.pill` spans that carry a state. A page script updates one in place with `FluBNFUI.setBadge(el, state, text)`.

```jinja
{{ tips.badge("ok", "all reported") }}
{{ tips.badge("warn", r.unreported | length ~ " not reported", id="nw-badge") }}
```

### Alert: `tips.alert(kind, text, title="", tiptext="", id="", action="", live=none, hidden=False, tip_label="")`

A line the user must act on now: a failure, a blocking problem, a deadline. `kind` is `error`, `warn`, `info` or `ok`. One short line; the explanation goes in its tip; an `action` (a link or a button, as markup) sits at the right. An error is announced as an alert, the other kinds politely (`role="status"`); `live=""` silences a line that is present from the first paint and is not news. It replaces multi-sentence `.banner` paragraphs and `p.warn` lines. `base.html` shows the update notice and the server's notices (the flash) this way. `hidden=True` renders it hidden for a page script to show (`el.hidden = false`); the kit keeps `[hidden]` hidden. The "?" is named from the title (or the line) in lower case; `tip_label` names it where that would read wrong (a long warning). The flash takes its kind from the server (`shared._flash(msg, kind, detail="")`): a refusal warns, a failure is an error, a completed action is ok. Its line is one short sentence with the essential fact first ("Not deleted: a run is using this dataset."); the reason's fine print or the next step goes in `detail`, shown as its tip.

```jinja
{% call tips.alert("warn", "Quit the app fully and reopen.", title="Update pulled.", id="restart") %}
This window still runs build {{ running_sha() }}.{% endcall %}
```

### Empty state: `tips.empty(title, icon_name="folder", action="", tiptext="", id="", compact=False, hidden=False)`

What a card shows before it has content: an icon, one short title, and at most one action that fills it. It replaces "Nothing here yet. Run a forecast first." paragraphs. `compact=True` is a single line for a list inside a card ("No workroots on disk"). `hidden=True` renders it hidden, as for an alert.

```jinja
{{ tips.empty("No forecasts yet", "clock", action='<a class="btn gold" href="/forecast">Run a forecast</a>' | safe) }}
```

### Stats: `tips.stats(cls="", label="")` and `tips.stat(label, value, unit="", tiptext="", id="", state="", after="", tip_label="")`

Labelled values. A sentence that strings facts together ("212 vintages, newest week 2026-09-20, 1,234 rows") becomes one stat per fact, each with its label, its unit and, where needed, its tip. `stats` is the definition list and takes the stats in a call block. `cls` picks the layout: tiles that wrap (default), `uk-stats--kv` (labels left, values right, one row per fact) or `uk-stats--row` (one compact line). `state` colors the value (`ok`, `warn`, `error`); say the state in a word too, with a badge in `after`. `id` lands on the value, for a script that updates it. The "?" is named from the label in lower case; `tip_label` names it where that would read wrong ("relWIS").

```jinja
{% call tips.stats("uk-stats--kv") %}
 {{ tips.stat("Data through", live_week, after=tips.badge("warn", "not archived")) }}
 {{ tips.stat("Vintages", n_vintages, "weeks", "Each archived week's snapshot.", id="dt-nv") }}
{% endcall %}
```

### Reason button: `tips.reason_button(text, id, reason, off=True, cls="", type="", name="", value="", data={}, attrs="", label="")`

A control that is off for a reason. The button is disabled and described by a "?" that states why, instead of a sentence beside it; the "?" takes focus where the disabled button cannot. Hovering the disabled button shows the reason too. `off=False` renders it enabled with the "?" hidden, for a script that switches it: `FluBNFUI.setReason(button, reason)` disables it with that reason, `FluBNFUI.setReason(button, null)` enables it. `data` becomes `data-*` attributes (`{"guard": "console-run"}`); `attrs` is raw markup for anything else.

```jinja
{{ tips.reason_button("Apply the Oracle step", "sb-oracle-why", oracle_gate.reason,
                      off=not oracle_gate.ok, cls="gold") }}
```

### Stepper: `tips.stepper(steps, current=0, label="Steps", id="steps", vertical=False)`

The steps of a flow as numbered marks joined by a line. `steps` is a list of dicts: `label`, and optionally `href`, `tip`, `tip_label` (names the "?" where the label alone would repeat a nav link's name: "the Data step"), `meta` (a short visible caption, used sparingly) and `state` (`done`, `current`, `todo`, `error`). Without a `state`, steps follow `current` (1-based: earlier steps done, that one current); `current=0` is a plain numbered guide. Each state is spoken as well as drawn, and the current step carries `aria-current="step"`. A horizontal stepper stacks itself when its container is under 40rem, rather than wrap a step onto a row of its own; a label and its "?" never part. `vertical=True` always stacks.

```jinja
{{ tips.stepper([{"label": "Data", "href": "/data", "tip": "confirm the feed is current"},
                 {"label": "Forecast", "href": "/forecast", "tip": "pick a date, run the models"},
                 {"label": "Output", "href": "/output", "tip": "submission files and the report"}],
                vertical=True, label="Start here", id="hm-start") }}
```

### Progress: `tips.progress(label, value=none, max=100, text="", id="progress")`

A labelled bar with a readout ("3 of 10 weeks") in place of a sentence about progress. `value=none` is work without an honest denominator: the bar slides (and holds still under reduced motion).

```jinja
{{ tips.progress("Replay", s.done, s.total, s.done ~ " of " ~ s.total ~ " weeks", id="rt-prog-" ~ s.name) }}
```

### Legend: `tips.legend(items, label="Legend", id="")`

Chart legend chips, a swatch and a word each, instead of a sentence that names colors ("the dotted ink line is what was later reported"). Items are `(color, text)`, `(color, text, shape)` or dicts `{color, text, shape, tip}`. `color` is a token (`var(--gold)`) or a palette value the server passes; `shape` is `box` (default), `line`, `dash`, `dotted`, `point`, `ring` or `band`, so a line style can be named without color.

```jinja
{{ tips.legend([("var(--gold)", "Oracle SIHRS", "line"), ("var(--official)", "FluSight ensemble", "dash"),
                {"color": "var(--ink)", "text": "reported later", "shape": "dotted",
                 "tip": "What was later reported, from the newest archived data."}], id="fc-lg") }}
```

### Fold: `tips.fold(summary, id="", open=False, after="", cls="")`

Progressive disclosure for detail the reader asks for: a closed fold whose summary says what is inside ("3 missing locations") and a list in the body (a call block). `after` is markup in the summary (a badge). It replaces lists printed under a row, and paragraphs of caveats that a tip would make too long.

```jinja
{% call tips.fold(c.missing | length ~ " missing", id="cov-" ~ loop.index) %}
<ul>{% for loc, why in c.missing %}<li><b>{{ loc }}</b>: {{ why }}</li>{% endfor %}</ul>
{% endcall %}
```

### Meta row: `tips.meta(items, label="")`

A row of facts, each an icon and a value, instead of a "run 2026-09-20 · on dataset X · 5.4 MB" sentence. Items are `(icon, text)`, `(icon, text, label)` or plain text; `label` is spoken before the text where the icon alone names the fact.

```jinja
{{ tips.meta([("calendar", w.when, "Run"), ("folder", w.size_h, "Size"), ("clock", r.elapsed_s | hms, "Wall time")]) }}
```

### Tag: `tips.tag(text, cls="")`

A kind or a unit in a word ("Mechanistic", "relWIS", "population"): an outlined, muted pill with no icon, because it states no status. A status is a badge; a count beside a heading is a neutral badge ("3 entries").

```jinja
{{ tips.heading("Measured performance", "home-perf", tip, after=tips.tag("relWIS")) }}
```

### Name chip: `tips.namechip(text, id, tiptext="", tip_label="")`

The short name of the formula or figure beside it, with its reading in the "?" the chip holds: an equation's caption becomes a named chip. Put the formula and its chip in a `<p class="uk-figline">`, a centered line under a figure (it also centers a badge about the figure, such as "illustrative values").

```jinja
<p class="uk-figline"><span class="math">...</span>
 {{ tips.namechip("Seasonal forcing", "hm-eq-forcing", "The curve the filter bends each week.") }}</p>
```

### Segmented switch: `<div class="uk-seg" role="group" aria-label="...">`

One choice among a few, joined in one outline: the chart's view, the map's model, a horizon. The children are buttons whose `aria-pressed` says which is on (a script flips it), or links with the current choice a `<span aria-current="true">`; the choice is filled as a primary button is. It has no macro because its buttons are the page's own (ids, handlers); the kit only draws them.

```jinja
<div class="uk-seg" role="group" aria-label="Chart view">
 <button type="button" id="vb-mode-raw" aria-pressed="true">full series</button>
 <button type="button" id="vb-mode-season" aria-pressed="false">season over season</button>
</div>
```

### Icons: `tips.icon(name, label="", cls="")` and `tips.icon_tip(id, label, name, text="", state="")`

Inline SVG icons in the text's color, 1em square: `info`, `warning`, `error`, `check`, `clock`, `download`, `upload`, `folder`, `external`, `lock`, `calendar`, `refresh`, `dot`, `close`. An icon is decorative (`aria-hidden`) unless given a `label`, which makes it an image with that name. Its drawing attributes are on the SVG itself, so it renders without `ui-kit.css` too. `icon_tip` is a tip whose button is an icon instead of "?": a warning mark whose tooltip names what to check, a lock whose tooltip says why something is protected; `state` colors it (`ok`, `warn`, `error`, `info`, `muted`). For an icon beside text, `<span class="uk-c-warn">` (or `-ok`, `-error`, `-info`, `-muted`) colors it with the state token.

```jinja
<a class="btn" href="{{ url }}" download>{{ tips.icon("download") }} Download</a>
{{ tips.icon_tip("st-protected", "protected trees", "lock", "The sealed record and the hub clone cannot be deleted here.", state="muted") }}
```

## Page scripts: `window.FluBNFUI`

`tips.js` is loaded deferred at the end of every page, so call these from event handlers or after `DOMContentLoaded`, not while the page parses:

| Call | Does |
|---|---|
| `FluBNFUI.icon(name, label)` | an icon's markup (string) |
| `FluBNFUI.badge(state, text)` | a badge's markup (string); the text is escaped |
| `FluBNFUI.setBadge(el, state, text)` | turns an existing badge into another state and word |
| `FluBNFUI.setReason(button, reason)` | disables a reason button with that reason, or enables it (`null`) |
| `FluBNFUI.tip(id, label, text)` | a tip's markup (`tips.tip`); the text is escaped |
| `FluBNFUI.alert(kind, text, title, tip, live)` | an alert's markup (`tips.alert`); `tip` is `[id, text]` for its "?"; `live` the role (by kind when left out, `''` for none inside a live region) |
| `FluBNFUI.progress(label, value, max, text, id)` | a progress bar's markup (`tips.progress`); `value` null slides |
| `FluBNFUI.setProgress(el, value, max, text)` | moves an existing bar: a number fills it, `null` slides it, `undefined` leaves the fill; `text` is the readout |
| `FluBNFUI.esc(text)` | HTML-escapes a string |

A script that fills a box with kit components builds them with these, never by copying the markup, so a change to a component reaches every page.

Static scripts stay ES5 (no arrow functions, `let`, `const` or template strings).

## Tab stylesheets

Each tab's own rules live in `app/ui/static/tabs/<tab>.css` (`home`, `data`, `forecast`, `output`, `retro`, `storage`, `models`, `methods`, `sandbox`). A page loads its tab's sheet from its `{% block head %}`, so it follows `nau.css` and `ui-kit.css`:

```jinja
{% block head %}<link rel="stylesheet" href="/static/tabs/data.css">{% endblock %}
```

A partial that renders on another tab's page (the upload box is on Data, Forecast and Retrospective) links its owner's sheet itself; a `<link>` in the body is valid and the browser loads the file once. So every rule in a tab sheet is scoped by the tab's class prefix (`hm-`, `dt-`, `fc-`, `out-`, `rt-`, `st-`, `md-`, `mt-`, `sb-`) and never styles a bare element or a kit class. A sheet a tab does not need is deleted. `nau.css` keeps the tokens, the themes and the shared layout; a tab edits it only to delete rules that only it used.

Colors come only from the `nau.css` tokens (`var(--ink)`, `var(--ok)`, a `color-mix()` of two tokens; the table of tokens is under "Display settings" in [app/ui/README.md](../app/ui/README.md)), never a literal, so a rule works in every theme, in high contrast and in the color-vision mode; `app/tests/test_ui_kit.py` holds the tab sheets and the kit to that. Sizes are in `rem`, `em` and the type tokens (`--fs-label`, `--fs-hint`), so they follow the text size, which runs from 80% to 160% of the root.

## Accessibility contract

- Every tip, toggletip and reason is reachable by keyboard and named for a screen reader; Escape closes what is open.
- Status is never color alone: a badge has an icon shape and a word, a stepper speaks each step's state, a legend names each swatch.
- Hit targets: the "?" and "i" buttons are drawn at 1.1rem, and their clickable ring reaches 24px at the standard text size.
- Measured in `app/tests/test_ui_kit.py` in every theme, with and without high contrast and the color-vision mode: a badge's word on the card, an alert's text on its tint, and the current step's number hold 4.5:1; an alert's icon holds 3:1.

## Where the kit does not reach

- The weekly report (`app/core/report_v2.py`) is a standalone file that carries the kit inside it: `app/core/html_page.py` inlines nau.css's tip rules and `ui-kit.css` (`kit_css`), `tips.js` (`kit_js`), the DM Sans faces and the theme marks, and renders the `_tips.html` macros from Python (`kit_macros`). A change to any of those files makes stored reports stale, so they are rebuilt from their inputs bundle when next served.
- The season report and the public site are standalone pages that load neither `ui-kit.css` nor `tips.js`. The season report inlines `static/player.js` verbatim and `app/core/runs.py`'s settings renderer feeds both reports, so markup that renderer writes must read without the kit.
- The public site renders `methods.html`'s content block through the console's Jinja env with only `diagrams.html` imported (`app/core/site_build.py` `harvest_methods`), and reads the first `class="perf"` table of `home.html` (`harvest_placement`). Import `_tips.html` inside Methods' content block, keep that table's markup, and run `app/tests/test_site_build.py` after changing either page.
