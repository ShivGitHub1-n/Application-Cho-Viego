"""Scoped Precision Workbench styling for the accepted Jobs workspace."""

def jobs_css() -> str:
    """Return CSS scoped to Jobs and mapped only to shared semantic tokens."""
    card = '.st-key-jobs-page [data-testid="stVerticalBlock"][class*="st-key-jobs-card-"]'
    action_container = '[data-testid="stElementContainer"][class*="st-key-jobs-card-action-"]'
    saved_card = (
        '.st-key-jobs-page [data-testid="stVerticalBlock"][class*="st-key-jobs-saved-card-"]'
    )
    detail_panels = (
        '.st-key-jobs-detail-panel[data-testid="stVerticalBlock"], '
        '.st-key-jobs-saved-detail-panel[data-testid="stVerticalBlock"]'
    )
    mobile_roots = (
        ".st-key-jobs-header-controls",
        ".st-key-jobs-explore-controls",
        ".st-key-jobs-feed-layout",
        ".st-key-jobs-preference-editor",
    )
    mobile_rows = ", ".join(
        f'{root} > [data-testid="stElementContainer"] > [data-testid="stHorizontalBlock"]'
        for root in mobile_roots
    )
    mobile_columns = ", ".join(f'{root} [data-testid="stColumn"]' for root in mobile_roots)
    return f"""
<style>
.st-key-jobs-page {{
  --jobs-canvas: var(--pw-canvas);
  --jobs-surface: var(--pw-surface);
  --jobs-surface-secondary: var(--pw-surface-raised);
  --jobs-surface-hover: var(--pw-surface-hover);
  --jobs-card-selected: color-mix(in srgb, var(--pw-state-info) 14%, var(--pw-surface));
  --jobs-border: var(--pw-border);
  --jobs-border-hover: var(--pw-border-strong);
  --jobs-accent: var(--pw-state-info);
  --jobs-selected-label: var(--pw-state-info);
  --jobs-text: var(--pw-text);
  --jobs-text-secondary: var(--pw-text-muted);
  --jobs-text-muted: var(--pw-text-subtle);
  --jobs-fit-inactive: var(--pw-border-strong);
  --jobs-warning-surface: color-mix(in srgb, var(--pw-state-review) 12%, var(--pw-surface));
  --jobs-warning-text: var(--pw-state-review);
  --jobs-selected-glow: transparent;
  --jobs-eligibility-eligible: var(--pw-state-positive);
  --jobs-eligibility-unknown: var(--pw-state-review);
  --jobs-eligibility-ineligible: var(--pw-state-critical);
  margin-inline: auto;
  max-width: 75rem;
}}
.st-key-jobs-page > [data-testid="stElementContainer"] > [data-testid="stVerticalBlock"] {{
  gap: .85rem;
}}
.st-key-jobs-header {{
  border-bottom: 1px solid var(--jobs-border);
  padding: .35rem 0 1rem;
}}
.st-key-jobs-header-controls [data-testid="stHorizontalBlock"] {{ align-items: end; }}
.st-key-jobs-header-status,
.st-key-jobs-page [data-testid="stCaptionContainer"] {{ color: var(--jobs-text-muted); }}

.st-key-jobs-section-nav {{
  border-bottom: 1px solid var(--jobs-border);
  padding-bottom: 0;
}}
.st-key-jobs-section-nav [data-testid="stButtonGroup"] {{
  align-items: flex-end;
  display: flex;
  flex-wrap: wrap;
  gap: 1.25rem;
  margin: 0;
}}
.st-key-jobs-section-nav [data-variant="pills"] {{
  background: transparent !important;
  border: 0 !important;
  border-bottom: 3px solid transparent !important;
  border-radius: 0 !important;
  box-shadow: none !important;
  color: var(--jobs-text-secondary) !important;
  font-size: .8125rem;
  font-weight: 500;
  flex: 0 0 auto;
  min-height: 2.25rem;
  min-width: auto;
  padding: .25rem .55rem;
  width: auto;
}}
.st-key-jobs-section-nav [data-variant="pills"]:hover {{
  background: var(--jobs-surface-secondary) !important;
  color: var(--jobs-text) !important;
}}
.st-key-jobs-section-nav [data-variant="pills"][data-selected] {{
  background: transparent !important;
  border-bottom-color: var(--jobs-accent) !important;
  color: var(--jobs-accent) !important;
  font-weight: 600;
}}
.st-key-jobs-section-nav [data-variant="pills"][aria-pressed="true"] {{
  background: transparent !important;
  border-bottom-color: var(--jobs-accent) !important;
  color: var(--jobs-accent) !important;
  font-weight: 600;
}}
.st-key-jobs-section-nav [data-variant="pills"][data-selected]:hover {{
  background: transparent !important;
  color: var(--jobs-accent) !important;
}}
.st-key-jobs-section-nav [data-variant="pills"][aria-pressed="true"]:hover {{
  background: transparent !important;
  color: var(--jobs-accent) !important;
}}
.st-key-jobs-section-nav [data-variant="pills"]:focus-visible {{
  outline: 2px solid var(--jobs-accent);
  outline-offset: -2px;
}}
.st-key-jobs-section-nav [data-variant="pills"]:focus-visible {{
  box-shadow: 0 0 0 2px var(--jobs-accent) !important;
}}

.st-key-jobs-page .jobs-filter-row {{
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: .5rem;
  margin: .1rem 0;
}}
.st-key-jobs-page .jobs-filter-chip {{
  background: var(--jobs-surface-secondary);
  border: 0;
  border-radius: 999px;
  color: var(--jobs-text-secondary);
  display: inline-block;
  font-size: .6875rem;
  font-weight: 500;
  padding: .3rem .75rem;
}}
.st-key-jobs-page .jobs-filter-summary {{
  color: var(--jobs-text-muted);
  font-size: .6875rem;
  margin-left: auto;
}}
.st-key-jobs-page .jobs-sort-note {{
  color: var(--jobs-text-muted);
  font-size: .6875rem;
  margin-top: -.2rem;
  overflow-wrap: anywhere;
}}

.st-key-jobs-page .jobs-fit-meter {{
  align-items: center;
  display: inline-flex;
  flex-wrap: wrap;
  gap: .25rem;
  max-width: 100%;
}}
.st-key-jobs-page .jobs-fit-bars {{ display: inline-flex; gap: .375rem; }}
.st-key-jobs-page .jobs-fit-bar {{
  background: var(--jobs-fit-inactive);
  border: 0;
  border-radius: 3px;
  box-sizing: border-box;
  display: inline-block;
  height: 7px;
  opacity: 1;
  width: 22px;
}}
.st-key-jobs-page .jobs-fit-bar--active {{ background: var(--jobs-accent); }}
.st-key-jobs-page .jobs-fit-bar--inactive {{ background: var(--jobs-fit-inactive); }}
.st-key-jobs-page .jobs-fit-label {{
  color: var(--jobs-text);
  font-size: .6875rem;
  font-weight: 600;
}}
.st-key-jobs-page .jobs-fit-description {{
  color: var(--jobs-text-muted);
  flex-basis: 100%;
  font-size: .625rem;
  line-height: 1.25;
  overflow-wrap: anywhere;
}}
.st-key-jobs-page .jobs-eligibility-indicator {{
  align-items: center;
  color: var(--jobs-text-secondary);
  display: inline-flex;
  font-size: .6875rem;
  gap: .25rem;
  line-height: 1.35;
}}
.st-key-jobs-page .jobs-eligibility-dot {{
  border-radius: 50%;
  display: inline-block;
  flex: 0 0 7px;
  height: 7px;
  width: 7px;
}}
.st-key-jobs-page .jobs-eligibility--eligible .jobs-eligibility-dot {{
  background: var(--jobs-eligibility-eligible);
}}
.st-key-jobs-page .jobs-eligibility--unknown .jobs-eligibility-dot {{
  background: var(--jobs-eligibility-unknown);
}}
.st-key-jobs-page .jobs-eligibility--ineligible .jobs-eligibility-dot {{
  background: var(--jobs-eligibility-ineligible);
}}
.st-key-jobs-page .jobs-selected-label {{
  color: var(--jobs-selected-label);
  font-size: .6875rem;
  font-weight: 600;
}}
.st-key-jobs-page [data-testid="stMarkdownContainer"] {{ overflow-wrap: anywhere; }}

{card} {{
  background: var(--jobs-surface) !important;
  border: 1px solid var(--jobs-border) !important;
  border-radius: 10px !important;
  overflow: visible;
  position: relative;
  transition: border-color 120ms ease, box-shadow 120ms ease, background 120ms ease;
}}
{card}:not(:has(.jobs-card-selected-marker)):has(button:hover) {{
  background: var(--jobs-surface-hover) !important;
  border-color: var(--jobs-border-hover) !important;
}}
{card}:has(.jobs-card-selected-marker) {{
  background: var(--jobs-card-selected) !important;
  border-color: var(--jobs-accent) !important;
  box-shadow: 0 0 0 1px var(--jobs-accent) !important;
}}
{card}:has(.jobs-card-selected-marker):has(button:hover) {{
  background: var(--jobs-card-selected) !important;
  border-color: var(--jobs-accent) !important;
  box-shadow: 0 0 0 1px var(--jobs-accent) !important;
}}
{card}:has(button:focus-visible) {{
  outline: 2px solid var(--jobs-accent);
  outline-offset: 2px;
}}
{card}:has(.jobs-card-selected-marker):has(button:focus-visible) {{
  outline-color: var(--jobs-accent);
}}
{card} [data-testid="stMarkdownContainer"] p {{ margin-bottom: .15rem; }}
{card} [data-testid="stCaptionContainer"] {{
  color: var(--jobs-text-muted) !important;
  font-size: .6875rem;
  line-height: 1.35;
}}
{card} strong {{
  color: var(--jobs-text);
  font-size: .9375rem;
  font-weight: 600;
}}
{card} > {action_container} {{
  inset: 0;
  margin: 0;
  position: absolute;
  z-index: 1;
}}
{card} > {action_container} [data-testid="stButton"] {{
  height: 100%;
  width: 100%;
}}
{card} > {action_container} [data-testid="stButton"] > button {{
  background: transparent !important;
  border: 0 !important;
  height: 100%;
  min-height: 100%;
  opacity: 0;
  width: 100%;
}}

{saved_card} {{
  background: var(--jobs-surface) !important;
  border: 1px solid var(--jobs-border) !important;
  border-radius: 10px !important;
}}
{saved_card}:has(.jobs-saved-selected-marker) {{
  background: var(--jobs-card-selected) !important;
  border-color: var(--jobs-accent) !important;
  box-shadow: 0 0 0 1px var(--jobs-accent), 0 0 12px var(--jobs-selected-glow) !important;
}}
{detail_panels} {{
  background: var(--jobs-surface) !important;
  border: 1px solid var(--jobs-border) !important;
  border-radius: 10px !important;
  padding: .25rem;
}}
.st-key-jobs-action-row,
.st-key-jobs-saved-action-row {{
  border-bottom: 1px solid var(--jobs-border);
  margin-top: .25rem;
  padding: .25rem 0 .9rem;
}}
.st-key-jobs-action-row [data-testid="stHorizontalBlock"],
.st-key-jobs-saved-action-row [data-testid="stHorizontalBlock"] {{ align-items: center; }}
.st-key-jobs-detail-panel .jobs-detail-section h4 {{
  color: var(--jobs-text-secondary);
  font-size: .6875rem;
  letter-spacing: .04em;
  margin: 1rem 0 .35rem;
  text-transform: uppercase;
}}
.st-key-jobs-detail-panel .jobs-detail-section li {{ color: var(--jobs-text-secondary); }}
.st-key-jobs-detail-panel [data-testid="stAlert"] {{
  background: var(--jobs-warning-surface);
  border-color: var(--jobs-warning-text);
  color: var(--jobs-warning-text);
}}
.st-key-jobs-preference-role-direction[data-testid="stVerticalBlock"],
.st-key-jobs-preference-skills[data-testid="stVerticalBlock"],
.st-key-jobs-preference-constraints[data-testid="stVerticalBlock"],
.st-key-jobs-preference-companies[data-testid="stVerticalBlock"],
.st-key-jobs-preference-suggestion[data-testid="stVerticalBlock"],
.st-key-jobs-preference-confirmed[data-testid="stVerticalBlock"],
.st-key-jobs-empty-state[data-testid="stVerticalBlock"],
.st-key-jobs-feed-empty-state[data-testid="stVerticalBlock"],
.st-key-jobs-saved-empty[data-testid="stVerticalBlock"] {{
  background: var(--jobs-surface) !important;
  border-color: var(--jobs-border) !important;
  border-radius: 10px !important;
}}
@media (max-width: 900px) {{
  .st-key-jobs-page {{ max-width: none; }}
  {mobile_rows} {{ flex-wrap: wrap; }}
  {mobile_columns} {{ flex: 1 1 100%; width: 100%; }}
  .st-key-jobs-feed-layout [data-testid="stHorizontalBlock"] {{ align-items: stretch; }}
  .st-key-jobs-page .jobs-filter-summary {{ margin-left: 0; }}
}}
@media (max-width: 620px) {{
  .st-key-jobs-action-row [data-testid="stHorizontalBlock"],
  .st-key-jobs-saved-action-row [data-testid="stHorizontalBlock"] {{ flex-wrap: wrap; }}
  .st-key-jobs-action-row [data-testid="stColumn"],
  .st-key-jobs-saved-action-row [data-testid="stColumn"] {{ flex: 1 1 100%; width: 100%; }}
}}
</style>
"""


__all__ = ["jobs_css"]
