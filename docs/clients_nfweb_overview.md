---
tags:
  - clients
  - web
---

# NFWeb Local Web Client

NFWeb is NORFAB's generic web client for applications that run locally on an
operator's computer. It connects directly to an existing NORFAB broker through the
native Python client and presents focused browser applications over a local,
loopback-only web host.

The application sidebar uses expandable Overview, Dashboards, and Admin sections.
Topology is the first dashboard; the other sections are intentionally empty until
additional NFWeb applications are introduced. Dashboard-specific controls belong
to the center application header rather than the application sidebar.

The 3D network topology dashboard is NFWeb's **first application**. It proves the
local runtime, frontend packaging, live updates, bounded application storage, and
safe browser boundary, but topology does not define the long-term scope of NFWeb.
Future NFWeb applications can cover other visual operations, assurance,
troubleshooting, reporting, inventory, workflow, and service-specific use cases.

NFWeb does not require a FastAPI worker, Node.js, an internet connection, or a
central web deployment at runtime. It listens only on `127.0.0.1` and does not
start a broker or any workers.

## Client and Application Model

NFWeb separates the local client runtime from the applications presented through
it:

```text
Local browser
    |
    | HTTP / WebSocket on loopback
    v
NFWeb client
    |-- local web host and packaged frontend
    |-- native NFPClient connection
    |-- shared lifecycle, configuration, and browser policy
    |-- applications
        |-- topology (first built-in application)
        |-- future focused applications
    |
    v
Existing NORFAB broker and service workers
```

NFWeb is the reusable client and application host. Each application owns its
domain model, narrowly scoped browser API, collection or execution behavior, and
local state. This prevents the browser from becoming a generic passthrough for
arbitrary NORFAB jobs while allowing new capabilities to use the full native
client inside the trusted local Python process.

## Current Application: 3D Network Topology

The first release opens directly into a live and historical 3D network topology
application. It combines intended and observed network layers into a persistent
Vasturiano scene, provides weather-map status and utilization styling, and retains
a bounded three-hour local history. Its top-bar device selector combines NetBox
devices and Nornir hosts; the default empty selection performs no topology
collection until the operator applies a scope.

See [3D Network Topology Application](clients_nfweb_topology.md) for its data
sources, configuration, storage, controls, and operational behavior.

## Configure NFWeb

Add shared NFWeb settings below `client.nfweb` in `inventory.yaml`:

```yaml
client:
  nfweb:
    port: 8080
    open_browser: true
```

Application settings are grouped by application below `client.nfweb`; see each
application's documentation for its fields. NFWeb runtime data uses
`__norfab__/nfweb/nfweb.sqlite`, with application-owned tables inside that local
database.

## Run NFWeb

Start the broker and the service workers required by the installed NFWeb
applications separately. From the client computer, use NFCLI's web UI mode:

```bash
nfcli --inventory inventory.yaml --web-ui
```

The default address is `http://127.0.0.1:8080`. Configure `port` and
`open_browser` under `client.nfweb`; NFWeb has no separate executable or
command-specific configuration overrides.

The current release routes the root page to the topology application. As more
applications are added, NFWeb can introduce a local application home and
application-specific navigation without changing its broker connection or
production runtime.

## Adding Future Applications

NFWeb applications should follow a small set of boundaries:

1. Keep application code and browser routes namespaced by application.
2. Define typed, presentation-oriented contracts instead of exposing raw worker
   replies directly to the frontend.
3. Add narrowly scoped operations; do not add a generic browser `run_job` endpoint.
4. Reuse the NFWeb process, native client, lifecycle, browser policy, and packaged
   frontend rather than starting another local service.
5. Keep collection, caching, and historical state application-owned so one
   application cannot silently change another application's behavior.
6. Require a separate security decision before adding remote access or
   change-capable operations.

This model allows NFWeb to stay simple for operators while growing beyond the
topology use case.

## Security Boundary

NFWeb is a local client and binds only to IPv4 loopback. Browser requests and
WebSocket upgrades are same-origin. The current browser API contains only
topology-specific, read-only routes and cannot submit arbitrary NORFAB service or
task names.

Do not place NFWeb behind a reverse proxy or expose its local port to another host.
Remote access and change operations require explicit authentication,
authorization, validation, and audit design.

## Develop NFWeb

All NFWeb backend, frontend, and compiled assets live below
`norfab/clients/nfweb`. The compiled frontend is included in the Python package.
Node.js is needed only by contributors changing frontend source:

```bash
cd norfab/clients/nfweb/frontend
npm ci
npm run typecheck
npm run build
```

The build writes packaged assets to `norfab/clients/nfweb/static`. Executable
frontend dependencies are bundled locally; the runtime does not load scripts from
a CDN.

The architecture decision for the NFWeb runtime and its first topology application
is documented in
[NFWeb Local Application Platform and First 3D Topology Application](development/adr_web_ui_topology_architecture.md).
Developers and coding agents should start with the
[NFWeb Developer Guide](development/nfweb_developer_guide.md) before changing the
runtime, application contracts, or frontend.
