# ADR - Invoke Developer Automation and Docker Test Commands

## Status

Implemented. Approved and completed on 2026-08-22.

Implementation amendment: at the maintainer's request, individual
`docker-tests-<suite>` tasks report but ignore pytest container return codes.
`docker-tests-all` retains and aggregates those codes so it can still summarize
failed suites and return non-zero.

File-parallel amendment: every individual suite task and `docker-tests-all`
accepts `--parallel-runs=N`. It discovers `test_*.py` files from the
conventional test tree and runs each file in a separate container and
`__norfab__` runtime, with at most `N` containers active at once. This remains
opt-in; the default single-container behavior is unchanged.

## Date

2026-08-22.

## Decision

Add [Invoke](https://www.pyinvoke.org/) as the repository's developer command
runner and define the tasks in a root-level `tasks.py`. The tasks will provide
one consistent interface for documentation, formatting checks, linting, dead
code detection, and the Docker Compose test runners already located in
`docker/norfab-docker-tests/`.

The intended command interface is:

```bash
poetry run inv --list
poetry run inv docs-build
poetry run inv docs-serve
poetry run inv lint
poetry run inv dead-code
poetry run inv checks
poetry run inv docker-tests-build
poetry run inv docker-tests-core
poetry run inv docker-tests-nornir
poetry run inv docker-tests-netbox
poetry run inv docker-tests-all
poetry run inv docker-tests-distributed
```

Use `docker-tests-*` as the canonical task family. Add singular
`docker-test-*` aliases for individual suites so commands such as
`poetry run inv docker-test-nornir` also work.

Invoke will be an orchestration layer, not a replacement for Poetry, pytest,
MkDocs, Ruff, Black, Vulture, or Docker Compose. Each task will call the
underlying tool and capture its real exit status for reporting or aggregation.

## Context

Developer commands are currently documented as separate raw commands in
`CLAUDE.md`. There is no `tasks.py` or other project command runner. The current
development dependency group contains Black and pytest, while Ruff is
documented but is not declared in the project or lock file. Invoke and Vulture
are also not declared.

The Docker test infrastructure is already functional and should be reused:

- `docker/norfab-docker-tests/compose.yaml` contains isolated all-in-one pytest
  runner services;
- `compose.distributed.yaml` starts a broker, separate workers, and a pytest
  client;
- `Dockerfile.norfab.test-runner` installs the checkout with the `full` extra;
- every existing runner mounts the canonical `tests/nf_tests_inventory`
  inputs and overlays a suite-local writable `__norfab__` runtime directory;
- the Compose entrypoint normalizes repository-root test selectors and writes
  JUnit XML into the suite runtime directory;
- the distributed environment has a checked-in test-only broker keypair and
  supplies its public key through `NORFAB_BROKER_PUBLIC_KEY`.

The current all-in-one Compose file covers these pytest groups:

```text
core, nornir, netbox, fakenos, containerlab, workflow,
clientagent, fastmcp, fastapi
```

Registered pytest groups for `filesharing`, `dummy`, and `nfcli` do not yet
have runner services. The Invoke work should close that gap so
`docker-tests-all` has an explicit, reviewable definition of all supported
Docker suites.

The broader design in
`docs/development/adr_norfab_docker_parallel_testing.md` proposes generated
test cells, a Python-version matrix, resource-aware parallel scheduling, and
artifact aggregation. This ADR does not supersede that proposal. It defines a
small command layer over the Compose infrastructure that exists now and gives
future matrix orchestration a stable developer-facing entry point.

## Goals

- Provide short, discoverable, cross-platform commands from the repository
  root.
- Keep raw tool commands available for debugging.
- Make documented lint and check commands reproducible from Poetry's locked
  environment.
- Add Vulture to static checks, run it, and record its initial findings without
  changing or suppressing the reported code in this change.
- Run each pytest group in its named Docker Compose test service.
- Allow a developer to pass a test path, node ID, marker expression, keyword
  expression, or additional pytest flags to a Docker test task.
- Preserve Compose service exit codes so failures can be reported by individual
  tasks and enforced by aggregate tasks.
- Optionally run every discovered test file for any suite in its own parallel,
  isolated Docker container without enumerating files in `tasks.py`.
- Prepare only the runtime directories and broker certificate files a selected
  Docker topology needs.
- Keep `CLAUDE.md` and the Docker test README aligned with the new command
  interface.

## Non-Goals

- Do not fix code reported by Vulture in this change.
- Do not hide Vulture findings with a broad exclusion or generated whitelist.
- Do not replace Poetry dependency management.
- Do not rewrite pytest fixtures or test behavior. Relocating a test into the
  conventional suite tree is allowed when needed for automatic discovery.
- Do not implement the parallel matrix scheduler from the earlier Docker
  testing ADR.
- Do not run integration tests concurrently by default. Several suites use
  shared external systems such as NetBox or host networking.
- Do not make Docker the only supported way to run an individual local test.
- Do not copy or print values from suite `.env` files.
- Do not copy a broker private key into a worker-only or client-only runtime.

## Dependency and Configuration Changes

Update `pyproject.toml` and `poetry.lock` as follows:

- add `invoke` to the development dependency group;
- add `vulture` to the development dependency group;
- add `ruff` to the development dependency group because the repository
  already documents Ruff as its linter but does not currently declare it;
- retain Black and pytest in the development group;
- retain MkDocs packages in the existing `docs` extra.

The documented setup command for all developer tasks will be:

```bash
poetry install -E docs
```

Add a narrow `[tool.vulture]` configuration to `pyproject.toml`. Its initial
scan scope will be production code plus the new task module, not tests, built
documentation, generated runtime data, or vendored fixtures:

```text
norfab/
tasks.py
```

Start with an explicitly documented confidence threshold and no whitelist.
During implementation, run Vulture once, capture the command, exit status, and
findings in the handoff, and do not modify findings merely to make the new
check green. A Vulture finding is allowed to make `dead-code` and `checks`
fail until the findings are reviewed in a separate change.

## Invoke Task Layout

Keep `tasks.py` small. Use constants for repository paths and one subprocess
helper that:

- resolves paths relative to `tasks.py`, not the caller's current directory;
- constructs argument lists instead of interpolating shell command strings;
- works from PowerShell, Windows Command Prompt, and POSIX shells;
- streams output in real time;
- does not echo secret environment values;
- raises on non-zero exit unless a task explicitly aggregates results;
- handles `Ctrl+C` by forwarding termination and returning a failing status.

Do not duplicate tool configuration in `tasks.py`. Ruff, pytest, and Vulture
configuration belongs in `pyproject.toml`; MkDocs configuration remains in
`mkdocs.yml`; test topology remains in the Compose files.

### Documentation Tasks

| Task | Underlying behavior |
| --- | --- |
| `docs-build` | Run `python -m mkdocs build` from the repository root. Support an optional `--strict` switch. |
| `docs-serve` | Run `python -m mkdocs serve`; pass through host/address and port options without starting a detached process. |

Keeping `docs-serve` in the foreground makes shutdown predictable and avoids
leaving an orphaned development server.

### Static Check Tasks

| Task | Underlying behavior |
| --- | --- |
| `format-check` | Run `python -m black --check .`. |
| `lint` | Run `python -m ruff check .`. |
| `dead-code` | Run Vulture with the paths and threshold configured in `pyproject.toml`. |
| `checks` | Run `format-check`, `lint`, and `dead-code`, returning failure if any check fails. |

Formatting changes remain explicit through the existing raw Black command or
an optional `format` Invoke task. `checks` must not mutate files. Documentation
builds remain separately callable because they require the `docs` extra and
because `docs-serve` is a long-running task.

## Docker Test Tasks

### Compose Command Rules

All Docker tasks will use these files directly:

```text
docker/norfab-docker-tests/compose.yaml
docker/norfab-docker-tests/compose.distributed.yaml
```

The helper will call Compose with an explicit file and project directory, so
the tasks work from any current directory. It will check that Docker Compose v2
is available before performing setup.

An individual suite task will execute the equivalent of:

```bash
docker compose \
  --project-directory docker/norfab-docker-tests \
  -f docker/norfab-docker-tests/compose.yaml \
  run --rm <compose-service> -m <pytest-marker> <extra-pytest-arguments>
```

The Invoke helper must always supply the suite marker explicitly when it adds
pytest arguments. Compose replaces a service's configured `command` when extra
arguments follow the service name; omitting the explicit marker could
accidentally run the entire test repository.

Support these task options:

- `--selector` for a repository-relative test file, directory, or node ID;
- `--marker` to override the suite's default pytest marker expression;
- `--keyword` for a pytest `-k` expression;
- `--pytest-args` for advanced flags such as `-x`, `-s`, or `--maxfail=1`;
- `--build` to ask Compose to build before running;
- `--python-version` to set the existing `PYTHON_VERSION` build argument.
- `--parallel-runs=N` to run one container per discovered file with at most
  `N` containers active at once.

Examples:

```bash
poetry run inv docker-tests-core
poetry run inv docker-test-nornir --selector=tests/services/nornir/test_worker.py
poetry run inv docker-tests-nornir --keyword=test_list_tasks --pytest-args="-x -s"
poetry run inv docker-tests-netbox --marker="netbox and netbox_get_devices"
poetry run inv docker-tests-core --python-version=3.13 --build
poetry run inv docker-tests-netbox --parallel-runs=2
```

### File-Level Parallel Runs

Parallel runs reuse the existing suite-to-Compose-service and marker mapping;
they do not add a Compose service or Invoke task per test file. Test roots are
derived, in order, from these repository conventions:

```text
tests/services/<suite>/
tests/clients/<suite>/
tests/<suite>/
```

The Agent test moves from `tests/core/test_client_agent.py` to
`tests/clients/agent/test_client_agent.py`, removing the only path exception.
Invoke recursively discovers `test_*.py` below the resolved root, or below a
directory supplied with `--selector`. A selected test file produces one
container. Pytest node IDs remain supported by normal single-container runs,
but are rejected with `--parallel-runs=N` because that mode partitions by file.

Each file uses the suite's existing Compose service and explicit pytest marker,
while overriding only the writable runtime mount and JUnit destination:

```text
docker/norfab-docker-tests/<service>/parallel/<relative-test-file>/__norfab__/
  artifacts/<test-file>-junit.xml
  files/
  logs/
```

The standard-library `ThreadPoolExecutor` schedules all discovered files
without another dependency or scheduler and starts no more than the requested
number concurrently. The numeric limit prevents heavyweight suite topologies
from starting one container for every test file simultaneously.
`--build` builds the service image once before the containers start. Per-file
return codes are printed and retained for the summary; individual suite tasks
continue to ignore them, while `docker-tests-all --parallel-runs=N` treats any
failed file as a failed suite.
Concurrent container output may interleave; isolated JUnit files remain the
authoritative per-file results.

### Suite Mapping

| Invoke task | Compose service | Default pytest marker | Change |
| --- | --- | --- | --- |
| `docker-tests-core` | `core-tests` | `core` | Reuse. |
| `docker-tests-nornir` | `nornir-service-tests` | `nornir` | Reuse. |
| `docker-tests-netbox` | `netbox-service-tests` | `netbox` | Reuse. |
| `docker-tests-fakenos` | `fakenos-service-tests` | `fakenos` | Reuse. |
| `docker-tests-containerlab` | `containerlab-service-tests` | `containerlab` | Reuse. |
| `docker-tests-workflow` | `workflow-service-tests` | `workflow` | Reuse. |
| `docker-tests-agent` | `agent-tests` | `clientagent` | Reuse. |
| `docker-tests-fastmcp` | `fastmcp-service-tests` | `fastmcp` | Reuse. |
| `docker-tests-fastapi` | `fastapi-service-tests` | `fastapi` | Reuse. |
| `docker-tests-filesharing` | `filesharing-service-tests` | `filesharing` | Add runner. |
| `docker-tests-dummy` | `dummy-service-tests` | `dummy` | Add runner. |
| `docker-tests-nfcli` | `nfcli-tests` | `nfcli` | Add runner. |

The three new Compose services will follow the existing anchors, read-only
source mount, suite-local writable `__norfab__` overlay, marker command, and
JUnit artifact convention. Add only the environment keys each group needs.
Do not copy real credentials into new files.

### Aggregate and Lifecycle Tasks

Add these supporting tasks:

| Task | Behavior |
| --- | --- |
| `docker-tests-prepare` | Validate Compose, create required ignored runtime/artifact directories, and validate certificate prerequisites. |
| `docker-tests-build` | Build all test-runner service images, optionally for a selected suite and Python version. |
| `docker-tests-all` | Run the supported suite mapping sequentially by default and print a final pass/fail summary. |
| `docker-tests-distributed` | Prepare certificates, start the distributed broker/workers, wait for readiness, run `distributed-client`, collect status/logs, and tear down in `finally`. |
| `docker-tests-down` | Run Compose `down --remove-orphans` for both test projects without deleting source fixtures or runtime artifacts. |
| `docker-tests-config` | Render/validate both effective Compose configurations without running containers. |

`docker-tests-all` should continue to the next suite after a test failure so
the developer receives one complete summary, but it must return non-zero if
any suite fails. Add an optional `--fail-fast` switch. Parallel file execution
must remain explicit through `--parallel-runs=N`.

External prerequisites remain visible. For example, a NetBox suite failure
caused by an unavailable configured NetBox endpoint should be reported as a
failure with the relevant suite name; Invoke must not conceal it or silently
substitute a different service.

### Broker Certificate Handling

Certificate preparation must be topology-aware:

1. All-in-one suite services run a broker, workers, and clients inside one
   container and one suite-local `__norfab__` tree. NorFab can normally create
   and distribute that suite's broker certificate itself, so no host copy is
   required by default.
2. The distributed broker owns the checked-in test-only broker private/public
   pair under
   `docker/norfab-docker-tests/distributed-basic/broker/__norfab__/files/broker/`.
   The public material must match `NORFAB_BROKER_PUBLIC_KEY` in the distributed
   environment before containers start.
3. If a topology requires certificate files before NorFab startup,
   `docker-tests-prepare` may copy from an explicitly allowlisted test
   certificate source into the selected suite's ignored `__norfab__` runtime.
   Copy the broker public certificate to worker/client public-key locations.
   Copy the private certificate only to a runtime that actually hosts that
   suite's broker.
4. Never discover certificate destinations with a broad recursive glob. Build
   destinations from the selected Compose service mapping, verify every
   resolved path remains under `docker/norfab-docker-tests/`, create parent
   directories, and copy files atomically.
5. Do not overwrite a different existing certificate unless an explicit
   `--force-certificates` option is supplied. Print paths and fingerprints for
   diagnostics, never private key contents or `.env` values.

This keeps certificate copying available where it is genuinely needed without
making private-key distribution a side effect of every Docker test command.

## Documentation Changes After Approval

Update `CLAUDE.md` to:

- use `poetry install -E docs` for the complete developer environment;
- add the Invoke command list and explain `inv --list`;
- retain raw pytest, Ruff, Black, MkDocs, and Compose commands as diagnostic
  escape hatches;
- describe `checks` and state that Vulture findings are not auto-fixed;
- document suite names, selector/marker/keyword pass-through, Python-version
  selection, distributed test lifecycle, artifacts, and certificate safety;
- link this ADR, the Docker testing README, and the existing parallel-testing
  ADR.

Update `docker/norfab-docker-tests/README.md` to make Invoke commands the
repository-root quick start while retaining the direct Compose reference.
Document the three added services, certificate preparation, runtime output,
cleanup, and examples for individual tests.

Add this ADR to the Development architecture-design-record navigation in
`mkdocs.yml` when implementation begins. This proposal file itself does not
change navigation before approval.

## Alternatives Considered

### Keep Raw Commands Only

This avoids another dependency but leaves path handling, suite-to-service
mapping, certificate preparation, argument pass-through, and aggregate status
reporting duplicated in documentation or developer shell history.

### Use Poetry Scripts

Poetry scripts are appropriate for installed application entry points. They
are less suitable for a family of repository-only tasks with dependencies,
options, lifecycle cleanup, and discoverable aliases.

### Replace Compose with Invoke

Encoding container topology in Python would duplicate Compose and make direct
Docker troubleshooting harder. Invoke should call the checked-in Compose
services, not model them again.

### Implement the Full Parallel Test Matrix Now

The earlier Docker testing ADR remains useful, but a matrix scheduler is much
larger than the requested developer command layer. Stable Invoke task names can
later call that orchestrator without changing the normal developer interface.

### Make Vulture Report-Only

Always returning success would make `checks` unable to detect newly introduced
dead code. The initial run may expose existing findings and make the new check
red. This is preferable to silently accepting findings or adding unreviewed
suppression. Remediation and any targeted whitelist should be separate,
reviewed work.

## Implementation Sequence

After approval:

1. Add Invoke, Vulture, and Ruff to the Poetry development group and refresh
   the lock file.
2. Add Vulture configuration and root-level `tasks.py` with documentation and
   static-check tasks.
3. Add the Docker Compose helper, suite tasks, aliases, lifecycle tasks, safe
   argument pass-through, and certificate preparation.
4. Add the FileSharing, Dummy, and NFCLI Compose runner services and their
   ignored runtime/artifact scaffolding.
5. Update `CLAUDE.md`, the Docker test README, and MkDocs navigation.
6. Validate the task list, Compose rendering, docs build, and docs server
   startup/shutdown.
7. Run Black check, Ruff, and Vulture. Record Vulture findings without fixing
   production code or adding suppressions.
8. Build the Docker test image, run at least the Core and Nornir tasks, then run
   every feasible suite. Report external-environment failures separately and
   preserve their artifacts.
9. Run the distributed task and verify teardown occurs on success, failure,
   and interruption.
10. Add convention-based test discovery and opt-in file-parallel containers,
    then move the Agent test into the conventional client suite directory.

## Acceptance Criteria

- A fresh development install with the docs extra exposes `poetry run inv`.
- `poetry run inv --list` shows every documented task and alias.
- Documentation and static-check tasks work from the repository root and a
  nested directory.
- `checks` never edits files and includes Vulture.
- The initial Vulture output is reported unchanged.
- Every pytest group in the suite mapping has a valid Compose runner and named
  Invoke task.
- Extra pytest arguments cannot cause a suite task to lose its default marker
  accidentally.
- Individual Docker tasks report and ignore test failures; `docker-tests-all`
  summarizes them and returns non-zero.
- Runtime state and JUnit files remain isolated below the selected suite's
  ignored `__norfab__` directory.
- `--parallel-runs=N` discovers files without a maintained file list, runs one
  container per file with at most `N` active containers, and isolates every
  file's runtime and JUnit report.
- Certificate preparation validates destinations, never prints key material,
  and never places a broker private key in a worker/client-only environment.
- Distributed containers are torn down even when pytest fails or the command
  is interrupted.
- `CLAUDE.md`, the Docker test README, task help, and actual commands agree.

## Approval Boundary

No dependency, lock file, task runner, Compose service, certificate, test,
lint configuration, or repository guide change should be made under this ADR
until the maintainer approves the proposal.
