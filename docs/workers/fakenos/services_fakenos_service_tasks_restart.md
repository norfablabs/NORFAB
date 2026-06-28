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


## Inputs

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `network` | `str` | required | Name of the FakeNOS network to restart. The network must already be running. |

## Output

Returns the same detailed host and process information as the [start](services_fakenos_service_tasks_start.md) task for the restarted network.

## Examples

=== "CLI"

    Restart a running network:

    ```bash
    nf#fakenos restart network lab1
    ```

=== "Python"

    Context manager:

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()

        result = client.run_job(
            service="fakenos",
            task="restart",
            workers="any",
            kwargs={"network": "lab1"},
        )
        print(result)
    ```

    Direct lifecycle:

    ```python
    from norfab.core.nfapi import NorFab

    nf = NorFab(inventory="./inventory.yaml")
    try:
        nf.start()
        client = nf.make_client()

        result = client.run_job(
            service="fakenos",
            task="restart",
            workers="any",
            kwargs={"network": "lab1"},
        )
        print(result)
    finally:
        nf.destroy()
    ```

## FakeNOS Restart Command Shell Reference

NorFab shell supports these command options for FakeNOS `restart` task:

```bash
nf# man tree fakenos.restart

R - required field, M - supports multiline input, D - dynamic key

root
└── fakenos:    FakeNOS service
    └── restart:    FakeNOS restart command
        ├── network (R):    FakeNOS network name to restart
        ├── timeout:    Job timeout
        ├── workers:    Filter workers to target, default 'all'
        ├── verbose-result:    Control output details, default 'False'
        ├── progress:    Display progress events, default 'True'
        └── nowait:    Do not wait for job to complete, default 'False'
nf#
```

## Python API Reference

::: norfab.workers.fakenos_worker.fakenos_worker.FakeNOSWorker.restart
