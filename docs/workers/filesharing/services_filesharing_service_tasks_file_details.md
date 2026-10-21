---
tags:
  - filesharing
---

# Filesharing Service File Details Task

> task api name: `file_details`

The `file_details` task returns metadata about one or more files, including existence status, size in bytes, and MD5 hash. Use it to verify file integrity or check a file before downloading it.

## Output

Returns results keyed by requested URL. Each entry contains `failed`, `errors`, and `result`; successful result payloads contain `exists`, `size_bytes`, and `md5hash`. Missing or unsafe files fail individually. An empty list returns an empty mapping. A string URL retains the original single-file result containing metadata directly, or a failed result for a missing or unsafe file.

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
            kwargs={"url": ["nf://filesharing/test_file_1.txt"]},
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
            kwargs={"url": ["nf://templates/base.j2"]},
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

Batch entry errors are also collected in the outer result's `errors` list, while successful entries remain available.
