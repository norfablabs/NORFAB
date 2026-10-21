---
tags:
  - filesharing
---

# Filesharing Service Fetch File Task

> task api name: `fetch_file`

The `fetch_file` task streams a file from the File Sharing worker to the client
in chunks with offset support. In most user code, prefer the client helper
method `NFPClient.fetch_file()` because it handles streaming, caching, local
file management, and on-demand Git remote synchronization.

## Output

The client helper accepts a URL string or list of URLs. A string returns the original `status`, `content`, and `error` dictionary; a list returns a list of those dictionaries in input order, preserving duplicate positions. Content is the local path or UTF-8 text with `read=True`. Metadata is checked in one batch, while changed files stream individually. Discovery queries all FileSharing workers. Each call rotates file selections across workers with successful metadata, skipping missing files. Each transfer uses its selected worker, including that worker's resolved Git mount. Local file and decoding errors propagate to the caller and stop a batch. The low-level worker task still streams one file per job and returns a boolean completion result; raw chunks arrive separately over STREAM messages.

## Examples

=== "CLI"

    Download a file:

    ```bash
    nf#file copy url nf://filesharing/test_file_1.txt
    ```

    Print file content:

    ```bash
    nf#file copy url nf://filesharing/test_file_1.txt read
    ```

    Synchronize a configured Git remote and print a file:

    ```bash
    nf#file copy url git://network-assets/README.md read
    ```

=== "Python"

    Context manager - helper method:

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()

        result = client.fetch_file(url="nf://filesharing/test_file_1.txt")
        local_path = result["content"]
        print(local_path)
    ```

    Context manager - read content as text:

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()

        result = client.fetch_file(
            url="nf://filesharing/test_file_1.txt",
            read=True,
        )
        print(result["content"])
    ```

    Context manager - synchronize and read a Git-backed file:

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()
        result = client.fetch_file(
            url="git://network-assets/templates/base.j2",
            read=True,
        )
        print(result["content"])
    ```

    Multiple files, including mixed sources:

    ```python
    urls = ["nf://templates/base.j2", "git://network-assets/README.md"]
    results = client.fetch_file(url=urls, read=True)
    for url, entry in zip(urls, results):
        print(url, entry["status"], entry["content"], entry["error"])
    ```

## Filesharing Fetch File Command Shell Reference

Direct task invocation requires the resolved `nf://` URL. The client helper
calls the File Sharing `resolve_git_url` task for `git://` inputs before
invoking the streaming task against the matching worker.

NorFab shell supports these command options for Filesharing `fetch_file` task:

```bash
nf# man tree file.copy
root
└── file:    File sharing service
    └── copy:    Copy files
        ├── url:    File location, default 'nf://'
        ├── destination:    File location to save downloaded content
        └── read:    Print file content, default 'False'

nf#
```

## Python API Reference

::: norfab.workers.filesharing_worker.local_files_tasks.LocalFilesTasks.fetch_file
