---
tags:
  - filesharing
---

# Filesharing Service Walk Task

> task api name: `walk`

The `walk` task recursively lists all files from all subdirectories under the specified URL path. This is useful when you need to discover all files available in a directory tree, returning a list of complete `nf://...` URLs for each file found. The task skips hidden files (starting with `.`) and special directories (containing `__`).

## Using it from Python

```python
from norfab.core.nfapi import NorFab

with NorFab(inventory="./inventory.yaml") as nf:
    client = nf.make_client()

    reply = client.run_job(
        service="filesharing",
        task="walk",
        workers="any",
        kwargs={"url": "nf://"},
    )
    print(reply)
```

## Using it from `nfcli`

NORFAB CLI exposes File Sharing under the `file` command group.

```
nf#man tree file
root
└── file:    File sharing service
    └── walk:    Walk directory tree recursively

nf#
```

## API Reference

::: norfab.workers.filesharing_worker.filesharing_worker.FileSharingWorker.walk
