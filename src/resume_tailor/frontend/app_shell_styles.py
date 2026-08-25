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
  background:
    radial-gradient(circle at 88% 4%, var(--pw-surface-glow), transparent 28rem),
    radial-gradient(circle at 18% 92%,
      color-mix(in srgb, var(--pw-accent-secondary) 7%, transparent), transparent 32rem),
    var(--pw-canvas);
}
[data-testid="stMainBlockContainer"] {
  color: var(--pw-text);
  max-width: 92rem;
  padding-top: 2.35rem;
}
[data-testid="stSidebar"] > div:first-child {
  background: linear-gradient(180deg, var(--pw-surface) 0%, var(--pw-canvas) 100%);
  border-right: 1px solid color-mix(in srgb, var(--pw-border) 72%, transparent);
  box-shadow: 14px 0 42px rgba(0, 0, 0, .08);
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
  background: linear-gradient(135deg,
    var(--pw-action-primary), var(--pw-action-primary-strong)) !important;
  border-color: color-mix(in srgb, var(--pw-action-primary) 75%, white) !important;
  box-shadow: 0 8px 20px color-mix(in srgb, var(--pw-action-primary) 25%, transparent);
  color: #071014 !important;
  font-weight: 700 !important;
  transition: transform .16s ease, box-shadow .16s ease, filter .16s ease;
}
[data-testid="stBaseButton-primary"]:hover {
  filter: brightness(1.06);
  transform: translateY(-1px);
  box-shadow: 0 11px 24px color-mix(in srgb, var(--pw-action-primary) 30%, transparent);
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
  box-shadow: 0 1px 0 rgba(255, 255, 255, .025);
}
.st-key-pw-page-header {
  margin-bottom: 1.35rem;
  padding: .35rem 0 .85rem;
  position: relative;
}
.st-key-pw-page-header::after {
  background: linear-gradient(90deg,
    var(--pw-action-primary), var(--pw-accent-secondary), transparent 72%);
  border-radius: 999px;
  bottom: 0;
  content: "";
  height: 2px;
  left: 0;
  opacity: .7;
  position: absolute;
  width: min(28rem, 72%);
}
.st-key-pw-page-header h1 {
  font-size: clamp(2rem, 3.3vw, 2.75rem);
  font-weight: 760;
  letter-spacing: -.045em;
  line-height: 1.02;
  margin: 0;
}
.st-key-pw-page-header [data-testid="stCaptionContainer"] {
  color: var(--pw-text-muted);
  font-size: .9rem;
  max-width: 48rem;
}
.pw-eyebrow {
  color: var(--pw-action-primary);
  font-size: .68rem;
  font-weight: 700;
  letter-spacing: .12em;
  margin-bottom: .35rem;
  text-transform: uppercase;
}
.pw-status-strip {
  display: grid;
  gap: .6rem;
  grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
  overflow: visible;
  background: transparent;
  border: 0;
  border-radius: var(--pw-radius-panel);
  margin: .5rem 0 1rem;
}
.pw-status-item {
  background: linear-gradient(145deg, var(--pw-surface-raised), var(--pw-surface));
  border: 1px solid var(--pw-border);
  border-radius: var(--pw-radius-control);
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
  box-shadow: inset 0 1px 0 rgba(255,255,255,.025);
  padding: 1.35rem;
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
.st-key-resume-workspace > [data-testid="stVerticalBlock"] { gap: 1rem; }
.st-key-resume-workspace {
  background: color-mix(in srgb, var(--pw-surface) 76%, transparent);
  border: 1px solid color-mix(in srgb, var(--pw-border) 82%, transparent);
  border-radius: calc(var(--pw-radius-panel) + .2rem);
  box-shadow: var(--pw-shadow-panel);
  padding: clamp(.9rem, 2vw, 1.5rem);
}
.st-key-resume-job-summary {
  background:
    linear-gradient(125deg, var(--pw-surface-raised),
      color-mix(in srgb, var(--pw-action-primary) 7%, var(--pw-surface)));
  border-color: color-mix(in srgb, var(--pw-action-primary) 32%, var(--pw-border)) !important;
}
.st-key-resume-controls {
  background: linear-gradient(180deg, var(--pw-surface-raised), var(--pw-surface));
  border: 1px solid var(--pw-border);
  border-radius: var(--pw-radius-panel);
  box-shadow: 0 12px 30px rgba(0,0,0,.1);
  padding: .7rem;
}
[class*="st-key-resume-suggestion-"] {
  background: var(--pw-surface) !important;
  border-left: 3px solid var(--pw-state-review) !important;
  box-shadow: 0 8px 18px rgba(0,0,0,.08);
  transition: border-color .16s ease, transform .16s ease;
}
[class*="st-key-resume-suggestion-"]:hover {
  border-color: color-mix(in srgb, var(--pw-state-review) 70%, var(--pw-border)) !important;
  transform: translateY(-1px);
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
  padding: .25rem 0 1rem;
}
.pw-brand-lockup {
  align-items: center;
  display: flex;
  gap: .7rem;
}
.pw-brand-lockup > span:last-child {
  display: flex;
  flex-direction: column;
}
.pw-brand-lockup strong {
  color: var(--pw-text);
  font-size: 1.08rem;
  letter-spacing: -.02em;
}
.pw-brand-lockup small { color: var(--pw-text-subtle); font-size: .68rem; }
.pw-brand-mark {
  align-items: center;
  background: linear-gradient(135deg, var(--pw-action-primary), var(--pw-accent-secondary));
  border-radius: .72rem;
  box-shadow: 0 8px 22px color-mix(in srgb, var(--pw-action-primary) 24%, transparent);
  color: #071014;
  display: flex;
  height: 2.2rem;
  justify-content: center;
  transform: rotate(-2deg);
  width: 2.2rem;
}
.pw-brand-mark svg { height: 1.55rem; width: 1.55rem; }
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
  transition: background .16s ease, border-color .16s ease, color .16s ease, transform .16s ease;
}
[class*="st-key-pw-route-row"] [data-testid="stButton"] button:hover,
.st-key-pw-mobile-navigation [data-testid="stButton"] button:hover {
  background: var(--pw-surface-hover);
  border-color: var(--pw-border);
  color: var(--pw-text);
  transform: translateX(2px);
}
[class*="st-key-pw-route-row"] [data-testid="stButton"] button:focus-visible,
.st-key-pw-mobile-navigation [data-testid="stButton"] button:focus-visible {
  outline: 2px solid var(--pw-state-info);
  outline-offset: 2px;
}
[class*="st-key-pw-route-row-active"] [data-testid="stButton"] button,
[class*="st-key-pw-mobile-navigation-active"] [data-testid="stButton"] button {
  background: linear-gradient(90deg,
    color-mix(in srgb, var(--pw-action-primary) 17%, transparent),
    color-mix(in srgb, var(--pw-accent-secondary) 8%, transparent));
  border-color: color-mix(in srgb, var(--pw-action-primary) 42%, var(--pw-border));
  color: var(--pw-text);
  font-weight: 600;
}
[class*="st-key-pw-route-row-active"] .pw-workspace-icon,
[class*="st-key-pw-mobile-navigation-active"] .pw-workspace-icon {
  color: var(--pw-state-info);
}
.st-key-pw-profile-context {
  background: linear-gradient(145deg, var(--pw-surface-raised), var(--pw-surface));
  border: 1px solid var(--pw-border);
  border-radius: var(--pw-radius-panel);
  margin-top: 1.25rem;
  padding: .7rem;
  box-shadow: 0 12px 28px rgba(0,0,0,.09);
}
[data-testid="stStatusWidget"] {
  background: linear-gradient(135deg, var(--pw-surface-raised),
    color-mix(in srgb, var(--pw-action-primary) 8%, var(--pw-surface))) !important;
  border-color: color-mix(in srgb, var(--pw-action-primary) 30%, var(--pw-border)) !important;
  border-radius: var(--pw-radius-panel) !important;
  box-shadow: 0 14px 34px rgba(0,0,0,.12);
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
