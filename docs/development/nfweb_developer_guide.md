---
tags:
  - development
  - clients
  - web
  - topology
---

# NFWeb Developer Guide

This is the working guide for developers and coding agents changing NFWeb. Read
it before editing `norfab/clients/nfweb`. It describes the current implementation,
the boundaries that must remain true, and the shortest safe workflows for extending
the client.

NFWeb is NORFAB's generic local web client. Topology is its first application; it
is not the definition or final scope of NFWeb.

## Start Here

For a new development session:

1. Read `CLAUDE.md` for repository-wide commands and conventions.
2. Read the
   [NFWeb architecture decision](adr_web_ui_topology_architecture.md) for accepted
   product and security boundaries.
3. Read the user-facing [NFWeb overview](../clients_nfweb_overview.md) and
   [topology application guide](../clients_nfweb_topology.md).
4. Inspect the current working tree before editing. NFWeb may be under active
   development, and uncommitted files belong to the developer.
5. Treat the current source and tests as authoritative when this guide and the
   implementation differ. Update this guide when a deliberate architecture or
   contract change makes it stale.

## Preserve These Boundaries

Every NFWeb change must preserve these rules unless a new architecture decision
explicitly replaces them:

- NFWeb is a generic client and local application host. Topology remains a
  namespaced application.
- `nfcli --web-ui` is the only NFWeb launcher. Do not add an `nfweb` executable or
  another dedicated command-line utility.
- NFWeb connects through the native Python `NFPClient` to an existing broker. It
  does not start a broker or workers.
- NFWeb does not depend on the FastAPI worker. Do not route local browser requests
  through a FastAPI service just to reach the fabric.
- The browser API exposes focused application operations. It must not expose a
  generic `service`, `task`, and `kwargs` job-execution endpoint.
- The listener remains fixed to `127.0.0.1`. Remote access requires a separate
  authentication, authorization, audit, and deployment design.
- State-changing requests require exact same-origin validation and an
  operation-specific `X-NFWeb-Request` marker.
- Production requires Python only. Node.js is a frontend development and release
  build tool.
- Frontend dependencies are pinned and bundled. Do not add runtime CDN assets.
- Use Mantine components and Tabler icons for general-purpose controls. Do not
  create bespoke buttons, selects, dropdowns, tabs, sliders, badges, or tooltips.
  Keep custom CSS focused on NFWeb layout and domain-specific visualization.
- The topology application uses Vasturiano 3D visualization only. Do not add a 2D
  renderer or a 2D/3D mode.
- An empty device selection performs no topology collection.
- Operational failures remain visible. Do not fabricate topology, health, or
  metrics when a worker does not return data.
- Local application history is bounded. Topology defaults to a maximum three-hour
  retention window.

## Repository Map

```text
norfab/clients/nfweb/
|-- __init__.py
|-- application.py            Shared NFWeb application-module protocol
|-- config.py                 Shared NFWeb configuration
|-- runtime.py                nfcli lifecycle, module composition, shutdown
|-- server.py                 Shared Tornado host and browser security policy
|-- topology/
|   |-- application.py        Topology module lifecycle and route composition
|   |-- config.py             Topology application configuration
|   |-- models.py             Authoritative Python browser/storage contracts
|   |-- layers.py             NORFAB calls and layer adapters
|   |-- collector.py          Scheduling, caching, merge, publication
|   |-- history.py            Compressed SQLite snapshots and derived logs
|   `-- web.py                Topology HTTP, WebSocket, and broadcaster
|-- frontend/
|   |-- package.json          Pinned frontend tools and runtime dependencies
|   |-- package-lock.json     Reproducible dependency lock
|   |-- vite.config.ts        Development proxy and static build destination
|   `-- src/
|       |-- main.tsx          React entry point
|       |-- App.tsx           Topology state and dashboard composition
|       |-- TopologyGraph.tsx Lazy-loaded Vasturiano/Three.js graph
|       |-- api.ts            Typed HTTP and WebSocket client
|       |-- graphModel.ts     Graph identities, styling, and curve helpers
|       |-- types.ts          Manual TypeScript mirror of Python contracts
|       |-- components/       Mantine toolbar, navigation, inspector, timeline
|       `-- styles.css        NFWeb layout, topology stage, inspector, event log
`-- static/                   Generated production assets served by Tornado

tests/clients/nfweb/
|-- test_config.py            Strict configuration and safety defaults
|-- test_collector.py         Worker payloads, adapters, merge, failures, events
|-- test_history.py           Retention, scope filtering, persistent logs
|-- test_server.py            Routes, request policy, static assets
`-- test_frontend_contracts.py Python/TypeScript fields and packaged assets
```

Do not edit `norfab/clients/nfweb/static` by hand. `npm run build` deletes and
regenerates that directory from `frontend/src`.

## Understand the Runtime

`norfab/utils/nfcli.py` handles `--web-ui` and calls
`norfab.clients.nfweb.runtime.serve()`.

The runtime performs this lifecycle:

```text
nfcli --web-ui
  -> load the normal NORFAB inventory
  -> validate client.nfweb with NFWebConfig
  -> create the native client named "nfweb"
  -> open __norfab__/nfweb/nfweb.sqlite
  -> compose NFWeb application modules
  -> validate and create the Tornado application
  -> listen on 127.0.0.1 only
  -> start periodic collection when a scope exists
  -> optionally open the browser
  -> on first Ctrl+C: stop HTTP, modules, SQLite, and native client
  -> on second Ctrl+C: force process exit if graceful cleanup is stuck
```

The `NorFab` object is used to load inventory and create the client. NFWeb does not
call `nf.start()` and therefore does not start local topology processes.

### Configuration Ownership

`client.nfweb` contains shared runtime configuration. Each application owns a
nested configuration model:

```yaml
client:
  nfweb:
    port: 9005
    open_browser: true
    footer:
      message: "Managed by the Network Automation team"
      fastapi_url: "http://127.0.0.1:8000/docs"
      docs_url: "https://docs.norfablabs.com/"
      github_url: "https://github.com/norfablabs/NORFAB"
    topology:
      devices: []
      collection_interval: 30
      inventory_refresh_interval: 300
      retention_minutes: 180
      request_timeout: 60
      netbox_workers: any
      nornir_workers: all
      layers:
        inventory: true
        lldp: true
        bgp: true
        interfaces: true
```

All configuration models use `extra="forbid"`. Do not silently accept unknown
settings. The listener host is intentionally not configurable.

`footer` is shared shell configuration. Only these display-safe fields are
returned by `/api/v1/config`; application configuration and broker details must
not be exposed to the browser. A `null` footer URL hides its pictogram link.

## Follow Topology Data Through the System

The topology data path is:

```text
NetBox and Nornir workers
  -> layer adapters produce LayerPatch values
  -> TopologyCollector merges patches into TopologySnapshot
  -> TopologyHistoryStore compresses and stores the snapshot
  -> TopologySnapshotBroadcaster publishes it over WebSocket
  -> React filters the snapshot and updates ForceGraph3D
```

### Discovery Is Separate From Collection

Device discovery combines:

- NetBox `get_devices`, filtered by configured sites when present;
- Nornir `get_nornir_hosts`.

Discovery returns the union of names and their sources. It does not collect graph
data. The collector begins only after the operator applies a non-empty selection
or `topology.devices` supplies a startup scope.

Changing the selected devices validates them against discovery, sorts and
deduplicates them, clears all layer caches, and immediately performs a forced
collection. Clearing the selection clears the active view and stops later
periodic cycles from submitting work.

### Worker Calls

| Purpose | Service and task | Important kwargs |
| --- | --- | --- |
| Discover NetBox devices | `netbox.get_devices` | `filters=[{"name__iregex": ".*"}]`; adds `site` when configured |
| Discover Nornir devices | `nornir.get_nornir_hosts` | none |
| Intended topology | `netbox.get_topology` | `devices=[...]` for the active scope |
| Observed adjacency | `nornir.parse_ttp` | `get="lldp_neighbors"`, `FL=[...]` |
| BGP sessions | `nornir.parse_ttp` | `get="bgp_neighbors"`, `FL=[...]` |
| Resolve BGP peer IPs | `netbox.crud_read` | unresolved IP addresses only |
| Interface state | `nornir.parse_ttp` | `get="interfaces_status"`, `FL=[...]` |

Use these exact TTP getter names. In particular, interface collection uses
`interfaces_status`.

`_submit_job()` always uses the native client's asynchronous `submit_job()` API and
retains events from the returned future. Worker errors become
`TopologyCollectionError` values; usable results from other workers remain in a
partial snapshot.

### Scheduling and Caching

`TopologyCollector` submits native NORFAB jobs with `submit_job` and asynchronously
waits for their futures without blocking Tornado's event loop. An `asyncio.Lock`
prevents overlapping topology collection cycles.

Adapters run in dependency order:

1. inventory;
2. LLDP;
3. BGP;
4. interface observations.

Inventory populates the IP-to-device map before BGP resolution. Each adapter has
an independent cache timestamp. Normal periodic collection reuses a fresh cache;
the Refresh action calls `collect(force=True)` and bypasses every layer cache.

Do not add another independent browser-owned polling loop. One collector is shared
by all browser tabs.

## Keep Graph Contracts Stable

The Pydantic models in `topology/models.py` are the authoritative contracts for
storage and browser responses. `frontend/src/types.ts` is a manual mirror. A field
change is incomplete until both sides and their tests are updated.

### Node Rules

- `TopologyNode.id` is the stable merge and ForceGraph identifier.
- A node can belong to multiple layers.
- Duplicate nodes merge by ID. Health becomes the worst reported health, layers
  are unioned, and stronger device metadata replaces placeholder metadata.
- Unresolved BGP addresses use the IP as an `external-peer` node ID.
- Do not use labels as IDs unless the worker contract guarantees the label is the
  canonical device identity.

### Link Rules

- `TopologyLink.id` is the merge identity.
- Link IDs include the layer, both devices, and available interfaces.
- `_link_id()` sorts its two `device:interface` endpoints. LLDP reverse
  advertisements with exactly matching names therefore produce one link.
- `source` and `target` are required by ForceGraph but do not automatically mean a
  relationship is directional. LLDP and physical cables are undirected.
- Exact normalization matters. `Ethernet1` and `Eth1`, or a short hostname and an
  FQDN, create different endpoint IDs. Add an explicit normalization policy and
  tests before trying to collapse those variants.
- Layers intentionally remain separate. A NetBox cable and an LLDP observation of
  that cable currently produce separate blue and gold links with different IDs.
- Multiple real cables between the same devices remain distinct because interface
  names are part of the ID.
- The interfaces adapter creates observations, not standalone graph links. During
  merge, an observation decorates a matching link endpoint with health,
  attributes, and metrics. The frontend therefore excludes `interfaces` from the
  graph-layer visibility controls.

The frontend currently groups all links between the same two node IDs and gives
them parallel curves. Link colour represents the discovery layer. Node colour and
the inspector carry health.

### Snapshot Rules

Snapshot status is derived after merging:

- `complete`: graph data and no errors;
- `partial`: graph data plus one or more errors;
- `failed`: errors and no graph data;
- `empty`: neither graph data nor errors.

Unknown values must remain unknown. Do not turn a missing rate, utilization, or
state into zero or healthy.

## Work With History and Logs

The generic database is:

```text
<inventory-base>/__norfab__/nfweb/nfweb.sqlite
```

Topology owns the `topology_snapshots` table. Each row stores a timestamp and a
zlib-compressed JSON representation of the complete `TopologySnapshot`.

History and logs are filtered by an exact, sorted device list. Logs are not stored
in a second table. `TopologyHistoryStore.logs()` derives terminal entries from the
events and errors embedded in retained snapshots and returns at most 300 entries.

Cleanup runs when the store opens and after every insert. The configuration model
prevents retention beyond 180 minutes.

For a future application, add application-owned tables inside the same generic
database. Do not name the database after topology, and do not reuse the topology
snapshot table for an unrelated domain model.

## Use the Browser API Deliberately

Current routes are:

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/health` | Shared runtime and application health |
| `GET` | `/api/v1/config` | Display-safe shared footer configuration |
| `GET` | `/api/v1/topology/devices` | Combined device discovery and active scope |
| `POST` | `/api/v1/topology/selection` | Apply a scope and collect when non-empty |
| `POST` | `/api/v1/topology/refresh` | Force a cache-bypassing collection |
| `GET` | `/api/v1/topology/history` | Timestamped snapshot entries for the active scope |
| `GET` | `/api/v1/topology/snapshots/{id}` | One stored snapshot |
| `GET` | `/api/v1/topology/logs` | Up to 300 retained terminal entries |
| WebSocket | `/api/v1/topology/stream` | Latest and newly completed snapshots |

POST routes validate both the browser `Origin` and an operation-specific request
marker. WebSocket upgrades accept only the exact local HTTP origin. Static assets
receive a restrictive content security policy.

Add new endpoints under an application namespace. Add the Python handler, route,
frontend method, TypeScript response type, and server test in one change.

## Understand the Current Frontend

The current frontend has one shared component system:

- `main.tsx` mounts one React application in strict mode inside `MantineProvider`
  and behind a fatal error boundary.
- `api.ts` owns JSON requests and WebSocket reconnection.
- `types.ts` mirrors the Pydantic browser contracts.
- `App.tsx` owns topology state and composes the shell, graph, inspector, timeline,
  navigation, and `TopologyToolbar` components.
- `TopologyGraph.tsx` isolates the imperative Vasturiano/Three.js integration and
  is loaded only when the topology view is rendered.
- `graphModel.ts` contains renderer-independent graph identities and calculations.
- Mantine supplies common controls and interaction states; `styles.css` owns the
  shell grid and domain-specific graph, inspector, and terminal presentation. Do
  not target Mantine's internal class names from this stylesheet.

### Frontend Stack

`frontend/package.json` and `frontend/package-lock.json` are the source of truth
for frontend versions. The current stack is:

| Concern | Technology | Responsibility |
| --- | --- | --- |
| UI runtime | React and React DOM `19.2.8` | Component rendering, state, and browser mounting |
| Language | TypeScript `7.0.2` | Static checking for components, graph models, and API contracts |
| Component system | Mantine Core and Hooks `9.5.2` | Standard controls, layout primitives, overlays, themes, and interaction hooks |
| Icons | Tabler Icons React `3.46.0` | Consistent application and footer pictograms |
| Topology renderer | React Force Graph 3D `1.29.1` | React integration for the interactive 3D topology |
| 3D engine | Three.js `0.185.1` | WebGL rendering and graph scene objects |
| Build tooling | Vite `8.2.2` with the React plugin `6.1.0` | Development server, module bundling, and hashed production assets |
| Unit tests | Vitest `4.1.11` | Component, graph-model, and regression tests without a browser |
| Browser tests | Playwright `1.62.1` | Chromium end-to-end tests for the rendered application and its controls |

The browser entry point imports Mantine's base stylesheet before NFWeb's
`styles.css`. Use Mantine components and their public props for general-purpose
controls. Use Tabler icons for application actions. Reserve custom CSS and React
components for NFWeb-specific layout, topology, inspector, and terminal behavior.

Vite writes the production bundle to `norfab/clients/nfweb/static`. The Python
server serves those committed assets directly, so production does not require
Node.js or a CDN. The topology renderer is lazy-loaded to keep its Three.js code
out of the initial application bundle.

The left navigation follows Mantine UI's nested-navbar pattern for generic NFWeb
applications and remains a fixed-width shell column. Topology controls, including
the live status and history selector, belong in one non-wrapping, horizontally
scrollable application toolbar, not the navigation panel. Graph-producing layers
use Mantine button-style checkbox chips for direct multi-selection. The remaining
desktop content width is split 80% for the topology stage and 20% for the
inspector, and the inspector spans into the top-right corner above its content.
Every inspector tab uses the same Mantine searchable, sortable table composition;
add domain columns and row adapters instead of another details layout. A shared
footer owns the configured message and external resource pictograms. Overview and
Admin are intentionally empty placeholders.

### Live and Historical State

The frontend retains the newest WebSocket snapshot separately from the frame being
displayed. In live mode, new frames update the graph. Selecting history from the
top bar's timestamp dropdown disables live display without stopping collection.
Return to live selects the newest known snapshot.

Collection logs are merged by stable entry ID and bounded to 300 lines in browser
memory. The initial `/logs` request restores retained events after page reload.

### Vasturiano and Three.js Rules

`react-force-graph-3d` wraps an imperative Three.js graph. Follow these rules:

- Pass graph data through the React `graphData` prop.
- The React ref exposes animation, camera, force, and refresh methods, but it does
  **not** expose the underlying library's `graphData()` getter. Calling
  `graphRef.current.graphData()` causes a runtime `TypeError`.
- Vasturiano mutates node objects with `x`, `y`, `z`, velocity, and resolved link
  endpoints. Use `endpointId()` whenever a link endpoint may be either a string or
  a mutated node object.
- `renderedGraphData` retains the actual object passed to the graph so callbacks
  can read mutated coordinates safely.
- `positions` stores coordinates by stable node ID before a live snapshot is
  replaced.
- Pausing layout pins nodes through `fx`, `fy`, and `fz`. Starting layout removes
  those fields and reheats the D3 force simulation.
- Layout distance changes the link force's `distance` parameter. It is not camera
  zoom.
- Pausing the view stops rendering animation. It is separate from pausing the
  force layout.
- Node labels are Three.js sprites added with `nodeThreeObjectExtend`; they do not
  replace the selectable node sphere.
- Do not recreate the graph solely to update controls or a snapshot. Preserve the
  camera, selection, and saved coordinates.

LLDP and physical cabling are displayed as undirected relationships. The graph
library still requires `source` and `target` fields, but the UI uses bidirectional
labels and does not render directional particles. Introduce directional cues only
for a layer or metric whose contract actually defines direction.

## Run a Development Environment

NFWeb needs an existing broker and the workers used by the selected applications.
Start those processes separately, then run from the repository root:

```bash
poetry run nfcli --inventory tests/nf_tests_inventory/inventory.yaml --web-ui
```

NFWeb normally opens `http://127.0.0.1:9005`. Use `open_browser: false` while
restarting the backend frequently.

For frontend dependencies and a production-style build:

```bash
cd norfab/clients/nfweb/frontend
npm ci
npm test
npx playwright install chromium
npm run test:e2e
npm run typecheck
npm run build
```

Playwright starts an isolated Vite server on `127.0.0.1:4173`. Its checked-in
fixtures mock the browser API and topology WebSocket, so browser tests do not
require a running broker or worker. Run `npm run test:e2e:headed` to observe the
same tests in a visible Chromium window.

The build output goes directly to `../static`. A backend restart is required for
Python changes. A hard browser refresh loads a newly hashed frontend bundle after a
frontend build.

Vite development mode runs on `127.0.0.1:5173` and proxies `/api` to port 9005:

```bash
cd norfab/clients/nfweb/frontend
npm run dev
```

When changing live delivery, verify both HTTP requests and the topology WebSocket;
do not assume that a working HTTP proxy proves WebSocket upgrades work.

## Verify Changes

Run focused checks from the repository root:

```bash
poetry run pytest tests/clients/nfweb -q
```

For frontend changes:

```bash
cd norfab/clients/nfweb/frontend
npm test
npm run build
```

`npm run build` runs both TypeScript projects before Vite creates production
assets. The large WebGL renderer is emitted as a lazy chunk, keeping it out of the
initial application bundle. Set `NFWEB_SOURCEMAPS=true` to emit hidden source maps
for a diagnostic build; production builds omit them by default.

For documentation changes:

```bash
poetry run inv docs-build
```

Also run the smallest relevant repository check for shared code changes. For
example, changing `ClientConfig` or NFCLI launch behavior is broader than the
NFWeb-focused test suite.

### Minimum Test Matrix

| Change | Required verification |
| --- | --- |
| Config field | Config validation test and NFWeb tests |
| Adapter or worker payload | Collector fixture with success, missing data, and worker error |
| Merge or identity rule | Forward/reverse and multi-link tests with exact IDs |
| History schema or retention | Round trip, scope filtering, cleanup, and restart behavior |
| HTTP or WebSocket contract | Server test plus matching TypeScript type |
| React calculation or formatting | Vitest, type-check, and production build |
| WebGL graph lifecycle | Production build and browser validation |
| Packaged asset behavior | Build, serve through Tornado, and hard-refresh test |
| Documentation navigation | MkDocs build |

Focused Vitest coverage exists for graph calculations and inspector formatting.
There is currently no automated WebGL browser suite, so manually validate graph
lifecycle changes in a WebGL-capable browser.

## Use Focused Change Playbooks

### Add or Change a Topology Field

1. Update the appropriate model in `topology/models.py`.
2. Populate or merge it in `layers.py` or `collector.py`.
3. Update `frontend/src/types.ts`.
4. Update filtering, rendering, or inspector code only where the field is used.
5. Add a collector or server assertion for the serialized value.
6. Build the frontend and update user documentation when behavior changes.

### Add a Topology Layer

1. Add a strict configuration switch.
2. Implement `TopologyLayerAdapter` and return a `LayerPatch`.
3. Choose stable node and link identities before adding presentation code.
4. Add it to `enabled_adapters()` in dependency order.
5. Add its label and colour to the frontend.
6. Test worker failures, partial payloads, deduplication, and merge behavior.
7. Document its NORFAB source and operational meaning.

Do not make an independent scheduler or database for a layer. Those are
application responsibilities.

### Add a Browser Operation

1. Confirm the operation is narrowly scoped to one application.
2. Add a Tornado handler under `/api/v1/<application>/...`.
3. For a state change, require exact origin plus a unique request marker.
4. Add the matching method and type in `api.ts` and `types.ts`.
5. Add success, invalid input, conflict, and cross-origin tests as applicable.

### Add Another NFWeb Application

1. Create an application-owned Python package, models, configuration, and state.
2. Add namespaced routes and contracts; do not expose raw worker results.
3. Reuse the shared native client, loopback listener, database location, browser
   policy, and lifecycle.
4. Give the application its own tables and retention behavior where required.
5. Add a frontend view and navigation entry without forcing its domain into
   topology models.
6. Register the module in `runtime.py`; the shared server discovers its routes,
   health, startup, and shutdown behavior through `NFWebApplicationModule`.

The Python host is application-neutral. The current frontend opens Topology as its
only implemented view; add a view registry only when a second application provides
concrete requirements for one.

## Troubleshoot Efficiently

### Collection Finishes but the Graph Is Empty

Check, in order:

1. the active selected-device count;
2. snapshot status and node/link counts;
3. Collection events and layer errors;
4. active search, health, and layer filters;
5. raw worker payload shape against the adapter fixture;
6. browser console errors.

A successful job does not guarantee its payload matches the adapter's expected
shape.

### A Link Appears Twice

Inspect link `layer`, ID, both device names, and both interface names. Common valid
cases are:

- NetBox and LLDP observations of the same cable;
- separate data and management links;
- two real parallel interfaces.

For reverse LLDP advertisements, canonical IDs are identical when device aliases
resolve uniquely to the selected scope and interfaces use a supported common short
or long spelling. If they are not, compare hostname qualification, ambiguous
aliases, and vendor-specific interface names. Do not deduplicate only by device
pair because that would collapse real parallel cables.

### The Graph Rearranges on Every Snapshot

Confirm that node IDs remain stable, coordinates are saved before replacing the
snapshot, and new `graphData` nodes receive saved coordinates. Do not call
`zoomToFit()` on every update.

### The Browser Loads an Old UI

Run `npm run build`, inspect `static/index.html` for the new hashed asset name, and
hard-refresh the browser. Static hashed assets are immutable; the HTML shell is
served with `no-cache`.

### The WebSocket Disconnects

Verify the exact scheme and host in the `Origin`, confirm the backend is running,
and inspect the browser network panel. The frontend reconnects with exponential
backoff up to ten seconds.

## Known Gaps

Keep these visible when planning work:

- The frontend has one implemented application view. A generic view registry is
  intentionally deferred until a second application establishes its requirements.
- TypeScript contracts remain manually authored, although an automated field-level
  parity test now prevents silent drift from the authoritative Pydantic models.
- Graph calculations have focused Vitest coverage, but there is no automated
  WebGL/browser lifecycle suite.
- The lazy WebGL chunk remains inherently large; it is excluded from the initial
  application bundle and covered by an explicit Vite warning threshold.
- LLDP canonicalization covers case, FQDN variants, whitespace, and common
  interface abbreviations. Ambiguous device aliases and vendor-specific interface
  spellings are deliberately preserved rather than guessed.

NetBox intent and LLDP observations intentionally remain separate edges. This
preserves independent layer visibility, source-specific properties, and the
requested layer colors; combining them would require an explicit multi-source edge
contract. Empty Overview and Admin navigation sections are reserved extension
points, not incomplete topology behavior.

Do not solve these gaps incidentally during an unrelated change. Make the smallest
coherent change, add tests for the intended behavior, and update this list when a
gap is deliberately resolved.

## Definition of Done

Before handing NFWeb work to another developer or coding agent:

- requested behavior is implemented without weakening the boundaries above;
- Python and TypeScript contracts agree;
- focused Python tests pass;
- the frontend production build passes when frontend source changed;
- generated static assets are updated when frontend source changed;
- browser behavior is manually checked for graph lifecycle changes;
- user documentation and this guide reflect changed behavior;
- unrelated working-tree changes are preserved;
- the handoff states what changed, what was verified, and any remaining limitation.
