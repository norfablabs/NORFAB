---
tags:
  - fakenos
---

# FakeNOS Service Get Nornir Inventory Task

> task api name: `get_nornir_inventory`

The FakeNOS service `get_nornir_inventory` task builds a [Nornir](https://github.com/nornir-automation/nornir)-compatible inventory from the hosts running in one or all FakeNOS virtual networks. The resulting inventory can be fed directly into the [Nornir Service](../nornir/services_nornir_service.md) to run automation tasks against simulated devices.

## FakeNOS Get Nornir Inventory Task Overview

The `get_nornir_inventory` task provides the following features:

- **Automatic Inventory Generation**: Queries running FakeNOS networks and maps host data (name, port, platform, credentials) to the Nornir inventory format.
- **Localhost Binding**: All generated hosts use `127.0.0.1` as their hostname because FakeNOS SSH servers listen on the local machine.
- **Group Assignment**: Optionally assign one or more Nornir group names to every host in the generated inventory.
- **Network Scoping**: Optionally limit inventory generation to a single named network.

## FakeNOS Get Nornir Inventory Task Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `network` | `str` or `None` | `None` | Name of a specific FakeNOS network to build inventory for. If `None`, hosts from all running networks are included. |
| `groups` | `str`, `list`, or `None` | `None` | A group name or list of Nornir group names to assign to every generated host. |

## FakeNOS Get Nornir Inventory Task Return Data

The task returns a dict with a single `hosts` key. The value is a dict keyed by host name.

| Field | Type | Description |
|-------|------|-------------|
| `hostname` | `str` | Always `127.0.0.1` — FakeNOS SSH servers listen on localhost. |
| `port` | `int` | TCP port assigned to this host in the FakeNOS inventory. |
| `platform` | `str` | NOS platform name (e.g. `RouterOS`). May be `None` if not set. |
| `username` | `str` | SSH username for the simulated device. |
| `password` | `str` | SSH password for the simulated device. |
| `groups` | `list` | List of Nornir group names. Empty list if `groups` was not specified. |

## FakeNOS Get Nornir Inventory Command Shell Reference

NorFab shell supports these command options for Netbox `create_prefix` task:

```
nf#man tree fakenos.get-nornir-inventory

R - required field, M - supports multiline input, D - dynamic key

root
└── fakenos:    FakeNOS service
    └── get-nornir-inventory:    Get Nornir inventory from FakeNOS networks
        ├── network:    FakeNOS network name to get Nornir inventory for
        ├── groups:    List of groups to include in host's inventory
        ├── timeout:    Job timeout
        ├── workers:    Filter workers to target, default 'all'
        ├── verbose-result:    Control output details, default 'False'
        ├── progress:    Display progress events, default 'True'
        └── nowait:    Do not wait for job to complete, default 'False'
nf#
```

## Python API Reference

::: norfab.workers.fakenos_worker.nornir_inventory_tasks.FakeNOSNornirInventoryTasks.get_nornir_inventory
