---
tags:
  - services
  - nfcli
---

# NORFAB File Service (File Sharing)

NORFAB includes a built-in **File Sharing** service (`service="filesharing"`) that lets clients and workers access files by an `nf://...` URL.

Common uses:

- Store templates, playbooks, golden configs, and other “assets” next to your inventory.
- Let workers download an input file (for example: Nornir `file_copy` can accept `nf://...` sources).
- Browse what files are available and fetch them locally.

For protocol-level streaming details, see [development/file_streaming_fetch_file.md](development/file_streaming_fetch_file.md).

## How it is enabled

When you start NORFAB via `NorFab` (NFAPI) **with the broker enabled**, NFAPI injects a filesharing worker:

- Worker name: `filesharing-worker-1`
- Service: `filesharing`
- Base directory: `base_dir = <inventory.base_dir>`

That means you usually do not need to add a File Sharing worker manually.

If you do want to define it explicitly (or point it at a different directory), add it to inventory:

```yaml title="inventory.yaml"
workers:
  filesharing-worker-1:
    - service: filesharing
      base_dir: ./

topology:
  broker: true
  workers:
    - filesharing-worker-1
```

## URL format and path rules

File Sharing uses URLs in the form:

- `nf://<path>`

Where `<path>` is resolved **relative to the File Sharing worker `base_dir`**.

Examples (assuming `base_dir` is your inventory folder):

- `nf://filesharing/test_file_1.txt` → `<base_dir>/filesharing/test_file_1.txt`
- `nf://cli/commands.txt` → `<base_dir>/cli/commands.txt`

The service rejects:

- Non-`nf://` URLs
- Absolute paths
- Directory traversal (paths that would escape `base_dir`)

## What the service provides

The File Sharing worker exposes these tasks:

- `list_files(url="nf://...")` — list directory entries (non-recursive)
- `walk(url="nf://...")` — recursively list files under a directory (returns a list of `nf://...` file URLs)
- `file_details(url="nf://...")` — returns `{exists, size_bytes, md5hash}`
- `fetch_file(url="nf://...", chunk_size=...)` — streams the file to the client (usually you call the client helper, not this task directly)

On the client side, you typically use:

- `NFPClient.fetch_file(url=...)`
- `NFPClient.delete_fetched_files(filepath=...)`

## Using it from Python

### List files

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

### Browse recursively (walk)

```python
files = client.run_job(
    service="filesharing",
    task="walk",
    workers="any",
    kwargs={"url": "nf://"},
)
print(files)
```

### Get file details (size + md5)

```python
details = client.run_job(
    service="filesharing",
    task="file_details",
    workers="any",
    kwargs={"url": "nf://filesharing/test_file_1.txt"},
)
print(details)
```

### Download a file (streaming)

`fetch_file()` downloads into the client’s local folder:

- `<client base_dir>/fetchedfiles/<nf-path>`

It also does a quick cache check: if the destination file already exists and the MD5 matches, it will not download again.

```python
ret = client.fetch_file(url="nf://filesharing/test_file_1.txt")
local_path = ret["content"]
print(local_path)
```

To read the file content as UTF-8 text:

```python
ret = client.fetch_file(url="nf://filesharing/test_file_1.txt", read=True)
print(ret["content"])  # text
```

Notes:

- `read=True` reads the downloaded file using UTF-8. For binary files, keep `read=False` and open the returned path in binary mode.
- For large files or slow links, you can tune `chunk_size`, `pipeline`, and `timeout`.

### Delete downloaded (fetched) files

`delete_fetched_files()` removes files under `<base_dir>/fetchedfiles/` using a glob pattern:

```python
# delete everything
client.delete_fetched_files(filepath="*")

# delete one file (any folder depth)
client.delete_fetched_files(filepath="*test_file_1.txt")
```

## Using it from `nfcli`

NORFAB CLI exposes File Sharing under the `file` command group.

```
nf#man tree file
root
└── file:    File sharing service
    ├── list:    List files
    │   └── url:    Directory to list content for, default 'nf://'
    ├── copy:    Copy files
    │   ├── url:    File location, default 'nf://'
    │   ├── destination:    File location to save downloaded content
    │   └── read:    Print file content, default 'False'
    ├── details:    Show file details
    │   └── url:    File location, default 'nf://'
    └── delete-fetched-files:    Delete local client files
        ├── timeout:    Job timeout
        ├── workers:    Filter workers to target, default 'all'
        ├── verbose-result:    Control output details, default 'False'
        ├── progress:    Display progress events, default 'True'
        └── filepath:    Files location glob pattern, default '*'
nf#
```

## API Reference

::: norfab.workers.filesharing_worker.filesharing_worker.FileSharingWorker
