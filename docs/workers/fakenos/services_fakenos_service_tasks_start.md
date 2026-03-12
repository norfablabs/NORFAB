---
tags:
  - fakenos
---

# FakeNOS Service Start Task

> task api name: `start`

The FakeNOS service `start` task launches a new virtual network in a dedicated child process. Each network runs independently, and the task returns detailed information about the started network and its hosts once the network is up.

## FakeNOS Start Task Overview

The `start` task provides the following features:

- **Network Isolation**: Each virtual network runs in its own OS child process, preventing one network's activity from blocking others.
- **Flexible Inventory**: Accepts an inline dict, a file path, or a URL pointing to a FakeNOS inventory YAML file.
- **Immediate Feedback**: Returns host details (name, platform, port, credentials) for the newly started network.

## FakeNOS Start Task Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `network` | `str` | required | Unique name to assign to the new FakeNOS network. |
| `inventory` | `str`, `dict`, or `None` | `None` | Inventory to use for the network. A `str` is treated as a file path or URL and fetched as YAML. A `dict` is used directly. `None` uses the default inventory from the worker configuration. |

## FakeNOS Start Task Return Data

The `start` task returns the same structure as [inspect_networks](services_fakenos_service_tasks_inspect_networks.md) with `details=True`, scoped to the newly started network.

| Field | Type | Description |
|-------|------|-------------|
| `pid` | `int` | OS process ID of the child process running the network. |
| `alive` | `bool` | Whether the child process is still running. |
| `hosts` | `list` | List of host dicts with `name`, `platform`, `port`, `username`, `password`. |
| `hosts_count` | `int` | Number of hosts in the network. |
| `status` | `str` | Process status string from `psutil` (e.g. `sleeping`, `running`). |
| `uptime_seconds` | `int` | Seconds elapsed since the network was started. |
| `cpu_percent` | `float` | CPU usage percentage of the child process. |
| `memory_rss_mb` | `float` | Resident set size memory in MB. |
| `memory_vms_mb` | `float` | Virtual memory size in MB. |
| `num_threads` | `int` | Number of threads in the child process. |

## FakeNOS Start Command Shell Reference

NorFab shell supports these command options for Netbox `create_prefix` task:

```
nf#man tree fakenos.start

R - required field, M - supports multiline input, D - dynamic key

root
└── fakenos:    FakeNOS service
    └── start:    FakeNOS start command
        ├── network (R):    FakeNOS network name to start
        ├── inventory:    Inventory content (dict) or path/URL to an inventory file
        ├── timeout:    Job timeout
        ├── workers:    Filter workers to target, default 'all'
        ├── verbose-result:    Control output details, default 'False'
        ├── progress:    Display progress events, default 'True'
        └── nowait:    Do not wait for job to complete, default 'False'
nf#
```

## Python API Reference

::: norfab.workers.fakenos_worker.fakenos_worker.FakeNOSWorker.start