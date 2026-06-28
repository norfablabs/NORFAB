---
tags:
  - netbox
---

# Netbox Create IP Bulk Task

> task api name: `create_ip_bulk`

Allocates IP addresses for multiple device interfaces. The task first retrieves matching interfaces with `get_interfaces`, then calls `create_ip` for each device/interface pair.

## Inputs

| Parameter | Required | Description |
|---|---:|---|
| `prefix` | Yes | Parent prefix as a network string, prefix description, or pynetbox filter dictionary |
| `devices` | Yes | Device names to assign IP addresses to |
| `interface_list` | No | Exact interface names to target |
| `interface_regex` | No | Regex pattern to match interface names |
| `description` | No | Description for allocated IP addresses |
| `vrf` | No | VRF name for allocated IP addresses |
| `tags` | No | Tags to associate with allocated IP addresses |
| `dns_name` | No | DNS name for allocated IP addresses |
| `tenant` | No | Tenant name to associate with allocated IP addresses |
| `comments` | No | IP address comments |
| `role` | No | IP address role |
| `status` | No | IP address status |
| `is_primary` | No | Set each IP as the primary IP for its device |
| `mask_len` | No | Allocate child subnets of this length before creating IPs |
| `create_peer_ip` | No | Create IP addresses for connected peer interfaces, default `True` |
| `instance` | No | NetBox instance name to target |
| `branch` | No | NetBox Branching plugin branch name to write to |
| `dry_run` | No | Preview allocations without writing |

## Output

Returns allocation results keyed by device and interface:

```python
{
    "ceos-leaf-1": {
        "Ethernet1": {
            "address": "10.0.0.1/31",
            "...": "...",
        },
    },
}
```

## Notes / Gotchas

- `interface_list` takes precedence over `interface_regex` when both are provided.
- Dry-run mode passes through to `create_ip`; the same `mask_len` dry-run limitation applies.
- `mask_len=32` or `mask_len=128` is invalid with `create_peer_ip=True`.
- Branch writes require the [NetBox Branching Plugin](https://github.com/netboxlabs/netbox-branching).

## Examples

=== "CLI"

    Allocate IPs for selected interfaces:

    ```bash
    nf#netbox create ip-bulk prefix 10.0.0.0/24 devices ceos-leaf-1 ceos-leaf-2 interface-list Ethernet1 Ethernet2
    ```

    Allocate IPs for interfaces matching a regex:

    ```bash
    nf#netbox create ip-bulk prefix 10.0.0.0/24 devices ceos-leaf-1 interface-regex "Ethernet[1-4]" mask-len 31
    ```

    Preview allocations:

    ```bash
    nf#netbox create ip-bulk prefix 10.0.0.0/24 devices ceos-leaf-1 interface-list Ethernet1 dry-run
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    nf = NorFab(inventory="./inventory.yaml")
    nf.start()
    client = nf.make_client()

    # allocate IPs for selected interfaces
    result = client.run_job(
        "netbox",
        "create_ip_bulk",
        workers="any",
        kwargs={
            "prefix": "10.0.0.0/24",
            "devices": ["ceos-leaf-1", "ceos-leaf-2"],
            "interface_list": ["Ethernet1", "Ethernet2"],
        },
    )

    # allocate /31 link subnets for matching interfaces
    result = client.run_job(
        "netbox",
        "create_ip_bulk",
        workers="any",
        kwargs={
            "prefix": {"prefix": "10.0.0.0/24", "site": "lab"},
            "devices": ["ceos-leaf-1"],
            "interface_regex": "Ethernet[1-4]",
            "mask_len": 31,
            "description": "fabric uplink",
        },
    )

    nf.destroy()
    ```

## NORFAB Netbox Create IP Bulk Command Shell Reference

NorFab shell supports these command options for Netbox `create_ip_bulk` task:

```bash
nf# man tree netbox.create.ip-bulk
root
└── netbox:    Netbox service
    └── create:    Create objects in Netbox
        └── ip-bulk:    Allocate next available IP address from prefix for multiple devices and interfaces
            ├── timeout:    Job timeout
            ├── workers:    Filter worker to target, default 'any'
            ├── verbose-result:    Control output details, default 'False'
            ├── progress:    Display progress events, default 'True'
            ├── nowait:    Do not wait for job to complete, default 'False'
            ├── instance:    Netbox instance name to target
            ├── dry-run:    Do not commit to database
            ├── branch:    Branching plugin branch name to use
            ├── prefix:    Prefix to allocate IP address from, can also provide prefix name or filters
            ├── devices:    List of device names to create IP address for
            ├── interface-regex:    Regular expression of device interface names to create IP address for
            ├── interface-list:    List of interface names to create IP address for
            ├── description:    IP address description
            ├── vrf:    VRF to associate with IP address
            ├── tags:    Tags to add to IP address
            ├── dns-name:    IP address DNS name
            ├── tenant:    Tenant name to associate with IP address
            ├── comments:    IP address comments field
            ├── role:    IP address functional role
            ├── mask-len:    Mask length to use for IP address
            ├── create-peer-ip:    Create link peer IP address as well
            └── status:    IP address status
nf#
```

## Python API Reference

::: norfab.workers.netbox_worker.ip_tasks.NetboxIpTasks.create_ip_bulk
