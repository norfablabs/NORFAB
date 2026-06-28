---
tags:
  - netbox
---

# NetBox Get Devices Task

> task api name: `get_devices`

Retrieves device records from NetBox using the REST API. Results are keyed by device name and include the full device payload returned by pynetbox, with site data expanded for each device.

## Inputs

| Parameter | Required | Description |
|---|---:|---|
| `filters` | No | List of NetBox device filter dictionaries |
| `devices` | No | Device names to retrieve |
| `instance` | No | NetBox instance name to target |
| `dry_run` | No | Return the merged filters without querying NetBox |
| `cache` | No | Cache usage mode: `True`, `False`, `refresh`, or `force` |

## Output

Normal mode returns a dictionary keyed by device name:

```python
{
    "ceos-leaf-1": {
        "name": "ceos-leaf-1",
        "status": {"value": "active", "label": "Active"},
        "site": {"name": "lab", "...": "..."},
        "platform": {"name": "eos"},
        "primary_ip4": {"address": "192.0.2.11/32"},
        "...": "...",
    },
}
```

## Notes / Gotchas

- When both `devices` and `filters` are provided, device names are merged into the filter list as a NetBox `name` filter.
- `cache=True` uses cached device data when `last_updated` matches NetBox. `cache="force"` uses cached data without the freshness check.
- `cache=False` skips cache reads and writes. `cache="refresh"` fetches fresh data and overwrites cache.

## Examples

=== "CLI"

    Get specific devices:

    ```bash
    nf#netbox get devices devices ceos-leaf-1 ceos-leaf-2
    ```

    Filter devices using a NetBox filter dictionary:

    ```bash
    nf#netbox get devices filters '[{"site": "lab", "status": "active"}]'
    ```

    Preview the merged filters without querying NetBox:

    ```bash
    nf#netbox get devices devices ceos-leaf-1 dry-run
    ```

    Refresh cached device data:

    ```bash
    nf#netbox get devices devices ceos-leaf-1 cache refresh
    ```

=== "Python"

    Context manager:

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()

        result = client.run_job(
            "netbox",
            "get_devices",
            workers="any",
            kwargs={
                "devices": ["ceos-leaf-1", "ceos-leaf-2"],
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
            "get_devices",
            workers="any",
            kwargs={
                "filters": [{"site": "lab", "status": "active"}],
            },
        )

        preview = client.run_job(
            "netbox",
            "get_devices",
            workers="any",
            kwargs={
                "devices": ["ceos-leaf-1"],
                "dry_run": True,
            },
        )
    finally:
        nf.destroy()
    ```

## NORFAB Netbox Get Devices Command Shell Reference

NorFab shell supports these command options for Netbox `get_devices` task:

```bash
nf# man tree netbox.get.devices
root
└── netbox:    Netbox service
    └── get:    Query data from Netbox
        └── devices:    Query Netbox devices data
            ├── instance:    Netbox instance name to target
            ├── workers:    Filter worker to target, default 'any'
            ├── timeout:    Job timeout
            ├── filters:    List of device filters dictionaries as a JSON string, examples: [{"q": "ceos1"}]
            ├── devices:    Device names to query data for
            ├── dry-run:    Only return query content, do not run it
            └── cache:    How to use cache, default 'True'
nf#
```

## Python API Reference

::: norfab.workers.netbox_worker.devices_tasks.NetboxDevicesTasks.get_devices
