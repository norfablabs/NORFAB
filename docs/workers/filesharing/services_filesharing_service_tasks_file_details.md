---
tags:
  - filesharing
---

# Filesharing Service File Details Task

> task api name: `file_details`

The `file_details` task returns metadata about a file including its existence status, size in bytes, and MD5 hash. This is useful for verifying file integrity, checking if a file exists before downloading, or comparing local and remote file versions without transferring the entire file.

## Using it from Python

```python
from norfab.core.nfapi import NorFab

with NorFab(inventory="./inventory.yaml") as nf:
    client = nf.make_client()

    reply = client.run_job(
        service="filesharing",
        task="file_details",
        workers="any",
        kwargs={"url": "nf://filesharing/test_file_1.txt"},
    )
    print(reply)
```

## Using it from `nfcli`

NORFAB CLI exposes File Sharing under the `file` command group.

```
nf#man tree file.details
root
└── file:    File sharing service
    └── details:    Show file details
        └── url:    File location, default 'nf://'

nf#
```

## API Reference

::: norfab.workers.filesharing_worker.filesharing_worker.FileSharingWorker.file_details
