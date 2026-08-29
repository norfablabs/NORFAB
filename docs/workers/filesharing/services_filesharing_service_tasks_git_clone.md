---
tags:
  - filesharing
  - git
---

# Filesharing Clone Git Remote Task

> task api name: `git_clone`

The `git_clone` task shallow-fetches a registered remote's branch and makes its
checked-out files available to NorFab workers at the configured `nf://` mount.

## Inputs

| Parameter | Required | Description |
|---|---:|---|
| `name` | Yes | Name previously registered by `create_remote_git` |

## Output

The result contains the name, synchronization status, and UTC attempt time:

```json
{
  "name": "automation-assets",
  "status": "cloned",
  "last_sync_attempt": "2026-08-29T10:30:00+00:00"
}
```

Status is `cloned` when content is made available and `unchanged` when the fetched
commit matches the previous local HEAD and the mount exists. Failures return
`failed` and preserve the previous shared snapshot.

## Examples

=== "CLI"

    ```bash
    nf# filesharing git clone-remote name automation-assets
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    nf = NorFab(inventory="./inventory.yaml")
    try:
        nf.start()
        client = nf.make_client()
        result = client.run_job(
            service="filesharing",
            task="git_clone",
            workers="filesharing-worker-1",
            kwargs={"name": "automation-assets"},
        )
        print(result)
    finally:
        nf.destroy()
    ```

## Notes

- Create or configure the remote in inventory before cloning it.
- Public HTTPS remotes need no credentials.
- Authenticated remotes use the username and password/token registered at creation.
- A per-remote lock prevents clone, create, and delete operations from overlapping.
- `.git` and symbolic links are not made available.

## Task Command Shell Reference

```bash
nf#man tree filesharing.git.clone-remote

R - required field, M - supports multiline input, D - dynamic key

root
└── filesharing:    File sharing service
    └── git:    Manage Git remotes
        └── clone-remote:    Synchronize a Git remote and make it available
            ├── timeout:    Job timeout
            ├── workers:    Filter workers to target, default 'all'
            ├── verbose-result:    Control output details, default 'False'
            ├── nowait:    Do not wait for job to complete, default 'False'
            └── name (R):    Configured remote name
nf#
```

## Python API Reference

::: norfab.workers.filesharing_worker.git_tasks.GitTasks.git_clone
