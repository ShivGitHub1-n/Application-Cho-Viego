# Jobs browser checklist

Run the offline harness before any live-source or browser work. It uses the
real Jobs frontend with an injected deterministic façade and never calls a
provider, employer site, Playwright, Gemini, or an external API.

## Launch command

```powershell
cd "$HOME\OneDrive\Desktop\Application-Cho-Viego"
$env:PYTHONPATH = (Resolve-Path ".\src").Path
$env:Path = "$env:ProgramFiles\LibreOffice\program;$env:Path"

& ".\.venv\Scripts\python.exe" -m streamlit run `
  ".\tests\streamlit_apps\jobs_test_app.py"
```

Use the `Offline scenario` selector to exercise visible grades, excluded
results, partial and total source failures, profile/preferences empty states,
saved availability, preference suggestions, tailoring handoff, and long
content. The harness uses Streamlit wide layout so it exercises the same
production page width boundary as the real app. Toggle Streamlit between light
and dark themes and resize the browser to a narrow mobile width.

The harness supplies deterministic example jobs through the production Jobs
frontend. The real application uses persisted profile and feed data, so an
empty real feed is expected until a successful refresh has persisted results.

## Visual remediation checks

At 1440 pixels or wider:

- The sidebar is compact and shows Resume Tailor, its evidence-backed subtitle, Navigation, Jobs, Resume Tailor, Cover letters, Master profile, and active profile information. In the harness, Offline scenario is subordinate development UI.
- Application navigation uses native text buttons without visible radio circles. Jobs sections are compact text tabs with red active text/underline and one divider, not outlined pills.
- The main product header reads Resume Tailor with the evidence-backed subtitle, followed by the Job discovery header; neither heading is clipped.
- The Jobs header has title, subtitle, profile selector, refresh action, last-refresh state, and divider hierarchy.
- The main workspace is aligned to a responsive approximately 1120px content width without large centered margins.
- Tailored and Explore use a roughly one-third recommendation list and two-thirds detail panel.
- Recommendation cards are single-border surfaces: title/meta on the left, grade on the right, eligibility/provisional lower-left, and compact View details/Selected lower-right.
- No separate `Select <job>` button appears below any card.
- The selected card uses the primary border, burgundy/red-tinted surface, and written Selected state; it has no giant Selected button.
- Fit bars are prominent red/inactive semantic bars with written grade and alignment copy.
- The detail area is one coherent bordered panel with status pills and one grouped action row; Open official posting is the red primary action.
- Saved uses the same card/detail treatment and grouped actions.
- Preferences uses grouped bordered panels across the desktop width.

In dark mode:

- Filled fit bars use the primary accent and remain prominent.
- Unfilled bars, card borders, selected surfaces, and muted text remain readable.

In light mode:

- The same hierarchy and spacing remain intact.
- Cards, borders, selected state, warning state, and eligibility remain distinct.

At mobile width:

- The sidebar is replaced by the compact Resume Tailor top bar and menu affordance.
- Feed and detail become one column at a practical breakpoint.
- Selected details expand inline; no squeezed right panel remains.
- Actions wrap or stack without horizontal overflow.
- Filter chips wrap, long content grows naturally, and fit bars remain inside cards.

For empty feeds:

- The header, section navigation, and metadata hierarchy remain present.
- One coherent empty-state card explains the condition and offers one clear action.
- No empty selected-job detail prompt is shown.

| Scenario | Viewport | Expected behavior | Actual result | Date | Commit | Screenshot |
| --- | --- | --- | --- | --- | --- | --- |
| visible-grades | desktop | Excellent/Good/Weak, eligibility, provisional, evidence, gaps, no numeric score, wide split layout, integrated card actions |  |  | 32cd52a baseline + visual remediation |  |
| excluded-results | desktop/mobile | Don’t Match absent until `Show excluded jobs (N)` is activated |  |  |  |  |
| partial-source-warning | desktop | Valid jobs remain visible with a non-destructive warning |  |  |  |  |
| all-sources-failure | desktop | Failure is explicit and stale content is not represented as success |  |  |  |  |
| no-reviewed-profile | desktop/mobile | Clear profile guidance and no feed controls |  |  |  |  |
| no-confirmed-preferences | desktop | Preferences guidance; no Tailored refresh as if confirmed |  |  |  |  |
| saved-unavailable | desktop/mobile | Immutable snapshot remains visible with unavailable status |  |  |  |  |
| preference-suggestion | desktop | Suggestion rationale is visible and confirmation is explicit |  |  |  |  |
| tailoring-handoff | desktop | Resume Tailor receives title/description; no generation starts |  |  |  |  |
| long-content | desktop/mobile | Titles, locations, evidence, and gaps wrap without clipping or horizontal overflow |  |  |  |  |

Final manual browser validation was completed by the user in the populated
offline harness and the real application. The accepted result includes
dark/light visual treatment, responsive stacking, full-card selection,
selected-hover behavior, keyboard selection, official-link navigation, detail
actions, all four Jobs sections, saved jobs, eligibility indicators, and safe
Tailor routing. Keep this checklist as the repeatable smoke-test record for
future changes; any code or visual change requires repeating the relevant
checks before approval.

## Current acceptance record

| Surface | Result | Evidence owner |
| --- | --- | --- |
| Populated offline harness | Accepted after manual browser validation | User |
| Real application routing and persisted-data path | Accepted after manual browser validation | User |
| Dark/light Jobs styling and responsive interaction | Accepted for Batch 4 handoff | User |
| Batch 4 independent review of the complete diff | Accepted | Batch 4 review record |
| Batch 5 independent review-only pass | Pending | Next Codex pass |
