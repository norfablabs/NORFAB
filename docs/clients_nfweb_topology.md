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

| Layer | NORFAB source | Purpose |
| --- | --- | --- |
| `inventory` | NetBox `get_topology` | Device metadata and intended physical cabling |
| `lldp` | Nornir `parse_ttp`, `get=lldp_neighbors` | Observed physical adjacency |
| `bgp` | Nornir `parse_ttp`, `get=bgp_neighbors` plus NetBox IP resolution | Peer sessions and state |
| `interfaces` | Nornir `parse_ttp`, `get=interfaces_status` | Link state, counters, rates, and utilization when available |

Each layer can be enabled independently. Static inventory data can refresh less
frequently than live operational layers.

## Configure the Application

Topology settings live below the application-specific `client.nfweb.topology`
section. Only the listener and browser behavior are configured at the NFWeb level:

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
      netbox_workers: any
      nornir_workers: all
      layers:
        inventory: true
        lldp: true
        bgp: true
        interfaces: true
```

`devices` is an optional startup selection. Its default is empty, so NFWeb does
not collect topology data until the operator selects devices in the dashboard.
The selector discovers the union of NetBox `get_devices` results and Nornir
`get_nornir_hosts` results; a device also shows which inventory reported it.
`sites` restricts NetBox discovery when configured, while Nornir still reports its
available hosts.

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

- a top-bar multi-device selector populated from combined NetBox and Nornir
  discovery, with an empty initial scope by default;
- independent NetBox, LLDP, BGP, and live-interface layer controls;
- health and text filters across device metadata such as site, role, and address;
- node and link inspection with source properties, state, and available metrics;
- weather-map link colors and utilization-derived widths, with physical links
  presented as undirected relationships;
- stable node positions and a persistent 3D camera across live snapshots;
- automatic coordinate locking after layout convergence, with explicit controls
  to restart or pause layout calculation without refreshes rearranging the graph;
- independent view pause, camera rotation, node-distance, and node-size controls;
- fixed, connection-count, or traffic-derived node sizing;
- compact inspector tabs for status and utilisation, related NetBox/LLDP/BGP
  connections, and complete source properties;
- explicit partial, failed, disconnected, empty, and unsupported-WebGL states;
- a persistent, scope-aware terminal log containing up to 300 entries and matching
  NFCLI's timestamp, severity, worker, status, task, resource, and message layout;
- vertical and horizontal log scrolling so long terminal lines remain available
  without wrapping or truncation;
- a manual refresh action that bypasses layer caches and collects fresh data;
- a three-hour time scrubber and a clear return-to-live action;
- automatic WebSocket reconnection without losing saved history.

Unknown metrics remain unknown rather than being displayed as zero. Collection
errors are included in partial snapshots, and successful worker data is retained
when another worker or layer fails. The application never substitutes mock
operational data for an unavailable source.

## Operational Boundary

The application is currently read-only and polling-based. Its browser API contains
only namespaced topology routes and cannot submit arbitrary NORFAB service or task
names. It binds through the shared NFWeb loopback listener and is not intended for
remote exposure.

Adding topology layers such as OSPF, IS-IS, tunnels, paths, alarms, or streaming
telemetry should extend the topology graph contract and adapter protocol. A use
case with a different domain model should be introduced as another NFWeb
application instead of being forced into the topology model.
