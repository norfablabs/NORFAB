---
tags:
  - services
  - nfcli
---

# NORFAB File Service (File Sharing)

NORFAB includes a built-in **File Sharing** service (`service="filesharing"`) that lets clients and workers access files by an `nf://...` URL.

Common uses:

- Store templates, playbooks, golden configs, and other "assets" next to your inventory.
- Let workers download an input file (for example: Nornir `file_copy` can accept `nf://...` sources).
- Browse what files are available and fetch them locally.

For protocol-level streaming details, see [development/file_streaming_fetch_file.md](../../development/file_streaming_fetch_file.md).

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

- **[list_files](services_filesharing_service_tasks_list_files.md)** — list directory entries (non-recursive)
- **[walk](services_filesharing_service_tasks_walk.md)** — recursively list files under a directory (returns a list of `nf://...` file URLs)
- **[file_details](services_filesharing_service_tasks_file_details.md)** — returns file metadata including existence, size in bytes, and MD5 hash
- **[fetch_file](services_filesharing_service_tasks_fetch_file.md)** — streams the file to the client with chunking and offset support

For detailed information about each task, see the individual task documentation pages linked above.
