---
tags:
  - netbox
---

# Netbox Sync MAC Addresses Task

> task api name: `sync_mac_addresses`

The Netbox Sync MAC Addresses Task synchronizes interface MAC addresses from live network devices into NetBox. The task collects current MAC address state from devices, compares it against existing NetBox MAC address objects, and applies create or update operations to bring NetBox into alignment.

## How It Works

The task follows a three-step pipeline:

1. **Collect live state** — Run a Nornir [`parse_ttp`](../nornir/services_nornir_service_tasks_parse.md) job against the target devices to collect live MAC addresses per interface.
2. **Fetch NetBox state** — Retrieve existing MAC address objects from NetBox for the discovered MACs.
3. **Reconcile** — Compare live versus NetBox state and apply changes:
    - **Create** — MAC not present in NetBox at all: create a new MAC address object assigned to the correct interface.
    - **Update** — MAC exists in NetBox but has no `assigned_object` (unassigned): assign it to the correct interface.
    - **In sync** — MAC already assigned to the correct interface: no action needed.
    - **Error** — MAC exists in NetBox and is assigned to a *different* interface: report a conflict error without modifying the record.

## Result Structure

Both dry-run and live-run return the same structure, keyed by device name:

```json
{
    "<device>": {
        "created": ["aa:bb:cc:dd:ee:01", "aa:bb:cc:dd:ee:02"],
        "updated": ["aa:bb:cc:dd:ee:03"],
        "in_sync": ["aa:bb:cc:dd:ee:04"]
    }
}
```

In **dry-run mode** (`dry_run=True`) the lists reflect what *would* happen — no changes are written to NetBox.

In **live-run mode** (`dry_run=False`, default) the lists reflect what was actually done.

Conflict errors (MAC assigned to a different interface) are reported in `res["errors"]` and do not appear in any action list.

## Filtering

MAC address collection can be scoped using glob patterns so that only a subset of interfaces and MACs is considered:

- `filter_by_name` — match interface names, e.g. `"Loopback*"` or `"Ethernet[1-4]"`
- `filter_by_description` — match interface descriptions, e.g. `"uplink*"` or `"p2p*"`
- `filter_by_mac` — match MAC address strings, e.g. `"aa:bb:cc:*"`

All filters are applied before the reconciliation step. Interfaces or MACs that do not match are completely ignored — they are neither created nor updated.

## Branching Support

The task is branch-aware and can push changes into a NetBox branch. The [Netbox Branching Plugin](https://github.com/netboxlabs/netbox-branching) must be installed. Specify the `branch` parameter; the branch is created automatically if it does not already exist.

## Duplicate MAC Handling

NetBox permits multiple MAC address records with the same MAC value. The task handles this safely:

- If a MAC exists in NetBox with an assigned interface that **matches** the live data — reported as `in_sync`.
- If a MAC exists in NetBox with an assigned interface that **differs** from the live data — reported as a conflict error; the record is not modified.
- If a MAC exists in NetBox but is **unassigned** — the record is updated to point at the correct interface.
- If both an assigned (conflicting) and an unassigned copy of the same MAC exist in NetBox, the assigned (conflicting) entry takes precedence and a conflict error is raised.

## Examples

=== "CLI"

    Sync MAC addresses for a list of devices:

    ```
    nf#netbox sync mac-addresses devices ceos-spine-1 ceos-spine-2
    ```

    Preview changes without writing to NetBox (dry run):

    ```
    nf#netbox sync mac-addresses devices ceos-spine-1 dry-run
    ```

    Restrict sync to Ethernet interfaces only:

    ```
    nf#netbox sync mac-addresses devices ceos-spine-1 filter-by-name "Ethernet*"
    ```

    Restrict sync to interfaces whose description matches a glob pattern:

    ```
    nf#netbox sync mac-addresses devices ceos-spine-1 filter-by-description "uplink*"
    ```

    Restrict sync to a specific MAC prefix:

    ```
    nf#netbox sync mac-addresses devices ceos-spine-1 filter-by-mac "aa:bb:cc:*"
    ```

    Sync MAC addresses into a NetBox branch:

    ```
    nf#netbox sync mac-addresses devices ceos-spine-1 ceos-spine-2 branch sprint-42-macs
    ```

    Sync using Nornir host filters instead of explicit device names:

    ```
    nf#netbox sync mac-addresses FC spine
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    nf = NorFab(inventory="./inventory.yaml")
    nf.start()
    client = nf.make_client()

    # sync MAC addresses for specific devices
    result = client.run_job(
        "netbox",
        "sync_mac_addresses",
        workers="any",
        kwargs={
            "devices": ["ceos-spine-1", "ceos-spine-2"],
        },
    )

    # dry run — preview creates/updates without writing
    result = client.run_job(
        "netbox",
        "sync_mac_addresses",
        workers="any",
        kwargs={
            "devices": ["ceos-spine-1", "ceos-spine-2"],
            "dry_run": True,
        },
    )

    # restrict sync to Ethernet interfaces only
    result = client.run_job(
        "netbox",
        "sync_mac_addresses",
        workers="any",
        kwargs={
            "devices": ["ceos-spine-1"],
            "filter_by_name": "Ethernet*",
        },
    )

    # restrict sync to interfaces with a specific description pattern
    result = client.run_job(
        "netbox",
        "sync_mac_addresses",
        workers="any",
        kwargs={
            "devices": ["ceos-spine-1"],
            "filter_by_description": "uplink*",
        },
    )

    # restrict sync to a specific MAC prefix
    result = client.run_job(
        "netbox",
        "sync_mac_addresses",
        workers="any",
        kwargs={
            "devices": ["ceos-spine-1"],
            "filter_by_mac": "aa:bb:cc:*",
        },
    )

    # sync into a NetBox branch
    result = client.run_job(
        "netbox",
        "sync_mac_addresses",
        workers="any",
        kwargs={
            "devices": ["ceos-spine-1", "ceos-spine-2"],
            "branch": "sprint-42-macs",
        },
    )

    # use Nornir host filters instead of explicit device names
    result = client.run_job(
        "netbox",
        "sync_mac_addresses",
        workers="any",
        kwargs={
            "FC": "spine",
        },
    )

    nf.destroy()
    ```

## NORFAB Netbox Sync MAC Addresses Command Shell Reference

NorFab shell supports these command options for the `sync_mac_addresses` task:

```
nf# man tree netbox.sync.mac-addresses
root
└── netbox:    Netbox service
    └── sync:    Sync Netbox data
        └── mac-addresses:    Sync device MAC addresses with NetBox
            ├── timeout:    Job timeout in seconds
            ├── workers:    Filter worker to target, default 'any'
            ├── verbose-result:    Control output details, default 'False'
            ├── progress:    Display progress events, default 'True'
            ├── instance:    Netbox instance name to target
            ├── dry-run:    Return reconciliation plan without pushing changes to NetBox
            ├── devices:    List of NetBox device names to sync
            ├── filter-by-name:    Glob pattern to restrict sync by interface name, e.g. 'Ethernet*'
            ├── filter-by-description:    Glob pattern to restrict sync by interface description
            ├── filter-by-mac:    Glob pattern to restrict sync by MAC address, e.g. 'aa:bb:*'
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

::: norfab.workers.netbox_worker.netbox_worker.NetboxWorker.sync_mac_addresses
