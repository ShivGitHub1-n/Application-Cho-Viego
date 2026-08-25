from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from resume_tailor.application.cover_letter_policy import (
    COVER_LETTER_WRITING_POLICY_VERSION,
)

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "src" / "resume_tailor" / "frontend" / "app.py"


def test_filename_launched_streamlit_prefers_the_app_checkout(
    tmp_path: Path,
) -> None:
    """Exercise the real filename launch without pytest's configured src path."""

    script = "\n".join(
        (
            "from streamlit.testing.v1 import AppTest",
            f"app = AppTest.from_file({str(APP_PATH)!r}).run(timeout=30)",
            "print('RUNTIME_ROOT=' + str(app.session_state['_runtime_source_root']))",
            "print('WRITING_POLICY=' + str(app.session_state['_cover_letter_writing_policy']))",
            "print('EXCEPTION_COUNT=' + str(len(app.exception)))",
        )
    )
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["APPLICATION_VIEGO_DATA_DIR"] = str(tmp_path)
    environment["GEMINI_API_KEY"] = ""
    environment["GEMINI_MODEL"] = ""
    for name in (
        "LLM_ENABLE_ROLE_CLASSIFICATION",
        "LLM_ENABLE_OPPORTUNITY_ANALYSIS",
        "LLM_ENABLE_COMPOSITION",
        "LLM_ENABLE_BULLET_REWRITE",
        "LLM_ENABLE_SHORTENING",
        "LLM_ENABLE_COVER_LETTER",
    ):
        environment[name] = "false"

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert f"RUNTIME_ROOT={ROOT / 'src'}" in completed.stdout
    assert f"WRITING_POLICY={COVER_LETTER_WRITING_POLICY_VERSION}" in completed.stdout
    assert "EXCEPTION_COUNT=0" in completed.stdout

