---
tags:
  - filesharing
---

# Filesharing Service List Files Task

> task api name: `list_files`

The `list_files` task lists the immediate files and subdirectories under a File Sharing URL. It does not descend into nested directories.

## Inputs

| Parameter | Required | Description |
|---|---:|---|
| `url` | No | Directory URL to list, default `nf://` |

## Output

Returns directory entries for the requested `nf://` URL. Results are worker keyed when called through `client.run_job(...)`.

## Examples

=== "CLI"

    List the repository root:

    ```bash
    nf#file list url nf://
    ```

    List a subdirectory:

    ```bash
    nf#file list url nf://templates/
    ```

=== "Python"

    Context manager:

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()

        result = client.run_job(
            service="filesharing",
            task="list_files",
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
            task="list_files",
            workers="any",
            kwargs={"url": "nf://templates/"},
        )
        print(result)
    finally:
        nf.destroy()
    ```

## Filesharing List Files Command Shell Reference

NorFab shell supports these command options for Filesharing `list_files` task:

```bash
nf# man tree file.list
root
└── file:    File sharing service
    └── list:    List files
        └── url:    Directory to list content for, default 'nf://'

nf#
```

## Python API Reference

::: norfab.workers.filesharing_worker.filesharing_worker.FileSharingWorker.list_files
