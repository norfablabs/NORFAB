---
tags:
  - netbox
---

# Netbox Get Containerlab Inventory Task

> task api name: `get_containerlab_inventory`

Builds a Containerlab topology inventory from NetBox device and connection data. The task is intended for Containerlab workers that deploy lab topologies sourced from NetBox.

## How It Works

1. Client submits a `get_containerlab_inventory` request with device selectors
2. Worker fetches matching devices from NetBox
3. Worker reads Containerlab node settings from each device config context at `norfab.containerlab`
4. Worker fetches NetBox connection data and converts links to Containerlab `veth` endpoints
5. Worker assigns management IP addresses and optional port mappings
6. Worker returns a Containerlab inventory dictionary

## Inputs

| Parameter | Required | Description |
|---|---:|---|
| `lab_name` | Conditional | Containerlab lab name; required unless `tenant` is used |
| `tenant` | Conditional | Tenant name used to source devices and as lab name when `lab_name` is omitted |
| `filters` | Conditional | NetBox device filter dictionaries |
| `devices` | Conditional | Device names to include in the lab |
| `instance` | No | NetBox instance name to target |
| `image` | No | Container image to use for all nodes |
| `ipv4_subnet` | No | Management subnet, default `172.100.100.0/24` |
| `ports` | No | TCP/UDP port allocation range |
| `ports_map` | No | Port mappings keyed by node name |
| `cache` | No | Cache usage mode passed to device retrieval |

Provide at least one device selector: `tenant`, `devices`, or `filters`.

## Output

Returns Containerlab inventory data:

```yaml
name: lab-demo
mgmt:
  ipv4-subnet: 172.100.100.0/24
  network: br-lab-demo
topology:
  nodes:
    fceos4:
      kind: ceos
      image: ceos:latest
      mgmt-ipv4: 172.100.100.2
      ports:
        - 12000:22/tcp
  links:
    - type: veth
      endpoints:
        - node: fceos4
          interface: eth1
        - node: fceos5
          interface: eth1
```

## Notes / Gotchas

- Node-specific Containerlab settings must be stored in NetBox device config context under `norfab.containerlab`.
- If `image` is provided, it overrides node image values. Otherwise, the task uses `{kind}:latest` when no image is configured.
- `interfaces_rename` in config context can rename interfaces in generated links.
- If `lab_name` is omitted and `tenant` is provided, the tenant name becomes the lab name.

## Examples

=== "CLI"

    Build inventory for explicit devices:

    ```bash
    nf#netbox get containerlab-inventory devices fceos4 fceos5 lab-name lab-demo
    ```

    Build inventory from tenant devices:

    ```bash
    nf#netbox get containerlab-inventory tenant lab-tenant
    ```

    Filter devices by site and role:

    ```bash
    nf#netbox get containerlab-inventory lab-name lab-demo filters site lab role leaf
    ```

    Use a custom management subnet and image:

    ```bash
    nf#netbox get containerlab-inventory devices fceos4 fceos5 lab-name lab-demo ipv4-subnet 172.20.20.0/24 image ceos:latest
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    nf = NorFab(inventory="./inventory.yaml")
    nf.start()
    client = nf.make_client()

    # build inventory for explicit devices
    result = client.run_job(
        "netbox",
        "get_containerlab_inventory",
        workers="any",
        kwargs={
            "devices": ["fceos4", "fceos5"],
            "lab_name": "lab-demo",
        },
    )

    # build inventory from NetBox filters
    result = client.run_job(
        "netbox",
        "get_containerlab_inventory",
        workers="any",
        kwargs={
            "filters": [{"site": "lab", "role": "leaf"}],
            "lab_name": "lab-demo",
            "ipv4_subnet": "172.20.20.0/24",
            "image": "ceos:latest",
        },
    )

    nf.destroy()
    ```

## NORFAB Netbox Get Containerlab Inventory Command Shell Reference

NorFab shell supports these command options for Netbox `get_containerlab_inventory` task:

```bash
nf# man tree netbox.get.containerlab-inventory
root
└── netbox:    Netbox service
    └── get:    Query data from Netbox
        └── containerlab-inventory:    Query Netbox and construct Containerlab inventory
            ├── timeout:    Job timeout
            ├── workers:    Filter worker to target, default 'any'
            ├── verbose-result:    Control output details, default 'False'
            ├── lab-name:    Lab name to generate lab inventory for
            ├── tenant:    Tenant name to generate lab inventory for
            │   ├── tenant:    Filter devices by tenants
            │   ├── device-name-contains:    Filter devices by name pattern
            │   ├── model:    Filter devices by models
            │   ├── platform:    Filter devices by platforms
            │   ├── region:    Filter devices by regions
            │   ├── role:    Filter devices by roles
            │   ├── site:    Filter devices by sites
            │   ├── status:    Filter devices by statuses
            │   └── tag:    Filter devices by tags
            ├── devices:    List of devices to generate lab inventory for
            ├── progress:    Display progress events, default 'True'
            ├── netbox-instance:    Name of Netbox instance to pull inventory from
            ├── ipv4-subnet:    IPv4 management subnet to use for lab, default '172.100.100.0/24'
            ├── image:    Docker image to use for all nodes
            └── ports:    Range of TCP/UDP ports to use for nodes, default '[12000, 13000]'
nf#
```

## Python API Reference

::: norfab.workers.netbox_worker.containerlab_inventory_tasks.NetboxContainerlabInventoryTasks.get_containerlab_inventory
