---
tags:
  - clients
  - web
---

# NFWeb Local Web Client

NFWeb is NORFAB's generic web client for applications that run locally on an
operator's computer. It connects directly to an existing NORFAB broker through the
native Python client and presents focused browser applications to browsers on the
operator's network.

The application sidebar uses Mantine's nested-navbar pattern for Overview,
Dashboards, and Admin. Topology is the first nested dashboard; the other sections
are intentionally empty until additional NFWeb applications are introduced.
Dashboard-specific controls belong to the center application header rather than
the application sidebar.

NFWeb uses Mantine's maintained React components and Tabler icons for its common
interface controls. Selects, buttons, filters, accordions, sliders, tabs, badges,
tooltips, and alerts therefore share one accessible component system. Custom CSS
is reserved for the application grid, 3D topology stage, inspector data, and
terminal event presentation.

The 3D network topology dashboard is NFWeb's **first application**. It proves the
local runtime, frontend packaging, live updates, bounded application storage, and
safe browser boundary, but topology does not define the long-term scope of NFWeb.
Future NFWeb applications can cover other visual operations, assurance,
troubleshooting, reporting, inventory, workflow, and service-specific use cases.

NFWeb does not require a FastAPI worker, Node.js, an internet connection, or a
central web deployment at runtime. It listens on all IPv4 interfaces by default
and does not start a broker or any workers.

## Client and Application Model

NFWeb separates the local client runtime from the applications presented through
it:

```text
Browser
    |
    | HTTP / WebSocket over the local network
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
    host: 0.0.0.0
    port: 9005
    open_browser: true
    footer:
      message: "Managed by the Network Automation team"
      fastapi_url: "http://127.0.0.1:8000/docs"
      docs_url: "https://docs.norfablabs.com/"
      github_url: "https://github.com/norfablabs/NORFAB"
```

The shared footer displays the optional `message` and pictogram links for the
configured FastAPI service, NORFAB documentation, and repository. Set any footer
URL to `null` to hide that link.

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

By default, NFWeb binds to `0.0.0.0:9005`, accepts connections through every IPv4
interface, and prints a browser URL containing the machine's preferred LAN IP.
Configure `host`, `port`, and `open_browser` under `client.nfweb`; set `host` to
`127.0.0.1` to restore local-only access. NFWeb has no separate executable or
command-specific configuration overrides.

Press Ctrl+C once to stop accepting connections and release application storage
and the native NORFAB client. If cleanup becomes stuck, press Ctrl+C a second time
to force the NFWeb process to exit with status 130.

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
6. Require a separate authentication and authorization decision before adding
   change-capable operations or deploying on an untrusted network.

This model allows NFWeb to stay simple for operators while growing beyond the
topology use case.

## Security Boundary

NFWeb binds to every IPv4 interface by default and accepts connections from any
source IP that can reach its port. HTTP routes and WebSocket upgrades do not
restrict the browser origin. The current browser API contains only
topology-specific routes and cannot submit arbitrary NORFAB service or task names.

NFWeb does not currently provide authentication, authorization, origin filtering,
or TLS. Any website reachable by an operator's browser can attempt requests to an
accessible NFWeb instance. Expose it only on a trusted administrative network and
use host firewall rules to restrict reachability where appropriate. Set
`host: 127.0.0.1` when remote access is not required. A deployment on an untrusted
network or behind a reverse proxy requires an explicit authentication,
authorization, forwarding-header, TLS, validation, and audit design.

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
