---
tags:
  - fakenos
---

# FakeNOS Service Restart Task

> task api name: `restart`

The FakeNOS service `restart` task stops a running virtual network and immediately starts it again using the same inventory. This allows you to refresh a network's simulated devices without having to re-supply the inventory configuration.

## FakeNOS Restart Task Overview

The `restart` task provides the following features:

- **Inventory Preservation**: Reuses the inventory that was provided when the network was originally started — no need to re-fetch or re-specify it.
- **Seamless Re-initialisation**: Stops the existing child process cleanly, then spawns a new one with the same configuration.
- **Immediate Feedback**: Returns the same detailed host and process information as the [start](services_fakenos_service_tasks_start.md) task.


## FakeNOS Restart Task Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `network` | `str` | required | Name of the FakeNOS network to restart. The network must already be running. |

## FakeNOS Restart Command Shell Reference

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

::: norfab.workers.fakenos_worker.fakenos_worker.FakeNOSWorker.restart