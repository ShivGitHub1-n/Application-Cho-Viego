import streamlit as st

from resume_tailor.frontend.app_shell import render_application_shell

st.set_page_config(layout="wide")
active_profile = bool(st.session_state.get("shell-test-active-profile", True))
render_application_shell(
    st,
    active_profile_label="Avery Engineer" if active_profile else None,
    active_profile_id="profile-1" if active_profile else None,
)
