# ADR - Docker-Based Parallel Testing Framework

## Status

Proposed.

## Date

2026-07-28.

## Decision

Build a NorFab test orchestration framework that runs isolated Docker Compose
test cells in parallel. A test cell is a complete, disposable test environment:

- one Compose project name;
- one generated inventory and runtime directory;
- one Docker network;
- one pytest runner container;
- the NorFab services needed by that test slice;
- optional external dependencies such as NetBox or Containerlab support;
- isolated artifacts, logs, coverage, and junit output.

The first implementation should not try to make one pytest process start many
NorFab environments concurrently. Instead, parallelism should happen above
pytest:

```text
test orchestrator
  cell py312-core-aio        -> docker compose up -> pytest -m core
  cell py312-nornir-split    -> docker compose up -> pytest services/nornir
  cell py312-netbox-split    -> docker compose up -> pytest services/netbox
  cell py313-fastmcp-split   -> docker compose up -> pytest services/fastmcp
```

This avoids fixture, port, `__norfab__`, and external-state collisions while
letting each cell keep normal pytest behavior.

The framework should be driven by a small matrix file, for example:

```yaml
python:
  - "3.10"
  - "3.11"
  - "3.12"
  - "3.13"
  - "3.14"

cells:
  - name: core
    topology: aio
    pytest: ["core"]
    scale: small

  - name: nornir
    topology: split
    pytest: ["services/nornir"]
    workers:
      nornir: 2
    scale: medium

  - name: netbox
    topology: split
    pytest: ["services/netbox"]
    dependencies: ["netbox"]
    workers:
      netbox: 1
    scale: large
```

The orchestrator expands the matrix, starts cells with unique Compose project
names, collects results, and tears everything down automatically.

## Context

NorFab is a multiprocessing and distributed-service framework. Tests currently
use pytest fixtures such as `nfclient` and `picle_shell` in `tests/conftest.py`
to start a real NorFab process tree from `tests/nf_tests_inventory/inventory.yaml`.

Current pressure points:

- fixtures use one inventory and one runtime folder per pytest process;
- test inventory and several tests assume fixed broker endpoints;
- Docker development Compose uses fixed container names, static IP addresses,
  and fixed host ports;
- a single shared environment makes raw in-process pytest parallelism risky;
- service suites touch shared external state, especially NetBox and
  Containerlab-style resources;
- some dependencies have Python-version limits, for example FakeNOS currently
  supports a narrower Python range than NorFab as a whole.

The repository already has useful building blocks:

- pytest markers in `pyproject.toml`;
- service-oriented test folders under `tests/services/<service>`;
- Docker role images under `docker/norfab-docker-build`;
- Docker development Compose under `docker/norfab-docker-dev`;
- documented test conventions in `docs/testing/norfab_testing_framework.md`;
- Python support declared as 3.10 through 3.14.

The new framework should use those pieces instead of replacing the test suite.

## Goals

- Use available large local compute efficiently, including high parallel cell
  counts on an 80-core / 128 GB machine.
- Fully automate container build, startup, readiness checks, pytest execution,
  artifact collection, and teardown.
- Support multiple Python versions.
- Support multiple deployment topologies.
- Support scaling knobs for broker, workers, services, runner concurrency, and
  external dependencies.
- Keep test cells isolated from each other by default.
- Preserve existing pytest markers and service test layout.
- Keep the first implementation small and maintainable.
- Make failures easy to debug through collected logs, generated inventories,
  Compose config, junit XML, and coverage artifacts.
- Allow local developer runs and CI runs to use the same matrix format.

## Non-Goals

- Do not rewrite service tests into a new testing framework.
- Do not require Kubernetes for the first implementation.
- Do not require pytest-xdist for integration tests in the first implementation.
- Do not make Linux Docker provide true Windows or macOS coverage.
- Do not require all optional service dependencies to pass on every Python
  version when their upstream packages do not support that version.
- Do not depend on fixed host ports or fixed Docker container names.
- Do not make Docker-based tests the only way to run a small local pytest
  command.

## Proposed Architecture

### Test Orchestrator

Add a small command-line orchestrator later, for example:

```text
tests/orchestrator/nftest.py
```

or:

```text
scripts/norfab-test
```

Responsibilities:

- read the test matrix;
- select cells by name, marker, topology, Python version, or scale;
- build or pull the required images;
- generate per-cell Compose files and inventory;
- assign unique project names;
- start dependencies and NorFab services;
- wait for readiness;
- run pytest inside the test runner container;
- collect artifacts;
- tear down containers, networks, and volumes;
- produce one summary at the end.

Example commands:

```bash
python tests/orchestrator/nftest.py run --matrix tests/matrix.yaml
python tests/orchestrator/nftest.py run --cell nornir --python 3.12
python tests/orchestrator/nftest.py run --profile smoke
python tests/orchestrator/nftest.py run --profile full --max-cells 16
python tests/orchestrator/nftest.py clean --run-id 20260728-101500
```

Use subprocess calls to `docker compose` in the first implementation. The
Docker SDK is optional later, but shelling out keeps behavior close to what
developers already know.

### Test Cell Layout

Each cell should get its own generated workspace under a gitignored runtime
directory:

```text
__norfab_test_runs__/
  20260728-101500/
    py312-nornir-split/
      compose.yaml
      inventory/
        inventory.yaml
        nornir/
        netbox/
      artifacts/
        junit.xml
        coverage.xml
        pytest.log
        compose.log
        docker-events.log
      logs/
```

Do not write generated inventories into `tests/nf_tests_inventory/` in place.
The orchestrator should copy or render from templates into the cell directory.

### Compose Isolation Rules

Test Compose files must avoid the fixed-name patterns used by the development
Compose stack:

- no `container_name`;
- no static IP addresses unless a specific topology test requires them;
- no fixed host port publishing by default;
- service-to-service communication should use Compose service DNS names;
- each cell uses a unique `--project-name`;
- every volume name and network name belongs to the Compose project;
- host-mounted artifact paths include the cell ID.

Broker endpoint inside generated inventory should prefer service DNS:

```yaml
broker:
  endpoint: "tcp://norfab-broker:5555"
```

The pytest runner container joins the same Compose network and uses the same
inventory, so host port publication is unnecessary for most tests.

### Runner Container

Each cell includes a runner container that executes pytest:

```text
norfab-test-runner
  command: pytest services/nornir --junitxml=/artifacts/junit.xml
```

The runner image should install test dependencies and the relevant NorFab
extras for that cell. Source code should be mounted read-only where practical,
while runtime and artifacts are writable per cell.

For development speed, the runner can mount the local source tree and set
`PYTHONPATH=/workspace`. CI can choose between source mounts and built wheels.

### Topology Profiles

Support these topology profiles:

| Topology | Purpose |
| --- | --- |
| `unit` | No broker or workers; fast tests that do not need NorFab runtime. |
| `aio` | Broker, workers, and client in one process/container. |
| `split` | Broker in one container, workers in role-specific containers, runner as client. |
| `client-remote` | Runner connects to a broker stack started by the cell. |
| `multi-broker-negative` | Failure and collision tests around ports, auth, or startup behavior. |
| `distributed` | Multiple worker containers per service to test worker selection and scale. |

The first useful target is `split`, because it resembles deployment and
naturally isolates broker, workers, and tests.

### Scaling Profiles

Use scale profiles to describe resource cost and breadth:

| Scale | Intent |
| --- | --- |
| `smoke` | Small marker subset, one Python version, minimal services. |
| `small` | Core and light service tests. |
| `medium` | One full service suite with normal worker counts. |
| `large` | Heavy service suites such as NetBox or Containerlab. |
| `stress` | Many workers, many concurrent jobs, longer timeouts. |
| `soak` | Long-running reliability tests, not part of normal PR runs. |

The orchestrator should map these to CPU, memory, worker counts, timeouts, and
parallel cell limits.

Example:

```yaml
scales:
  small:
    cpus: 2
    memory: 4g
    pytest_workers: 0
    timeout: 10m

  large:
    cpus: 8
    memory: 16g
    pytest_workers: 0
    timeout: 45m

  stress:
    cpus: 16
    memory: 24g
    worker_scale:
      nornir: 8
      netbox: 4
    timeout: 2h
```

### Python Version Matrix

Build images with existing `PYTHON_VERSION` Docker build args:

```text
3.10
3.11
3.12
3.13
3.14
```

The matrix should allow exclusions where optional dependencies do not support a
Python version.

Example:

```yaml
exclude:
  - python: "3.13"
    cell: fakenos
    reason: "fakenos dependency supports Python <3.13"
  - python: "3.14"
    cell: fakenos
    reason: "fakenos dependency supports Python <3.13"
```

Keep the default developer smoke profile on one Python version, likely the
project's current default Docker build version. Run the full Python matrix in
nightly or explicit full validation.

### Operating System Coverage

Use Docker for Linux distribution coverage first:

```text
python:3.12-slim-trixie
python:3.12-slim-bookworm
python:3.12-alpine   # only if dependencies support musl cleanly
```

True Windows and macOS coverage should use native CI runners or VMs, not Linux
Docker containers. Docker cannot make Linux containers validate Windows file
locking, Windows process semantics, or macOS behavior.

Recommended OS strategy:

- local Docker matrix for Linux behavior and deployment topologies;
- Windows runner for NFAPI, NFCLI, logging, and filesystem-sensitive tests;
- macOS runner for core/client compatibility if required;
- avoid Containerlab or privileged networking tests on Windows/macOS unless a
  dedicated environment supports them.

### External Dependencies

Treat external dependencies as cell-owned services unless the cell explicitly
targets a shared external environment.

Examples:

- NetBox cell starts its own NetBox and PostgreSQL containers, then seeds test
  data before pytest.
- FastAPI/FastMCP cells use service containers inside the same project network.
- Containerlab cells run only on hosts marked as privileged-capable and should
  use a dedicated runtime namespace.
- Nornir tests that need fake network devices should prefer FakeNOS or
  containerized network simulators inside the same cell.

Each dependency should have a readiness probe and a cleanup path. Seed data
should be idempotent and scoped to the cell.

### Fixture Changes

Keep fixture changes narrow. Existing test code should mostly keep using
`nfclient` and `picle_shell`.

Modify fixtures so they can read test runtime settings from environment
variables supplied by the orchestrator:

```text
NORFAB_TEST_INVENTORY
NORFAB_TEST_BASE_DIR
NORFAB_TEST_BROKER_ENDPOINT
NORFAB_TEST_RUN_ID
NORFAB_TEST_CELL_ID
```

If these variables are absent, keep current local behavior:

```python
NorFab(inventory="./nf_tests_inventory/inventory.yaml")
```

Inside Docker cells, the orchestrator sets:

```text
NORFAB_TEST_INVENTORY=/cell/inventory/inventory.yaml
NORFAB_TEST_BASE_DIR=/cell/inventory
NORFAB_TEST_BROKER_ENDPOINT=tcp://norfab-broker:5555
```

This keeps the existing tests usable while allowing generated inventories and
remote/split broker endpoints.

### Pytest Split Strategy

Prefer cell-level splitting by path and marker:

```text
core
nfcli
nornir
netbox
fastapi
fastmcp
filesharing
fakenos
containerlab
workflow
dummy
```

Avoid running pytest-xdist across integration tests in the first version. Many
tests share `nfclient` and external service state, so concurrency inside one
cell can create subtler collisions than cell-level parallelism.

Use pytest-xdist later for pure unit/core tests or test groups proven safe.

### Artifact Collection

Each cell should always collect:

- pytest stdout/stderr;
- junit XML;
- coverage XML or coverage data;
- generated inventory;
- rendered Compose config;
- `docker compose ps`;
- `docker compose logs --timestamps`;
- NorFab `__norfab__` logs and databases where useful;
- dependency logs, for example NetBox/PostgreSQL logs;
- orchestrator timing and resource summary.

On failure, preserve the cell directory by default for local debugging. In CI,
upload artifacts and then tear down containers.

### Scheduling

The orchestrator should be resource-aware but simple:

- each cell declares CPU and memory cost;
- the host declares total usable CPU and memory;
- the scheduler starts cells while the sum of costs fits the host budget;
- cells can also declare exclusivity labels such as `containerlab` or
  `host-network`;
- failed cells do not stop unrelated cells unless `--fail-fast` is set.

For an 80-core / 128 GB host, a first practical default could be:

```text
max-cells: 12-20
reserve-cpus: 4
reserve-memory: 8g
```

Tune this empirically. Network automation tests often bottleneck on startup,
external services, and IO before they use all CPU cores.

## Alternatives Considered

### Plain pytest-xdist In One Environment

This is attractive because it is simple:

```bash
pytest -n auto
```

But NorFab tests start brokers, workers, databases, logs, and external state.
Running many tests inside one process namespace risks port collisions, shared
`__norfab__` state, and order-dependent failures. It is useful later for
pure core/unit tests, not as the integration-test foundation.

### tox or nox Matrix Only

tox/nox is good for Python-version environments and command organization, but
it does not solve distributed service isolation by itself. It can wrap the
orchestrator later:

```text
tox env py312-docker-smoke -> nftest run --python 3.12 --profile smoke
```

### GitHub Actions Matrix Only

CI matrix jobs are useful for official validation, especially Windows and
macOS. They are not enough for the local 80-core machine because the local goal
is to pack many isolated test cells onto one host with controlled cleanup and
artifacts.

### Kubernetes-Based Test Farm

Kubernetes can model this well, but it is too much for the first step. Compose
is easier to inspect and closer to existing NorFab Docker development assets.
Keep Kubernetes as a future remote executor if Compose starts to creak.

### One Long-Lived Shared Test Stack

A shared stack is convenient for manual debugging, but it weakens test
isolation. State leaks between suites become normal. It can remain a developer
mode, but automated validation should default to disposable cells.

### Docker-In-Docker Per Test

Starting nested Docker inside each test or test container adds security and
performance complexity. Prefer the host orchestrator controlling Compose
projects directly.

## Proposed Minimal Implementation

Implement this in stages.

### Stage 1 - Matrix And Compose Cells

- Add a matrix file under `tests/`, such as `tests/docker_matrix.yaml`.
- Add a small orchestrator script.
- Generate Compose files into `__norfab_test_runs__/`.
- Support `core`, `nfcli`, and one service suite first.
- Use one Python version first.
- Collect logs, junit, and Compose state.

### Stage 2 - Fixture Environment Hooks

- Update `tests/conftest.py` to honor `NORFAB_TEST_INVENTORY`,
  `NORFAB_TEST_BASE_DIR`, and `NORFAB_TEST_BROKER_ENDPOINT`.
- Keep existing local defaults when env vars are absent.
- Make test inventories generated per cell rather than mutating source
  fixtures.

### Stage 3 - Service Matrix

- Add cells for Nornir, NetBox, FastAPI, FastMCP, FileSharing, FakeNOS,
  Containerlab, Workflow, and Dummy service tests.
- Add external dependency startup and seeding for NetBox.
- Add skip/exclusion rules for unsupported Python/dependency combinations.

### Stage 4 - Scaling And Stress

- Add worker scale parameters.
- Add high-concurrency job tests.
- Add long-running stress and soak profiles.
- Add resource-aware scheduling.

### Stage 5 - OS And CI Integration

- Add Linux distro image variants where useful.
- Add CI jobs that call the same orchestrator.
- Add native Windows and macOS jobs for non-Docker or limited Docker coverage.
- Publish combined junit and coverage reports.

## Code Change Guidelines

Keep initial codebase changes surgical:

- add orchestration files rather than refactoring NorFab runtime;
- update `tests/conftest.py` only enough to accept orchestrator-provided
  inventory and broker endpoint values;
- keep existing pytest markers and test paths;
- avoid broad changes to service tests in the first pass;
- keep Docker development Compose intact for manual development;
- create separate generated test Compose files for parallel automation;
- prefer templates and small helpers over a large framework.

## Risks

### Fixed Ports And Names

Any fixed `container_name`, static IP, or host port can break parallel cells.
Test Compose generation must default to project-scoped names and service DNS.

### Shared External State

NetBox and Containerlab tests can leak state if they share an external service.
Automated cells should own their dependency containers and seed data.

### Python Version Dependency Gaps

Optional dependencies may lag NorFab's declared Python support. The matrix must
support explicit exclusions with reasons.

### Windows And macOS Expectations

Linux Docker validates Linux behavior. It does not validate Windows file
locking, Windows process behavior, or macOS behavior. Native runners or VMs
remain necessary for those.

### Over-Parallelization

An 80-core machine can still bottleneck on Docker image pulls, disk IO,
PostgreSQL startup, network namespace creation, or test data seeding. The
scheduler should default to bounded parallelism and make limits explicit.

### Debugging Failed Cells

Disposable environments can make failures hard to inspect if cleanup runs too
early. Local failed cells should be preserved by default unless `--cleanup` or
CI mode is selected.

## Documentation Updates

Update testing documentation when this is implemented:

- add a Docker parallel testing tutorial;
- document the matrix schema;
- document common local commands for smoke, service, full, and stress runs;
- explain generated test cell directories and cleanup;
- explain how to add a new service test cell;
- explain Python-version exclusions;
- explain OS coverage boundaries;
- document artifact locations and failure debugging workflow.

## Open Questions

- Should the orchestrator live under `tests/orchestrator/` or `scripts/`?
- Should the first runner install from editable source, built wheel, or both as
  separate cell modes?
- Should NetBox dependency containers be built into NorFab test assets or use
  upstream images directly?
- Which service suites are safe to run against scaled worker counts without
  rewriting cleanup assumptions?
- Should coverage be collected per cell and combined automatically in the first
  implementation, or added after the matrix is stable?

