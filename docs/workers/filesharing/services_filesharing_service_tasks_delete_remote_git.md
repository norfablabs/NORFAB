---
tags:
  - filesharing
  - git
---

# Filesharing Delete Git Remote Task

> task api name: `delete_remote_git`

The `delete_remote_git` task unregisters a runtime Git remote and removes its
private repository, staging folder, and shared mount.

## Inputs

| Parameter | Required | Description |
|---|---:|---|
| `name` | Yes | Registered remote name to delete |

## Output

Successful deletion returns `true`. An unknown name returns a failed result with
no boolean result.

```json
true
```

## Examples

=== "CLI"

    ```bash
    nf# filesharing git delete-remote name automation-assets
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()
        result = client.run_job(
            service="filesharing",
            task="delete_remote_git",
            workers="filesharing-worker-1",
            kwargs={"name": "automation-assets"},
        )
        print(result)
    ```

## Notes

- Deletion is limited to the registered repository path and safe `nf://` mount.
- Deleting an inventory remote affects the running worker only. It is registered
  again when the worker restarts.
- The task waits for an active operation on the same remote, subject to the job
  timeout.

## Task Command Shell Reference

```bash
nf#man tree filesharing.git.delete-remote

R - required field, M - supports multiline input, D - dynamic key

root
└── filesharing:    File sharing service
    └── git:    Manage Git remotes
        └── delete-remote:    Delete and unregister a Git remote
            ├── timeout:    Job timeout
            ├── workers:    Filter workers to target, default 'all'
            ├── verbose-result:    Control output details, default 'False'
            ├── nowait:    Do not wait for job to complete, default 'False'
            └── name (R):    Configured remote name
nf#
```

## Python API Reference

::: norfab.workers.filesharing_worker.git_tasks.GitTasks.delete_remote_git
