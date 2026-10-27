---
name: CaseFile
description: An AI investigation engine that cites its evidence.
colors:
  background: "#ffffff"
  sidebar: "#f6f7f9"
  surface: "#ffffff"
  raised: "#ffffff"
  text: "#141a21"
  muted: "#5b6572"
  line: "#e3e6ea"
  line-strong: "#c9ced5"
  cited: "#2457c5"
  cited-soft: "#e8effc"
  conflict: "#9a5300"
  conflict-soft: "#fdf3e5"
  danger: "#b42318"
  danger-soft: "#fdecea"
  danger-text: "#ffffff"
  ready: "#1f8a4c"
  button: "#141a21"
  button-text: "#ffffff"
  focus: "#2457c5"
  selection: "#cfdcf7"
  background-dark: "#111418"
  sidebar-dark: "#171b21"
  surface-dark: "#171b21"
  raised-dark: "#1d2229"
  text-dark: "#e8ebef"
  muted-dark: "#a1aab5"
  line-dark: "#2a3039"
  line-strong-dark: "#3a414c"
  cited-dark: "#8fb3ff"
  cited-soft-dark: "#1d2a45"
  conflict-dark: "#f0b35c"
  conflict-soft-dark: "#2c2416"
  danger-dark: "#ff8a80"
  danger-soft-dark: "#3a1d1b"
  danger-text-dark: "#111418"
  ready-dark: "#4cc38a"
  button-dark: "#e8ebef"
  button-text-dark: "#111418"
  focus-dark: "#8fb3ff"
  selection-dark: "#2c3f66"
typography:
  display:
    fontFamily: "Onest, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "28px"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "Onest, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "26px"
    fontWeight: 700
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Onest, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "20px"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  answer:
    fontFamily: "Onest, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "17px"
    fontWeight: 400
    lineHeight: 1.75
  body:
    fontFamily: "Onest, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.55
  body-small:
    fontFamily: "Onest, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.4
  label:
    fontFamily: "Onest, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "13px"
    fontWeight: 600
    lineHeight: 1.4
  citation:
    fontFamily: "Onest, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "12px"
    fontWeight: 600
    fontFeature: "tnum"
  mono:
    fontFamily: "ui-monospace, SF Mono, Menlo, monospace"
    fontSize: "0.86em"
rounded:
  chip: "4px"
  small: "6px"
  button: "9px"
  panel: "10px"
  bubble: "14px"
  dot: "50%"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
  exchange: "36px"
  page-top: "40px"
components:
  button-primary:
    backgroundColor: "{colors.button}"
    textColor: "{colors.button-text}"
    typography: "{typography.label}"
    rounded: "{rounded.button}"
    padding: "0 16px"
    height: "38px"
  button-secondary:
    backgroundColor: "transparent"
    textColor: "{colors.text}"
    rounded: "{rounded.button}"
    padding: "0 16px"
    height: "38px"
  button-danger:
    backgroundColor: "{colors.danger}"
    textColor: "{colors.danger-text}"  # dark text on the lighter dark-mode red keeps 8:1 contrast
    rounded: "{rounded.button}"
    padding: "0 12px"
    height: "32px"
  button-small:
    rounded: "{rounded.button}"
    padding: "0 12px"
    height: "32px"
  icon-button:
    backgroundColor: "transparent"
    textColor: "{colors.muted}"
    rounded: "{rounded.small}"
    size: "34px"
  icon-button-hover:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.text}"
  nav-item:
    backgroundColor: "transparent"
    textColor: "{colors.muted}"
    rounded: "{rounded.small}"
    padding: "8px 10px"
  nav-item-current:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.text}"
  citation-chip:
    backgroundColor: "{colors.cited-soft}"
    textColor: "{colors.cited}"
    typography: "{typography.citation}"
    rounded: "{rounded.chip}"
    padding: "0 5px"
    height: "18px"
  citation-chip-hover:
    backgroundColor: "{colors.cited}"
    textColor: "{colors.background}"
  ask-box:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.bubble}"
    padding: "10px 10px 10px 16px"
  question-bubble:
    backgroundColor: "{colors.sidebar}"
    rounded: "{rounded.bubble}"
    padding: "12px 16px"
  investigation-log:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.panel}"
    padding: "12px 16px"
  conflict-panel:
    backgroundColor: "{colors.conflict-soft}"
    textColor: "{colors.text}"
    rounded: "{rounded.panel}"
    padding: "14px 16px"
  source-card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.panel}"
    padding: "12px 14px"
  declined-panel:
    backgroundColor: "transparent"
    rounded: "{rounded.panel}"
    padding: "16px 18px"
  failure-panel:
    backgroundColor: "{colors.danger-soft}"
    textColor: "{colors.danger}"
    rounded: "{rounded.panel}"
    padding: "14px 16px"
  source-drawer:
    backgroundColor: "{colors.surface}"
    padding: "18px 24px 32px"
    width: "480px"
---

# Design System: CaseFile

## Overview

**Creative North Star: "The Open Case File"**

CaseFile wears the familiar research-assistant layout on purpose: a quiet sidebar on the left, one centred reading column, an ask box pinned to the bottom. Nothing about the frame is themed. What sets it apart is that the work is never hidden: every investigation shows its log of searches and reads above the answer, every claim carries a numbered citation chip, conflicts and refusals are stated in their own plainly marked panels, and any source opens in a drawer beside the answer for checking.

The ground is neutral (white in light, near-black in dark) with one slightly tinted sidebar tone. Colour is rationed: each hue has exactly one meaning, so a reader learns the vocabulary in one answer and can scan the next one by colour alone. Depth comes from 1px hairlines and a single tonal step, not from shadows. Onest carries every word; hierarchy comes from size and weight, never from a second face.

Light and dark are equal citizens. Both palettes are full token sets; the page follows the system setting until the visitor uses the toggle, and that choice is saved and applied before first paint. The code is plain CSS custom properties and React with no UI library, deliberately simple enough for its author to explain line by line.

**Key Characteristics:**
- Familiar sidebar + 760px column layout, executed cleanly rather than themed.
- Every colour is a meaning: blue cited, amber conflict, grey not cited / declined, green ready, red error or destructive.
- The investigation log always sits above the answer it produced.
- Hairline 1px borders and 10px panel radii; only the ask box and the source drawer cast shadows.
- One typeface (Onest) at a 13 / 15 / 17 / 20 / 26 / 28px ramp.
- Light and dark both first-class, from one set of token names.

## Colors

A neutral grey-blue ground with five rationed signal hues, each holding one meaning in both themes.

### Primary
- **Evidence Blue** (cited / cited-dark): the colour of a claim backed by a source. Citation chip text (on Cited Wash), source-card numbers, source-card hover border, investigation-log dots for completed steps, links, the text caret and the focus ring (focus shares the cited value). Also the faint background of upload status messages.
- **Cited Wash** (cited-soft / cited-soft-dark): the chip background behind citation numbers and the upload message panel.

### Secondary
- **Conflict Amber** (conflict / conflict-dark): sources disagree. Conflict panel title and the log dot on the citation-check row when a conflict was found. Never used for warnings, emphasis or decoration.
- **Conflict Wash** (conflict-soft / conflict-soft-dark): the conflict panel's fill.

### Tertiary
- **Ready Green** (ready / ready-dark): the status dot only, when the backend is up and indexed.
- **Failure Red** (danger / danger-dark) with **Failure Wash** (danger-soft / danger-soft-dark): errors and destructive actions only: the failure panel, failed log steps, the offline / degraded status dot, error text, the delete-confirm button, and the trash icon's hover.
- **Not ready yet** uses Slate (muted / muted-dark), pulsing: the status dot while connecting or while the free-tier server wakes. Amber is never used for it, so amber only ever means conflict.

### Neutral
- **Paper** (background) / **Night Ink** (background-dark): the page ground.
- **Sidebar Mist** (sidebar) / **Sidebar Night** (sidebar-dark): the one tonal step; sidebar, question bubble, table header row.
- **Surface** (surface, raised and their dark pair): cards, log, ask box, drawer; raised is the hover and current-nav fill (one step lighter than surface in dark).
- **Ink** (text) / **Chalk** (text-dark): body text; also the primary button fill, inverted per theme (button / button-text).
- **Slate** (muted / muted-dark): secondary text, uncited passages, declined log dot, pending log dot, meta counts. Grey means "not cited / declined / not yet", never a disabled-only tint.
- **Hairline** (line) and **Hairline Strong** (line-strong): 1px borders; strong for the ask box, drawer edge, secondary-button ring and the dashed declined panel.
- **Selection** (selection / selection-dark): text selection, a pale Evidence Blue.

### Named Rules
**The One Meaning Rule.** Each signal hue means one thing everywhere: blue = cited, amber = conflict, grey = not cited / declined, green = ready, red = error or destructive. If a new element needs a colour that is not one of these meanings, it stays neutral.

**The Paired Token Rule.** Every colour exists as a light value and a dark value under the same token name. Never write a colour that only works in one theme; never hard-code a hex in a component.

## Typography

**Display Font:** Onest (with system-ui, -apple-system, Segoe UI, sans-serif)
**Body Font:** Onest
**Label/Mono Font:** ui-monospace, SF Mono, Menlo for inline code only

**Character:** One friendly, slightly geometric sans for everything. Hierarchy is size and weight with tight negative tracking on the larger headings; counts and timings use tabular figures so they do not jitter as the log fills in.

### Hierarchy
- **Display** (700, 28px, 1.25, -0.02em, balanced wrapping): the empty-state intro title on the Ask view.
- **Headline** (700, 26px, -0.02em): page titles such as Documents.
- **Title** (700, 20px, 1.3, -0.01em): source drawer title. The brand wordmark is a sibling at 700, 18px, -0.01em.
- **Answer** (400, 17px, 1.75, max 70ch): answer text and, at 16px / 1.75, the drawer passage. The reading text is deliberately larger than the interface text.
- **Body** (400, 15px, 1.55): base text, question bubble. 14px for log rows, source-card titles (600), conflict sub-text, tables and sample questions.
- **Label** (600, 13px): sidebar section heading, table headers, small buttons; 13px at 400 in Slate for meta lines, hints and status. 12.5px for sample-question outcomes.
- **Citation** (600, 12px, tabular figures): the numbered chips.

### Named Rules
**The One Face Rule.** Onest is the only typeface; monospace appears only inside inline code. Do not introduce a display face.

**The Steady Numbers Rule.** Any count, timing or citation number uses tabular figures (`font-variant-numeric: tabular-nums`).

## Layout

A two-column grid: a fixed 272px sidebar and a scrolling main area. The Ask view centres a 760px column (`min(760px, 100% - 48px)`); the Documents view widens to 1040px for its table. The thread starts 40px from the top, exchanges are separated by a hairline with 36px above and below, and the ask box docks to the bottom of the column with a 12px fade from transparent to the page ground so the thread scrolls beneath it. The empty-state intro sits 12vh down, capped at 620px.

Spacing runs on a small, tight rhythm: 4 / 8 / 12 / 16 / 24px for gaps and padding, 36–40px between major blocks. Source cards flow in an auto-fill grid with a 220px minimum and a 10px gap.

The source passage opens in a fixed right-hand drawer, `min(480px, 100%)` wide, sliding in over the content rather than reflowing it; on phones it is full width.

Under 860px the layout becomes a single column: the sidebar turns into a top bar with a bottom hairline, nav items sit in a row, sample questions become a horizontal scrolling strip of bordered cards (240px min, 80% max), and the samples are hidden entirely on the Documents tab. The column narrows to `100% - 32px`, the intro loses its top offset, and the documents table drops its third column with the action cell shrinking to its icons.

### Named Rules
**The Work Above The Answer Rule.** The investigation log is always rendered above the answer it produced, open by default, and its header counts by kind ("2 searches · 1 read · 1.2 s") so the summary matches the rows beneath it.

## Elevation & Depth

Flat by default. Depth is a 1px hairline plus one tonal step (sidebar tone against the page ground; raised against surface in dark). Exactly two elements cast shadows, both because they float over content: the docked ask box and the source drawer. Selected nav items use a 1px ring drawn as a zero-blur shadow, which reads as a hairline, not as lift.

### Shadow Vocabulary
- **Ask lift** (`box-shadow: 0 8px 24px -12px rgba(20, 26, 33, 0.18)`; dark `rgba(0, 0, 0, 0.6)`): the docked ask box, separating it from the thread scrolling underneath.
- **Drawer edge** (`box-shadow: -16px 0 40px -24px rgba(0, 0, 0, 0.35)`): the left edge of the source drawer.
- **Hairline ring** (`box-shadow: 0 0 0 1px var(--line)` or `inset 0 0 0 1px var(--line-strong)`): current nav item and secondary button outline; a border, not elevation.

### Named Rules
**The Floating Only Rule.** A shadow is allowed only on something that floats over scrolling content (the ask dock, the drawer). Panels, cards and the log sit flat on hairlines.

## Shapes

Gently rounded, never pill-shaped. Panels (log, conflict, declined, failure, source cards, table wrapper) use 10px; buttons 9px; nav items, icon buttons and focus outlines 6px; citation chips a tight 4px; the conversational pieces (question bubble and ask box) a softer 14px. Status and log dots are 8px circles. Borders are always 1px; the declined panel is the only dashed border, marking "no answer" as an absence rather than a result.

## Components

### Buttons
- **Shape:** gently rounded (9px), 38px tall, 600 weight at 14px, icon + label with an 8px gap.
- **Primary:** Ink fill with white label in light, inverted to Chalk with Night Ink label in dark (button / button-text). One per view: "Investigate", "Upload".
- **Hover / Focus:** hover drops opacity to 0.88 over 150ms; disabled is 0.45 opacity with a not-allowed cursor. Focus is the global 2px Evidence Blue outline offset 2px.
- **Secondary:** transparent with an inset 1px Hairline Strong ring and text colour; used for Try again, Cancel, Load more.
- **Danger:** Failure Red fill, used only as the confirm step of a two-step inline delete (32px small size).
- **Icon button:** 34px square, 6px radius, Slate icon; hover fills raised and turns text colour. The danger variant hovers to Failure Wash with Failure Red.
- **Link button:** Slate, underlined (3px offset), for uncited passage titles.

### Chips
- **Citation chip:** a small inline number (12px / 600, tabular) on Cited Wash, 4px radius, 18px tall, raised 2px off the baseline. Hover inverts to Evidence Blue fill with page-ground text. Each chip opens its source in the drawer; it carries an aria-label with the source number and title.

### Cards / Containers
- **Corner Style:** 10px.
- **Background:** surface on the page ground; the conflict and failure panels use their washes instead of a border.
- **Shadow Strategy:** none (see Elevation & Depth).
- **Border:** 1px Hairline; source cards turn their border Evidence Blue on hover (150ms).
- **Internal Padding:** 12–16px.
- **Source card:** citation number in Evidence Blue beside a 600-weight title and a two-line clamped excerpt of the passage in Slate; the whole card is a button that opens the drawer.

### Inputs / Fields
- **Ask box:** a 14px-radius surface with a 1px Hairline Strong border and the Ask lift shadow; the textarea inside is borderless, grows with content up to 160px, and the primary button sits at its bottom-right. Placeholder in Slate.
- **Focus:** the global focus ring; the caret is Evidence Blue.

### Navigation
- **Sidebar:** brand wordmark (700, 18px) with the theme toggle icon button beside it, then the Ask / Documents nav (500 weight, Slate, 8px 10px padding, 6px radius). The current page gets the raised fill, text colour and a 1px hairline ring. Below: a "Try a question" heading and three sample questions, each with its outcome line in Slate. The connection status line sits at the foot.
- **Mobile:** becomes a top bar; nav in a row; samples become a horizontal strip, hidden on Documents.

### Investigation Log (signature)
A bordered 10px panel built on a native disclosure, open by default. The summary row reads "Investigation" on the left and the counts by kind with total time in Slate tabular figures on the right. Each row is an 8px dot, a description, and a right-aligned Slate result count. Dots: Evidence Blue for completed steps, pulsing Slate while pending, Slate for the declined row, Conflict Amber on the citation-check row when a conflict was found, Failure Red for a failed step (whose result text also turns red). New rows rise 4px and fade in over 420ms on the ease-out curve.

### Conflict Panel (signature)
A Conflict Wash panel without a border: a 14px / 600 "Sources conflict" title in Conflict Amber, then the backend's description followed by "Between sources" in Slate and the numbered citation chips linking to each conflicting source. It does not show the two values side by side, because the backend's conflict record carries only a description and citations; the source cards beneath carry a two-line excerpt of each passage instead.

### Declined Panel
A dashed Hairline Strong border with no fill: a 16px / 600 "Not enough evidence to answer" heading, the reason, and a Slate line stating how many searches ran and passages were read.

### Failure Panel
Failure Wash with Failure Red text, the headline at 500, an optional disclosure for technical detail, and a secondary "Try again" button on the right.

### Status Indicator
An 8px dot and a 13px Slate line at the sidebar foot: Ready Green when ready (with the indexed document count), pulsing Slate while connecting or waking, Failure Red when degraded or offline.

### Source Drawer
A fixed right-hand panel (480px, full width on phones) on surface with a 1px Hairline Strong left edge and the Drawer edge shadow, sliding in 24px over 320ms. Title at 20px / 700, a Slate meta line, then the passage at 16px / 1.75 with preserved line breaks, and a close icon button that receives focus.

### Documents Table
A 10px hairline-bordered wrapper around a full-width table; header row on Sidebar Mist at 13px / 600 Slate; rows separated by hairlines. The action cell has a fixed width so the two-step delete confirm (Delete in Failure Red + Cancel secondary) replaces the icons inline without shifting columns. There is no modal dialog.

## Do's and Don'ts

### Do:
- **Do** take every colour from the custom properties so both themes resolve from the same token name.
- **Do** keep each signal hue to its one meaning: blue cited, amber conflict, grey not cited / declined, green ready, red error or destructive.
- **Do** keep the investigation log above the answer, open by default, with counts by kind that match its rows.
- **Do** use 1px hairlines and 10px radii for panels and cards; 14px only for the question bubble and ask box.
- **Do** use tabular figures for every count, timing and citation number.
- **Do** confirm destructive actions inline in two steps (icon, then Delete / Cancel) rather than in a dialog.
- **Do** open source passages in the right-hand drawer, full width under 860px.
- **Do** honour reduced motion: all animation and transitions switch off under `prefers-reduced-motion`.
- **Do** keep the styling plain CSS with React only, simple enough to explain live.

### Don't:
- **Don't** use any signal colour (blue, amber, green, red) for decoration, emphasis or branding.
- **Don't** add shadows to panels, cards or the log; shadows are for the ask dock and the drawer only.
- **Don't** introduce a second typeface or a UI component library.
- **Don't** hide the reasoning behind a spinner; pending work shows as a pulsing grey row in the log.
- **Don't** write a colour that exists in only one theme.
