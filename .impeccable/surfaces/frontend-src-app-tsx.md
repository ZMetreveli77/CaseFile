---
version: 1
slug: "frontend-src-app-tsx"
primary_target: "frontend/src/App.tsx"
related_targets: []
---

# CaseFile app UI

Scope: the whole React app (Ask view, Documents view, source drawer). Mode: Operate.
Audience and job: an analyst (and an assignment reviewer) asks hard questions over 66k documents and must see
how the answer was reached. Constraints: code simple enough to explain live; Render cold starts; LLM quota errors.
Chosen after three rounds: the category standard ("Standard+"), light and dark both designed.
Memorable moment: the investigation log filling in live above the answer, then the answer landing with its
citations and any conflict laid out side by side.

## Direction contract

THESIS: A familiar research-assistant layout that never hides its work: the investigation steps are always on
screen above the answer. Refuses the chat-with-PDF default where the reasoning is a hidden spinner.

OWN-WORLD: Neutral ground (white / near-black #111418) with one sidebar tone; Onest for all text; three meaning
colours only: blue = cited (chips, log dots), amber = conflict (panel), grey = not cited / declined; green dot
for system ready. Hairline 1px borders, 10px radii, no shadows beyond the ask box.

STORY: The visitor sees a ready corpus, clicks a sample question or types one, watches each search step land,
reads a cited answer, opens a source to verify it, and sees conflicts and refusals stated plainly.

FIRST VIEWPORT: 272px sidebar (brand, Ask/Documents nav, three sample questions labelled by outcome, status dot
at the foot). Main column 760px centred: question bubble right-aligned, Investigation panel (step list with
result counts and total time), answer at 17px with numbered citation chips, conflict panel with the two values
side by side, source cards. Ask box pinned to the bottom of the column; primary action "Investigate".

FORM: Category standard (canon), chosen by the user over rolled directions; seed: seed:82c6ceb3697c11a5

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict,
DESIGN.md, and every shipping raster carrying its provenance
