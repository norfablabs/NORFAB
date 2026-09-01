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

## Inputs

| Parameter | Required | Description |
|---|---:|---|
| `url` | Yes | `nf://` file URL, or `git://<remote-name>/<path>` when using the client or worker helper |
| `chunk_size` | No | Number of bytes to return from the given offset when invoking the task directly |
| `offset` | No | Byte offset for direct task invocation |
| `destination` | No | Local destination path when using the CLI/helper |
| `read` | No | Return file content as text instead of only downloading |

## Output

The client helper returns a dictionary whose `content` value is either the local file path or the file text when `read=True`. Direct task invocation returns a chunk-oriented response intended for the helper protocol.

## Examples

=== "CLI"

    Download a file:

    ```bash
    nf#file copy url nf://filesharing/test_file_1.txt destination ./test_file_1.txt
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

    Direct lifecycle - direct task invocation:

    ```python
    from norfab.core.nfapi import NorFab

    nf = NorFab(inventory="./inventory.yaml")
    try:
        nf.start()
        client = nf.make_client()

        result = client.run_job(
            service="filesharing",
            task="fetch_file",
            workers="any",
            kwargs={
                "url": "nf://filesharing/test_file_1.txt",
                "chunk_size": 256000,
                "offset": 0,
            },
        )
        print(result)
    finally:
        nf.destroy()
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

::: norfab.workers.filesharing_worker.filesharing_worker.FileSharingWorker.fetch_file
