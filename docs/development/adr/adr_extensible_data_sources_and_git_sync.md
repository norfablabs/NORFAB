# ADR - File Sharing Git Remotes

## Status

Accepted, 2026-08-29. Amended, 2026-09-01, to add first-class on-demand
`git://` file retrieval.

## Decision

The File Sharing service will mirror configured Git repository branches into
local folders. Clients and workers can access already mirrored files through
existing URLs:

```text
nf://<remote-name>/<path/to/file>
```

The initial implementation is read-only. It supports startup creation, explicit
creation and deletion, and periodic refresh from Git remotes to local storage.
Remote write-back, webhooks, and SSH credential management are out of scope.
The client-side `git://<remote-name>/<path>` URL synchronizes a configured
remote on demand before retrieving the file from its published `nf://` mount.
`NFPClient` delegates the complete resolution to the File Sharing
`resolve_git_url` task; the task validates the remote and path, synchronizes the
repository, and returns the corresponding `nf://` URL.

## Remote Inventory

File Sharing inventory contains a `remotes` list. Each item has the same fixed
schema:

```yaml
service: filesharing
base_dir: "./shared"

remotes:
  - name: "openclaw-main"
    mount: "repositories/openclaw"
    description: "OpenClaw main branch"
    url: "https://github.com/openclaw/openclaw.git"
    branch: "main"
    type: "git"
    username: "octocat"
    password: '{{ env["GITHUB_TOKEN"] }}'
    auto_sync: true
    sync_interval: 30
```

| Key | Requirement |
| --- | --- |
| `name` | Required unique local name matching `[A-Za-z0-9][A-Za-z0-9._-]*` |
| `mount` | Optional relative publication path; defaults to `name` |
| `description` | Optional text; defaults to an empty string |
| `url` | Required remote URL |
| `branch` | Required for `type: git`; otherwise optional |
| `type` | Required remote type; this ADR implements `git` |
| `username` | Optional for public Git remotes; required when `password` is set |
| `password` | Optional for public Git remotes; required when `username` is set |
| `auto_sync` | Enable periodic refresh; defaults to `false` |
| `sync_interval` | Periodic refresh interval in seconds; defaults to `30` |

The remote model rejects unknown keys, empty required strings, path-like remote
names, unsafe mount paths, and mount collisions. The worker also resolves every mount through the same safe path check
used by local file tasks before creating or publishing content.

Every configured remote is initialized during worker startup, but content is
not fetched by `create_remote_git`. `auto_sync: false` disables periodic cloning
regardless of `sync_interval`; clients can still call `git_clone` explicitly.

During inventory loading, calculate the effective interval as
`max(5, min(sync_interval, 86_400))`. Values below 5 become 5 seconds, values
above 86,400 become 86,400 seconds, and values within that range are accepted
unchanged. Store and report the effective value. File Sharing logs one warning
when it clamps a value. Non-integer values fail inventory validation.

Inventory files may use Jinja2 to populate `username` and `password`. The remote
model receives the rendered values and does not read environment variables
itself. Public Git remotes may omit both fields; authenticated remotes must
provide both fields together.

The `password` field may contain a password, application password, or access
token according to the configured Git server. The GitHub integration inventory
uses a personal access token because GitHub does not accept account passwords
for Git authentication.

## Authentication

`type: git` selects the GitPython implementation in `git_tasks.py`. GitPython
runs the system Git executable and fetches the configured branch over HTTPS.
Public remotes use no authentication header. For authenticated remotes,
pass `username` and `password` as a temporary HTTP Basic authorization header
through the Git process environment. Do not put credentials in the clone URL or
persist them in Git configuration. Every Git fetch disables terminal prompts,
Git Credential Manager interaction and GUI prompts, and configured credential
helpers. Authentication failures fail the task without requesting user input.

## Local Layout and URLs

Each remote name owns one private Git repository and one staging folder. Its
mount owns the published folder:

```text
<worker-runtime>/remotes/<name>/
  repository/.git/          # private local repository and shallow history
  staging/snapshot/         # incomplete publication snapshot

<filesharing-base>/<mount>/
  ...             # files available through nf://<mount>/...
```

Different branches of one repository use separate remote entries and names:

```yaml
remotes:
  - name: "openclaw-main"
    mount: "openclaw-main"
    description: "Main branch"
    url: "https://github.com/openclaw/openclaw.git"
    branch: "main"
    type: "git"
    username: "octocat"
    password: '{{ env["GITHUB_TOKEN"] }}'
    auto_sync: true
    sync_interval: 30

  - name: "openclaw-development"
    mount: "openclaw-development"
    description: "Development branch"
    url: "https://github.com/openclaw/openclaw.git"
    branch: "development"
    type: "git"
    username: "octocat"
    password: '{{ env["GITHUB_TOKEN"] }}'
    auto_sync: false
    sync_interval: 30
```

Clients use `nf://openclaw-main/README.md` and
`nf://openclaw-development/README.md`. Each entry has independent repository,
staging, locking, and publication. No checkout is shared between branches.

Before replacing the `base_dir` inherited from `NFPWorker` with the configured
File Sharing publication path, preserve the inherited value as
`self.runtime_dir`. Private Git repositories are stored below
`self.runtime_dir`.

Inventory validation rejects names that collide after platform path
normalization or are unsafe on the current operating system. Inventory
configuration remains authoritative and remote synchronization state is not
persisted separately.

## Git Clone Operation

`create_remote_git` accepts the complete remote inventory fields, registers the
validated remote in worker memory, initializes its private repository, and
configures the credential-free `origin` URL. It does not contact the remote Git
server or publish content. Worker startup invokes this same task for every
inventory remote. Runtime-created remotes are not persisted across restarts.

The `git_clone(name)` task performs these steps under a per-remote lock:

1. Find the remote by `name` and select the Git driver.
2. Read the current local Git HEAD, then use GitPython to shallow-fetch the configured branch into the private local
   repository, check it out, and read its commit SHA.
3. Return unchanged only when the fetched SHA matches the previous local HEAD and
   the configured mount exists.
4. Copy working-tree content into the locked staging snapshot, excluding `.git`
   and rejecting symbolic links.
5. Replace `<filesharing-base>/<mount>` only after the
    complete snapshot is ready.
A fetch, checkout, validation, or publication failure preserves the previous
published folder and logs a sanitized error. Remove the staging folder
after either success or failure.

## Credential Handling

The existing File Sharing inventory task must redact every remote `password`.
Logs, events, task results, errors, and request headers must also exclude
credentials. Always exclude `.git` from published content and reject symbolic
links.

## Periodic Refresh

`FileSharingWorker` starts one daemon thread if at least one remote has
`auto_sync: true`.

```python
while not self.remote_sync_stop.wait(1):
    now = time.monotonic()
    for remote in self.remotes.values():
        if remote.type == "git" and remote.auto_sync and (
            remote._last_sync_timer is None
            or now - remote._last_sync_timer >= remote.sync_interval
        ):
            self.git_clone(None, remote.name)
```

Rules:

- Only remotes with `auto_sync: true` can become due.
- An enabled remote with no successful local snapshot is due immediately after
  worker initialization.
- Later runs are due after the effective, clamped `sync_interval` has elapsed
  since the previous attempt completed.
- A failed attempt is retried only after the same interval.
- Each entry in `self.remotes` is a plain dictionary holding validated
  configuration, repository path, status, lock, last-attempt timestamp, and
  monotonic timer; no parallel runtime-state dictionaries are maintained. The
  runtime `mount` value is normalized once to its canonical `nf://` URL.
- Remotes run sequentially in the first implementation.
- The scheduler acquires a remote lock without waiting and skips a locked
  remote until the next due check. A manual task may wait for that lock until
  its job timeout.
- One remote failure does not stop the thread.
- `worker_exit()` sets `remote_sync_stop` and joins the thread.
- `auto_sync: false` prevents periodic cloning after startup initialization.

The scheduler calls `git_clone` directly with no NorFab job object, so manual
and periodic synchronization share the same implementation.

## Code Changes

Keep changes confined to File Sharing:

```text
filesharing_worker.py   # inventory loading and common tasks
local_files_tasks.py    # local listing, details, walking, and streaming tasks
filesharing_models.py   # remote inventory and task result models
git_tasks.py            # Git authentication, synchronization, and lifecycle tasks
```

Add `GitPython` to the File Sharing optional dependencies. The system Git
executable must be installed; the all-in-one and test container images include
it. The 2026-09-01 amendment adds surgical changes to `NFPClient` and
`NFPWorker` for `git://` URL recognition and resolution. The broker, NFP, and
consumer workers remain unchanged. Git operations continue to run only as File
Sharing tasks.

Expose these new tasks:

- `get_remotes`
- `create_remote_git`
- `delete_remote_git`
- `git_clone`
- `resolve_git_url`

Periodic refresh invokes the same `git_clone` implementation.

NFCLI exposes the lifecycle tasks as `filesharing git create-remote`,
`filesharing git clone-remote`, and `filesharing git delete-remote`.

The existing File Sharing inventory task must redact every remote `password`.
Logs, events, task results, errors, and request headers must also exclude
credentials.

## Acceptance Criteria

Tests must prove that:

- existing `nf://` behavior remains unchanged;
- clients read a published remote with `nf://<mount>/<path>`;
- inventory is a list with the exact fields and defaults defined above;
- token-authenticated repositories can be downloaded;
- public repositories can be downloaded without credentials;
- configured local repositories are initialized during worker startup without
  fetching content;
- clients can explicitly delete and recreate local remote data;
- create accepts a complete remote definition while clone and delete use its
  registered name;
- first synchronization publishes the selected branch;
- an unchanged branch SHA causes no download or publication;
- two branches of one repository publish to separate folders;
- `auto_sync` defaults to `false` and prevents automatic refresh when disabled;
- the interval defaults to 30 seconds, clamps lower values to 5, clamps higher
  values to 86,400, and preserves values within that range;
- failures preserve the previous snapshot and retry only after the interval;
- shutdown interrupts the scheduler wait and joins the thread; and
- credentials never appear in observable or persisted data.

Use NorFab client integration tests against the dedicated read-only
`norfablabs/norfab-gitsync-test` repository. Tests must not mock Git operations,
use raw HTTP requests, or modify the repository.

## References

- [GitHub remote authentication](https://docs.github.com/en/get-started/git-basics/about-remote-repositories)
