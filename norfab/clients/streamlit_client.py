import streamlit as st

from norfab.core.nfapi import NorFab

# Theme must be configured before set_page_config
st.config.set_option("theme.base", "dark")
st.config.set_option("theme.backgroundColor", "#0b0f1a")
st.config.set_option("theme.secondaryBackgroundColor", "#0f172a")
st.config.set_option("theme.primaryColor", "#3b82f6")
st.config.set_option("theme.textColor", "#e2e8f0")
st.config.set_option("theme.font", "monospace")

st.set_page_config(
    page_title="NORFAB",
    page_icon=":gear:",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.set_option("client.toolbarMode", "minimal")


def about() -> None:
    st.title("About Page")
    st.write("This is the about page.")


@st.cache_resource(show_spinner="Connecting to NORFAB...")
def _create_norfab_client(inventory: str = "inventory.yaml"):
    """Create and cache NorFab + client objects across Streamlit reruns."""
    nf = NorFab(inventory=inventory)
    return nf, nf.make_client()


def _init_norfab_session_state() -> None:
    """Expose shared NorFab client in Streamlit session state for page modules."""
    if "nfclient" in st.session_state:
        return

    nf, nfclient = _create_norfab_client()
    st.session_state["norfab"] = nf
    st.session_state["nfclient"] = nfclient
    # Compatibility alias for existing references that use uppercase name.
    st.session_state["NFCLIENT"] = nfclient


def run_streamlit_app() -> None:
    _init_norfab_session_state()

    pages = {
        "Overview": [
            st.Page(page=about, title="Dashboard", icon=":material/home:"),
        ],
        "Apps": [
            st.Page(
                page="./streamlit_apps/network_map.py",
                title="Network Map",
                icon=":material/graph_2:",
            ),
        ],
    }

    pg = st.navigation(
        pages,
        position="sidebar",
        expanded=True,
    )
    pg.run()


if __name__ == "__main__":
    run_streamlit_app()
