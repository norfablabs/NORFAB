---
tags:
  - netbox
---

# Netbox Get Circuits Task

> task api name: `get_circuits`

Retrieves NetBox circuit data for selected devices. The task maps circuit terminations back to requested devices and can optionally enrich each circuit with interface details.

## How It Works

1. Client submits a `get_circuits` request with a device list
2. Worker fetches device data to identify the devices' sites
3. Worker queries NetBox circuits for terminations at those sites
4. Worker traces terminations and maps matching circuits back to requested devices
5. Optional `cid` filtering limits results to specific circuit IDs
6. Optional `add_interface_details=True` adds interface data from `get_interfaces`

## Inputs

| Parameter | Required | Description |
|---|---:|---|
| `devices` | Yes | Device names to retrieve circuits for |
| `cid` | No | Circuit identifiers to retrieve |
| `instance` | No | NetBox instance name to target |
| `dry_run` | No | Return GraphQL query content without running it |
| `cache` | No | Cache usage mode: `True`, `False`, `refresh`, or `force` |
| `add_interface_details` | No | Add interface IP, VRF, and child-interface details |

## Output

Normal mode returns circuit data keyed by device name and circuit ID:

```python
{
    "fceos4": {
        "CID1": {
            "provider": "Provider1",
            "type": "DarkFibre",
            "status": "active",
            "interface": "eth101",
            "remote_device": "fceos5",
            "remote_interface": "eth101",
            "tenant": None,
            "tags": [],
            "custom_fields": {},
        },
    },
}
```

## Notes / Gotchas

- The task queries circuits broadly by device site, then filters and maps results client-side.
- `devices` uses the NFCLI alias `device-list`.
- `add_interface_details=True` performs extra interface lookups and increases runtime.

## Examples

=== "CLI"

    Get circuits for one device:

    ```bash
    nf#netbox get circuits device-list fceos4
    ```

    Get selected circuit IDs:

    ```bash
    nf#netbox get circuits device-list fceos4 fceos5 cid CID1 CID2
    ```

    Add interface details:

    ```bash
    nf#netbox get circuits device-list fceos4 add-interface-details
    ```

    Preview the query content:

    ```bash
    nf#netbox get circuits device-list fceos4 dry-run
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    nf = NorFab(inventory="./inventory.yaml")
    nf.start()
    client = nf.make_client()

    # get circuits for devices
    result = client.run_job(
        "netbox",
        "get_circuits",
        workers="any",
        kwargs={
            "devices": ["fceos4", "fceos5"],
        },
    )

    # filter by circuit IDs and add interface details
    result = client.run_job(
        "netbox",
        "get_circuits",
        workers="any",
        kwargs={
            "devices": ["fceos4"],
            "cid": ["CID1", "CID2"],
            "add_interface_details": True,
        },
    )

    nf.destroy()
    ```

## NORFAB Netbox Get Circuits Command Shell Reference

NorFab shell supports these command options for Netbox `get_circuits` task:

```bash
nf# man tree netbox.get.circuits
root
└── netbox:    Netbox service
    └── get:    Query data from Netbox
        └── circuits:    Query Netbox circuits data for devices
            ├── instance:    Netbox instance name to target
            ├── workers:    Filter worker to target, default 'any'
            ├── timeout:    Job timeout
            ├── device-list:    Device names to query data for
            ├── dry-run:    Only return query content, do not run it
            ├── cid:    List of circuit identifiers to retrieve data for
            ├── add-interface-details:    Add interface details to circuit results
            └── cache:    How to use cache, default 'True'
nf#
```

## Python API Reference

::: norfab.workers.netbox_worker.circuits_tasks.NetboxCircuitsTasks.get_circuits
