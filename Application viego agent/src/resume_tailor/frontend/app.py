import streamlit as st


st.set_page_config(page_title="Resume Tailor", page_icon="📄", layout="wide")
st.title("Resume Tailor")
st.caption("Evidence-backed tailoring for engineering roles.")

st.info(
    "The application foundation is ready. Upload, tailoring, and export workflows "
    "will be added in the next development phases."
)

with st.expander("Product principles", expanded=True):
    st.markdown(
        "- Tailor the complete resume, not isolated bullets.\n"
        "- Preserve truthfulness with evidence-backed claims.\n"
        "- Explain important inclusion and removal decisions.\n"
        "- Keep all document formatting under template control."
    )

