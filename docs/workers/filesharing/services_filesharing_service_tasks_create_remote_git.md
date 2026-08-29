---
tags:
  - filesharing
  - git
---

# Filesharing Create Git Remote Task

> task api name: `create_remote_git`

The `create_remote_git` task validates and registers a Git remote in worker
memory. It initializes the private local repository and configures `origin`, but
does not fetch or make repository content available.

## Inputs

| Parameter | Required | Default | Description |
|---|---:|---|---|
| `name` | Yes | — | Unique runtime remote name |
| `url` | Yes | — | Git repository URL |
| `type` | Yes | — | Must be `git` |
| `branch` | For Git | — | Branch cloned by `git_clone` |
| `mount` | No | `name` | Relative publication path under `nf://` |
| `description` | No | Empty | Operator-facing description |
| `username` | No | `null` | HTTPS username; requires `password` |
| `password` | No | `null` | HTTPS password or token; requires `username` |
| `auto_sync` | No | `false` | Enable periodic synchronization |
| `sync_interval` | No | `30` | Attempt interval in seconds, clamped to 5–86,400 |

## Output

A newly registered remote returns its name with `unsynchronized` status:

```json
{
  "name": "automation-assets",
  "status": "unsynchronized"
}
```

## Examples

=== "CLI"

    ```bash
    nf# filesharing git create-remote name automation-assets type git url https://github.com/example/automation-assets.git branch main mount repositories/automation-assets
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()
        result = client.run_job(
            service="filesharing",
            task="create_remote_git",
            workers="filesharing-worker-1",
            kwargs={
                "name": "automation-assets",
                "type": "git",
                "url": "https://github.com/example/automation-assets.git",
                "branch": "main",
                "mount": "repositories/automation-assets",
            },
        )
        print(result)
    ```

## Notes

- The remote exists in memory until it is deleted or the worker restarts.
- Inventory remotes are registered through this same task during startup.
- Credentials are used for Git fetches and are redacted from remote listings.
- Call `git_clone` to fetch content and make it available under `nf://`.

## Task Command Shell Reference

```bash
nf#man tree filesharing.git.create-remote

R - required field, M - supports multiline input, D - dynamic key

root
└── filesharing:    File sharing service
    └── git:    Manage Git remotes
        └── create-remote:    Register and initialize a Git remote
            ├── timeout:    Job timeout
            ├── workers:    Filter workers to target, default 'all'
            ├── verbose-result:    Control output details, default 'False'
            ├── nowait:    Do not wait for job to complete, default 'False'
            ├── name (R):    Unique name used to identify the remote
            ├── mount:    Relative path to make the repository available at; defaults to name
            ├── description:    Optional human-readable remote description, default ''
            ├── url (R):    Git repository URL
            ├── branch:    Git branch to synchronize
            ├── type (R):    Remote driver type; use git
            ├── username:    HTTPS username for an authenticated remote
            ├── password:    HTTPS password or access token for an authenticated remote
            ├── auto_sync:    Periodically synchronize the remote after it is created, default 'False'
            └── sync_interval:    Seconds between automatic synchronization attempts, default '30'
nf#
```

## Python API Reference

::: norfab.workers.filesharing_worker.git_tasks.GitTasks.create_remote_git
