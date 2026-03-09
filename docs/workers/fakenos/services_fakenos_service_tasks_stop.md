---
tags:
  - fakenos
---

# FakeNOS Service Stop Task

> task api name: `stop`

The FakeNOS service `stop` task gracefully terminates one or all running FakeNOS virtual networks. The task signals each target child process to exit, waits up to one second for a clean shutdown, and forcibly kills any process that does not stop in time.

## FakeNOS Stop Task Overview

The `stop` task provides the following features:

- **Selective Stop**: Stop a single network by name or all networks at once by omitting the `network` argument.
- **Graceful Shutdown**: Sends a stop signal to the child process and waits up to one second before forcibly killing it.
- **Automatic Cleanup**: Removes stopped networks from the worker's internal tracking dictionary.

## FakeNOS Stop Task Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `network` | `str` or `None` | `None` | Name of the network to stop. If `None`, all currently running networks are stopped. |

## FakeNOS Stop Command Shell Reference

NorFab shell supports these command options for Netbox `create_prefix` task:

```
nf#man tree fakenos.stop

R - required field, M - supports multiline input, D - dynamic key

root
└── fakenos:    FakeNOS service
    └── stop:    FakeNOS stop command
        ├── network:    FakeNOS network name to stop; stops all networks if omitted
        ├── timeout:    Job timeout
        ├── workers:    Filter workers to target, default 'all'
        ├── verbose-result:    Control output details, default 'False'
        ├── progress:    Display progress events, default 'True'
        └── nowait:    Do not wait for job to complete, default 'False'
nf#

```

## Python API Reference

::: norfab.workers.fakenos_worker.fakenos_worker.FakeNOSWorker.stop
