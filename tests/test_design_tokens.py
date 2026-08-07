from types import SimpleNamespace

from resume_tailor.frontend.design_tokens import design_token_css, resolve_theme_type
from resume_tailor.frontend.routes import AppRoute, normalize_route


def test_normalize_route_maps_legacy_labels_to_canonical_routes() -> None:
    assert normalize_route("Master profile") is AppRoute.CAREER_PROFILE
    assert normalize_route("Resume Tailor") is AppRoute.RESUME_STUDIO
    assert normalize_route("Cover letters") is AppRoute.COVER_LETTERS
    assert normalize_route("Jobs") is AppRoute.JOBS


def test_normalize_route_defaults_unknown_values_to_career_profile() -> None:
    assert normalize_route("unexpected") is AppRoute.CAREER_PROFILE
    assert normalize_route(None) is AppRoute.CAREER_PROFILE


def test_design_token_css_declares_complete_deterministic_semantic_values() -> None:
    dark_css = design_token_css("dark")
    light_css = design_token_css("light")

    for css in (dark_css, light_css):
        assert "--pw-canvas:" in css
        assert "--pw-action-primary:" in css
        assert "--pw-state-info:" in css
        assert "--pw-state-review:" in css
        assert "--pw-state-critical:" in css
        assert "body {" not in css
        assert "@media (prefers-color-scheme: light)" not in css
    assert dark_css != light_css
    assert "#071014" in dark_css
    assert "#f5f8f9" in light_css


def test_theme_resolver_uses_streamlit_context_theme_with_a_dark_fallback() -> None:
    dark = SimpleNamespace(context=SimpleNamespace(theme=SimpleNamespace(type="dark")))
    light = SimpleNamespace(context=SimpleNamespace(theme=SimpleNamespace(type="light")))
    system = SimpleNamespace(context=SimpleNamespace(theme=SimpleNamespace(type="system")))
    assert resolve_theme_type(dark) == "dark"
    assert resolve_theme_type(light) == "light"
    assert resolve_theme_type(SimpleNamespace()) == "dark"
    assert resolve_theme_type(system) == "dark"
