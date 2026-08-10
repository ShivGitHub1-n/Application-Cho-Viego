# Batch 4 Jobs UI retrospective

Date: 2026-07-31
Status: manually accepted by the user; final independent review APPROVED; merged in the current baseline.

## Executive summary

Batch 4 delivered a dedicated Jobs workspace inside the existing Streamlit
application. It preserved the domain evaluator, feed ordering, provider
boundaries, persistence, Gemini, resume generation, cover letters, and DOCX
rendering while adding a typed page façade, four Jobs sections, a deterministic
offline harness, and browser-oriented interaction coverage. The final manual
browser pass accepted the populated harness and real application, and the final
independent review returned APPROVED with zero blocking findings.

## Original goals and delivered architecture

The goal was a complete Jobs experience: Tailored for you, Explore sectors,
Saved, Preferences, reviewed-profile selection, refresh, excluded results,
immutable saved snapshots, availability checks, safe tailoring handoff, and
responsive dark/light presentation.

The application layer is in `experience.py`, `profile_queries.py`, and
`handoff.py`. The frontend is split among `jobs_page.py`, `job_feed_view.py`,
`job_preferences_view.py`, `saved_jobs_view.py`, `jobs_styles.py`, and the
shared `app_shell.py`. The offline harness injects deterministic façade data
into the same production frontend; the real app uses persisted data.

The UI preserves exact grades Excellent, Good, Weak, and Don’t Match
(`dont_match`), separate Eligible/Unknown/Ineligible eligibility, independent
Provisional state, backend-owned ordering, and no numeric score display.
Don’t Match is hidden until explicit excluded-result expansion. Tailor resume
prepares existing workflow inputs and does not generate anything.

## Major defects and root causes

| Defect | Root cause | Corrective practice |
| --- | --- | --- |
| Tailor action crashed | `app_active_page` was mutated after its widget was instantiated | Store a `jobs_pending_page` intent and consume it before widget creation |
| Selection did not update reliably | Context collisions and stale reconciliation obscured the clicked selection | Use deterministic profile/feed/sector/visibility/job keys and reconcile only when absent |
| Full-card click initially covered only a small area | Only the nested button was sized; Streamlit wrappers retained their intrinsic size | Size the keyed container, `stElementContainer`, `stButton` wrapper, and native button together |
| Selected style was invisible | CSS targeted a marker child instead of the visible bordered `stVerticalBlock` | Target the actual keyed visible card and preserve selected-over-hover precedence |
| Selected glow disappeared on hover | Generic button hover rules overrode selected rules | Define selected + focus, selected + hover, selected, then unselected precedence |
| Eligibility looked like ordinary text | Presentation had no shared semantic indicator | Centralize eligibility dot/label markup while keeping domain state unchanged |
| Visual confidence was overstated | CSS-string tests and optimistic reports were treated as browser evidence | Require harness and real-app screenshots/manual checks for visual acceptance |

## What went well

- The deterministic offline harness enabled repeatable populated testing.
- Native Streamlit controls and keyboard-accessible full-card selection were preserved.
- Deferred navigation corrected state ownership without changing application boundaries.
- Tailored and Explore selection remained independent.
- Backend ordering authority remained intact.
- Selected-card state became visually clear and eligibility indicators were accepted.
- Direct Figma inspection eventually produced concrete scoped tokens.
- Focused red-green fixes protected already-working behavior.
- The user manually tested both the harness and production routing.
- Scoring, providers, persistence, Gemini, rendering, and DOCX systems were preserved.

## What did not go well

- Several broad visual prompts preceded root-cause investigation.
- Tests sometimes proved that CSS strings existed rather than that the browser matched them.
- Completion reports were optimistic before screenshots disproved them.
- The first full-card hitbox sized only the nested button.
- The first selected glow targeted the wrong or incomplete element.
- Hover styling overrode selected styling.
- The widget-owned session-state crash was found only through browser use.
- Early Figma guidance demanded fidelity while forbidding explicit Figma colors.
- Repeated broad remediation passes consumed time that DOM/cascade inspection could have saved.
- Browser availability was inconsistent, making manual validation the real gate.
- Broad searches and commands did not initially protect the locked benchmark strongly enough.
- Documentation lagged behind implementation and accumulated context in chat transcripts.

## Production risks and remaining limitations

The Batch 4 implementation is merged. Documentation may expose follow-up
inconsistencies. Playwright and exact-DOCX checks have known
environment-only failures. Unit and AppTest
coverage cannot establish exact browser appearance or physical pointer bounds.
Streamlit owns parts of widget rendering, so exact Figma pixel parity is not a
stable contract.

## Skills to improve

| Skill | Weakness observed | Risk/time cost | Improved practice | Evidence gate |
| --- | --- | --- | --- | --- |
| Widget/session ownership | Widget keys were mutated too late | Runtime exception | Consume pending intents before widget creation | AppTest handoff test |
| Streamlit DOM inspection | Source selectors were trusted without rendered confirmation | Invisible styling and hitboxes | Inspect actual wrapper chain and computed dimensions | Browser/DOM check |
| CSS cascade | Hover overrode selected state | Lost visual meaning | Write explicit state precedence | Selected-hover screenshot |
| Accessibility | Hit area was not initially a complete native control | Keyboard and pointer inconsistency | Keep one native full-card button with focus treatment | Keyboard smoke test |
| Figma token extraction | Values were initially described vaguely | Repeated visual rework | Inspect frames and centralize tokens | Gap matrix plus screenshot |
| Responsive comparison | Desktop assumptions leaked into mobile | Overflow and poor grouping | Compare desktop, tablet, and mobile states | Manual viewport checklist |
| Theme testing | Generic variables did not reproduce intended Jobs states | Low contrast or wrong surfaces | Validate dark and light separately | Two-theme screenshots |
| Browser evidence | Browser availability was treated as optional | False readiness | Make screenshots/manual checks acceptance gates | User acceptance record |
| AppTest design | String assertions overclaimed visual behavior | Weak regression protection | Assert state, control semantics, and routing separately | Focused AppTests |
| Dirty-worktree discipline | Batch state was easy to misread | Accidental overwrite risk | Preflight and preserve uncommitted files | Final diff review |
| Locked-data isolation | Broad diagnostics could surface fixtures | Benchmark contamination risk | Explicit path exclusions and narrow searches | Command audit |
| Scope control | Broad remediation changed too much at once | Regression risk | Narrow prompts for confirmed defects | Diff scope review |
| Review discipline | Review was deferred until late | Large remediation loop | Independent review before commit | APPROVED result |
| Documentation maintenance | Context stayed in chat | Handoff loss | Update canonical docs in the same batch | Handoff inspection |
| Release readiness | Environment and manual evidence were mixed | Unclear approval | Separate verified, user-reported, and blocked results | DoD checklist |

## Process changes and Definition of Done

Future work uses a standard preflight, an explicit locked-benchmark exclusion,
root-cause debugging, red-green tests, focused and affected verification,
offline and real-app browser acceptance, independent review, remediation and
retest, documentation, then user-controlled commit and PR.

The Definition of Done is:

1. Functional requirements are implemented.
2. Focused red-green tests pass.
3. The affected suite passes.
4. The broad offline suite passes except documented environment restrictions.
5. Ruff, compileall, mypy, and imports pass as applicable.
6. The offline harness is manually accepted.
7. The real app is manually accepted.
8. Accessibility interactions are checked.
9. Relevant Figma comparison is accepted.
10. Independent review returns APPROVED.
11. Review remediations are retested.
12. Documentation is current.
13. Canonical documentation is current.
14. The user stages and commits.
15. The PR includes risks, test evidence, environment conditions, and benchmark disclosure.

## Final acceptance and next steps

The user manually accepted the harness and real app, including full-card
selection, selected/hover/focus states, dark/light styling, eligibility
indicators, all Jobs sections, detail actions, saved jobs, and safe Tailor
routing. The final independent review returned APPROVED with zero blocking
findings.

Final verification recorded:

- Strict mypy passed on 14 materially changed production modules.
- The affected Jobs suite produced 429 passes with one documented Playwright
  sandbox failure.
- The broad offline suite produced 580 passes, two documented environment-only
  failures, and two deselections.
- Migration compatibility produced 5 passes.
- Focused and existing Streamlit tests produced 40 passes.
- Compileall and application, API, production Streamlit, and offline-harness
  imports passed.
- Zero Batch 4-introduced or Batch 4-modified Ruff violations remain.
- 72 verified untouched legacy E501 findings remain in the dirty repository.

Batch 4 is merged. Batch 5 is the final Jobs hardening pass and adds no new
Jobs product feature. Its offline validation and manual-evidence boundary are
recorded in `docs/job-discovery/VALIDATION_REPORT.md` and
`docs/job-discovery/MANUAL_TEST_REPORT.md`. A separate independent review-only
pass remains the next gate.

## Benchmark disclosure

A prior broad command historically collected the locked benchmark gate once.
Later, an accidental broad `rg` diagnostic surfaced benchmark fixture lines.
No locked cases, labels, metrics, expected outputs, or artifacts were used.
The benchmark must not be run or inspected again; future commands explicitly
exclude `tests/job_discovery/benchmark`.
