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
  compose.distributed.yaml
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
  fakenos-service-tests/
    .env
    __norfab__/       # writable runtime output
  containerlab-service-tests/
    .env
    __norfab__/       # writable runtime output
  workflow-service-tests/
    .env
    __norfab__/       # writable runtime output
  agent-tests/
    .env
    __norfab__/       # writable runtime output
  fastmcp-service-tests/
    .env
    __norfab__/       # writable runtime output
  fastapi-service-tests/
    .env
    __norfab__/       # writable runtime output
  distributed-basic/
    .env              # common distributed env, including broker public key
    broker/
      inventory.yaml
      __norfab__/     # broker runtime, including broker private key
    netbox-worker/
      inventory.yaml
      __norfab__/     # netbox worker runtime
    nornir-worker/
      inventory.yaml
      __norfab__/     # nornir worker runtime
    dummy-worker/
      inventory.yaml
      __norfab__/     # dummy worker runtime
    client/
      inventory.yaml
      conftest.py     # distributed client pytest fixtures
      __norfab__/     # client runtime
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

Run other service-marked tests:

```bash
docker compose run --rm fakenos-service-tests
docker compose run --rm containerlab-service-tests
docker compose run --rm workflow-service-tests
docker compose run --rm agent-tests
docker compose run --rm fastmcp-service-tests
docker compose run --rm fastapi-service-tests
```

Run the basic distributed setup:

```bash
docker compose -f compose.distributed.yaml up -d distributed-broker distributed-netbox-worker distributed-nornir-worker distributed-dummy-worker
docker compose -f compose.distributed.yaml run --rm distributed-client
```

Stop the distributed services:

```bash
docker compose -f compose.distributed.yaml stop distributed-broker distributed-netbox-worker distributed-nornir-worker distributed-dummy-worker
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
fakenos-service-tests  -m fakenos
containerlab-service-tests -m containerlab
workflow-service-tests -m workflow
agent-tests            -m clientagent
fastmcp-service-tests  -m fastmcp
fastapi-service-tests  -m fastapi
```

The distributed services are not marker-based pytest runners. They start
separate NorFab processes with separate mounted runtime folders:

```text
distributed-broker         nfcli -i inventory.yaml -b -l INFO
distributed-netbox-worker  nfcli -i inventory.yaml -wl netbox-worker-1.1 -l INFO
distributed-nornir-worker  nfcli -i inventory.yaml -wl nornir-worker-1,nornir-worker-2 -l INFO
distributed-dummy-worker   nfcli -i inventory.yaml -wl dummy-worker-1 -l INFO
distributed-client         pytest -m core core
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

docker compose run --rm fakenos-service-tests tests/services/fakenos/test_start.py
docker compose run --rm fakenos-service-tests -m "fakenos and fakenos_start"

docker compose run --rm containerlab-service-tests tests/services/containerlab/test_inspect.py
docker compose run --rm containerlab-service-tests -m "containerlab and containerlab_inspect"

docker compose run --rm workflow-service-tests tests/services/workflow/test_run.py
docker compose run --rm workflow-service-tests -m "workflow and workflow_run"

docker compose run --rm agent-tests tests/core/test_client_agent.py
docker compose run --rm agent-tests -m clientagent

docker compose run --rm fastmcp-service-tests tests/services/fastmcp/test_tools.py
docker compose run --rm fastmcp-service-tests -m "fastmcp and fastmcp_get_tools"

docker compose run --rm fastapi-service-tests tests/services/fastapi/test_server.py
docker compose run --rm fastapi-service-tests -m fastapi

docker compose -f compose.distributed.yaml run --rm distributed-client core/test_client.py::TestClientApi::test_mmi_show_broker
docker compose -f compose.distributed.yaml run --rm distributed-client -k test_list_tasks
```

Selectors can use repository-root paths like `tests/services/nornir/test_task.py`
or tests-local paths like `services/nornir/test_task.py`.
For `distributed-client`, selectors use the mounted client-local path, such as
`core/test_client.py`.

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

docker/norfab-docker-tests/fakenos-service-tests/
  __norfab__/artifacts/fakenos-service-junit.xml
  __norfab__/files/
  __norfab__/logs/

docker/norfab-docker-tests/containerlab-service-tests/
  __norfab__/artifacts/containerlab-service-junit.xml
  __norfab__/files/
  __norfab__/logs/

docker/norfab-docker-tests/workflow-service-tests/
  __norfab__/artifacts/workflow-service-junit.xml
  __norfab__/files/
  __norfab__/logs/

docker/norfab-docker-tests/agent-tests/
  __norfab__/artifacts/agent-junit.xml
  __norfab__/files/
  __norfab__/logs/

docker/norfab-docker-tests/fastmcp-service-tests/
  __norfab__/artifacts/fastmcp-service-junit.xml
  __norfab__/files/
  __norfab__/logs/

docker/norfab-docker-tests/fastapi-service-tests/
  __norfab__/artifacts/fastapi-service-junit.xml
  __norfab__/files/
  __norfab__/logs/

docker/norfab-docker-tests/distributed-basic/broker/
  __norfab__/files/broker/private_keys/broker.key_secret
  __norfab__/files/broker/public_keys/broker.key
  __norfab__/logs/

docker/norfab-docker-tests/distributed-basic/netbox-worker/
  __norfab__/files/
  __norfab__/logs/

docker/norfab-docker-tests/distributed-basic/nornir-worker/
  __norfab__/files/
  __norfab__/logs/

docker/norfab-docker-tests/distributed-basic/dummy-worker/
  __norfab__/files/
  __norfab__/logs/

docker/norfab-docker-tests/distributed-basic/client/
  __norfab__/artifacts/distributed-core-junit.xml
  __norfab__/files/
  __norfab__/logs/
```

Because each service gets its own `__norfab__` overlay, client keys, worker
keys, SQLite files, fetched files, artifacts, and logs do not collide between
test environments. Broker keys are generated or reused by NorFab inside that
writable runtime tree.

For `distributed-basic`, the broker keypair is pre-generated and kept in the
broker runtime folder. The broker public key value is also stored in
`distributed-basic/.env` as `NORFAB_BROKER_PUBLIC_KEY`; worker and client
inventories render that value into `broker.shared_key`. The broker private key
is not mounted into worker or client containers.

Clean containers and the default Compose network:

```bash
docker compose down --remove-orphans
```

Remove local runtime output:

```bash
rm -rf core-tests/__norfab__/*
rm -rf nornir-service-tests/__norfab__/*
rm -rf netbox-service-tests/__norfab__/*
rm -rf fakenos-service-tests/__norfab__/*
rm -rf containerlab-service-tests/__norfab__/*
rm -rf workflow-service-tests/__norfab__/*
rm -rf agent-tests/__norfab__/*
rm -rf fastmcp-service-tests/__norfab__/*
rm -rf fastapi-service-tests/__norfab__/*
rm -rf distributed-basic/client/__norfab__/*
rm -rf distributed-basic/netbox-worker/__norfab__/*
rm -rf distributed-basic/nornir-worker/__norfab__/*
rm -rf distributed-basic/dummy-worker/__norfab__/*
```

Do not remove `distributed-basic/broker/__norfab__/files/broker/private_keys` or
`distributed-basic/broker/__norfab__/files/broker/public_keys` unless you also
regenerate `NORFAB_BROKER_PUBLIC_KEY` in `distributed-basic/.env`.

## Inventory Endpoint

The canonical `tests/nf_tests_inventory/inventory.yaml` controls the broker bind
address. On Docker Desktop, a container cannot bind a host LAN address that only
exists on the host OS, such as `192.168.x.x`. Use `127.0.0.1` in the canonical
inventory when running the all-in-one broker, workers, and client inside one
container. Remove `broker.shared_key` from the canonical inventory when you want
each Docker runtime to generate and reuse its own broker keys under its mounted
`__norfab__` folder.
