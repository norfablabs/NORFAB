import json
import uuid
import streamlit as st
from streamlit.components.v1 import html


def _default_graph():
    return {
        "nodes": [
            {"id": "Node 1", "group": 1},
            {"id": "Node 2", "group": 1},
            {"id": "Node 3", "group": 2},
            {"id": "Node 4", "group": 2},
            {"id": "Node 5", "group": 3},
        ],
        "links": [
            {"source": "Node 1", "target": "Node 2", "value": 1},
            {"source": "Node 1", "target": "Node 3", "value": 2},
            {"source": "Node 2", "target": "Node 4", "value": 1},
            {"source": "Node 3", "target": "Node 5", "value": 1},
        ],
    }


_HTML_TEMPLATE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    html,body {{ margin:0; padding:0; height:100%; overflow:hidden; background:{bg}; }}
    #3d-graph {{ width:100%; height:100vh; }}
  </style>
</head>
<body>
  <div id="3d-graph"></div>
  <!-- THREE.js and 3d-force-graph from CDN -->
  <script src="https://unpkg.com/three@0.135.0/build/three.min.js"></script>
  <script src="https://unpkg.com/3d-force-graph@1.76.0/dist/3d-force-graph.min.js"></script>
  <script>
    const graphData = {graph_json};
    const elem = document.getElementById('3d-graph');
    const Graph = ForceGraph3D()(elem)
      .graphData(graphData)
      .linkDirectionalParticles({linkDirectionalParticles})
      .linkWidth(d => Math.max(0.1, {link_width} * (d.value || 1)))
      .nodeRelSize({node_size})
      .nodeLabel(node => node.id ? node.id.toString() : '')
      .nodeAutoColorBy('{color_field}')
      .d3Force('link').distance({link_distance});

    // background / camera / controls
    Graph.cameraPosition({{ z: {camera_z} }});
    Graph.onNodeClick(node => {{
      const distance = 100;
      const distRatio = 1 + distance/Math.hypot(node.x, node.y, node.z);
      Graph.cameraPosition(
        {{ x: node.x * distRatio, y: node.y * distRatio, z: node.z * distRatio }},
        node,
        1000
      );
    }});
  </script>
</body>
</html>
"""


def _render_graph(
    graph,
    *,
    bg="#111111",
    node_size=4,
    link_width=1,
    link_distance=30,
    camera_z=200,
    color_field="group",
    linkDirectionalParticles=0,
):
    graph_json = json.dumps(graph)
    html_content = _HTML_TEMPLATE.format(
        graph_json=graph_json,
        bg=bg,
        node_size=node_size,
        link_width=link_width,
        link_distance=link_distance,
        camera_z=camera_z,
        color_field=color_field,
        linkDirectionalParticles=linkDirectionalParticles,
    )
    html(html_content, height=800, scrolling=True)


def network_visualizer_page():
    col1, col2 = st.columns([1, 4])

    with col1:
        st.subheader("Controls")
        graph = _default_graph()

        st.subheader("Visualization parameters")
        bg = st.color_picker("Background color", "#0b0f1a", key="nv_bg")
        node_size = st.slider("Node relative size", 1, 40, 6, key="nv_node_size")
        link_width = st.slider(
            "Link width multiplier", 0.1, 5.0, 1.0, key="nv_link_width"
        )
        link_distance = st.slider("Link distance", 1, 200, 40, key="nv_link_distance")
        camera_z = st.slider("Camera distance (z)", 50, 1000, 200, key="nv_camera_z")
        color_field = st.text_input(
            "Node color field (property name)", value="group", key="nv_color_field"
        )
        particles = st.checkbox(
            "Show link directional particles", value=False, key="nv_particles"
        )
        link_particles = 4 if particles else 0

        if st.button("Randomize node positions", key="nv_random"):
            import random

            for n in graph.get("nodes", []):
                n["x"] = random.uniform(-50, 50)
                n["y"] = random.uniform(-50, 50)
                n["z"] = random.uniform(-50, 50)

        st.markdown("Download the current graph:")
        st.download_button(
            "Download JSON",
            data=json.dumps(graph, indent=2),
            file_name=f"graph_{uuid.uuid4().hex}.json",
            key="nv_download",
        )

        st.session_state["_nv_graph"] = graph

    with col2:
        st.subheader("3D Graph")
        _render_graph(
            graph,
            bg=bg,
            node_size=node_size,
            link_width=link_width,
            link_distance=link_distance,
            camera_z=camera_z,
            color_field=color_field,
            linkDirectionalParticles=link_particles,
        )


if __name__ == "__main__":
    network_visualizer_page()
