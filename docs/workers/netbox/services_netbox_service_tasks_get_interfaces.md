---
tags:
  - netbox
---

# Netbox Get Interfaces Task

> task api name: `get_interfaces`

Retrieves interface data from NetBox for one or more devices using the REST API. The task can include related IP addresses, inventory items, child interfaces, and LAG member relationships.

## Inputs

| Parameter | Required | Description |
|---|---:|---|
| `devices` | No | Device names to retrieve interfaces for |
| `interface_list` | No | Exact interface names to retrieve |
| `interface_regex` | No | Regex pattern to match interface names |
| `ip_addresses` | No | Include IP addresses assigned to interfaces |
| `inventory_items` | No | Include inventory items attached to interfaces |
| `instance` | No | NetBox instance name to target |
| `branch` | No | NetBox Branching plugin branch name to read from |
| `dry_run` | No | Return REST filter parameters without querying NetBox |
| `cache` | No | Cache usage mode: `True`, `False`, `refresh`, or `force` |
| `brief` | No | Return a stripped-down interface payload for smaller context windows |
| `raise_on_empty` | No | Raise an error when no interfaces match; defaults to `True` |

## Output

Normal mode returns a dictionary keyed by device name and interface name:

```python
{
    "ceos-leaf-1": {
        "Ethernet1": {
            "name": "Ethernet1",
            "type": {"value": "1000base-t", "label": "1000BASE-T"},
            "enabled": True,
            "ip_addresses": [{"address": "192.0.2.1/31"}],
            "inventory_items": [],
            "child_interfaces": [],
            "member_interfaces": [],
            "...": "...",
        },
    },
}
```

## Notes / Gotchas

- `interface_list` maps to the NFCLI alias `interface-list`.
- `interface_regex` maps to the NFCLI alias `interface-regex`.
- `brief=True` affects only the returned payload. The task still fetches full interface data before reducing it.
- If no interface data is returned, the task raises an error by default. Set
  `raise_on_empty=False` to return the selected device keys with empty interface
  dictionaries instead.

## Examples

=== "CLI"

    Get all interfaces for a device:

    ```bash
    nf#netbox get interfaces devices ceos-leaf-1
    ```

    Get selected interfaces:

    ```bash
    nf#netbox get interfaces devices ceos-leaf-1 interface-list Ethernet1 Ethernet2
    ```

    Match interfaces by regex and include IP addresses:

    ```bash
    nf#netbox get interfaces devices ceos-leaf-1 interface-regex "Ethernet.*" ip-addresses
    ```

    Include inventory items and refresh cache:

    ```bash
    nf#netbox get interfaces devices ceos-leaf-1 inventory-items cache refresh
    ```

    Preview REST filters:

    ```bash
    nf#netbox get interfaces devices ceos-leaf-1 interface-list Ethernet1 dry-run
    ```

=== "Python"

    Context manager:

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()

        result = client.run_job(
            "netbox",
            "get_interfaces",
            workers="any",
            kwargs={
                "devices": ["ceos-leaf-1"],
                "interface_list": ["Ethernet1", "Ethernet2"],
            },
        )
    ```

    Direct lifecycle:

    ```python
    from norfab.core.nfapi import NorFab

    nf = NorFab(inventory="./inventory.yaml")
    try:
        nf.start()
        client = nf.make_client()

        result = client.run_job(
            "netbox",
            "get_interfaces",
            workers="any",
            kwargs={
                "devices": ["ceos-leaf-1"],
                "interface_regex": "Ethernet.*",
                "ip_addresses": True,
                "inventory_items": True,
            },
        )

        branch_result = client.run_job(
            "netbox",
            "get_interfaces",
            workers="any",
            kwargs={
                "devices": ["ceos-leaf-1"],
                "branch": "my-branch",
            },
        )
    finally:
        nf.destroy()
    ```

## NORFAB Netbox Get Interfaces Command Shell Reference

NorFab shell supports these command options for Netbox `get_interfaces` task:

```bash
nf# man tree netbox.get.interfaces
root
└── netbox:    Netbox service
    └── get:    Query data from Netbox
        └── interfaces:    Query Netbox device interfaces data
            ├── instance:    Netbox instance name to target
            ├── branch:    Branching plugin branch name to use
            ├── workers:    Filter worker to target, default 'any'
            ├── timeout:    Job timeout
            ├── devices:    Devices to retrieve interface for
            ├── interface-list:    List of interface names to retrieve
            ├── interface-regex:    Regex pattern to match interfaces by name
            ├── ip-addresses:    Retrieves interface IP addresses
            ├── inventory-items:    Retrieves interface inventory items
            ├── dry-run:    Only return query content, do not run it
            ├── cache:    Cache usage mode
            ├── brief:    Return stripped-down interface data
            └── raise-on-empty:    Raise an error when no interfaces match
nf#
```

## Python API Reference

::: norfab.workers.netbox_worker.interfaces_tasks.NetboxInterfacesTasks.get_interfaces
