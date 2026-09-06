# ADR: NFWeb Local Application Platform and 3D Topology Architecture

- **Status:** Accepted
- **Date:** 24 August 2026
- **Last amended:** 6 September 2026
- **Decision owners:** NORFAB maintainers
- **Scope:** Generic local NORFAB web client and its 3D topology application

## Context

NFWeb replaced the experimental Streamlit topology prototype with a generic,
Python-hosted local web client. Tornado hosts a packaged React application and
connects to the existing NORFAB broker through a native `NFPClient`. The topology
application owns collection, normalization, bounded history, browser routes, and
3D presentation.

The first topology implementation discovers devices from both NetBox and Nornir.
It reads device metadata and intended physical links directly from NetBox, then
adds live LLDP, BGP, and interface state from Nornir. This duplicates data already
cached in Nornir inventory and performs poorly when NetBox devices have hundreds
of interfaces and connections.

Nornir inventory can already contain NetBox-derived device attributes,
interfaces, interface IP addresses, connections, circuits, and BGP peerings.
NFWeb should reuse that cached data, query NetBox only for its dedicated topology
result and unresolved BGP addresses, and restrict live collection to devices
managed by Nornir.

NFWeb must also be validated with thousands of displayed nodes and links before
production inventories reach that size. The dedicated environment and fixture
design for that validation is defined separately in
[ADR: NFWeb Scale-Test Environment](adr_nfweb_scale_test_environment.md).

## Decision

Retain NFWeb as the generic Tornado and React application host, and refactor its
topology application around a Nornir-first source model.

### NFWeb Runtime

- `nfcli --web-ui` remains the only launcher.
- NFWeb connects to an existing broker through a native `NFPClient`; it does not
  start a broker or workers.
- Browser code never connects to ZeroMQ and never receives broker credentials.
- NFWeb remains independent of the FastAPI worker.
- Tornado serves the packaged React application, namespaced JSON routes, and
  WebSocket streams.
- Python is the only production runtime. Node.js is required only for frontend
  development and release builds.
- The topology application uses Vasturiano `ForceGraph3D` only. No 2D renderer or
  2D/3D selector is provided.
- The browser API exposes focused topology operations, never a generic NORFAB
  service/task passthrough.
- NFWeb retains its current remotely reachable listener and permissive origin
  policy. Deployments must restrict access to trusted networks or use a secured
  reverse proxy because NFWeb has no built-in authentication, authorization, or
  TLS.

Topology is one NFWeb application, not the boundary of the web client. Future
applications own their configuration, routes, state, collection, persistence, and
frontend composition within the shared runtime.

## Topology Source Model

### Device Discovery and Scope

Nornir is the authoritative source of selectable devices. NFWeb discovers devices
only through:

```text
nornir.get_nornir_hosts
```

NetBox-only devices do not appear in the selector. An empty selection performs no
topology collection. An optional configured startup selection is validated against
the current Nornir hosts before collection begins.

After a non-empty selection is applied, every collection cycle is scoped to the
selected Nornir hosts. Multiple Nornir workers may contribute different hosts and
their results form a superset. The initial implementation assumes the same host is
not duplicated across Nornir workers and does not add worker-ownership machinery.

### Initial Nornir Seed

NFWeb reads the selected hosts through the existing dedicated inventory task:

```text
nornir.get_inventory, FL=<selected devices>
```

The result supplies the initial graph seed and may contain:

- host name, hostname, platform, and groups;
- role, site, status, manufacturer, device type, tags, and primary address;
- interfaces and interface IP addresses;
- cached connections;
- cached circuits;
- cached BGP peerings.

NFWeb copies only topology-safe fields into its browser contract. Credentials,
connection options, arbitrary host data, and unrelated configuration context are
not copied.

Optional topology structures may be absent or empty. This is normal and does not
produce a warning or collection error.

### NetBox Topology

NetBox remains the source of desired physical topology. NFWeb calls only:

```text
netbox.get_topology, devices=<selected Nornir hosts>
```

The call never enumerates the complete NetBox device inventory. A successful
empty result is normal. Directly connected adjacent nodes returned by
`get_topology` remain visible even when they are not selected Nornir hosts. NFWeb
does not recursively expand those adjacent nodes or run live collection against
them.

NetBox topology complements Nornir inventory and live discovery. It is not
required to return every selected host or link.

### Live Nornir Collection

NFWeb collects live state for selected Nornir hosts through:

| Purpose | Task |
| --- | --- |
| LLDP adjacency | `nornir.parse_ttp`, `get=lldp_neighbors` |
| BGP sessions | `nornir.parse_ttp`, `get=bgp_neighbors` |
| Interface state and statistics | `nornir.parse_ttp`, `get=interfaces_status` |

Refresh bypasses NFWeb's layer caches and repeats the scoped inventory, NetBox
topology, and live Nornir reads. It does not refresh or mutate the Nornir worker's
inventory.

### BGP Resolution

NFWeb resolves BGP peer addresses in this order:

1. Interface IP addresses from Nornir inventory.
2. Nornir host primary or management addresses.
3. A NetBox IP address lookup for unresolved peers.
4. The live peer group as a display-label fallback.
5. The peer IP address when no other label is available.

Peer IPs remain the stable identity. A peer-group fallback is displayed as
`<peer-group> (<peer-ip>)`.

## Topology Domain Model

The Python Pydantic models are authoritative. TypeScript mirrors their browser
contract.

```json
{
  "snapshot_id": "01K...",
  "collected_at": "2026-09-06T05:20:30Z",
  "duration_ms": 1840,
  "status": "complete",
  "devices": ["spine-1", "leaf-1"],
  "layers": ["topology", "lldp", "bgp", "interfaces"],
  "nodes": [
    {
      "id": "spine-1",
      "label": "spine-1",
      "health": "healthy",
      "origin": ["netbox", "nornir"],
      "attributes": {"site": "dc-1", "role": "spine"}
    }
  ],
  "links": [
    {
      "id": "topology:spine-1:ethernet1--leaf-1:ethernet49",
      "source": "spine-1",
      "target": "leaf-1",
      "layer": "topology",
      "health": "healthy",
      "origin": ["netbox", "nornir"],
      "metrics": {},
      "attributes": {
        "source_interface": "Ethernet1",
        "target_interface": "Ethernet49"
      }
    }
  ],
  "errors": [],
  "events": []
}
```

### Identity and Origin

- Nodes and links have stable IDs.
- Nodes do not have an inferred `kind`. Neither NetBox nor Nornir alone can
  determine whether a device is external to a network.
- Every node and link has an `origin` list.
- The complete origin vocabulary is `netbox`, `nornir`, and `live-lldp`.
- Origins are unioned and sorted when objects merge.
- Layers describe topology semantics; origins describe provenance.
- Source-specific fields remain under `attributes` until promoted into the common
  contract.

### Attribute Precedence

NetBox attributes override equivalent Nornir inventory attributes. Nornir fills
attributes absent from NetBox. Conflicting values are not duplicated under
source-qualified names.

Health is the worst reported value and is one of `healthy`, `warning`, `critical`,
or `unknown`. Missing metrics remain unknown and are never invented as zero.

### Physical Connections and Circuits

Physical relationships merge by normalized device and interface endpoints. A
connection reported by NetBox and Nornir becomes one relationship with both
origins.

Circuits use the concrete circuit type and other fields present in Nornir
inventory. NFWeb does not invent circuit node kinds or classifications. A circuit
with the same resolved endpoints as another physical connection merges with that
relationship while retaining its circuit attributes. Provider or unresolved
endpoints use the concrete identifiers in the source data.

### BGP Sessions

Cached inventory and live BGP sessions share the BGP layer. Normalized session IP
addresses form the deduplication key, including reverse advertisements. Matching
records merge and preserve their combined origin. Inventory-only and live-only
sessions remain visible.

### Errors and Partial Data

Absent topology data and successful empty results are normal. Explicit worker
failures and timeouts remain collection errors. NFWeb retains all usable results,
marks the snapshot `partial`, and displays a useful error at the top of the
application.

## Browser Controls

The frontend maintains one long-lived `ForceGraph3D` scene and updates its data
without discarding stable coordinates, camera state, or the current selection.

The link controls are:

- **Topology:** a normal multi-select union filter containing NetBox, Nornir,
  LLDP, and Circuits. NetBox, Nornir, and LLDP use `origin`; Circuits matches
  concrete circuit data.
- **Protocols:** contains BGP and is the extension point for later protocols.
- **Stats:** a mutually exclusive selector containing Off, Traffic, Errors, and
  Flaps. It is not a checkbox group.

Traffic uses interface rate and utilization. Errors turns a link red when any
current `errors_in`, `errors_out`, or `crc_errors` counter is non-zero. Flaps uses
the interface transition counter:

- 0 through 10 is green;
- 11 through 100 is yellow;
- above 100 is red.

Links without the selected statistics remain visible in subdued grey. The graph
does not hide structural topology merely because telemetry is unavailable.

The browser also provides health and text filtering, node and link inspection,
layout pause and restart, camera rotation, node-distance and node-size controls,
historical snapshot selection, return to live state, WebSocket reconnection, and
a bounded scope-aware terminal.

## Configuration

Topology configuration remains below `client.nfweb.topology`:

```yaml
client:
  nfweb:
    topology:
      devices: []
      collection_interval: 30
      inventory_refresh_interval: 300
      retention_minutes: 180
      request_timeout: 60
      netbox_workers: any
      nornir_workers: all
      layers:
        topology: true
        lldp: true
        bgp: true
        interfaces: true
```

The previous `sites` setting, combined NetBox/Nornir discovery, `kind` field,
`inventory` layer name, and old toolbar grouping are removed. No compatibility
shim or deprecated aliases are retained. Tests, frontend types, documentation, and
configuration examples move directly to the new contract.

## Persistence and Browser Boundary

NFWeb stores compressed topology snapshots in the application-owned
`topology_snapshots` table within:

```text
<inventory-base>/__norfab__/nfweb/nfweb.sqlite
```

Retention defaults to three hours and is bounded to that maximum. Cleanup runs at
startup and after inserts. History and logs are filtered by the exact sorted
device scope. Logs are derived from retained snapshot events and errors rather
than stored in a separate table.

The topology browser API remains namespaced:

| Route | Purpose |
| --- | --- |
| `GET /api/v1/topology/devices` | Nornir device discovery and current selection |
| `POST /api/v1/topology/selection` | Validate and apply a non-empty or cleared scope |
| `POST /api/v1/topology/refresh` | Force one non-overlapping scoped collection |
| `GET /api/v1/topology/history` | Retained timestamps for the active scope |
| `GET /api/v1/topology/snapshots/{id}` | One retained snapshot |
| `GET /api/v1/topology/logs` | Bounded events and errors for the active scope |
| `WS /api/v1/topology/stream` | Latest and newly completed snapshots |

One collector is shared by all browser tabs. An asynchronous lock prevents
overlapping cycles. Browser tab count does not multiply NORFAB collection load.

## Implementation Plan

### Phase 1: Contracts and Inventory Source

1. Replace combined device discovery with Nornir-only discovery.
2. Remove `kind`, add the `origin` list, and rename the physical topology layer.
3. Add scoped Nornir inventory adaptation with a strict metadata whitelist.
4. Remove obsolete configuration, types, frontend code, tests, and documentation.

### Phase 2: Topology and Protocol Merging

1. Restrict `netbox.get_topology` to selected Nornir hosts.
2. Adapt Nornir connections, circuits, interface addresses, and BGP peerings.
3. Merge physical records by endpoints and BGP records by session IPs.
4. Resolve BGP peers from Nornir addresses before using the NetBox fallback.
5. Preserve partial results while distinguishing successful emptiness from worker
   failures.

### Phase 3: Frontend

1. Update TypeScript contracts for `origin` and removal of `kind`.
2. Replace the old link groups with Topology and Protocols selectors.
3. Add the exclusive Off, Traffic, Errors, and Flaps Stats selector.
4. Add origin, circuit, missing-statistics, and top-level error presentation.
5. Rebuild and verify packaged frontend assets.

## Alternatives Considered

### Continue Reading Complete Topology Data from NetBox

Rejected because it duplicates cached Nornir inventory and makes collection time
depend on large NetBox interface datasets.

### Retain Combined NetBox and Nornir Device Discovery

Rejected because live collection is Nornir-scoped and NetBox-only selectable
devices create incomplete and misleading operational coverage.

### Preserve the Previous Browser and Snapshot Contract

Rejected. The topology application is refactored directly to the new contract;
unused compatibility fields and aliases would add complexity without a required
consumer.

## Consequences

Benefits:

- NetBox reads are limited to selected-host topology and unresolved BGP mapping;
- cached Nornir data seeds the graph without repeating broad NetBox reads;
- selected devices always have a Nornir management path;
- intended, cached, and live topology can be compared through merged origins;
- missing optional inventory structures do not create false alarms;
- the browser can distinguish topology sources, protocols, and statistics.

Costs:

- Nornir inventory parsing and safe field projection become part of NFWeb;
- endpoint and BGP identity normalization must remain deterministic;
- current snapshot history is not compatible with the new graph contract.

## Acceptance Criteria

- device discovery calls Nornir only;
- an empty device selection submits no topology work;
- selected devices seed nodes and topology-safe metadata from scoped Nornir
  inventory;
- NetBox topology calls always contain the selected Nornir device list;
- directly adjacent NetBox nodes remain visible without recursive expansion;
- absent inventory topology and successful empty NetBox results are not errors;
- explicit worker failures retain successful data and produce a visible partial
  snapshot error;
- nodes contain no `kind` field;
- all nodes and links use only `netbox`, `nornir`, and `live-lldp` origins;
- NetBox attributes override Nornir attributes during merge;
- physical links merge by normalized endpoints;
- BGP sessions merge by normalized session IPs;
- BGP resolution prefers Nornir interface addresses before NetBox lookup;
- refresh re-reads data without refreshing Nornir inventory;
- Topology source filters use union behavior;
- Protocols contains BGP;
- Stats provides mutually exclusive Off, Traffic, Errors, and Flaps modes;
- links without selected statistics remain visible in grey;
- tests, developer guidance, user documentation, and the feature catalogue match
  the implemented behavior.

## References

- [NFWeb developer guide](nfweb_developer_guide.md)
- [ADR: NFWeb Scale-Test Environment](adr_nfweb_scale_test_environment.md)
- [NFWeb topology user guide](../clients_nfweb_topology.md)
- [NORFAB testing framework](../testing/norfab_testing_framework.md)
- [Vite production build](https://vite.dev/guide/build)
- [Mantine React components](https://mantine.dev/)
- [Vasturiano 3D Force Graph](https://github.com/vasturiano/3d-force-graph)
- [Vasturiano React Force Graph](https://github.com/vasturiano/react-force-graph)
