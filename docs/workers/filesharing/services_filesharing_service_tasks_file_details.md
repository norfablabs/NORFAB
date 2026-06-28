---
tags:
  - filesharing
---

# Filesharing Service File Details Task

> task api name: `file_details`

The `file_details` task returns metadata about a file, including existence status, size in bytes, and MD5 hash. Use it to verify file integrity or check a file before downloading it.

## Inputs

| Parameter | Required | Description |
|---|---:|---|
| `url` | Yes | File URL to inspect |

## Output

Returns metadata for the requested file, including whether it exists, its size, and its MD5 hash when available.

## Examples

=== "CLI"

    Show file details:

    ```bash
    nf#file details url nf://filesharing/test_file_1.txt
    ```

=== "Python"

    Context manager:

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()

        result = client.run_job(
            service="filesharing",
            task="file_details",
            workers="any",
            kwargs={"url": "nf://filesharing/test_file_1.txt"},
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
            task="file_details",
            workers="any",
            kwargs={"url": "nf://templates/base.j2"},
        )
        print(result)
    finally:
        nf.destroy()
    ```

## Filesharing File Details Command Shell Reference

NorFab shell supports these command options for Filesharing `file_details` task:

```bash
nf# man tree file.details
root
└── file:    File sharing service
    └── details:    Show file details
        └── url:    File location, default 'nf://'

nf#
```

## Python API Reference

::: norfab.workers.filesharing_worker.filesharing_worker.FileSharingWorker.file_details
