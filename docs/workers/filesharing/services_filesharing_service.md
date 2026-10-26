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

Downloads, uploads, metadata, caching, and checksum verification belong to the
[core file-transfer APIs](../../api_ref/core/api_reference_core_file_transfer.md).
FileSharing handles publication and Git synchronization. Directory browsing
uses the inherited [core tasks](../../api_ref/core/api_reference_core_file_transfer.md#browse-worker-files).

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

Published nf:// paths cannot escape the configured base directory. Git URLs
must identify a configured remote and file path. These publication rules do not
restrict native filesystem paths supplied to core transfer tasks.

Client and worker fetch helpers resolve `git://` automatically through
`resolve_git_url`. The core serving task then reads the resolved `nf://` path.

## What the service provides

The FileSharing-specific tasks include:

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

The former FileSharing `fetch_file` and `file_details` tasks are removed.
Use `client.fetch_file()` to download and core `file_stat` to inspect metadata.
CLI `file copy` and `show filesharing files details` commands remain available;
see the [core reference](../../api_ref/core/api_reference_core_file_transfer.md).
