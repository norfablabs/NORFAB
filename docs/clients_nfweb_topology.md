---
tags:
  - clients
  - web
  - topology
---

# 3D Network Topology Application

Network topology is the first built-in application delivered through the
[NFWeb Local Web Client](clients_nfweb_overview.md). It is a weather-map-style
window into current and recent network state, not the complete scope of NFWeb.

The application collects topology through NFWeb's native NORFAB client, maintains
one persistent Vasturiano 3D scene, and stores a bounded local history while the
NFWeb process is running.

## Data Sources and Layers

Nornir is the source of selectable devices. For selected hosts, NFWeb reads the
running Nornir inventory and uses its host metadata, interfaces and addresses,
connections, circuits, and BGP peerings as the initial graph. Passwords,
usernames, connection options, and unrelated host data are not sent to the
browser.

| Layer | NORFAB source | Purpose |
| --- | --- | --- |
| `topology` | Nornir `get_inventory`, NetBox `get_topology`, and live LLDP | Physical connections and circuits |
| `bgp` | Cached Nornir peerings and live Nornir `bgp_neighbors` | Peer sessions and current state |
| `interfaces` | Live Nornir `interfaces_status` | Link state, counters, rates, and utilization |

NetBox is queried only for topology related to the selected Nornir hosts and for
unresolved BGP addresses. Adjacent nodes returned by NetBox, Nornir inventory, or
LLDP remain visible even when they are outside the selected scope. Missing cached
connections, circuits, peerings, or NetBox topology is a normal empty result.

Connections reported by more than one source merge by device and interface
endpoints. Their `origin` records `netbox`, `nornir`, and/or `live-lldp`. Cached
and live BGP sessions merge by their local and remote session IP addresses.

## Configure the Application

Topology settings live below the application-specific `client.nfweb.topology`
section. Only the listener and browser behavior are configured at the NFWeb level:

```yaml
client:
  nfweb:
    host: 0.0.0.0
    port: 9005
    open_browser: true
    footer:
      message: "Managed by the Network Automation team"
      fastapi_url: "http://127.0.0.1:8000/docs"
    topology:
      collection_interval: 30
      inventory_refresh_interval: 300
      retention_minutes: 180
      request_timeout: 60
      devices: []
      netbox_workers: any
      nornir_workers: all
      layers:
        topology: true
        lldp: true
        bgp: true
        interfaces: true
```

`devices` is an optional startup selection. Its default is empty, so NFWeb does
not collect topology data until the operator selects devices in the dashboard.
The selector contains only Nornir `get_nornir_hosts` results. NetBox-only devices
cannot be selected, although directly adjacent NetBox nodes can appear in the
graph.

`collection_interval` controls live collection and cannot be less than five
seconds. `inventory_refresh_interval` defaults to five minutes. The history window
cannot exceed 180 minutes.

## Local History

Snapshots are compressed in the topology-owned `topology_snapshots` table within
NFWeb's local SQLite database:

```text
__norfab__/nfweb/nfweb.sqlite
```

The default 30-second cadence retains at most approximately 360 snapshots across
the three-hour window. Cleanup removes older snapshots after successful inserts.
History is shared by browser tabs and survives browser refreshes and NFWeb
restarts. Once a non-empty scope is selected, periodic collection continues while
NFWeb is running without an open browser. An empty scope performs no collection.

## Dashboard Behavior

The topology dashboard provides:

- a top-bar multi-device selector populated from Nornir, with an empty initial
  scope by default;
- a **Topology** multi-select for NetBox, Nornir connections, LLDP, and circuits;
- a **Protocols** multi-select containing BGP;
- a mutually exclusive **Stats** selector with Off, Traffic, Errors, and Flaps;
- health and text filters across device metadata such as site, role, and address;
- node and link inspection with source properties, state, and available metrics;
- traffic animation and utilization coloring when Traffic statistics are selected;
- red error links when any reported input, output, or CRC error counter is non-zero;
- green links for 0–10 transitions, yellow for 11–100, and red above 100 in Flaps
  mode;
- subdued grey links when the selected statistic is unavailable, without hiding
  structural topology;
- stable node positions and a persistent 3D camera across live snapshots;
- automatic coordinate locking after layout convergence, with explicit controls
  to restart or pause layout calculation without refreshes rearranging the graph;
- independent view pause, camera rotation, node-distance, and node-size controls;
- fixed, connection-count, or traffic-derived node sizing;
- compact inspector tabs with search and column sorting for status and
  utilisation, related NetBox/LLDP/BGP connections, and complete source
  properties;
- explicit partial, failed, disconnected, empty, and unsupported-WebGL states;
- a persistent, scope-aware terminal log containing up to 300 entries and matching
  NFCLI's timestamp, severity, worker, status, task, resource, and message layout;
- vertical and horizontal log scrolling so long terminal lines remain available
  without wrapping or truncation;
- a manual refresh action that bypasses NFWeb caches and repeats the scoped
  inventory, topology, and live reads without refreshing Nornir inventory;
- a single-line, horizontally scrollable top toolbar containing live status, a
  three-hour timestamp snapshot selector, and a clear return-to-live action;
- an 80/20 topology-to-inspector desktop split, with the inspector extending into
  the top-right corner;
- a shared footer with an inventory-defined message and pictogram links to the
  configured FastAPI service, NORFAB documentation, and GitHub repository;
- automatic WebSocket reconnection without losing saved history.

Unknown metrics remain unknown rather than being displayed as zero. Collection
errors are included in partial snapshots, and successful worker data is retained
when another worker or layer fails. The application never substitutes mock
operational data for an unavailable source.

## Operational Boundary

The application is currently read-only and polling-based. Its browser API contains
only namespaced topology routes and cannot submit arbitrary NORFAB service or task
names. It binds through the shared NFWeb listener and is remotely reachable when
the host network and firewall permit it. NFWeb has no authentication, origin
filtering, or TLS, so limit that access to trusted administrative networks.

Adding topology layers such as OSPF, IS-IS, tunnels, paths, alarms, or streaming
telemetry should extend the topology graph contract and adapter protocol. A use
case with a different domain model should be introduced as another NFWeb
application instead of being forced into the topology model.
