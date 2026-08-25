# ADR: NFWeb Local Application Platform and First 3D Topology Application

- **Status:** Accepted
- **Date:** 24 August 2026
- **Decision owners:** NORFAB maintainers
- **Scope:** Generic local NORFAB web client and its first 3D network topology application

## Context

NORFAB currently has an experimental Streamlit client in
`norfab/clients/streamlit_client.py`. Its network topology page is implemented in
`norfab/clients/streamlit_apps/network_map.py` and embeds separate 2D and 3D HTML
documents.

The current implementation is useful as a prototype, but it is not yet a built-in,
operational web UI:

- the Streamlit dependency and an installed web-client command are absent from
  `pyproject.toml`;
- the 2D view is the default and duplicates behavior that the target product does
  not need;
- graph controls and node selection cross iframe boundaries through custom
  Streamlit components and polling of `window.name`;
- widget interactions rerun Python page code and can recreate the embedded graph;
- topology collection is tied to an individual browser session and manual refresh;
- no bounded historical store, playback API, shared collector, or live update
  channel exists;
- BGP mock data is used when live data is unavailable, which can make an
  operational view look authoritative when it is not;
- browser dependencies are loaded from unpinned public CDNs at runtime;
- there is no web UI configuration model, authentication boundary, focused test
  suite, or user documentation.

The target is a built-in, generic NORFAB web client that is straightforward to
install and run locally and can grow into multiple focused applications. Its first
application is a weather-map-style topology view. That application must use only
Vasturiano's 3D visualization, show selectable network layers, consume current
state collected through NORFAB, and retain a small rolling three-hour history.

Streamlit's execution model intentionally reruns application code when widgets
change. Fragments and cached resources can reduce the cost, but the persistent,
high-frequency browser scene and application-owned collector required here remain a
poor fit for that model. Tornado is already a NORFAB core dependency and can provide
the small loopback-only HTTP and WebSocket bridge required between browser code and
the native Python client. A Vite production build produces static files that can be
packaged and served without a Node.js production runtime.

## Decision

Replace the Streamlit topology application with a generic, local Python-hosted
NFWeb client and deliver topology as its first built-in application.

- **Local host:** Tornado in the dedicated `norfab.clients.nfweb` package. It serves
  only on loopback and provides the packaged frontend, application routing,
  lifecycle, and browser boundary shared by NFWeb applications.
- **Frontend:** React, TypeScript, and Vite.
- **Visualization:** Vasturiano `react-force-graph-3d` / `3d-force-graph` only.
  No 2D graph implementation or 2D/3D selector will remain.
- **Production runtime:** Python only. Node.js is a development and release-build
  dependency. Compiled frontend assets are included in the Python distribution.
- **NORFAB access:** the local process creates the native `NFPClient` from the
  selected inventory and connects to its existing broker. It never starts a broker
  or workers. Browser code never connects to ZeroMQ and never receives broker
  credentials.
- **FastAPI independence:** neither the local application nor topology collection
  depends on the NORFAB FastAPI worker. The native client retains access to the
  complete fabric without routing jobs through another service worker.
- **Application scope:** topology is the first application, not the definition of
  NFWeb. Future applications add namespaced contracts, routes, state, and UI within
  the shared client runtime.
- **Browser API scope:** the first release exposes topology operations only. NFWeb
  does not provide a generic HTTP or WebSocket mechanism for arbitrary NORFAB jobs,
  even though the local Python process uses a full native client internally.
- **Live delivery:** device discovery combines NetBox and Nornir host names without
  starting topology collection. The shared collector starts only after a non-empty
  scope is selected, then polls configured NORFAB tasks and publishes completed
  snapshots over a WebSocket. “Live” means near-real-time state at the configured
  polling interval, not fabricated streaming telemetry.
- **History:** NFWeb's local SQLite database contains a topology-owned snapshot
  table retained for exactly the configured window, defaulting to three hours.
  Retention cleanup runs after each successful insert. History is shared by browser
  tabs and survives a web UI restart. Collection continues without an open browser
  only while the topology scope is non-empty.
- **Replacement:** remove the Streamlit client, its application package, both graph
  templates, mock operational fallbacks, and component bridges when NFWeb is added.
  Git history is the only rollback mechanism; no compatibility shim is retained.

NFWeb is a NORFAB **client and local application host**, not an extension or
consumer of the FastAPI service worker. The existing worker remains available for
external REST API consumers. NFWeb connects directly to the broker; each installed
application owns its presentation-specific aggregation, contracts, namespaced
tables, and browser operations.

## Runtime Architecture

```text
Browser
  |  HTTP / JSON / WebSocket on loopback
  v
NFWeb (local Tornado runtime launched by `nfcli --web-ui`)
  |-- static packaged React application
  |-- shared local client lifecycle and browser policy
  |-- native NFPClient connection
  |-- applications
      |-- topology (first application)
          |-- loopback-only topology API
          |-- WebSocket snapshot broadcaster
          |-- collector and layer adapters
          |-- SQLite rolling snapshot store
      |-- future focused applications
  |
  |  NFP over ZeroMQ
  v
NORFAB broker --> NetBox / Nornir / future telemetry workers
```

The NFWeb runtime owns the NORFAB client, Tornado host, installed application
services, and orderly shutdown. It constructs `NorFab` without calling `start()`,
then calls `make_client(name="nfweb")` to connect to the existing broker. The
NFWeb owns the local database location, while the topology application owns its
collector and namespaced table access. The collector uses `NFPClient.submit_job`
and asynchronously waits for each returned future without blocking the Tornado I/O
loop. Only one topology collection cycle may run at a time; when a cycle exceeds
its interval, the next cycle is skipped instead of creating an unbounded queue.

The web client always connects to an existing broker. Starting a broker or workers
from the web process is outside the application contract, not merely deferred from
the first release.

## NFWeb Application Architecture

NFWeb is the stable local client boundary. Topology is the first application
implemented within that boundary. A future NFWeb application should:

- use an application-specific configuration section and route namespace;
- define typed, presentation-oriented contracts instead of returning unbounded raw
  worker replies to browser code;
- own its collectors, caches, persistence, and application state;
- reuse the NFWeb process, native client, frontend shell, lifecycle, and security
  policy;
- expose narrow operations for its use case rather than a generic service/task
  passthrough;
- require another architecture and security decision before introducing remote
  access or change-capable browser operations.

The first release may open directly into topology. A home screen, navigation, and
an application registry can be introduced when a second application is added;
they are not required merely to claim an abstraction before it has another user.

## Topology Domain Model

Use a presentation-neutral graph contract. The frontend must not know which worker
or parser produced a field.

```json
{
  "snapshot_id": "01K...",
  "collected_at": "2026-08-24T05:20:30Z",
  "duration_ms": 1840,
  "status": "complete",
  "devices": ["spine-1", "leaf-1"],
  "layers": ["inventory", "lldp", "bgp", "interfaces"],
  "nodes": [
    {
      "id": "spine-1",
      "label": "spine-1",
      "kind": "device",
      "health": "healthy",
      "attributes": {"site": "dc-1", "role": "spine"}
    }
  ],
  "links": [
    {
      "id": "spine-1:Ethernet1--leaf-1:Ethernet49",
      "source": "spine-1",
      "target": "leaf-1",
      "layer": "inventory",
      "health": "healthy",
      "metrics": {},
      "attributes": {
        "source_interface": "Ethernet1",
        "target_interface": "Ethernet49"
      }
    }
  ],
  "errors": [],
  "events": [
    {
      "service": "netbox",
      "task": "get_topology",
      "severity": "INFO",
      "message": "fetched 12 device(s)"
    }
  ]
}
```

Rules:

- node IDs and link IDs are stable across snapshots;
- timestamps are UTC and generated by the collector;
- unknown metrics are omitted, never invented as zero;
- `status: partial` and the `errors` collection make unavailable layers
  visible without discarding successful data;
- `events` retains the NORFAB job events emitted during that collection cycle;
- every node and link records its layer or provenance;
- health is one of `healthy`, `warning`, `critical`, or `unknown`;
- source-specific fields stay below `attributes` until promoted into the common
  contract.

## Layer Adapters

Each layer implements a small Python adapter protocol and returns a graph patch plus
collection metadata. Initial adapters are:

| Layer | Source | Initial purpose | Default cadence |
| --- | --- | --- | --- |
| `inventory` | NetBox `get_topology` | Device metadata and intended physical cables | 5 minutes |
| `lldp` | Nornir `parse_ttp`, `get=lldp_neighbors` | Observed physical adjacency | 30 seconds |
| `bgp` | Nornir `parse_ttp`, `get=bgp_neighbors` plus NetBox IP resolution | Observed peer sessions and state | 30 seconds |
| `interfaces` | Nornir `parse_ttp`, `get=interfaces_status` | Link state, speed, counters, and utilization when supplied | 30 seconds |

Cadences are configuration defaults, not hard-coded UI behavior. Static layers may
be reused across multiple live snapshots. Adapters must return a partial result on
worker or device failure and must not silently substitute mock data.

Future OSPF, IS-IS, tunnel, path, service, alarm, or streaming-telemetry adapters
use the same protocol and graph contract. Adding a layer must not require changes to
the collector or database schema.

## NFWeb Database and Topology History

NFWeb uses one SQLite file below the inventory's ignored runtime directory:

```text
__norfab__/nfweb/nfweb.sqlite
```

Applications own namespaced tables within this database rather than naming the
database after the first application. Topology stores compressed JSON snapshots in
`topology_snapshots` with only the fields needed to retain and load them:

- unique snapshot ID as the primary key;
- indexed collection timestamp;
- JSON payload.

Use one event-loop-owned SQLite connection through a repository class. The default
30-second cadence produces at most 360 snapshots in a three-hour window. Cleanup
deletes rows older than the retention cutoff after a successful insert. A startup
cleanup handles downtime and clock changes. The history API returns ordered
snapshot IDs, while selecting a point loads its corresponding full snapshot.

Do not store one history per browser filter. Collect one shared, explicitly
selected topology scope, record that scope in each snapshot, then apply layer,
health, and metadata filters when rendering. This keeps storage and device
collection bounded as browser tab count grows.

## First Application Browser Boundary

The topology application exposes only presentation-specific routes that read the
fabric on the shared NFWeb loopback listener:

| Route | Purpose |
| --- | --- |
| `GET /api/v1/health` | NFWeb health with status grouped by installed application |
| `GET /api/v1/topology/snapshots/{snapshot_id}` | One historical snapshot |
| `GET /api/v1/topology/history` | Ordered retained snapshot IDs for the three-hour timeline |
| `GET /api/v1/topology/logs` | Up to 300 persisted terminal entries for the active device scope |
| `GET /api/v1/topology/devices` | Combined NetBox and Nornir device discovery plus current selection |
| `POST /api/v1/topology/selection` | Validate and apply the shared device scope; collect it when non-empty |
| `POST /api/v1/topology/refresh` | Force one fresh, non-overlapping collection cycle |
| `WS /api/v1/topology/stream` | Latest snapshot for the active scope followed by live snapshots |

Do not expose a generic `run_job` route, task name passthrough, or user-supplied
service/task pair to the browser. Future applications and operational actions must
be added as namespaced, narrowly scoped APIs with authorization, validation, and
audit requirements appropriate to the operation.

## Frontend Behavior

Create one long-lived `ForceGraph3D` scene. New snapshots update graph data in that
scene instead of recreating an iframe or canvas.

The initial topology screen provides:

- an application-only accordion navigation with Topology under Dashboards;
- topology controls in the center application header above the 3D topology view;
- a top-bar multi-device selector populated from combined NetBox and Nornir
  discovery, empty by default, that starts collection only after a scope is
  applied;
- live/paused state and last successful collection time;
- a three-hour time scrubber with a clear return-to-live action;
- independent layer visibility controls;
- health and metadata text filters, including device, site, role, and address data;
- node and link detail panels with source, state, and available metrics;
- weather-map styling: health controls color and utilization controls link width;
- undirected presentation for physical and LLDP relationships even though the
  renderer internally requires `source` and `target` endpoints;
- stable node positions between snapshots where IDs are unchanged;
- settled coordinates pinned and reused across snapshot updates, with an explicit
  layout restart when recalculation is wanted;
- graph controls for view animation, force-layout pause/start, camera rotation,
  node distance, and fixed/connection/traffic-based node sizing;
- dense Status and utilisation, Connections, and Properties inspector tabs, with
  related NetBox, LLDP, and BGP records grouped in the Connections view;
- explicit empty, partial, disconnected, and unsupported-WebGL states;
- a bottom-right, persistent terminal log retaining up to 300 entries for the
  active device scope, following NFCLI's field order and horizontally scrolling
  full, unwrapped lines;
- a manual refresh action that bypasses layer caches without overlapping a cycle;
- keyboard-accessible controls and non-color status labels.

The frontend imports pinned npm packages and produces hashed local assets. It must
not fetch executable JavaScript from a public CDN at runtime.

## Configuration and Operation

Add a typed `client.nfweb` inventory section. Proposed defaults:

```yaml
client:
  nfweb:
    port: 8080
    open_browser: true
    topology:
      collection_interval: 30
      inventory_refresh_interval: 300
      retention_minutes: 180
      request_timeout: 60
      devices: []
      sites: []
      layers:
        inventory: true
        lldp: true
        bgp: true
        interfaces: true
```

Use NFCLI's installed web UI mode:

```bash
nfcli --inventory inventory.yaml --web-ui
```

The loopback bind is mandatory in the first release. `nfcli --web-ui` must not
accept a non-loopback host through configuration or command-line arguments. The application
must also validate browser origins for HTTP state transitions and WebSocket
upgrades. The first release is read-only. Authentication and a new architecture
decision are required before remote access or change operations are introduced.

Tornado is already a core dependency, so the local host adds no Python web-framework
dependency or NFWeb runtime extra. The Python wheel and source distribution include
the compiled frontend output. Contributors need Node.js only when changing or
verifying frontend source.

The default empty `devices` list is intentional: starting NFWeb performs device
discovery for the selector but no topology job. Configured device names provide an
optional startup selection; otherwise an operator applies the scope in the UI.

## Implementation Plan

The obsolete Streamlit files are removed at the start so new work cannot depend on
their iframe bridge, mock data, or 2D rendering path.

### Phase 1: Contracts and Backend Foundation

1. Add typed local web UI configuration and integrate it with `nfcli --web-ui`.
2. Add graph models, adapter protocol, SQLite repository, and deterministic
   retention and merge tests.
3. Add the Tornado loopback host, collector, health/history APIs, origin
   checks, and WebSocket broadcaster.
4. Implement NetBox physical topology and LLDP adapters.

### Phase 2: 3D-Only Frontend

1. Scaffold the Vite/React/TypeScript application and pin Vasturiano dependencies.
2. Build a persistent 3D graph, layers, filters, details, and live connection state.
3. Add the three-hour time scrubber and historical snapshot loading.
4. Add BGP and interface-health adapters and weather-map styling.

### Phase 3: Productization and Cutover

1. Package built assets and document installation, configuration, development, and
   local operation.
2. Add local host API tests and browser tests for live updates, layer filtering,
   playback, selection, reconnection, and failure states.
3. Add the Web UI to the NORFAB feature catalogue.
4. Verify the package contains no Streamlit, iframe-graph, mock-topology, or 2D
   topology code paths.

## Alternatives Considered

### Continue with Streamlit

This minimizes the first code change and remains appropriate for ad-hoc internal
tools. It was rejected as the long-term UI because the current dashboard already
needs custom cross-iframe state bridges to preserve a WebGL scene. A shared
collector, push updates, historical playback, stable client-side state, and future
web applications would increase that accidental complexity.

### Use a Node.js Production Server

This would provide a unified JavaScript stack but would duplicate NORFAB lifecycle,
configuration, packaging, logging, and Python client integration. It also adds an
operator runtime. It was rejected; Node.js remains a build tool only.

### Use the Existing FastAPI Worker

The existing worker can expose NetBox and Nornir tasks to REST clients, but requiring
it would make a local UI depend on another deployed worker, REST authentication,
and topology aggregation in browser code. It would also provide less direct access
than the native client already available on the client computer. It was rejected in
favor of connecting the local application directly to the broker.

### Use FastAPI for the Local Browser Bridge

FastAPI would provide typed routes and WebSockets, but it is an optional NORFAB
service dependency while Tornado is already required by the core. The local bridge
is deliberately small and topology-specific, so adding FastAPI and Uvicorn would
not simplify operation enough to justify another runtime dependency.

### Use Tornado with Handwritten HTML and JavaScript

This removes the frontend framework dependency and is viable for a single page. It
was rejected because the stated goal is an extensible built-in web UI, not only one
graph. Typed components, predictable state updates, routing, and focused tests
justify the small build-time framework cost. Tornado remains the local asset and
data host in either case.

### Store History in Browser Memory

This is simple but creates different histories per user, loses data when no browser
is open, and discards history on refresh. It was rejected in favor of bounded
local-process-owned SQLite storage.

## Consequences

Benefits:

- one local NFWeb runtime can host multiple focused browser applications over one
  native client connection;
- one persistent 3D renderer receives incremental live updates;
- collection load is independent of connected browser count;
- historical playback survives browser and NFWeb restarts;
- frontend assets are deterministic and do not depend on public CDNs;
- Python remains the only production runtime;
- no FastAPI worker or additional Python web framework is required;
- NFWeb has native access to the fabric while each browser-facing application
  remains narrowly scoped;
- layer adapters and versioned graph contracts provide a clear extension point.

Costs:

- contributors who change frontend code need a supported Node.js toolchain;
- release automation must build and verify frontend assets;
- origin validation, CSP, dependency scanning, and asset licensing need explicit
  ownership;
- two test layers are required: Python API/storage tests and frontend/browser tests.

## Acceptance Criteria

- `nfcli --web-ui` starts from a normal NORFAB inventory without a Node.js
  installation, internet access, or FastAPI worker;
- documentation and code treat NFWeb as the generic local web client and topology
  as its first application;
- NFWeb connects to the inventory's existing broker and never starts a broker or
  worker;
- all listeners bind to loopback and reject unsupported browser origins;
- the shipped UI contains no 2D topology renderer or 2D/3D selector;
- the browser creates one Vasturiano 3D graph instance and updates it without losing
  camera or selection state;
- NetBox, LLDP, BGP, and interface layers can be enabled independently and report
  source failures explicitly;
- live snapshots are broadcast at the configured cadence without overlapping
  collection jobs;
- the `topology_snapshots` table contains no snapshot older than the configured
  three-hour window after cleanup;
- the timeline loads a selected stored snapshot and can return to live mode;
- node and link status, freshness, and available metrics are visible without
  relying only on color;
- multiple browser sessions share one collector and one history;
- all executable frontend dependencies are bundled and pinned;
- the local browser API exposes no arbitrary service/task execution route;
- local host tests cover collection, partial failures, retention, response schemas,
  and shutdown; browser tests cover live update, layers, filtering, details,
  history, reconnect, and WebGL failure;
- web UI documentation and `docs/norfab_features.md` match the shipped behavior.

## References

- [Streamlit execution model](https://docs.streamlit.io/develop/concepts/architecture)
- [Tornado documentation](https://www.tornadoweb.org/en/stable/)
- [Vite production build](https://vite.dev/guide/build)
- [Vasturiano 3D Force Graph](https://github.com/vasturiano/3d-force-graph)
- [Vasturiano React Force Graph](https://github.com/vasturiano/react-force-graph)

## Implementation Boundary

This ADR approves NFWeb as the generic local Tornado and native `NFPClient`-based
web client, with an immediate, non-compatible replacement of the experimental
Streamlit client. Keep all NFWeb source, frontend source, and compiled assets inside
`norfab/clients/nfweb/`. The first shipped application and browser API remain
topology-only; future use cases are added as focused NFWeb applications rather than
through a generic job-execution endpoint.
