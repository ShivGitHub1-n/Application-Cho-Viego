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
  }
}
</style>
"""


__all__ = ["application_shell_css"]
