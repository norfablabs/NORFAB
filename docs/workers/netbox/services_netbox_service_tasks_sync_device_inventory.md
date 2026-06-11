---
tags:
  - netbox
---

# Netbox Sync Device Inventory Task

> task api name: `sync_device_inventory`

The `sync_device_inventory` task reconciles live hardware inventory collected
from the Nornir service with NetBox device and module data.

Live inventory is collected with Nornir `parse_ttp` using `get="inventory"`.
The chassis inventory record updates `dcim.device.serial`. Non-chassis
inventory records, including optics and transceivers, are managed as NetBox
`dcim.modules` installed in device-level `dcim.module_bays`.

## Managed Data

- NetBox device serial number, sourced only from the live chassis record.
- NetBox module bays when `create_module_bays=True`.
- NetBox module types when `create_module_types=True`.
- Installed NetBox modules for line cards, route processors, fan trays, power
  modules, optics, and transceivers.
- Module serial number, module type, status, and description.

The task does not create NetBox devices, interfaces, cables, IP addresses, MAC
addresses, BGP objects, or legacy inventory items.

## Safety Controls

Module deletions are disabled by default. Set `process_deletions=True` to
delete NetBox modules that are absent from live inventory.

Missing module bays and module types are reported by default. Set
`create_module_bays=True` or `create_module_types=True` when the task should
extend NetBox modeling from live inventory.

Live records with empty module identity, empty serial numbers, or `BUILTIN`
serial numbers are skipped and reported in `res["errors"]`. Skipped slots
suppress deletion so incomplete live data does not remove existing NetBox
modules.

## Branching Support

This task is branch aware and can push updates to a NetBox branch when the
NetBox Branching plugin is installed. Use the `branch` argument to target a
branch.

## Result Structure

**Dry-run mode** (`dry_run=True`) returns the raw diff without writing to
NetBox:

```json
{
    "<device>": {
        "create": ["module 0/RSP0/CPU0", "module mau 0/1/0/0"],
        "update": {
            "chassis": {
                "serial": {"old_value": "OLD123", "new_value": "JCY98XR393D"}
            }
        },
        "delete": ["module stale"],
        "in_sync": []
    }
}
```

**Live-run mode** (`dry_run=False`, default) applies changes and returns a
per-device action summary:

```json
{
    "<device>": {
        "created": [
            "Cisco A9K-RSP440-TR",
            "Cisco SFP-10G-LR",
            "module 0/RSP0/CPU0",
            "module mau 0/1/0/0"
        ],
        "updated": ["chassis"],
        "deleted": [],
        "in_sync": []
    }
}
```

The `created` list includes created module bays, module types, and installed
modules. In live-run mode `res["diff"]` is also populated with the raw diff.
Missing module bays, missing module types, failed writes, and ignored live
records are reported in `res["errors"]`.

## Examples

=== "NFCLI"

    Preview chassis serial and module changes for one device:

    ```
    nf#netbox sync device-inventory devices iosxr1 dry-run
    ```

    Sync a device using only existing NetBox module bays and module types:

    ```
    nf#netbox sync device-inventory devices iosxr1
    ```

    Create missing module bays from live slot names, but require module types
    to already exist:

    ```
    nf#netbox sync device-inventory devices iosxr1 create-module-bays
    ```

    Create missing module bays and module types, then install modules:

    ```
    nf#netbox sync device-inventory devices iosxr1 create-module-bays create-module-types
    ```

    Sync multiple devices:

    ```
    nf#netbox sync device-inventory devices iosxr1 iosxr2 create-module-bays create-module-types
    ```

    Delete stale NetBox modules that are absent from live inventory:

    ```
    nf#netbox sync device-inventory devices iosxr1 create-module-bays create-module-types process-deletions
    ```

    Sync into a NetBox branch:

    ```
    nf#netbox sync device-inventory devices iosxr1 branch inventory-sync-branch create-module-bays create-module-types
    ```

    Add a NetBox changelog message to write operations:

    ```
    nf#netbox sync device-inventory devices iosxr1 message "sync inventory from live device" create-module-bays create-module-types
    ```

    Use Nornir host filters instead of explicit device names:

    ```
    nf#netbox sync device-inventory FC iosxr create-module-bays create-module-types
    ```

    Target a specific NetBox worker and keep detailed output:

    ```
    nf#netbox sync device-inventory workers netbox-worker-1 devices iosxr1 verbose-result
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    nf = NorFab(inventory="./inventory.yaml")
    nf.start()
    client = nf.make_client()

    # dry run - preview raw create/update/delete/in_sync diff
    result = client.run_job(
        "netbox",
        "sync_device_inventory",
        workers="any",
        kwargs={
            "devices": ["iosxr1"],
            "dry_run": True,
        },
    )

    # sync using existing NetBox module bays and module types only
    result = client.run_job(
        "netbox",
        "sync_device_inventory",
        workers="any",
        kwargs={
            "devices": ["iosxr1"],
        },
    )

    # create missing module bays from live inventory slot names
    result = client.run_job(
        "netbox",
        "sync_device_inventory",
        workers="any",
        kwargs={
            "devices": ["iosxr1"],
            "create_module_bays": True,
        },
    )

    # create missing module bays and module types, then install modules
    result = client.run_job(
        "netbox",
        "sync_device_inventory",
        workers="any",
        kwargs={
            "devices": ["iosxr1"],
            "create_module_bays": True,
            "create_module_types": True,
        },
    )

    # sync multiple devices
    result = client.run_job(
        "netbox",
        "sync_device_inventory",
        workers="any",
        kwargs={
            "devices": ["iosxr1", "iosxr2"],
            "create_module_bays": True,
            "create_module_types": True,
        },
    )

    # delete stale NetBox modules absent from live inventory
    result = client.run_job(
        "netbox",
        "sync_device_inventory",
        workers="any",
        kwargs={
            "devices": ["iosxr1"],
            "create_module_bays": True,
            "create_module_types": True,
            "process_deletions": True,
        },
    )

    # sync into a NetBox branch and attach a changelog message
    result = client.run_job(
        "netbox",
        "sync_device_inventory",
        workers="any",
        kwargs={
            "devices": ["iosxr1"],
            "branch": "inventory-sync-branch",
            "message": "sync inventory from live device",
            "create_module_bays": True,
            "create_module_types": True,
        },
    )

    # use Nornir host filters instead of explicit device names
    result = client.run_job(
        "netbox",
        "sync_device_inventory",
        workers="any",
        kwargs={
            "FC": "iosxr",
            "create_module_bays": True,
            "create_module_types": True,
        },
    )

    nf.destroy()
    ```

## NORFAB Netbox Sync Device Inventory Command Shell Reference

NorFab shell supports these command options for the NetBox
`sync_device_inventory` task:

```
nf# man tree netbox.sync.device-inventory
root
└── netbox:    Netbox service
    └── sync:    Sync Netbox data
        └── device-inventory:    Sync device inventory facts e.g. serial number
            ├── timeout:    Job timeout
            ├── workers:    Filter worker to target, default 'any'
            ├── verbose-result:    Control output details, default 'False'
            ├── nowait:    Do not wait for job to complete, default 'False'
            ├── instance:    Netbox instance name to target
            ├── dry-run:    Do not commit to database
            ├── branch:    NetBox branching plugin branch name to use
            ├── devices:    List of NetBox devices to sync inventory for
            ├── process-deletions:    Delete NetBox modules present in module bays but absent from live inventory
            ├── create-module-types:    Create missing NetBox module types from live inventory model data
            ├── create-module-bays:    Create missing NetBox module bays using the live inventory slot names
            ├── message:    Changelog message recorded on NetBox writes
            ├── FO:    Filter hosts using Filter Object
            ├── FB:    Filter hosts by name using Glob Patterns
            ├── FH:    Filter hosts by hostname
            ├── FC:    Filter hosts containment of pattern in name
            ├── FR:    Filter hosts by name using Regular Expressions
            ├── FG:    Filter hosts by group
            ├── FP:    Filter hosts by hostname using IP Prefix
            ├── FL:    Filter hosts by names list
            ├── FM:    Filter hosts by platform
            ├── FX:    Filter hosts excluding them by name
            └── FN:    Negate the match
nf#
```

## Python API Reference

::: norfab.workers.netbox_worker.netbox_worker.NetboxWorker.sync_device_inventory
