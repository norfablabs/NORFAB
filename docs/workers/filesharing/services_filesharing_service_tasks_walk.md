---
tags:
  - filesharing
---

# Filesharing Service Walk Task

> task api name: `walk`

The `walk` task recursively lists files under a File Sharing URL. It returns complete `nf://...` URLs for each file found and skips hidden files and special directories.

## Inputs

| Parameter | Required | Description |
|---|---:|---|
| `url` | No | Directory URL to walk, default `nf://` |

## Output

Returns a recursive list of file URLs under the requested path.

## Examples

=== "CLI"

    Walk the repository root:

    ```bash
    nf#file walk
    ```

    Walk a subdirectory:

    ```bash
    nf#file walk url nf://templates/
    ```

=== "Python"

    Context manager:

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()

        result = client.run_job(
            service="filesharing",
            task="walk",
            workers="any",
            kwargs={"url": "nf://"},
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
            service="filesharing",
            task="walk",
            workers="any",
            kwargs={"url": "nf://templates/"},
        )
        print(result)
    finally:
        nf.destroy()
    ```

## Filesharing Walk Command Shell Reference

NorFab shell supports these command options for Filesharing `walk` task:

```bash
nf# man tree file
root
└── file:    File sharing service
    └── walk:    Walk directory tree recursively

nf#
```

## Python API Reference

::: norfab.workers.filesharing_worker.filesharing_worker.FileSharingWorker.walk
