# NorFab Docker Tests

This folder contains Docker runners for the repository test suite. The runners
use the canonical inventory in `tests/nf_tests_inventory`; they do not maintain
their own inventory or test asset copies.

Each service mounts:

- repository source at `/workspace`, read-only;
- `tests/nf_tests_inventory` at `/workspace/tests/nf_tests_inventory`, writable;
- a service-local writable `__norfab__` folder over the inventory runtime path.

That keeps inventory and tests single-sourced while isolating broker, worker,
and client runtime files per Docker test service.

```text
docker/norfab-docker-tests/
  compose.yaml
  Dockerfile.norfab.test-runner
  core-tests/
    .env
    __norfab__/       # writable runtime output
  nornir-service-tests/
    .env
    __norfab__/       # writable runtime output
  netbox-service-tests/
    .env
    __norfab__/       # writable runtime output
```

## Build

Run from this folder:

```bash
docker compose build
```

Select a Python version:

```bash
PYTHON_VERSION=3.12 docker compose build
```

## Run

Run all core-marked tests:

```bash
docker compose run --rm core-tests
```

Run all nornir-marked tests:

```bash
docker compose run --rm nornir-service-tests
```

Run all netbox-marked tests:

```bash
docker compose run --rm netbox-service-tests
```

The service entrypoint already contains `python -m pytest` and common pytest
flags:

```bash
python -m pytest -vv \
  -c /workspace/pyproject.toml \
  -o cache_dir=/tmp/pytest-cache \
  --junitxml=<service artifacts path>
```

Compose supplies only the marker selector:

```text
core-tests             -m core
nornir-service-tests   -m nornir
netbox-service-tests   -m netbox
```

## Run Individual Tests

Pass pytest selectors or options after the service name:

```bash
docker compose run --rm core-tests tests/core/test_broker.py
docker compose run --rm core-tests tests/core/test_worker.py::TestWorkersListTasks::test_list_tasks
docker compose run --rm core-tests -m core -k test_mmi_show_broker

docker compose run --rm nornir-service-tests tests/services/nornir/test_worker.py
docker compose run --rm nornir-service-tests tests/services/nornir/test_task.py::TestNornirTask::test_task_nornir_salt_nr_test
docker compose run --rm nornir-service-tests -m "nornir and nornir_cli"

docker compose run --rm netbox-service-tests tests/services/netbox/test_worker.py
docker compose run --rm netbox-service-tests tests/services/netbox/test_worker.py::TestNetboxWorker::test_get_netbox_status
docker compose run --rm netbox-service-tests -m "netbox and netbox_get_devices"
```

Selectors can use repository-root paths like `tests/services/nornir/test_task.py`
or tests-local paths like `services/nornir/test_task.py`.

## Runtime Output

Runtime files are written under the service-local folders:

```text
docker/norfab-docker-tests/core-tests/
  __norfab__/artifacts/core-junit.xml
  __norfab__/files/
  __norfab__/logs/

docker/norfab-docker-tests/nornir-service-tests/
  __norfab__/artifacts/nornir-service-junit.xml
  __norfab__/files/
  __norfab__/logs/

docker/norfab-docker-tests/netbox-service-tests/
  __norfab__/artifacts/netbox-service-junit.xml
  __norfab__/files/
  __norfab__/logs/
```

Because each service gets its own `__norfab__` overlay, client keys, worker
keys, SQLite files, fetched files, artifacts, and logs do not collide between
test environments. Broker keys are generated or reused by NorFab inside that
writable runtime tree.

Clean containers and the default Compose network:

```bash
docker compose down --remove-orphans
```

Remove local runtime output:

```bash
rm -rf core-tests/__norfab__/*
rm -rf nornir-service-tests/__norfab__/*
rm -rf netbox-service-tests/__norfab__/*
```

## Inventory Endpoint

The canonical `tests/nf_tests_inventory/inventory.yaml` controls the broker bind
address. On Docker Desktop, a container cannot bind a host LAN address that only
exists on the host OS, such as `192.168.x.x`. Use `127.0.0.1` in the canonical
inventory when running the all-in-one broker, workers, and client inside one
container. Remove `broker.shared_key` from the canonical inventory when you want
each Docker runtime to generate and reuse its own broker keys under its mounted
`__norfab__` folder.
