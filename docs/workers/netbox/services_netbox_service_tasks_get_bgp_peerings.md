---
tags:
  - netbox
---

# NetBox Get BGP Peerings Task

> task api name: `get_bgp_peerings`

This task integrates with the [NetBox BGP Plugin](https://github.com/netbox-community/netbox-bgp) and fetches BGP peerings for devices.

## Inputs

| Parameter | Required | Description |
|---|---:|---|
| `devices` | Yes | Device names to retrieve BGP peerings for |
| `instance` | No | NetBox instance name to target |
| `branch` | No | NetBox Branching plugin branch name to read from |
| `dry_run` | No | Return query content without running it |
| `cache` | No | Cache usage mode: `True`, `False`, `refresh`, or `force` |

## How It Works

- Requires NetBox BGP plugin: The worker verifies the plugin is installed on the target instance before proceeding.
- Resolves device IDs: It calls `get_devices()` to map provided device names to NetBox device IDs for accurate API queries.
- Fetches sessions via REST: Uses `pynetbox` `plugins.bgp.session.filter(device_id=...)` to retrieve sessions per device.
- Returns structured data: The result is a dictionary keyed by device name; each device contains a dictionary keyed by BGP session `name`, with the full session dict as value.
- Smart caching: Per-device cache key `get_bgp_peerings::<device>` is used. Modes:
  - `True`: Uses cache when up-to-date; performs smart update by comparing `last_updated` and fetching only changed/new sessions.
  - `False`: Bypasses cache entirely and does not write to cache.
  - `refresh`: Forces re-fetch from NetBox and overwrites cache.
  - `force`: Returns cached data if present without freshness checks.

## Output

Returns BGP session data keyed by device name and session name:

```python
{
    "fceos4": {
        "fceos4-fceos5-eth105": {
            "name": "fceos4-fceos5-eth105",
            "description": "BGP peering between fceos4 and fceos5 on eth105",
            "status": {"label": "Active", "value": "active"},
            "local_address": {"address": "10.0.2.1/30"},
            "remote_address": {"address": "10.0.2.2/30"},
            "local_as": {"asn": 65100},
            "remote_as": {"asn": 65101},
            "peer_group": {"name": "TEST_BGP_PEER_GROUP_1"},
            "...": "...",
        },
    },
}
```

## Notes / Gotchas

- Supported and tested NetBox version is 4.4 and later.
- NetBox BGP plugin required: If missing, the task fails early with an error. Confirm plugin availability and version compatibility.
- Device name must exist: Unknown devices are skipped with warnings; verify names beforehand or use `get_devices` to inspect inventory.
- Session key uniqueness: Sessions in the result are keyed by `name`. If session names are not unique per device, later entries overwrite earlier ones.
- Partial-field queries: Smart update relies on `fields="id,last_updated,name"`. Older NetBox versions may not support `fields`, which can affect cache comparison.
- Supplying `branch` forces `cache=False` so main-context cached data cannot be returned for a branch read.
- Large datasets: Fetching many devices or sessions may be slow; prefer cache or limit `devices` for interactive runs.

## Examples

=== "CLI"

    Get BGP peerings for devices:

    ```bash
    nf#netbox get bgp-peerings devices fceos4 fceos5
    ```

    Refresh cached BGP peering data:

    ```bash
    nf#netbox get bgp-peerings devices fceos4 cache refresh
    ```

    Preview query content:

    ```bash
    nf#netbox get bgp-peerings devices fceos4 dry-run
    ```

=== "Python"

    Context manager:

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()

        result = client.run_job(
            "netbox",
            "get_bgp_peerings",
            workers="any",
            kwargs={
                "devices": ["fceos4", "fceos5"],
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
            "get_bgp_peerings",
            workers="any",
            kwargs={
                "devices": ["fceos4"],
                "cache": "refresh",
            },
        )
    finally:
        nf.destroy()
    ```

## NORFAB Netbox Get BGP Peerings Command Shell Reference

NorFab shell supports these command options for Netbox `get_bgp_peerings` task:

```bash
nf# man tree netbox.get.bgp-peerings
root
└── netbox:    Netbox service
    └── get:    Query data from Netbox
        └── bgp-peerings:    Query Netbox BGP Peerings data
            ├── timeout:    Job timeout
            ├── workers:    Filter worker to target, default 'any'
            ├── verbose-result:    Control output details, default 'False'
            ├── progress:    Display progress events, default 'True'
            ├── instance:    Netbox instance name to target
            ├── dry-run:    Only return query content, do not run it
            ├── branch:    Branching plugin branch name to use
            ├── *devices:    Device names to query data for
            └── cache:    How to use cache, default 'True'
nf#
```

## Python API Reference

::: norfab.workers.netbox_worker.bgp_peerings_tasks.NetboxBgpPeeringsTasks.get_bgp_peerings
