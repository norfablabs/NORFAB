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

## Inputs

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `network` | `str` or `None` | `None` | Name of the network to stop. If `None`, all currently running networks are stopped. |

## Output

Returns a stop result for the requested network, or for all running networks when `network` is omitted.

## Examples

=== "CLI"

    Stop a single network:

    ```bash
    nf#fakenos stop network lab1
    ```

    Stop all running networks:

    ```bash
    nf#fakenos stop
    ```

=== "Python"

    Context manager:

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()

        result = client.run_job(
            service="fakenos",
            task="stop",
            workers="any",
            kwargs={"network": "lab1"},
        )
        print(result)
    ```

    Direct lifecycle - stop all networks:

    ```python
    from norfab.core.nfapi import NorFab

    nf = NorFab(inventory="./inventory.yaml")
    try:
        nf.start()
        client = nf.make_client()

        result = client.run_job(
            service="fakenos",
            task="stop",
            workers="any",
            kwargs={},
        )
        print(result)
    finally:
        nf.destroy()
    ```

## FakeNOS Stop Command Shell Reference

NorFab shell supports these command options for FakeNOS `stop` task:

```bash
nf# man tree fakenos.stop

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
