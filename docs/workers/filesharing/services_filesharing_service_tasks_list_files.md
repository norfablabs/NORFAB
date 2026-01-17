---
tags:
  - filesharing
---

# Filesharing Service List FIles Task

> task api name: `list_files`

The `list_files` task lists the contents of a directory at the specified URL path in a non-recursive manner. This task returns only the immediate files and subdirectories within the given path, without descending into nested directories. It's useful for browsing the structure of your file sharing repository one level at a time.

## Using it from Python

```python
from norfab.core.nfapi import NorFab

with NorFab(inventory="./inventory.yaml") as nf:
    client = nf.make_client()

    reply = client.run_job(
        service="filesharing",
        task="list_files",
        workers="any",
        kwargs={"url": "nf://"},
    )
    print(reply)
```

## Using it from `nfcli`

NORFAB CLI exposes File Sharing under the `file` command group.

```
nf#man tree file.list
root
└── file:    File sharing service
    └── list:    List files
        └── url:    Directory to list content for, default 'nf://'

nf#
```

## API Reference

::: norfab.workers.filesharing_worker.filesharing_worker.FileSharingWorker.list_files
