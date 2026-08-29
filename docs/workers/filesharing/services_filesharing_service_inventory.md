# Filesharing Worker Inventory

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

## Configure Git remotes

Extend the built-in worker by associating an additional inventory file with
`filesharing-worker-1`:

```yaml title="inventory.yaml"
workers:
  filesharing-worker-1:
    - filesharing/remotes.yaml
```

Define remotes as a list in that file:

```yaml title="filesharing/remotes.yaml"
service: filesharing

remotes:
  - name: automation-assets
    description: Shared automation templates
    type: git
    url: https://github.com/example/automation-assets.git
    branch: main
    mount: repositories/automation-assets
    auto_sync: true
    sync_interval: 300

  - name: private-runbooks
    description: Authenticated runbooks repository
    type: git
    url: https://github.com/example/private-runbooks.git
    branch: main
    username: '{{ env["GITHUB_USERNAME"] }}'
    password: '{{ env["GITHUB_TOKEN"] }}'
    auto_sync: false
```

The first remote is available at `nf://repositories/automation-assets/`. The
second omits `mount`, so it uses its name and is available at
`nf://private-runbooks/`.

| Key | Required | Default | Description |
|---|---:|---|---|
| `name` | Yes | — | Unique runtime name used by clone and delete tasks |
| `type` | Yes | — | Remote driver; currently `git` |
| `url` | Yes | — | Git repository URL |
| `branch` | For Git | — | Branch fetched by GitPython |
| `mount` | No | `name` | Safe relative path made available under `nf://` |
| `description` | No | Empty | Operator-facing description |
| `username` | No | `null` | HTTPS username; must be supplied with `password` |
| `password` | No | `null` | HTTPS password or token; must be supplied with `username` |
| `auto_sync` | No | `false` | Enable periodic synchronization |
| `sync_interval` | No | `30` | Seconds between attempts, clamped to 5–86,400 |

Mounts cannot be absolute, contain traversal components, or overlap another
remote mount. Task and inventory output redact non-empty passwords.

## Understand synchronization

At startup, the worker calls `create_remote_git` for every inventory remote.
This initializes a private repository and registers the remote in memory, but
does not contact the Git server or make repository content available.

Call `git_clone` to make a remote available manually. For `auto_sync: true`, the worker
also calls it when `sync_interval` elapses. Synchronization shallow-fetches the
configured branch, checks it out, and compares the fetched commit with the
previous local Git HEAD. Changed content is copied into a locked staging folder
and atomically moved to the configured mount. The task returns `unchanged` when
Git reports the same commit and the mount already exists.

Runtime status is kept in the live remote registry rather than a database.
`show filesharing remotes detail` displays each status and last attempt;
`show filesharing remotes summary` provides the corresponding nested summary.
Remotes created through the task API exist until deletion or worker restart;
place a remote in inventory when it must be recreated automatically.
