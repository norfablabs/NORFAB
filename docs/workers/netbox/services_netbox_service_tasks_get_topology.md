---
tags:
  - netbox
---

# Netbox Get Topology Task

> task api name: `get_topology`

## Overview

The `get_topology` task retrieves network topology data from NetBox and returns it as a
structured list of **nodes** (devices) and **links** (physical cable connections). The output
is designed to feed network visualisation applications such as the NorFab web UI topology viewer,
D3.js graphs, or any tool that consumes node-link graph data.

Nodes carry rich device metadata — platform, primary management IP, role, site, manufacturer,
and tags. Links carry interface-level details — interface type, speed, MTU, cable type/status,
and tags. Every physical cable appears **exactly once** in the links list regardless of which
side of the connection was queried first.

## Get Topology Sample Usage

### Python API

```python
from norfab.core.nfapi import NorFab

nf = NorFab(inventory="./inventory.yaml")
nf.start()
client = nf.make_client()

result = client.run_job(
    "netbox",
    "get_topology",
    workers="any",
    kwargs={"devices": ["spine-1", "leaf-1", "leaf-2"]},
)

for worker, res in result.items():
    nodes = res["result"]["nodes"]
    links = res["result"]["links"]
    print(f"Nodes: {len(nodes)}, Links: {len(links)}")

nf.destroy()
```

### Sample Output

```json
{
  "nodes": [
    {
      "id": "spine-1",
      "name": "spine-1",
      "type": "arista_eos",
      "ip": "10.0.0.1/32",
      "status": "active",
      "role": "spine",
      "site": "dc-nyc",
      "tags": ["core", "production"],
      "manufacturer": "Arista",
      "device_type": "DCS-7050CX3-32S"
    },
    {
      "id": "leaf-1",
      "name": "leaf-1",
      "type": "arista_eos",
      "ip": "10.0.0.2/32",
      "status": "active",
      "role": "leaf",
      "site": "dc-nyc",
      "tags": ["production"],
      "manufacturer": "Arista",
      "device_type": "DCS-7050TX-64"
    }
  ],
  "links": [
    {
      "source": "spine-1",
      "target": "leaf-1",
      "src_iface": "Ethernet1",
      "dst_iface": "Ethernet49",
      "type": "1000base-t",
      "speed": 1000000,
      "mtu": 9214,
      "tags": [],
      "cable_type": "smf",
      "cable_status": "connected",
      "cable_label": ""
    }
  ]
}
```

### Fetching Topology for All Devices

Omit the `devices` argument to build a full topology of every device in NetBox:

```python
result = client.run_job(
    "netbox",
    "get_topology",
    workers="any",
    kwargs={},
)
```

!!! warning
    Fetching all devices at once can be slow on large NetBox installations. Use the
    `devices` filter to narrow down the scope when possible.

## Filtering Devices

The task provides several filtering parameters, all resolved via the NetBox REST API before
interface connections are queried.

| Parameter         | Description                                                                 |
|-------------------|-----------------------------------------------------------------------------|
| `devices`         | Exact device name list                                                      |
| `device_contains` | Case-insensitive substring match on device name (NetBox `name__ic` filter)  |
| `device_regex`    | Regular-expression match on device name (NetBox `name__re` filter)          |
| `role`            | List of device role slugs (e.g. `["spine", "leaf"]`)                        |
| `platform`        | List of platform slugs (e.g. `["arista-eos", "cisco-ios"]`)                 |
| `manufacturers`   | List of manufacturer slugs (e.g. `["arista", "cisco"]`)                     |
| `status`          | List of status values (e.g. `["active", "planned"]`)                        |

Filters can be combined freely. For example, to get all active spine devices made by Arista:

```python
result = client.run_job(
    "netbox",
    "get_topology",
    workers="any",
    kwargs={
        "role": ["spine"],
        "manufacturers": ["arista"],
        "status": ["active"],
    },
)
```

Or filter by a name pattern:

```python
result = client.run_job(
    "netbox",
    "get_topology",
    workers="any",
    kwargs={"device_contains": "spine"},
)
```

## Adjacent Nodes

When a device in the filtered set has a physical cable connected to a device **outside** the
filtered set, the remote device is automatically fetched from NetBox and added to the nodes
list. This ensures the topology graph is always consistent — every link endpoint has a
corresponding node entry — and lets you visualise partial topologies without orphaned links.

For example, if you query only `spine-1` but it has cables to `leaf-1` and `leaf-2`, the
result will contain three nodes (`spine-1`, `leaf-1`, `leaf-2`) and all links between them.

Adjacent nodes are fetched in a single additional REST call after the interface connection
query, so the overhead is minimal regardless of how many extra devices are discovered.

### Dry Run

Pass `dry_run=True` to inspect the REST filter parameters and GraphQL query that would
be sent to NetBox without executing any network calls:

Pass `dry_run=True` to inspect the REST filter parameters and GraphQL query that would
be sent to NetBox without executing any network calls:

```python
result = client.run_job(
    "netbox",
    "get_topology",
    workers="any",
    kwargs={"devices": ["spine-1", "leaf-1"], "dry_run": True},
)
```

## NORFAB Netbox Get Topology Command Shell Reference

NorFab shell supports these command options for Netbox `get_topology` task:

```
nf#man tree netbox.get.topology
root
└── netbox:    Netbox service
    └── get:    Query data from Netbox
        └── topology:    Query Netbox topology data for devices
            ├── timeout:    Job timeout
            ├── workers:    Filter worker to target, default 'any'
            ├── verbose-result:    Control output details, default 'False'
            ├── progress:    Display progress events, default 'True'
            ├── instance:    Netbox instance name to target
            ├── dry-run:    Do not commit to database
            ├── devices:    List of device names to build topology for
            ├── device-contains:    Case-insensitive substring filter on device name
            ├── device-regex:    Regex filter on device name
            ├── role:    List of device role slugs to filter by
            ├── platform:    List of platform slugs to filter by
            ├── manufacturers:    List of manufacturer slugs to filter by
            └── status:    List of device status values to filter by
nf#
```

### Shell Usage Examples

Retrieve topology for specific devices:

```
nf#netbox get topology devices spine-1 leaf-1 leaf-2
```

Retrieve topology for a single device and pipe through JSON formatter:

```
nf#netbox get topology devices spine-1 | json
```

Filter by name substring (returns all matching devices plus their adjacent neighbours):

```
nf#netbox get topology device-contains spine
```

Filter by role and status:

```
nf#netbox get topology role spine leaf status active
```

Dry run to inspect the query parameters:

```
nf#netbox get topology devices spine-1 leaf-1 dry-run
```

Target a specific NetBox instance:

```
nf#netbox get topology devices spine-1 leaf-1 instance prod
```

## Output Structure Reference

### Node Fields

| Field          | Type             | Description                                              |
|----------------|------------------|----------------------------------------------------------|
| `id`           | string           | Device name used as a unique graph node identifier       |
| `name`         | string           | Device name                                              |
| `type`         | string or null   | Device platform slug (e.g. `arista_eos`, `cisco_iosxr`) |
| `ip`           | string or null   | Primary management IP with prefix length (e.g. `10.0.0.1/32`) |
| `status`       | string or null   | NetBox device status value (e.g. `active`, `planned`)    |
| `role`         | string or null   | Device role name (e.g. `spine`, `leaf`, `access-switch`) |
| `site`         | string or null   | Site name the device belongs to                          |
| `tags`         | list of strings  | Tag names assigned to the device                         |
| `manufacturer` | string or null   | Manufacturer name (e.g. `Arista`, `Cisco`)               |
| `device_type`  | string or null   | Device type model name (e.g. `DCS-7050CX3-32S`)         |

### Link Fields

| Field          | Type             | Description                                              |
|----------------|------------------|----------------------------------------------------------|
| `source`       | string           | Source device name                                       |
| `target`       | string           | Target device name                                       |
| `src_iface`    | string           | Source interface name                                    |
| `dst_iface`    | string           | Destination interface name                               |
| `type`         | string or null   | Interface type value (e.g. `1000base-t`, `10gbase-x-sfpp`) |
| `speed`        | integer or null  | Interface speed in Kbps                                  |
| `mtu`          | integer or null  | Interface MTU in bytes                                   |
| `tags`         | list of strings  | Tag names assigned to the interface                      |
| `cable_type`   | string or null   | Cable type value (e.g. `smf`, `mmf`, `cat6`)            |
| `cable_status` | string or null   | Cable status value (e.g. `connected`, `planned`)         |
| `cable_label`  | string or null   | Cable label text                                         |

## Python API Reference

::: norfab.workers.netbox_worker.netbox_worker.NetboxWorker.get_topology
