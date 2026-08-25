"""Semantic Precision Workbench design tokens for Streamlit presentation layers."""

from __future__ import annotations

from typing import Any, Literal

ThemeType = Literal["dark", "light"]

_DARK_TOKENS = {
    "--pw-canvas": "#071014",
    "--pw-surface": "#0d181e",
    "--pw-surface-raised": "#112129",
    "--pw-surface-hover": "#172c36",
    "--pw-border": "#243a45",
    "--pw-border-strong": "#36505d",
    "--pw-text": "#edf5f7",
    "--pw-text-muted": "#b4c4cb",
    "--pw-text-subtle": "#7f959f",
    "--pw-action-primary": "#66d9b7",
    "--pw-action-primary-strong": "#40bc9a",
    "--pw-accent-secondary": "#8aa8ff",
    "--pw-accent-warm": "#f2c879",
    "--pw-surface-glow": "rgba(102, 217, 183, .12)",
    "--pw-state-info": "#7cb7ff",
    "--pw-state-review": "#e4af55",
    "--pw-state-critical": "#ea6c75",
    "--pw-state-positive": "#66d9b7",
    "--pw-radius-control": ".65rem",
    "--pw-radius-panel": "1rem",
    "--pw-shadow-panel": "0 18px 48px rgba(0, 0, 0, .22)",
}

_LIGHT_TOKENS = {
    "--pw-canvas": "#f5f8f9",
    "--pw-surface": "#ffffff",
    "--pw-surface-raised": "#f8fbfc",
    "--pw-surface-hover": "#edf4f5",
    "--pw-border": "#cedde1",
    "--pw-border-strong": "#9db5bd",
    "--pw-text": "#17252b",
    "--pw-text-muted": "#536a72",
    "--pw-text-subtle": "#6b838c",
    "--pw-action-primary": "#237d68",
    "--pw-action-primary-strong": "#176453",
    "--pw-accent-secondary": "#456fd3",
    "--pw-accent-warm": "#a66d0f",
    "--pw-surface-glow": "rgba(35, 125, 104, .09)",
    "--pw-state-info": "#246cc3",
    "--pw-state-review": "#9a680b",
    "--pw-state-critical": "#b53a44",
    "--pw-state-positive": "#237d68",
    "--pw-radius-control": ".65rem",
    "--pw-radius-panel": "1rem",
    "--pw-shadow-panel": "0 16px 40px rgba(23, 37, 43, .10)",
}


def resolve_theme_type(streamlit_module: Any) -> ThemeType:
    """Read Streamlit's public context theme when it is available.

    ``st.context.theme`` is available in the installed Streamlit 1.59.2. The
    guarded fallback preserves deterministic rendering for AppTest, bare
    imports, and older supported Streamlit environments where context is not
    exposed.
    """

    try:
        theme = streamlit_module.context.theme
    except AttributeError:
        return "dark"
    theme_type = getattr(theme, "type", None)
    return theme_type if theme_type in {"dark", "light"} else "dark"


def design_token_css(theme_type: ThemeType | str = "dark") -> str:
    """Return one deterministic semantic token set for the resolved theme."""

    tokens = _LIGHT_TOKENS if theme_type == "light" else _DARK_TOKENS
    declarations = "\n".join(f"  {name}: {value};" for name, value in tokens.items())
    return f"""
<style>
:root {{
{declarations}
}}
</style>
"""


__all__ = ["ThemeType", "design_token_css", "resolve_theme_type"]
