import json
import math
from pathlib import Path

import streamlit as st

_TAB_LABELS = ["\u26bf L1", "\u25c8 BGP"]
_TAB_KEYS = ["L1", "BGP"]
_SUBTITLES = {
    "L1": "Physical Topology \u2014 LLDP Neighbors",
    "BGP": "BGP Peerings",
}


def _get_nfclient():
    """Return the shared NorFab client from Streamlit session state."""
    nfclient = st.session_state.get("nfclient")
    if nfclient is None:
        nfclient = st.session_state.get("NFCLIENT")

    if nfclient is not None and "nfclient" not in st.session_state:
        st.session_state["nfclient"] = nfclient

    return nfclient


def _get_web_folder() -> Path:
    """Get the path to the web folder containing HTML templates."""
    return Path(__file__).parent / "web"


def _load_topologies() -> dict:
    """Load sample topologies from the mock_topologies.json file.

    Returns:
        Dictionary with topology data keyed by topology name.
    """
    topo_path = _get_web_folder() / "mock_topologies.json"
    try:
        return json.loads(topo_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Topologies file not found: {topo_path}. "
            f"Make sure the 'web' folder exists with mock_topologies.json."
        )


@st.cache_data(show_spinner=False)
def _fetch_topology_data(topology_key: str, refresh_nonce: int) -> dict:
    """Fetch topology data through a helper function.

    Args:
        topology_key: Topology key such as "L1" or "BGP".
        refresh_nonce: A monotonically increasing value to force re-fetch.

    Returns:
        Topology dictionary with nodes and links.
    """
    if topology_key == "L1":
        nfclient = _get_nfclient()
        if nfclient is not None:
            result = nfclient.run_job(
                "netbox",
                "get_topology",
                workers="any",
                kwargs={"devices": ["bulk-conn-01"]},
            )
            # result is a dict keyed by worker name; take the first successful result
            for worker_result in result.values():
                if not worker_result.get("errors") and worker_result.get("result"):
                    topo = worker_result["result"]
                    return json.loads(json.dumps(topo))

    topologies = _load_topologies()
    topology = topologies.get(topology_key, {"nodes": [], "links": []})

    # Return a detached copy so view-specific transforms don't affect cached source data.
    return json.loads(json.dumps(topology))


def _apply_link_curvature(topo: dict) -> dict:
    """Add curvature and rotation to parallel links between the same device pair."""
    links = topo.get("links", [])
    pair_indices: dict = {}
    for i, link in enumerate(links):
        pair = tuple(sorted([str(link.get("source", "")), str(link.get("target", ""))]))
        if pair not in pair_indices:
            pair_indices[pair] = []
        pair_indices[pair].append(i)

    new_links = [dict(lnk) for lnk in links]
    for indices in pair_indices.values():
        n = len(indices)
        if n == 1:
            new_links[indices[0]]["curvature"] = 0
            new_links[indices[0]]["rotation"] = 0
        else:
            for j, idx in enumerate(indices):
                new_links[idx]["curvature"] = 0.8
                new_links[idx]["rotation"] = (2 * math.pi / n) * j

    return {**topo, "links": new_links}


def _load_html_template(template_name: str) -> str:
    """Load an HTML template from the web folder.

    Args:
        template_name: Name of the template file (e.g., 'graph_2d.html', 'graph_3d.html')

    Returns:
        The HTML template content as a string.
    """
    template_path = _get_web_folder() / template_name
    try:
        return template_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FileNotFoundError(
            f"HTML template not found: {template_path}. "
            f"Make sure the 'web' folder exists with the required HTML files."
        )


def _build_html(topo: dict, use_3d: bool = False) -> str:
    """Build the final HTML by injecting topology data into a template.

    Args:
        topo: Topology dictionary with nodes and links
        use_3d: If True, use 3D visualization; otherwise use 2D

    Returns:
        Complete HTML string with injected data
    """
    topo = _apply_link_curvature(topo)

    if use_3d:
        # Map topology nodes to 3d-force-graph canonical structure:
        # { id, name, val, ...extra fields preserved }
        nodes_3d = [
            {**n, "name": n.get("name", n.get("id", "")), "val": 1}
            for n in topo.get("nodes", [])
        ]
        topo = {**topo, "nodes": nodes_3d}

    # 3D: near-pure-black so UnrealBloomPass additive composite
    # doesn't visibly alter the background (matches official example pattern)
    bg = "#000003" if use_3d else "#0b0f1a"
    data_vars = f"var GRAPH_DATA={json.dumps(topo)};" f"var BG_COLOR='{bg}';"

    # Load the appropriate template
    template_name = "graph_3d.html" if use_3d else "graph_2d.html"
    template = _load_html_template(template_name)

    # Inject the data variables
    return template.replace("/*INJECT*/", data_vars)


def _render_refresh_button(key: str, refresh_key: str, refreshing_key: str) -> None:
    """Render a compact icon refresh button with inline loading state."""
    is_refreshing = st.session_state[refreshing_key]
    icon = ":material/progress_activity:" if is_refreshing else ":material/refresh:"
    help_text = "Refreshing topology..." if is_refreshing else "Refresh topology"

    if st.button(
        " ",
        key=f"refresh_{key}",
        icon=icon,
        type="tertiary",
        help=help_text,
        width="content",
        disabled=is_refreshing,
    ):
        st.session_state[refreshing_key] = True
        st.session_state[refresh_key] += 1
        st.rerun()


def network_visualizer_page() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stMainBlockContainer"] {
            padding-bottom: 10px !important;
        }

        </style>
        """,
        unsafe_allow_html=True,
    )

    tabs = st.tabs(_TAB_LABELS)
    for tab, key in zip(tabs, _TAB_KEYS):
        with tab:
            refresh_key = f"refresh_nonce_{key}"
            refreshing_key = f"refreshing_{key}"
            st.session_state.setdefault(refresh_key, 0)
            st.session_state.setdefault(refreshing_key, False)

            # ── Toolbar: subtitle | 3D toggle | refresh  ─────────
            c_title, c_mode, c_refresh, c_stats = st.columns([3.4, 0.9, 0.4, 1.2])
            with c_title:
                st.caption(_SUBTITLES[key])
            with c_mode:
                use_3d = st.toggle("3D", key=f"v3d_{key}", value=False)
            with c_refresh:
                _render_refresh_button(key, refresh_key, refreshing_key)

            refresh_nonce = st.session_state[refresh_key]
            topo = _fetch_topology_data(key, refresh_nonce)

            if st.session_state[refreshing_key]:
                st.session_state[refreshing_key] = False
                st.rerun()

            n_nodes = len(topo.get("nodes", []))
            n_links = len(topo.get("links", []))
            with c_stats:
                st.caption(f"**{n_nodes}** nodes \u00b7 **{n_links}** links")

            with st.container(height="stretch", border=True):
                st.iframe(_build_html(topo, use_3d), width="stretch", height=700)


if __name__ == "__main__":
    network_visualizer_page()
