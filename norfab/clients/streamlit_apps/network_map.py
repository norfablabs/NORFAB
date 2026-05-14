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

# Orbit speed labels for select_slider
_SPEED_LABELS = ["0.1x", "0.3x", "0.5x", "1x", "1.5x", "2x"]

# Register the node-receiver component using the v2 API.
# st.components.v2.component() stores plain HTML/JS strings and does NOT call
# inspect.getmodule(), so it is safe to call here even when Streamlit exec()s
# this file via the path-based st.Page() pattern.
# Controller component: pushes orbit/bloom/speed values to the 3D graph iframe
# via window.parent without touching the iframe HTML.  This means the HTML string
# passed to st.iframe stays identical when those toggles change, so the browser
# never recreates the iframe and the camera/zoom position is preserved.
_graph_ctrl = st.components.v2.component(
    name="nf_graph_ctrl",
    html="",
    js="""
    export default function({ parentElement, data }) {
        try {
            window.parent['_nf_gctrl_' + (data?.tab_key ?? '')] = {
                orbit: data?.orbit_active  ?? false,
                bloom: data?.bloom_active  ?? false,
                speed: data?.orbit_speed_idx ?? 2,
            };
        } catch (_) {}
    }
    """,
)

_node_receiver = st.components.v2.component(
    name="nf_node_receiver",
    html="",  # invisible — zero visible content
    js="""
    export default function({ parentElement, data, setStateValue }) {
        // Guard: set up the polling interval only once per DOM element
        // (the component function is called again on every Streamlit rerun).
        if (parentElement._nf_initialized) {
            parentElement._nf_tab_key = data?.tab_key ?? null;
            return;
        }
        parentElement._nf_initialized = true;
        parentElement._nf_tab_key = data?.tab_key ?? null;

        // lastSeen is a local closure variable (NOT a property on window.parent
        // which would be blocked by the cross-origin policy for the component
        // iframe).  Initialize it to the current window.parent.name so that on
        // component remount (Streamlit rerun) we do NOT re-fire setStateValue
        // for a value that was already processed before the rerun.
        // window.parent.name is cross-origin accessible per the HTML spec and is
        // used as the inter-iframe channel by both graph_2d.html and graph_3d.html.
        let lastSeen;
        try { lastSeen = window.parent.name; } catch (_) { lastSeen = undefined; }

        function poll() {
            try {
                const raw = window.parent.name;
                if (raw === lastSeen) return;
                lastSeen = raw;
                const tk = parentElement._nf_tab_key;
                let parsed = null;
                if (raw) {
                    try { parsed = JSON.parse(raw); } catch (_) {}
                }
                if (parsed && parsed._nfnm && (!tk || parsed.tab === tk)) {
                    setStateValue("node", parsed);
                } else {
                    setStateValue("node", null);
                }
            } catch (_) {}
        }

        setInterval(poll, 300);
    }
    """,
)


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
def _fetch_device_names(refresh_nonce: int) -> list:
    """Fetch all device names from NetBox via NorFab.

    Args:
        refresh_nonce: A monotonically increasing value to force re-fetch.

    Returns:
        Sorted list of device name strings.
    """
    nfclient = _get_nfclient()
    if nfclient is None:
        return []
    result = nfclient.run_job(
        "netbox",
        "get_devices",
        workers="any",
        kwargs={"filters": [{"name__iregex": ".*"}]},
    )
    names = set()
    for worker_result in result.values():
        if not worker_result.get("errors") and worker_result.get("result"):
            names.update(worker_result["result"].keys())
    return sorted(names)


@st.cache_data(show_spinner=False)
def _fetch_netbox_topology_data(topology_key: str, refresh_nonce: int, devices: tuple = ()) -> dict:
    """Fetch topology data through a helper function.

    Args:
        topology_key: Topology key such as "L1" or "BGP".
        refresh_nonce: A monotonically increasing value to force re-fetch.
        devices: Tuple of device names to include; empty tuple means all devices.

    Returns:
        Topology dictionary with nodes and links.
    """
    if not devices:
        return {"nodes": [], "links": []}

    if topology_key == "L1":
        nfclient = _get_nfclient()
        if nfclient is not None:
            kwargs = {"devices": list(devices)}
            result = nfclient.run_job(
                "netbox",
                "get_topology",
                workers="any",
                kwargs=kwargs,
            )
            # result is a dict keyed by worker name; take the first successful result
            for worker_result in result.values():
                if not worker_result.get("errors") and worker_result.get("result"):
                    topo = worker_result["result"]
                    topo = json.loads(json.dumps(topo))
                    for lnk in topo.get("links", []):
                        lnk.setdefault("link_color", "#3b82f6")  # blue for NetBox
                    return topo

    topologies = _load_topologies()
    topology = topologies.get(topology_key, {"nodes": [], "links": []})

    # Return a detached copy so view-specific transforms don't affect cached source data.
    topology = json.loads(json.dumps(topology))
    for lnk in topology.get("links", []):
        lnk.setdefault("link_color", "#3b82f6")  # blue for NetBox
    return topology


@st.cache_data(show_spinner=False)
def _fetch_lldp_data(devices: tuple, refresh_nonce: int) -> dict:
    """Fetch LLDP neighbor data from devices via Nornir parse_ttp.

    Args:
        devices: Tuple of device names to query.
        refresh_nonce: A monotonically increasing value to force re-fetch.

    Returns:
        Dictionary mapping device name to list of LLDP neighbor dicts.
    """
    nfclient = _get_nfclient()
    if nfclient is None:
        return {}
    result = nfclient.run_job(
        "nornir",
        "parse_ttp",
        kwargs={"get": "lldp_neighbors", "FL": list(devices)},
        workers="all",
    )
    merged: dict = {}
    for worker_result in result.values():
        if not worker_result.get("errors") and worker_result.get("result"):
            for device, neighbors in worker_result["result"].items():
                if device not in merged:
                    merged[device] = neighbors
    return merged


def _merge_lldp_into_topology(topo: dict, lldp_data: dict) -> dict:
    """Overlay LLDP neighbor data as yellow links onto a topology graph.

    Args:
        topo: Base topology with nodes and links.
        lldp_data: Dict mapping device name to list of LLDP neighbor dicts.

    Returns:
        New topology dict with LLDP links added in yellow.
    """
    nodes = {n["id"]: n for n in topo.get("nodes", [])}
    links = list(topo.get("links", []))

    for device, neighbors in lldp_data.items():
        if device not in nodes:
            nodes[device] = {"id": device, "name": device}
        for nb in (neighbors or []):
            remote = nb.get("remote_device", "")
            if not remote:
                continue
            if remote not in nodes:
                nodes[remote] = {"id": remote, "name": remote}
            links.append({
                "source": device,
                "target": remote,
                "src_iface": nb.get("interface", ""),
                "dst_iface": nb.get("remote_interface", ""),
                "link_color": "#eab308",  # yellow for LLDP
                "link_type": "lldp",
            })

    return {"nodes": list(nodes.values()), "links": links}


@st.cache_data(show_spinner=False)
def _fetch_bgp_data(devices: tuple, refresh_nonce: int) -> tuple:
    """Fetch BGP neighbor data and interface IPs for peer-IP-to-device resolution.

    Args:
        devices: Tuple of device names to query.
        refresh_nonce: A monotonically increasing value to force re-fetch.

    Returns:
        Tuple of (bgp_data, ip_to_device) where bgp_data maps device name to list
        of BGP peer dicts, and ip_to_device maps IP address string to device name.
    """
    nfclient = _get_nfclient()
    if nfclient is None:
        return {}, {}

    bgp_result = nfclient.run_job(
        "nornir",
        "parse_ttp",
        kwargs={"get": "bgp_neighbors", "FL": list(devices)},
        workers="all",
    )
    bgp_data: dict = {}
    for worker_result in bgp_result.values():
        if not worker_result.get("errors") and worker_result.get("result"):
            for device, neighbors in worker_result["result"].items():
                if device not in bgp_data:
                    bgp_data[device] = neighbors

    # Collect all unique peer IPs across all devices
    peer_ips = list({
        nb.get("remote_address", "")
        for neighbors in bgp_data.values()
        for nb in (neighbors or [])
        if nb.get("remote_address")
    })

    ip_to_device: dict = {}
    if peer_ips:
        ip_result = nfclient.run_job(
            "netbox",
            "crud_read",
            kwargs={
                "object_type": "ipam.ip_addresses",
                "filters": [{"address": peer_ips}],
                "fields": ["assigned_object", "address"]
            },
            workers="any",
        )
        for worker_result in ip_result.values():
            for entry in worker_result["result"]["results"]:
                ip = entry.get("address", "").split("/")[0]
                assigned = entry.get("assigned_object") or {}
                device_name = (assigned.get("device") or {}).get("name", "")
                if ip and device_name:
                    ip_to_device[ip] = device_name

    return bgp_data, ip_to_device


def _merge_bgp_into_topology(topo: dict, bgp_data: dict, ip_to_device: dict) -> dict:
    """Overlay BGP peer sessions as purple links onto a topology graph.

    Args:
        topo: Base topology with nodes and links.
        bgp_data: Dict mapping device name to list of BGP peer dicts.
        ip_to_device: Dict mapping peer IP address to device name.

    Returns:
        New topology dict with BGP links added in purple.
    """
    nodes = {n["id"]: n for n in topo.get("nodes", [])}
    links = list(topo.get("links", []))
    seen_pairs: set = set()

    for device, neighbors in bgp_data.items():
        if device not in nodes:
            nodes[device] = {"id": device, "name": device}
        for nb in (neighbors or []):
            remote_ip = nb.get("remote_address", "")
            if not remote_ip:
                continue
            remote_device = ip_to_device.get(remote_ip, remote_ip)
            if remote_device not in nodes:
                nodes[remote_device] = {"id": remote_device, "name": remote_device}
            # Deduplicate: both peers report the same session
            pair = tuple(sorted([device, remote_device]))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            links.append({
                "source": device,
                "target": remote_device,
                "src_iface": nb.get("local_interface", ""),
                "session_type": nb.get("peering_type", ""),
                "link_color": "#a855f7",  # purple for BGP
                "link_type": "bgp",
            })

    return {"nodes": list(nodes.values()), "links": links}


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
        step = 8  # graph-unit perpendicular offset between parallel links
        for j, idx in enumerate(indices):
            offset = step * (j - (n - 1) / 2)
            new_links[idx]["offset_2d"] = offset
            # 2D curve mode: symmetric curvatures around 0
            max_c = min(0.8, 0.3 + 0.1 * n)
            new_links[idx]["curvature_2d"] = (-max_c + (2 * max_c / (n - 1)) * j) if n > 1 else 0
            # 3D: fan arcs via curvature + rotation
            if n == 1:
                new_links[idx]["curvature"] = 0
                new_links[idx]["rotation"] = 0
            else:
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


def _build_html(
    topo: dict,
    use_3d: bool = False,
    search_query: str = "",
    orbit_active: bool = False,
    bloom_active: bool = False,
    orbit_speed_idx: int = 2,
    link_style: str = "straight",
    tab_key: str = "",
) -> str:
    """Build the final HTML by injecting topology data and control state into a template.

    Args:
        topo: Topology dictionary with nodes and links.
        use_3d: If True, use 3D visualization; otherwise use 2D.
        search_query: Search string to pre-highlight matching nodes.
        orbit_active: If True, start 3D orbit on load (3D only).
        bloom_active: If True, enable bloom effect on load (3D only).
        orbit_speed_idx: Index into ORBIT_SPEEDS array (0-5).
        link_style: "straight" or "curve" (2D only).
        tab_key: Tab identifier used for the node-selection bridge.

    Returns:
        Complete HTML string with injected data.
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
    data_vars = (
        f"var GRAPH_DATA={json.dumps(topo)};"
        f"var BG_COLOR='{bg}';"
        f"var SEARCH_QUERY={json.dumps(search_query)};"
        f"var TAB_KEY={json.dumps(tab_key)};"
        f"var LINK_STYLE={json.dumps(link_style)};"
    )

    # Load the appropriate template
    template_name = "graph_3d.html" if use_3d else "graph_2d.html"
    template = _load_html_template(template_name)

    # Inject the data variables
    return template.replace("/*INJECT*/", data_vars)


@st.fragment
def _render_details_panel(tab_key: str) -> None:
    """Fragment: renders selected-node details.  Reruns only when node selection
    changes, leaving the graph iframe untouched.
    """
    result = _node_receiver(
        data={"tab_key": tab_key},
        default={"node": None},
        on_node_change=lambda: None,
        key=f"nr_{tab_key}",
    )
    selected = result.node if result else None

    if selected is None:
        st.markdown(
            "<p style='color:#334155;font-size:12px;text-align:center;"
            "margin-top:40px;line-height:1.8'>Click a node<br>to see details</p>",
            unsafe_allow_html=True,
        )
        return

    _skip = {"_nfnm", "tab", "neighbors", "x", "y", "z", "vx", "vy", "vz", "val"}
    node_id = selected.get("id", "?")

    # Build full detail block as one HTML string so it can share a single
    # scrollable container without Streamlit wrapping each piece separately.
    html_parts: list[str] = []

    # Title badge
    html_parts.append(
        f"<div style='display:inline-block;background:#1e3a5f;border:1px solid "
        f"#3b82f6;border-radius:4px;padding:3px 10px;font-size:13px;"
        f"font-weight:bold;color:#fff;margin-bottom:10px;font-family:monospace'>"
        f"{node_id}</div>"
    )

    # Properties table
    node_data = selected.get("data", {})
    rows_html = ""
    for k, v in node_data.items():
        if k in _skip or k == "id":
            continue
        rows_html += (
            f"<div style='display:flex;justify-content:space-between;padding:3px 0;"
            f"border-bottom:1px solid #1e293b;gap:6px'>"
            f"<span style='color:#64748b;font-size:11px;flex-shrink:0'>{k}</span>"
            f"<span style='color:#e2e8f0;font-size:11px;font-weight:bold;"
            f"text-align:right;word-break:break-all'>{v}</span></div>"
        )
    if rows_html:
        html_parts.append(f"<div style='font-family:monospace'>{rows_html}</div>")

    # Neighbors
    neighbors = selected.get("neighbors", [])
    if neighbors:
        html_parts.append(
            f"<p style='font-size:9px;text-transform:uppercase;letter-spacing:1px;"
            f"color:#475569;margin:12px 0 6px'>Neighbors ({len(neighbors)})</p>"
        )
        for nb in neighbors:
            peer = nb.get("peer", "?")
            li = nb.get("local_iface") or ""
            ri = nb.get("remote_iface") or ""
            iface_html = (
                f"<div style='color:#64748b;font-size:10px'>{li or '?'} \u2194 {ri or '?'}</div>"
                if (li or ri)
                else ""
            )
            html_parts.append(
                f"<div style='padding:6px 9px;margin:3px 0;background:#1e293b;"
                f"border-radius:5px;border:1px solid #334155;font-family:monospace'>"
                f"<div style='color:#e2e8f0;font-size:11px;font-weight:bold;"
                f"margin-bottom:2px'>{peer}</div>{iface_html}</div>"
            )

    inner = "".join(html_parts)
    st.markdown(
        f"<div style='height:660px;overflow-y:auto;padding-right:4px'>{inner}</div>",
        unsafe_allow_html=True,
    )



def network_visualizer_page() -> None:

    st.markdown(
        """
        <style>
        [data-testid="stMainBlockContainer"] { padding-bottom: 10px !important; }
        /* Compact devices selector */
        div[data-testid="stMultiSelect"] [data-baseweb="select"] > div > div {
            max-height: 35px !important;
            overflow: auto !important;
        }
        /* Rounded visible border on the graph iframe */
        [data-testid="stIFrame"] iframe {
            border: 1px solid #334155 !important;
            border-radius: 8px !important;
            overflow: hidden !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    tabs = st.tabs(_TAB_LABELS)
    for tab, key in zip(tabs, _TAB_KEYS):
        with tab:
            # ── Persistent state keys ────────────────────────────────────────────────────
            refresh_key   = f"nmap_refresh_{key}"
            show_left_key = f"nmap_show_left_{key}"
            st.session_state.setdefault(refresh_key, 0)
            st.session_state.setdefault(show_left_key, True)

            show_left = st.session_state[show_left_key]

            # ── Panel toggle button (minimal, above columns) ──────────────────────────
            _bt = st.columns([0.3, 11.7])
            with _bt[0]:
                left_icon = ":material/chevron_right:" if not show_left else ":material/chevron_left:"
                if st.button(
                    " ",
                    key=f"nmap_tl_{key}",
                    icon=left_icon,
                    type="tertiary",
                    help="Show/hide controls",
                ):
                    st.session_state[show_left_key] = not show_left
                    st.rerun()

            # ── Column layout ──────────────────────────────────────────────────────────────
            if show_left:
                cols = st.columns([2, 7, 2.5])
                left_col, graph_col, right_col = cols[0], cols[1], cols[2]
            else:
                cols = st.columns([9, 2.5])
                left_col, graph_col, right_col = None, cols[0], cols[1]

            # ── Controls (left column) ───────────────────────────────────────────────
            refresh_nonce = st.session_state[refresh_key]

            if show_left:
                with left_col:
                    st.caption(_SUBTITLES[key])

                    search_query = st.text_input(
                        "Search",
                        key=f"nmap_search_{key}",
                        placeholder="Name, IP, type...",
                        label_visibility="collapsed",
                    )

                    use_3d = st.toggle("3D view", key=f"nmap_3d_{key}", value=False)

                    if use_3d:
                        orbit_active = st.toggle("Orbit", key=f"nmap_orbit_{key}", value=False)
                        bloom_active = st.toggle("Bloom", key=f"nmap_bloom_{key}", value=False)
                        orbit_speed_idx = st.select_slider(
                            "Speed",
                            options=list(range(6)),
                            value=2,
                            format_func=lambda x: _SPEED_LABELS[x],
                            key=f"nmap_ospeed_{key}",
                            label_visibility="collapsed",
                        )
                    else:
                        orbit_active    = False
                        bloom_active    = False
                        orbit_speed_idx = 2
                        link_style = st.selectbox(
                            "Link style",
                            options=["straight", "curve"],
                            key=f"nmap_lstyle_{key}",
                            label_visibility="visible",
                        )

                    if use_3d:
                        link_style = "straight"  # not applicable in 3D

                    if st.button(
                        " ",
                        key=f"nmap_refresh_btn_{key}",
                        icon=":material/refresh:",
                        type="tertiary",
                        help="Refresh topology",
                        width="content",
                    ):
                        st.session_state[refresh_key] += 1
                        refresh_nonce = st.session_state[refresh_key]

                    device_names = _fetch_device_names(refresh_nonce)
                    selected_devs = st.multiselect(
                        "Devices",
                        options=device_names,
                        default=[],
                        placeholder="Select devices",
                        label_visibility="collapsed",
                        key=f"nmap_devices_{key}",
                    )
                    selected_devices = tuple(selected_devs)
            else:
                # Read last-known values from session state when panel is hidden
                search_query     = st.session_state.get(f"nmap_search_{key}", "")
                use_3d           = st.session_state.get(f"nmap_3d_{key}", False)
                orbit_active     = st.session_state.get(f"nmap_orbit_{key}", False) if use_3d else False
                bloom_active     = st.session_state.get(f"nmap_bloom_{key}", False) if use_3d else False
                orbit_speed_idx  = st.session_state.get(f"nmap_ospeed_{key}", 2) if use_3d else 2
                link_style       = st.session_state.get(f"nmap_lstyle_{key}", "straight")
                bgp_active       = st.session_state.get(f"nmap_bgp_{key}", False)
                selected_devices = tuple(st.session_state.get(f"nmap_devices_{key}", []))

            # ── Graph (middle column) ─────────────────────────────────────────────────
            with graph_col:
                st.markdown(
                    """
                    <style>
                    label[data-testid="stCheckboxLabel"] span[data-nf-netbox] { color: #3b82f6; font-weight: bold; }
                    </style>
                    """,
                    unsafe_allow_html=True,
                )
                _cb_cols = st.columns(3)
                with _cb_cols[0]:
                    netbox_active = st.checkbox(
                        ":blue[**NetBox**]",
                        key=f"nmap_netbox_{key}",
                        value=True,
                    )
                with _cb_cols[1]:
                    lldp_active = st.checkbox(
                        ":orange[**LLDP**]",
                        key=f"nmap_lldp_{key}",
                        value=False,
                    )
                with _cb_cols[2]:
                    bgp_active = st.checkbox(
                        ":violet[**BGP**]",
                        key=f"nmap_bgp_{key}",
                        value=False,
                    )

                topo: dict = {"nodes": [], "links": []}
                # Auto-fetch NetBox data when devices are selected, regardless of checkbox
                if netbox_active or selected_devices:
                    topo = _fetch_netbox_topology_data(key, refresh_nonce, selected_devices)
                if lldp_active and selected_devices:
                    lldp_data = _fetch_lldp_data(selected_devices, refresh_nonce)
                    topo = _merge_lldp_into_topology(topo, lldp_data)
                if bgp_active and selected_devices:
                    bgp_data, ip_to_device = _fetch_bgp_data(selected_devices, refresh_nonce)
                    topo = _merge_bgp_into_topology(topo, bgp_data, ip_to_device)

                html = _build_html(
                    topo,
                    use_3d=use_3d,
                    search_query=search_query,
                    orbit_active=orbit_active,
                    bloom_active=bloom_active,
                    orbit_speed_idx=orbit_speed_idx,
                    link_style=link_style,
                    tab_key=key,
                )
                st.iframe(html, height=700)
                if use_3d:
                    _graph_ctrl(
                        data={
                            "tab_key": key,
                            "orbit_active": orbit_active,
                            "bloom_active": bloom_active,
                            "orbit_speed_idx": int(orbit_speed_idx),
                        },
                        key=f"gc_{key}",
                        height=0,
                    )

            # ── Details panel (right column) ───────────────────────────────────────────
            with right_col:
                st.caption("Node Details")
                _render_details_panel(key)


if __name__ == "__main__":
    network_visualizer_page()

