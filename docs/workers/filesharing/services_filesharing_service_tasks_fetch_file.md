---
tags:
  - filesharing
---

# Filesharing Service Fetch File Task

> task api name: `fetch_file`

The `fetch_file` task streams a file from the File Sharing worker to the client in chunks with offset support. This enables efficient downloading of large files with resume capability. The task is typically called through the client helper method `NFPClient.fetch_file()` which handles the streaming protocol, caching, and local file management automatically.

## Using it from Python

```python
from norfab.core.nfapi import NorFab

with NorFab(inventory="./inventory.yaml") as nf:
    client = nf.make_client()

    # Download file (recommended way - uses client helper)
    ret = client.fetch_file(url="nf://filesharing/test_file_1.txt")
    local_path = ret["content"]
    print(local_path)

    # Download and read content as text
    ret = client.fetch_file(url="nf://filesharing/test_file_1.txt", read=True)
    print(ret["content"])  # text content

    # Direct task invocation (not recommended - use client helper instead)
    reply = client.run_job(
        service="filesharing",
        task="fetch_file",
        workers="any",
        kwargs={
            "url": "nf://filesharing/test_file_1.txt",
            "chunk_size": 256000,
            "offset": 0,
        },
    )
    print(reply)
```

## Using it from `nfcli`

NORFAB CLI exposes File Sharing under the `file` command group.

```
nf#man tree file.copy
root
└── file:    File sharing service
    └── copy:    Copy files
        ├── url:    File location, default 'nf://'
        ├── destination:    File location to save downloaded content
        └── read:    Print file content, default 'False'

nf#
```

## API Reference

::: norfab.workers.filesharing_worker.filesharing_worker.FileSharingWorker.fetch_file
