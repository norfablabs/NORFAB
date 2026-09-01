---
tags:
  - services
  - nfcli
---

# NORFAB File Service (File Sharing)

NORFAB includes a built-in **File Sharing** service (`service="filesharing"`)
that lets clients and workers access published files by an `nf://...` URL or
synchronize and fetch a configured Git remote with a `git://...` URL.

Common uses:

- Store templates, playbooks, golden configs, and other "assets" next to your inventory.
- Let workers download an input file (for example: Nornir `file_copy` can accept `nf://...` sources).
- Browse what files are available and fetch them locally.
- Make read-only Git repository snapshots available in the `nf://` namespace
  and synchronize them on demand through `git://`.

For protocol-level streaming details, see [development/file_streaming_fetch_file.md](../../development/file_streaming_fetch_file.md).

## URL format and path rules

File Sharing uses URLs in the form:

- `nf://<path>`
- `git://<remote-name>/<path>`

Where `<path>` is resolved **relative to the File Sharing worker `base_dir`**.

Examples (assuming `base_dir` is your inventory folder):

- `nf://filesharing/test_file_1.txt` → `<base_dir>/filesharing/test_file_1.txt`
- `nf://cli/commands.txt` → `<base_dir>/cli/commands.txt`

For example, `git://network-assets/templates/base.j2` synchronizes the
configured `network-assets` remote, resolves its mount, and fetches
`templates/base.j2`.

The service rejects unsupported schemes, absolute paths, directory traversal,
and `git://` URLs that do not identify a configured remote and file path.

Only the client and worker fetch helpers accept `git://`; low-level File Sharing
tasks continue to operate on the resolved `nf://` mount.

## What the service provides

The File Sharing worker exposes these tasks:

- **[list_files](services_filesharing_service_tasks_list_files.md)** — list directory entries (non-recursive)
- **[walk](services_filesharing_service_tasks_walk.md)** — recursively list files under a directory (returns a list of `nf://...` file URLs)
- **[file_details](services_filesharing_service_tasks_file_details.md)** — returns file metadata including existence, size in bytes, and MD5 hash
- **[fetch_file](services_filesharing_service_tasks_fetch_file.md)** — streams the file to the client with chunking and offset support
- **[create_remote_git](services_filesharing_service_tasks_create_remote_git.md)** — registers a Git remote and initializes its private local repository
- **[git_clone](services_filesharing_service_tasks_git_clone.md)** — fetches a registered Git remote and makes its current branch available under `nf://`
- **[delete_remote_git](services_filesharing_service_tasks_delete_remote_git.md)** — deletes and unregisters a runtime Git remote

The `get_remotes` task returns the live remote registry, including mount URLs,
status, and the last synchronization attempt. NFCLI exposes it through
`show filesharing remotes`.

The `resolve_git_url` task synchronizes the remote named by a `git://` file URL
and returns its published `nf://` URL. Client and worker file-fetch helpers call
this task automatically and continue the transfer against the same File Sharing
worker.

For detailed information about each task, see the individual task documentation pages linked above.
