---
tags:
  - fakenos
---

# FakeNOS Service Inspect Networks Task

> task api name: `inspect_networks`

The FakeNOS service `inspect_networks` task returns status and host information for one or all running FakeNOS virtual networks. It can return a simple list of network names or rich per-network details including process metrics and host inventories.

## FakeNOS Inspect Networks Task Overview

The `inspect_networks` task provides the following features:

- **Network Summary**: Returns a list of running network names when `details=False`.
- **Detailed View**: When `details=True`, queries each child process for its host list and enriches the result with process-level metrics from `psutil` (CPU, memory, uptime, thread count).
- **Selective Query**: Optionally scope the result to a single named network.

## FakeNOS Inspect Networks Task Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `network` | `str` or `None` | `None` | Name of the network to inspect. If `None`, all running networks are returned. |
| `details` | `bool` | `True` | When `True`, returns full host and process information. When `False`, returns only the list of network names. |

## FakeNOS Inspect Networks Task Return Data

### Detailed mode (`details=True`)

Returns a dict keyed by network name. Each value is a dict with the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `pid` | `int` | OS process ID of the child process running the network. |
| `alive` | `bool` | Whether the child process is still running. |
| `hosts` | `list` | List of host dicts, each with `name`, `platform`, `port`, `username`, `password`. |
| `hosts_count` | `int` | Number of hosts in the network. |
| `status` | `str` | Process status from `psutil` (e.g. `sleeping`, `running`). |
| `uptime_seconds` | `int` | Seconds elapsed since the network was started. |
| `cpu_percent` | `float` | CPU usage percentage of the child process. |
| `memory_rss_mb` | `float` | Resident set size memory in MB. |
| `memory_vms_mb` | `float` | Virtual memory size in MB. |
| `num_threads` | `int` | Number of threads in the child process. |

!!! note

    The `status`, `uptime_seconds`, `cpu_percent`, `memory_rss_mb`, `memory_vms_mb`, and `num_threads` fields are populated via `psutil`. If the child process is not accessible (e.g. access denied), these fields will be absent and a warning is logged.

### Summary mode (`details=False`)

Returns a list of strings — one entry per running network name.

## FakeNOS Inspect Networks Command Shell Reference

NorFab shell supports these command options for Netbox `create_prefix` task:

```
nf#man tree show.fakenos.networks

R - required field, M - supports multiline input, D - dynamic key

root
└── show:    NorFab show commands
    └── fakenos:    Show FakeNOS service
        └── networks:    show FakeNOS networks details
            ├── network:    FakeNOS network name to show; shows all networks if omitted
            └── details:    show network details, default 'False'
nf#
```

## Python API Reference

::: norfab.workers.fakenos_worker.fakenos_worker.FakeNOSWorker.inspect_networks