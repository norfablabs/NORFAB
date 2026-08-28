# ADR - File Sharing GitHub Remotes

## Status

Proposed, 2026-08-29.

## Decision

The File Sharing service will mirror configured GitHub repository branches into
local folders. Clients and workers remain unchanged and access mirrored files
only through existing URLs:

```text
nf://<remote-name>/<path/to/file>
```

The initial implementation is read-only. It supports initial download and
periodic refresh from GitHub to local storage. Remote write-back, client-side
remote URLs, webhooks, non-GitHub remotes, and other providers are out of scope.

## Remote Inventory

File Sharing inventory contains a `remotes` list. Each item has the same fixed
schema:

```yaml
service: filesharing
base_dir: "./shared"

remotes:
  - name: "openclaw-main"
    description: "OpenClaw main branch"
    url: "https://github.com/openclaw/openclaw.git"
    branch: "main"
    type: "git"
    username: "octocat"
    password: '{{ env["GITHUB_TOKEN"] }}'
    ignore_rules:
      - ".github/*"
      - "tests/*"
      - "*.pyc"
    auto_sync: true
    sync_interval: 30
```

| Key | Requirement |
| --- | --- |
| `name` | Required unique local name matching `[A-Za-z0-9][A-Za-z0-9._-]*` |
| `description` | Optional text; defaults to an empty string |
| `url` | Required standard GitHub HTTPS clone URL ending in `.git` |
| `branch` | Required GitHub branch name |
| `type` | Required; must be `git` |
| `username` | Optional GitHub login; must be supplied with `password` |
| `password` | Optional GitHub personal access token; must be supplied with `username` |
| `ignore_rules` | Optional list of glob patterns; defaults to `[]` |
| `auto_sync` | Enable periodic refresh; defaults to `false` |
| `sync_interval` | Periodic refresh interval in seconds; defaults to `30` |

The model rejects unknown keys, empty required strings, and non-string
`ignore_rules` entries.

`auto_sync: false` disables automatic download and refresh regardless of
`sync_interval`. The explicit `github_clone` task remains available.

During inventory loading, calculate the effective interval as
`max(5, min(sync_interval, 86_400))`. Values below 5 become 5 seconds, values
above 86,400 become 86,400 seconds, and values within that range are accepted
unchanged. Store and report the effective value. File Sharing logs one warning
when it clamps a value. Non-integer values fail inventory validation.

Inventory files may use Jinja2 to populate `username` and `password`. The
remote model receives the rendered values and does not read environment
variables itself. `username` and `password` must either both contain values or
both be null or omitted.

Despite the field name, `password` must contain a GitHub personal access token,
not the user's GitHub account password. GitHub no longer supports account
passwords for Git or API authentication.

## Provider Detection and Authentication

`type: git` identifies the repository family. File Sharing detects the provider
from `url`:

1. Parse and normalize the URL.
2. Require scheme `https`, host `github.com`, no embedded credentials, and a
   path consisting of exactly two non-empty segments,
   `<owner>/<repository>.git`. Reject ports, query parameters, and fragments.
3. Select the GitHub driver in `github_tasks.py`.
4. Reject every other host as an unsupported Git provider in the initial
   implementation.

When credentials are present, construct `github.Auth.Token(password)` and pass
it to `github.Github(auth=auth)`. Verify that the authenticated user's login
matches `username`; fail without downloading on mismatch. When both fields are
absent, use an unauthenticated `github.Github()` client for a public repository.

Never use `github.Auth.Login(username, password)`. Tokens and account passwords
are not interchangeable even though the inventory key is named `password`.

## Local Layout and URLs

Each remote name owns one private state folder and one published folder:

```text
<worker-runtime>/remotes/<name>/
  staging/<uuid>/ # one incomplete download and extraction attempt
  state.json      # managed marker, URL, branch, SHA, status, timestamps; no credentials

<filesharing-base>/<name>/
  ...             # files available through nf://<name>/...
```

Different branches of one repository use separate remote entries and names:

```yaml
remotes:
  - name: "openclaw-main"
    description: "Main branch"
    url: "https://github.com/openclaw/openclaw.git"
    branch: "main"
    type: "git"
    username: null
    password: null
    ignore_rules: []
    auto_sync: true
    sync_interval: 30

  - name: "openclaw-development"
    description: "Development branch"
    url: "https://github.com/openclaw/openclaw.git"
    branch: "development"
    type: "git"
    username: null
    password: null
    ignore_rules: []
    auto_sync: false
    sync_interval: 30
```

Clients use `nf://openclaw-main/README.md` and
`nf://openclaw-development/README.md`. Each entry has independent state,
staging, locking, and publication. No checkout is shared between branches.

Before replacing the `base_dir` inherited from `NFPWorker` with the configured
File Sharing publication path, preserve the inherited value as
`self.runtime_dir`. Private remote state is stored below `self.runtime_dir`.

Inventory validation rejects names that collide after platform path
normalization or are unsafe on the current operating system. File Sharing must
not adopt or overwrite a publication folder unless its private `state.json`
contains the expected managed marker. If a managed remote keeps its name but
changes `url` or `branch`, treat it as unsynchronized and replace its published
folder only after the new snapshot succeeds.

Persist `name`, normalized `url`, `branch`, `ignore_rules`, snapshot fingerprint,
last accepted SHA, status, last attempt completion time, last success time, and
sanitized last error. Never persist `username` or `password`.

## GitHub Clone Operation

For this ADR, clone means materializing a branch snapshot. Git history and a
`.git` directory are not retained.

The internal `_clone_remote(name)` method performs these steps under a
per-remote lock:

1. Find the remote by `name` and select the GitHub driver.
2. Authenticate with PyGithub.
3. Resolve `<owner>/<repository>` from `url`.
4. Read the configured branch with `repository.get_branch(branch)` and set
   `sha = branch.commit.sha`.
5. Build a deterministic fingerprint from normalized `url`, `branch`, and the
   sorted `ignore_rules`; rule order is irrelevant because rules only exclude.
6. Return unchanged only when the SHA and fingerprint match `state.json` and
   the published folder exists.
7. Obtain a tarball URL with `repository.get_archive_link("tarball", sha)`.
8. Stream the archive into a unique staging folder using HTTPS with certificate
   validation and finite connection and read timeouts. Send the token only to
   `api.github.com` and `codeload.github.com`; reject redirects to other hosts.
9. Validate every archive member before writing it, remove the archive's
   single generated top-level directory, and apply `ignore_rules`. Reject an
   archive without exactly one top-level directory.
10. Validate all paths and replace `<filesharing-base>/<name>` only after the
    complete snapshot is ready.
11. Atomically record the SHA, success time, and status in `state.json`.

A download, extraction, validation, or publication failure preserves the
previous published folder and records a sanitized error. Remove the unique
staging folder after either success or failure.

## Ignore Rules

Convert extracted paths to repository-relative POSIX form before matching.
Match the full path and each parent directory with Python
`fnmatch.fnmatchcase()`. Matching is case-sensitive. `fnmatchcase()` treats `/`
as an ordinary character, so `*` may span directory levels. A matching file is
omitted; a matching parent directory omits all of its children.

Rules are exclusion-only. Negation and re-inclusion syntax are not supported.
Always exclude `.git`, even if inventory does not list it. Reject symlinks,
hard links, devices, absolute archive paths, and path traversal before applying
ignore rules.

## Periodic Refresh

`FileSharingWorker` starts one daemon thread if at least one remote has
`auto_sync: true`.

```python
while not self.remote_sync_stop.wait(1):
    for remote in self.due_remotes():
        self._clone_remote(remote.name)
```

Rules:

- Only remotes with `auto_sync: true` can become due.
- An enabled remote with no successful local snapshot is due immediately after
  worker initialization.
- Later runs are due after the effective, clamped `sync_interval` has elapsed
  since the previous attempt completed.
- A failed attempt is retried only after the same interval.
- Remotes run sequentially in the first implementation.
- The scheduler acquires a remote lock without waiting and skips a locked
  remote until the next due check. A manual task may wait for that lock until
  its job timeout.
- One remote failure does not stop the thread.
- `worker_exit()` sets `remote_sync_stop` and joins the thread.
- `auto_sync: false` prevents all automatic activity for that remote.

The `github_clone` task is a thin wrapper around `_clone_remote`. The scheduler
calls `_clone_remote` directly, so manual and periodic operations share the
same implementation without creating an internal NorFab job.

## Code Changes

Keep changes confined to File Sharing:

```text
filesharing_worker.py   # inventory loading, common tasks, scheduler, publication
filesharing_models.py   # remote inventory and task result models
github_tasks.py         # GitHub detection, authentication, and clone task
```

Add `PyGithub` and `requests` to the File Sharing optional dependencies. Do not
change `NFPClient`, `NFPWorker`, the broker, NFP, or any consumer worker.

Expose only these new tasks initially:

- `remote_list`
- `remote_status`
- `github_clone`

Periodic refresh invokes the same private clone helper as `github_clone`.

The existing File Sharing inventory task must redact every remote `password`.
Logs, events, task results, errors, request headers, and `state.json` must also
exclude credentials.

## Acceptance Criteria

Tests must prove that:

- existing `nf://` behavior remains unchanged;
- clients read a published remote with `nf://<name>/<path>`;
- inventory is a list with the exact fields and defaults defined above;
- GitHub URLs select the PyGithub driver and other Git hosts are rejected;
- public and token-authenticated private repositories can be downloaded;
- an actual GitHub account password is never used as `Auth.Login`;
- first synchronization publishes the selected branch;
- an unchanged branch SHA causes no download or publication;
- changing `url`, `branch`, or `ignore_rules` forces a new publication even
  when the resolved SHA is unchanged;
- two branches of one repository publish to separate folders;
- ignored files and directories are absent from the published folder;
- `auto_sync` defaults to `false` and prevents automatic refresh when disabled;
- the interval defaults to 30 seconds, clamps lower values to 5, clamps higher
  values to 86,400, and preserves values within that range;
- failures preserve the previous snapshot and retry only after the interval;
- shutdown interrupts the scheduler wait and joins the thread; and
- credentials never appear in observable or persisted data.

Use mocked PyGithub objects and an in-process HTTP archive server. Tests must
not clone or modify a real GitHub repository.

## References

- [GitHub remote authentication](https://docs.github.com/en/get-started/git-basics/about-remote-repositories)
- [PyGithub authentication](https://pygithub.readthedocs.io/en/stable/examples/Authentication.html)
- [PyGithub repository API](https://pygithub.readthedocs.io/en/stable/github_objects/Repository.html)
