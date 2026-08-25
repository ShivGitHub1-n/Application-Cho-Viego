"""Scoped Streamlit selectors owned by the Precision Workbench shell."""

from __future__ import annotations


def application_shell_css() -> str:
    """Return the shell CSS.

    Selectors intentionally target explicit ``st.container(key=...)`` markers
    and documented Streamlit test ids rather than generated CSS class names.
    Browser verification remains required for Streamlit DOM changes.
    """

    return """
<style>
.st-key-pw-shell-root {
  color: var(--pw-text);
}
[data-testid="stMain"] {
  background: var(--pw-canvas);
}
[data-testid="stMainBlockContainer"] {
  color: var(--pw-text);
  max-width: 92rem;
  padding-top: 2rem;
}
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stSelectbox"] [data-baseweb="select"] > div {
  background: var(--pw-surface) !important;
  border-color: var(--pw-border) !important;
  color: var(--pw-text) !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus,
[data-testid="stSelectbox"] input:focus {
  border-color: var(--pw-state-info) !important;
  box-shadow: 0 0 0 1px var(--pw-state-info) !important;
}
[data-testid="stButton"] button:focus-visible,
[data-testid="stDownloadButton"] button:focus-visible,
[data-testid="stLinkButton"] a:focus-visible {
  outline: 2px solid var(--pw-state-info) !important;
  outline-offset: 2px;
}
[data-testid="stBaseButton-primary"] {
  background: var(--pw-action-primary) !important;
  border-color: var(--pw-action-primary) !important;
  color: #071014 !important;
}
[data-testid="stBaseButton-primary"]:hover {
  background: var(--pw-action-primary-strong) !important;
  border-color: var(--pw-action-primary-strong) !important;
}
[data-testid="stBaseButton-primary"]:disabled {
  background: var(--pw-surface-raised) !important;
  border-color: var(--pw-border) !important;
  color: var(--pw-text-subtle) !important;
}
[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--pw-surface);
  border-color: var(--pw-border) !important;
  border-radius: var(--pw-radius-panel);
}
.st-key-pw-page-header {
  border-bottom: 1px solid var(--pw-border);
  margin-bottom: 1rem;
  padding: .25rem 0 1rem;
}
.st-key-pw-page-header h1 {
  font-size: clamp(1.75rem, 3vw, 2.4rem);
  letter-spacing: -.035em;
  line-height: 1.05;
  margin: 0;
}
.st-key-pw-page-header [data-testid="stCaptionContainer"] {
  color: var(--pw-text-muted);
  font-size: .9rem;
  max-width: 48rem;
}
.pw-eyebrow {
  color: var(--pw-state-info);
  font-size: .68rem;
  font-weight: 700;
  letter-spacing: .12em;
  margin-bottom: .35rem;
  text-transform: uppercase;
}
.pw-status-strip {
  display: grid;
  gap: 1px;
  grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
  overflow: hidden;
  background: var(--pw-border);
  border: 1px solid var(--pw-border);
  border-radius: var(--pw-radius-panel);
  margin: .5rem 0 1rem;
}
.pw-status-item {
  background: var(--pw-surface);
  display: flex;
  flex-direction: column;
  gap: .18rem;
  min-height: 3.5rem;
  padding: .75rem .9rem;
}
.pw-status-item span {
  color: var(--pw-text-subtle);
  font-size: .65rem;
  font-weight: 700;
  letter-spacing: .07em;
  text-transform: uppercase;
}
.pw-status-item strong { color: var(--pw-text); font-size: .86rem; }
.pw-empty-state {
  align-items: center;
  background: var(--pw-surface-raised);
  border: 1px dashed var(--pw-border-strong);
  border-radius: var(--pw-radius-panel);
  display: flex;
  gap: .85rem;
  padding: 1.1rem;
}
.pw-empty-state p { color: var(--pw-text-muted); margin: .2rem 0 0; }
.pw-empty-icon {
  align-items: center;
  background: color-mix(in srgb, var(--pw-state-info) 14%, transparent);
  border-radius: 50%;
  color: var(--pw-state-info);
  display: flex;
  flex: 0 0 2.25rem;
  font-size: .75rem;
  font-weight: 700;
  height: 2.25rem;
  justify-content: center;
}
.pw-empty-icon svg { height: 1rem; width: 1rem; }
.st-key-resume-workspace > [data-testid="stVerticalBlock"] { gap: .8rem; }
.st-key-resume-controls {
  background: var(--pw-surface-raised);
  border: 1px solid var(--pw-border);
  border-radius: var(--pw-radius-panel);
  padding: .35rem;
}
[class*="st-key-resume-suggestion-"] {
  background: var(--pw-surface) !important;
  border-left: 3px solid var(--pw-state-review) !important;
}
.pw-suggestion-label {
  color: var(--pw-state-review);
  font-size: .67rem;
  font-weight: 700;
  letter-spacing: .06em;
  text-transform: uppercase;
}
.pw-current-copy, .pw-suggested-copy {
  border-radius: var(--pw-radius-control);
  color: var(--pw-text-muted);
  font-size: .82rem;
  line-height: 1.5;
  margin: .35rem 0;
  padding: .55rem .65rem;
}
.pw-current-copy { background: var(--pw-surface-raised); }
.pw-suggested-copy {
  background: color-mix(in srgb, var(--pw-state-positive) 9%, var(--pw-surface));
  color: var(--pw-text);
}
.st-key-cover-letter-error-summary { border-left: 3px solid var(--pw-state-critical); }
.st-key-cover-letter-workspace [data-testid="stMetric"] {
  background: var(--pw-surface-raised);
  border: 1px solid var(--pw-border);
  border-radius: var(--pw-radius-control);
  padding: .5rem .7rem;
}
@media (max-width: 980px) {
  .st-key-resume-workspace [data-testid="stHorizontalBlock"] {
    flex-wrap: wrap;
  }
  .st-key-resume-workspace [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    flex: 1 1 100%;
    width: 100%;
  }
}
.st-key-pw-shell-root [data-testid="stMarkdownContainer"] {
  color: inherit;
}
.st-key-pw-sidebar-brand {
  border-bottom: 1px solid var(--pw-border);
  padding: .15rem 0 .9rem;
}
.st-key-pw-sidebar-brand h1,
.st-key-pw-sidebar-brand h2,
.st-key-pw-sidebar-brand h3 {
  color: var(--pw-text);
  font-size: 1rem;
  letter-spacing: .01em;
  margin: 0;
}
.st-key-pw-sidebar-brand p,
.st-key-pw-profile-context [data-testid="stCaptionContainer"] {
  color: var(--pw-text-subtle);
}
[class*="st-key-pw-route-row"] [data-testid="stHorizontalBlock"] {
  align-items: center;
  gap: .35rem;
}
.pw-workspace-icon {
  align-items: center;
  color: var(--pw-text-muted);
  display: flex;
  height: 2.25rem;
  justify-content: center;
  width: 1.4rem;
}
.pw-workspace-icon svg {
  height: 1rem;
  stroke: currentColor;
  width: 1rem;
}
[class*="st-key-pw-route-row"] [data-testid="stButton"] button,
.st-key-pw-mobile-navigation [data-testid="stButton"] button {
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--pw-radius-control);
  color: var(--pw-text-muted);
  font-size: .84rem;
  justify-content: flex-start;
  min-height: 2.25rem;
  padding: .4rem .55rem;
}
[class*="st-key-pw-route-row"] [data-testid="stButton"] button:hover,
.st-key-pw-mobile-navigation [data-testid="stButton"] button:hover {
  background: var(--pw-surface-hover);
  border-color: var(--pw-border);
  color: var(--pw-text);
}
[class*="st-key-pw-route-row"] [data-testid="stButton"] button:focus-visible,
.st-key-pw-mobile-navigation [data-testid="stButton"] button:focus-visible {
  outline: 2px solid var(--pw-state-info);
  outline-offset: 2px;
}
[class*="st-key-pw-route-row-active"] [data-testid="stButton"] button,
[class*="st-key-pw-mobile-navigation-active"] [data-testid="stButton"] button {
  background: color-mix(in srgb, var(--pw-state-info) 15%, transparent);
  border-color: color-mix(in srgb, var(--pw-state-info) 48%, var(--pw-border));
  color: var(--pw-text);
  font-weight: 600;
}
[class*="st-key-pw-route-row-active"] .pw-workspace-icon,
[class*="st-key-pw-mobile-navigation-active"] .pw-workspace-icon {
  color: var(--pw-state-info);
}
.st-key-pw-profile-context {
  background: var(--pw-surface-raised);
  border: 1px solid var(--pw-border);
  border-radius: var(--pw-radius-panel);
  margin-top: 1.25rem;
  padding: .7rem;
}
.st-key-pw-profile-context [data-testid="stMarkdownContainer"] p {
  color: var(--pw-text);
  font-size: .82rem;
  margin-bottom: .2rem;
  overflow-wrap: anywhere;
}
.st-key-pw-mobile-navigation {
  display: none;
}
@media (max-width: 760px) {
  [data-testid="stSidebar"] { display: none; }
  .st-key-pw-mobile-navigation {
    background: var(--pw-surface);
    border-top: 1px solid var(--pw-border);
    bottom: 0;
    display: block;
    left: 0;
    padding: .35rem .5rem calc(.35rem + env(safe-area-inset-bottom));
    position: fixed;
    right: 0;
    z-index: 100;
  }
  .st-key-pw-mobile-navigation [data-testid="stHorizontalBlock"] {
    align-items: stretch;
    gap: .15rem;
  }
  .st-key-pw-mobile-navigation [data-testid="stButton"] button {
    font-size: .67rem;
    justify-content: center;
    min-height: 2.55rem;
    padding: .25rem;
    width: 100%;
  }
  .st-key-pw-mobile-navigation .pw-workspace-icon {
    height: 1rem;
    justify-content: center;
    margin: 0 auto .1rem;
    width: 100%;
  }
  .st-key-pw-shell-root {
    padding-bottom: 5rem;
  }
  [data-testid="stMainBlockContainer"] {
    padding-bottom: 5rem;
    padding-top: 1.25rem;
  }
  .pw-status-strip { grid-template-columns: repeat(2, 1fr); }
}
</style>
"""


__all__ = ["application_shell_css"]
