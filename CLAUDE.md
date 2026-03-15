# CLAUDE.md - NorFab Repository Guide

## Project Overview

**NorFab** (Network Automations Fabric) is a Service-Oriented Architecture (SOA) framework for extreme network automation. It runs equally on Windows, Linux, and macOS — locally on a laptop or distributed across servers.

- **License**: Apache-2.0
- **Python**: 3.10–3.14
- **Docs**: https://docs.norfablabs.com
- **Repo**: https://github.com/norfablabs/NORFAB

## Architecture

Three core components communicate via ZeroMQ using the NFP (NorFab Protocol):

```
Clients  ──►  Broker  ──►  Workers
```

- **Broker** (`norfab/core/broker.py`) — Central message router. Distributes jobs from clients to available service workers.
- **Workers** (`norfab/workers/`) — Service processes that execute automation tasks. Multiple workers can form a service (load-balanced).
- **Clients** (`norfab/clients/`) — Interfaces to submit jobs and retrieve results (Python API, CLI, Robot Framework).
- **Inventory** (`norfab/core/inventory.py`) — YAML-based configuration loaded at startup; supports glob patterns for worker config mapping.

### NFP Protocol

The communication protocol is defined in `norfab/core/NFP.py`. Workers, broker, and clients speak NFP over ZeroMQ sockets. Jobs are tracked by UUID in a SQLite database on the client side (`norfab/core/client.py`).

### Job Lifecycle

`NEW` → `SUBMITTING` → `DISPATCHED` → `STARTED` → `COMPLETED` / `FAILED` / `STALE`

## Directory Structure

```
norfab/
├── core/
│   ├── nfapi.py        # NorFab main class — starts broker + workers + client
│   ├── broker.py       # NFPBroker — routes jobs between clients and workers
│   ├── worker.py       # NFPWorker base class — all service workers extend this
│   ├── client.py       # NFPClient — submits jobs, stores results in SQLite
│   ├── inventory.py    # NorFabInventory — loads YAML inventory files
│   ├── NFP.py          # Protocol constants and message builders
│   ├── keepalives.py   # Keepalive heartbeat implementation
│   ├── security.py     # ZeroMQ certificate generation
│   └── exceptions.py   # Custom exceptions
├── workers/
│   ├── nornir_worker/  # Nornir network automation service
│   ├── netbox_worker/  # NetBox DCIM/IPAM integration service
│   ├── agent_worker/   # AI/LLM agent service (LangChain/Ollama)
│   ├── fastapi_worker.py    # REST API service (FastAPI + Uvicorn)
│   ├── fastmcp_worker.py    # Model Context Protocol (MCP) service
│   ├── workflow_worker.py   # Workflow orchestration service
│   ├── containerlab_worker.py  # ContainerLab integration
│   └── filesharing_worker/ # File sharing service
├── clients/
│   ├── picle_shell_client.py  # Interactive CLI (nfcli)
│   ├── robot_client.py        # Robot Framework library
│   ├── textual_client.py      # TUI client (Textual)
│   └── streamlit_client.py    # Web UI client (Streamlit)
├── models/
│   ├── norfab_configuration.py          # Pydantic models for inventory config
│   ├── norfab_configuration_logging.py  # Logging config models
│   ├── fastapi/                          # FastAPI response models
│   └── containerlab/                     # ContainerLab models
└── utils/
    └── nfcli.py   # CLI entry point script
tests/
├── conftest.py                      # pytest fixtures (NorFab start/teardown)
├── nf_tests_inventory/              # Test inventory (inventory.yaml + service configs)
├── test_nornir_service.py
├── test_netbox_service.py
├── test_fastapi_service.py
├── test_workflow_service.py
├── test_filesharing_service.py
├── test_fastmcp_service.py
├── test_fakenos_service.py
├── test_containerlab_service.py
├── test_picle_shell_client.py
└── test_dummy_service_plugin.py
docs/                  # MkDocs documentation source (Material theme)
docker/                # Docker deployment configs
```

## Common Commands

### Installation

```bash
# Core only
poetry run pip install norfab

# With CLI
poetry run pip install norfab[nfcli]

# With Nornir service
poetry run pip install norfab[nornirservice]

# Everything
poetry run pip install norfab[full]

# Development (using Poetry)
poetry install
```

### Running

```bash
# Start interactive CLI (from directory containing inventory.yaml)
poetry run nfcli

# Create a new NorFab environment scaffold
poetry run nfcli --create-env norfab
```

### Testing

```bash
# Run all tests (from repo root, requires a running/startable NorFab)
cd tests && poetry run pytest

# Run a specific service test
cd tests && poetry run pytest test_nornir_service.py

# Run tests with output
cd tests && poetry run pytest -s -v
```

### Linting & Formatting

```bash
# Format with Black
poetry run black .

# Lint with Ruff
poetry run ruff check .

# Ruff auto-fix
poetry run ruff check . --fix
```

### Important formatting Rules

1. Workers `job.event` calls messages must start with lowercase letter, `job.event` call support setting event seveiryt through `severity=WARNING/INFO/ERROR`  
2. Logging calls e.f. `log.info` messages us tstart with uppercase letters
3. Any spelling mistakes in docstrings, comments or variable names must be fixed

### Documentation

```bash
# Serve docs locally
poetry run mkdocs serve

# Build docs
poetry run mkdocs build
```

## Inventory File Structure

NorFab is configured via a YAML `inventory.yaml`. The default search path is `./inventory.yaml`.

```yaml
broker:
  endpoint: "tcp://127.0.0.1:5555"

logging:
  handlers:
    terminal:
      level: CRITICAL
    file:
      level: DEBUG

workers:
  nornir-*:               # glob pattern — applies to all matching workers
    - nornir/common.yaml
  nornir-worker-1:        # specific worker name
    - nornir/nornir-worker-1.yaml

topology:
  broker: True            # start broker in this process
  workers:
    - nornir-worker-1     # start these workers in this process
```

Worker config files are merged recursively — glob patterns first, then specific names.

## Python API Usage

```python
from norfab.core.nfapi import NorFab

# Start NorFab (broker + workers + client)
nf = NorFab(inventory="./inventory.yaml")
nf.start()

client = nf.make_client()

# Run a job
result = client.run_job(
    service="nornir",
    task="cli",
    workers="nornir-worker-1",
    kwargs={"commands": ["show version"]}
)

nf.destroy()
```

## Worker Plugin System

Workers are registered via Python entry points in `pyproject.toml`:

```toml
[project.entry-points."norfab.workers"]
"nornir"      = "norfab.workers.nornir_worker.nornir_worker:NornirWorker"
"netbox"      = "norfab.workers.netbox_worker.netbox_worker:NetboxWorker"
"fastapi"     = "norfab.workers.fastapi_worker:FastAPIWorker"
"agent"       = "norfab.workers.agent_worker.agent_worker:AgentWorker"
"workflow"    = "norfab.workers.workflow_worker:WorkflowWorker"
"containerlab"= "norfab.workers.containerlab_worker:ContainerlabWorker"
"fastmcp"     = "norfab.workers.fastmcp_worker:FastMCPWorker"
"filesharing" = "norfab.workers.filesharing_worker.filesharing_worker:FileSharingWorker"
"fakenos"     = "norfab.workers.fakenos_worker.fakenos_worker:FakeNOSWorker"
```

Custom workers can be registered by installing a package that declares the same entry point group. Set `service: <name>` in the worker's inventory config.

## Key Design Patterns

- **All workers extend `NFPWorker`** (`norfab/core/worker.py`). Task methods decorated with `@task` are auto-registered and callable by clients.
- **Pydantic models** are used for all job inputs/output, API validation, and documentation generation.
- **Jinja2 templating** is supported inside inventory YAML files.
- **SQLite** stores client-side job results and events (`ClientJobDatabase` in `client.py`). Database files are stored in `__norfab__/` directories (gitignored).
- **ZeroMQ** with optional CurveZMQ encryption (`security.py`) handles all inter-process communication.
- **Multiprocessing** — broker and each worker run in separate OS processes (`multiprocessing.Process`).

## Ruff Lint Rules

Configured in `pyproject.toml`. Ignored rules:
- `E712` — true-false-comparison
- `E501` — line too long
- `ANN401` — disallow `Any` annotation

Selected rule sets: `E`, `F`, `I`, `ANN`

## Gitignored Patterns

- `__norfab__/` directories (runtime data: job DBs, certs, logs)
- `private/` directory
- `site/` (built docs)
- `*.log`, `*.pyc`, `dist/`, `build/`

## Community & Support

- Slack: Networktocode `#norfab` channel / NetDev Community
- GitHub Discussions: https://github.com/norfablabs/NORFAB/discussions
