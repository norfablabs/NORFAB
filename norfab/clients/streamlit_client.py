import streamlit as st

from norfab.core.nfapi import NorFab

st.set_page_config(
    page_title="NORFAB",  # or appropriate title
    page_icon=":gear:",  # optional
    layout="wide",  # optional
)
st.set_option("client.toolbarMode", "viewer")


def about():
    st.title("About Page")
    st.write("This is the about page.")


def run_streamlit_app():

    nf = NorFab(inventory="inventory.yaml")
    NFCLIENT = nf.make_client()  # noqa

    pages = {
        "Overview": [
            st.Page(page=about, title="About", icon=":material/home:"),
        ],
        "Network": [
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
