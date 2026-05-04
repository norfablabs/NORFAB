---
tags:
  - netbox
---

# Netbox Sync Device Interfaces Task

> task api name: `sync_device_interfaces`

The Netbox Sync Device Interfaces Task synchronizes device interface configuration from live network devices into NetBox using a normalized desired/current state model and DeepDiff-driven reconciliation. The task computes an explicit action plan and applies interface create, update, and delete operations in a safe dependency order.

## How It Works

The task follows a four-step pipeline:

1. **Fetch** — Pull current interface state from NetBox for the target devices.
2. **Collect live state** — Run a Nornir [`parse_ttp`](../nornir/services_nornir_service_tasks_parse.md) job against the devices to collect real interface attributes (type, enabled, MTU, VLANs, VRF, mode, parent, LAG membership, etc.).
3. **Diff** — Normalize both sides to a common schema and compare using DeepDiff to classify each interface as `create`, `update`, `delete`, or `in_sync`.
4. **Reconcile** — Apply changes to NetBox in dependency order to avoid constraint errors:
    1. Create LAG interfaces first
    2. Create parent (non-child) interfaces
    3. Create child (sub)interfaces referencing their parents
    4. Bulk update changed interfaces
    5. Delete interfaces present in NetBox but absent in live data (only when `process_deletions=True`)

![Netbox Sync Device Interfaces](../../images/Netbox_Service_Sync_Interfaces.jpg)

1. Client submits an on-demand request to the NorFab Netbox worker to sync device interfaces
2. Netbox worker sends a job request to the Nornir service to fetch live interface data from devices
3. Nornir service collects interface data from the network using `parse_ttp`
4. Nornir returns normalized interface data to the Netbox worker
5. Netbox worker applies planned actions and returns per-device action summaries and field-level diffs

## Result Structure

**Dry-run mode** (`dry_run=True`) returns the diff plan without making any changes, keyed by device name:

```json
{
    "<device>": {
        "create": ["Loopback99", "Port-Channel41"],
        "update": {
            "Ethernet1": {
                "description": {"old_value": "old desc", "new_value": "new desc"}
            }
        },
        "delete": ["StaleInterface"],
        "in_sync": ["Loopback0", "Ethernet2"]
    }
}
```

**Live-run mode** (`dry_run=False`, default) applies changes and returns a summary of actions taken:

```json
{
    "<device>": {
        "created": ["Loopback99", "Port-Channel41"],
        "updated": ["Ethernet1"],
        "deleted": ["StaleInterface"],
        "in_sync": ["Loopback0", "Ethernet2"]
    }
}
```

In live-run mode `res["diff"]` is also populated with field-level change details for all interfaces that were created or updated.

## Filtering

Interfaces can be scoped using glob patterns so that only a subset is considered on both the live and NetBox sides:

- `filter_by_name` — match interface names, e.g. `"Loopback*"` or `"Ethernet[1-4]"`
- `filter_by_description` — match interface descriptions, e.g. `"uplink*"` or `"TEST_SYNC_*"`

Both filters are applied before the diff, so interfaces that do not match are completely ignored by the sync — they are neither created, updated, nor deleted.

## Branching Support

The task is branch-aware and can push changes into a NetBox branch. The [Netbox Branching Plugin](https://github.com/netboxlabs/netbox-branching) must be installed. Specify the `branch` parameter; the branch is created automatically if it does not already exist.

## Deletions

By default `process_deletions=False` — interfaces present in NetBox but absent in live data are left untouched. Set `process_deletions=True` to enable deletion. Child interfaces are always deleted before their parents to avoid foreign-key constraint errors.

## Examples

=== "CLI"

    Sync interfaces for a list of devices:

    ```
    nf#netbox sync interfaces devices ceos-spine-1 ceos-spine-2
    ```

    Preview changes without writing to NetBox (dry run):

    ```
    nf#netbox sync interfaces devices ceos-spine-1 dry-run
    ```

    Sync and delete interfaces absent from live data:

    ```
    nf#netbox sync interfaces devices ceos-spine-1 ceos-spine-2 process-deletions
    ```

    Restrict sync to loopback interfaces only:

    ```
    nf#netbox sync interfaces devices ceos-spine-1 filter-by-name "Loopback*"
    ```

    Restrict sync to interfaces whose description matches a glob pattern:

    ```
    nf#netbox sync interfaces devices ceos-spine-1 filter-by-description "TEST_SYNC_*"
    ```

    Sync interfaces into a NetBox branch:

    ```
    nf#netbox sync interfaces devices ceos-spine-1 ceos-spine-2 branch sprint-42-interfaces
    ```

    Sync using Nornir host filters instead of explicit device names:

    ```
    nf#netbox sync interfaces FC spine
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    nf = NorFab(inventory="./inventory.yaml")
    nf.start()
    client = nf.make_client()

    # sync interfaces for specific devices
    result = client.run_job(
        "netbox",
        "sync_device_interfaces",
        workers="any",
        kwargs={
            "devices": ["ceos-spine-1", "ceos-spine-2"],
        },
    )

    # dry run — preview creates/updates/deletes without writing
    result = client.run_job(
        "netbox",
        "sync_device_interfaces",
        workers="any",
        kwargs={
            "devices": ["ceos-spine-1", "ceos-spine-2"],
            "dry_run": True,
        },
    )

    # sync and delete interfaces absent from live data
    result = client.run_job(
        "netbox",
        "sync_device_interfaces",
        workers="any",
        kwargs={
            "devices": ["ceos-spine-1"],
            "process_deletions": True,
        },
    )

    # restrict sync to loopback interfaces only
    result = client.run_job(
        "netbox",
        "sync_device_interfaces",
        workers="any",
        kwargs={
            "devices": ["ceos-spine-1"],
            "filter_by_name": "Loopback*",
        },
    )

    # restrict sync to interfaces with a specific description pattern
    result = client.run_job(
        "netbox",
        "sync_device_interfaces",
        workers="any",
        kwargs={
            "devices": ["ceos-spine-1"],
            "process_deletions": True,
            "filter_by_description": "TEST_SYNC_*",
        },
    )

    # sync into a NetBox branch
    result = client.run_job(
        "netbox",
        "sync_device_interfaces",
        workers="any",
        kwargs={
            "devices": ["ceos-spine-1", "ceos-spine-2"],
            "branch": "sprint-42-interfaces",
        },
    )

    # use Nornir host filters instead of explicit device names
    result = client.run_job(
        "netbox",
        "sync_device_interfaces",
        workers="any",
        kwargs={
            "FC": "spine",
        },
    )

    nf.destroy()
    ```

## NORFAB Netbox Sync Device Interfaces Command Shell Reference

NorFab shell supports these command options for the `sync_device_interfaces` task:

```
nf# man tree netbox.sync.interfaces
root
└── netbox:    Netbox service
    └── sync:    Sync Netbox data
        └── interfaces:    Sync device interfaces with NetBox
            ├── timeout:    Job timeout in seconds
            ├── workers:    Filter worker to target, default 'any'
            ├── verbose-result:    Control output details, default 'False'
            ├── progress:    Display progress events, default 'True'
            ├── instance:    Netbox instance name to target
            ├── dry-run:    Return diff plan without pushing changes to NetBox
            ├── devices:    List of NetBox device names to sync
            ├── process-deletions:    Delete interfaces present in NetBox but absent in live data
            ├── filter-by-name:    Glob pattern to restrict sync by interface name, e.g. 'Loopback*'
            ├── filter-by-description:    Glob pattern to restrict sync by interface description
            ├── branch:    Branching plugin branch name to push changes into
            ├── FO:    Filter Nornir hosts using Filter Object
            ├── FB:    Filter Nornir hosts by name using Glob Patterns
            ├── FH:    Filter Nornir hosts by hostname
            ├── FC:    Filter Nornir hosts by name containment
            ├── FR:    Filter Nornir hosts by name using Regular Expressions
            ├── FG:    Filter Nornir hosts by group
            ├── FP:    Filter Nornir hosts by hostname using IP Prefix
            ├── FL:    Filter Nornir hosts by names list
            ├── FM:    Filter Nornir hosts by platform
            └── FN:    Negate the Nornir host filter match
nf#
```

## Python API Reference

::: norfab.workers.netbox_worker.netbox_worker.NetboxWorker.sync_device_interfaces