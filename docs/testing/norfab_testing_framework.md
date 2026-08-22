# NORFAB Testing Framework

## Overview

NORFAB uses `pytest` for core, client, worker, and service integration tests. Most service tests start a real NorFab process tree through shared fixtures and exercise workers through `NFPClient.run_job()`.

The test suite is intentionally organized by the NORFAB architecture:

- Core framework behavior lives under `tests/core/`.
- Service-worker suites live under `tests/services/<service>/`.
- Larger service suites are split by task area; smaller services may still have only one or two files in their service folder.
- Shared test inventories and data live under `tests/nf_tests_inventory/`.

## TL;DR

Run tests from the `tests/` directory through Poetry.

```bash
cd tests
poetry run pytest
```

Run by folder or file:

```bash
poetry run pytest services/nornir
poetry run pytest services/netbox/test_interfaces.py
poetry run pytest nfcli
```

Run by service marker:

```bash
poetry run pytest -m nornir
poetry run pytest -m netbox
poetry run pytest -m containerlab
poetry run pytest -m fastmcp
poetry run pytest -m nfcli
```

Run by task marker:

```bash
poetry run pytest -m nornir_cli
poetry run pytest -m netbox_get_interfaces
poetry run pytest -m containerlab_deploy
poetry run pytest -m filesharing_fetch_file
```

Combine markers:

```bash
poetry run pytest -m "netbox and netbox_get_interfaces"
poetry run pytest -m "nornir and not nornir_snmp"
poetry run pytest -m "containerlab and containerlab_deploy"
poetry run pytest services/netbox -m "not netbox_crud_create"
```

List available markers:

```bash
poetry run pytest --markers
```

## Test Organization

```text
tests/
  conftest.py
  netbox_data.py
  nf_tests_inventory/
  nfcli/
    test_shell_client.py
    test_shell_common.py
  core/
    test_broker.py
    test_client.py
    test_nfapi.py
    test_simple_inventory_datastore.py
    test_worker.py
  clients/
    agent/
      test_client_agent.py
  services/
    containerlab/
      common.py
      test_deploy.py
      test_deploy_netbox.py
      test_inspect.py
      test_inventory.py
      test_restart.py
      test_save.py
      test_worker.py
    dummy/
      test_plugin.py
    fakenos/
      common.py
      test_inspect.py
      test_inventory.py
      test_restart.py
      test_start.py
      test_stop.py
      test_worker.py
    fastapi/
      common.py
      test_server.py
      test_worker.py
    fastmcp/
      common.py
      test_auth.py
      test_prompts.py
      test_tools.py
      test_tools_call.py
      test_worker.py
    filesharing/
      test_fetch_file.py
      test_file_details.py
      test_list_files.py
      test_walk.py
      test_worker.py
    netbox/
      common.py
      test_worker.py
      test_graphql.py
      test_interfaces.py
      test_devices.py
      test_connections.py
      test_inventory.py
      test_circuits.py
      test_bgp.py
      test_ipam.py
      test_cache.py
      test_containerlab.py
      test_designs.py
      test_crud.py
      test_sync.py
    nornir/
      test_cfg.py
      test_cli.py
      test_file_copy.py
      test_jinja2.py
      test_juniper_integration.py
      test_netbox_ipam.py
      test_network.py
      test_parse.py
      test_runtime_inventory.py
      test_snmp.py
      test_task.py
      test_tests.py
      test_worker.py
    workflow/
      test_run.py
      test_worker.py
```

## Support Files

- `tests/conftest.py` provides shared pytest fixtures.
- `tests/nf_tests_inventory/` contains the inventory used by integration tests.
- `tests/netbox_data.py` contains NetBox test data and NetBox population helpers.
- `tests/services/netbox/common.py` contains shared NetBox test helpers used by NetBox and Nornir tests.

Do not put generated runtime output under source control. Directories such as `__norfab__/`, `.pytest_cache/`, `.ruff_cache/`, and `__pycache__/` are runtime artifacts.

## Fixtures

### `nfclient`

Starts NorFab from `./nf_tests_inventory/inventory.yaml`, waits for workers, yields a client, and destroys NorFab after the test session finishes.

```python
@pytest.fixture(scope="session")
def nfclient():
    nf = NorFab(inventory="./nf_tests_inventory/inventory.yaml")
    nf.start()
    time.sleep(3)
    yield nf.make_client()
    nf.destroy()
```

Use this fixture for service integration tests that call real workers. Because the fixture is session-scoped, tests must clean up any external or worker state they create instead of relying on a per-file NorFab restart.

### `nfclient_dict_inventory`

Starts NorFab from a dictionary-based inventory for the test session. Use it when a test needs a custom topology or worker map without adding a permanent inventory file.

### `picle_shell`

Starts NorFab for the test session and mounts the interactive NFCLI shell model. Use it for shell and CLI behavior tests.

## Running Tests

Follow the repository convention from `CLAUDE.md`: run pytest from the `tests/` directory through Poetry.

```bash
cd tests
poetry run pytest
```

Run a split service suite:

```bash
cd tests
poetry run pytest services/nornir
```

Run one task marker:

```bash
cd tests
poetry run pytest services/netbox
poetry run pytest services/containerlab/test_deploy.py
```

Run NFCLI shell tests:

```bash
cd tests
poetry run pytest nfcli
poetry run pytest -m nfcli
```

Run one file, class, or test:

```bash
cd tests
poetry run pytest services/netbox/test_interfaces.py
poetry run pytest services/netbox/test_interfaces.py::TestGetInterfaces
poetry run pytest services/netbox/test_interfaces.py::TestGetInterfaces::test_get_interfaces
```

Run by marker:

```bash
cd tests
poetry run pytest services/netbox -m netbox
poetry run pytest services/netbox -m netbox_get_interfaces
poetry run pytest services/netbox -m "netbox and not netbox_crud_create"
poetry run pytest nfcli -m nfcli
```

Use verbose output when diagnosing worker behavior:

```bash
cd tests
poetry run pytest -s -v services/netbox/test_worker.py::TestNetboxWorker
```

## Docker Test Environments

Docker test runners live under `docker/norfab-docker-tests/`. Each runner reuses
the canonical `tests/nf_tests_inventory` tree and mounts a service-local
`__norfab__` runtime folder for logs, artifacts, keys, and generated files.

Run from `docker/norfab-docker-tests/`:

```bash
docker compose build
docker compose run --rm core-tests
docker compose run --rm nornir-service-tests
docker compose run --rm netbox-service-tests
docker compose run --rm fakenos-service-tests
docker compose run --rm containerlab-service-tests
docker compose run --rm workflow-service-tests
docker compose run --rm agent-tests
docker compose run --rm fastmcp-service-tests
docker compose run --rm fastapi-service-tests
```

Docker runners use these service markers by default:

```text
core-tests                 -m core
nornir-service-tests       -m nornir
netbox-service-tests       -m netbox
fakenos-service-tests      -m fakenos
containerlab-service-tests -m containerlab
workflow-service-tests     -m workflow
agent-tests                -m clientagent
fastmcp-service-tests      -m fastmcp
fastapi-service-tests      -m fastapi
```

Pass pytest selectors after the Compose service name to run narrower slices:

```bash
docker compose run --rm nornir-service-tests -m "nornir and nornir_cli"
docker compose run --rm netbox-service-tests -m "netbox and netbox_get_devices"
docker compose run --rm containerlab-service-tests tests/services/containerlab/test_inspect.py
docker compose run --rm fastmcp-service-tests tests/services/fastmcp/test_tools.py::TestGetTools::test_get_tools
```

## Markers

Markers are registered in `pyproject.toml` under `[tool.pytest.ini_options]`.

Use service markers on whole files:

```python
pytestmark = pytest.mark.netbox
```

Use `<service>_<task>` markers for tests associated with a specific NorFab task:

```python
@pytest.mark.netbox_get_interfaces
class TestGetInterfaces:
    ...
```

This gives three stable ways to run tests:

- By path, such as `services/netbox/test_interfaces.py`.
- By class, such as `::TestGetInterfaces`.
- By service or task marker, such as `-m "netbox and netbox_get_interfaces"`.

## Writing Service Tests

Keep test classes grouped by NORFAB task or closely related behavior.

```python
import pytest

pytestmark = pytest.mark.netbox


@pytest.mark.netbox_get_interfaces
class TestGetInterfaces:
    def test_get_interfaces(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_interfaces",
            workers="any",
            kwargs={"devices": ["ceos1"]},
        )

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} returned errors"
            assert "ceos1" in res["result"]
```

Prefer explicit imports. Do not use `import *` in tests. Standard library, third-party, and worker-code imports should live in the test file that uses them. Import only shared NetBox helper names from `services/netbox/common.py`.

```python
import pprint

import pytest

try:
    from tests.services.netbox.common import clear_nb_cache, get_nb_version
except ModuleNotFoundError as exc:
    if exc.name not in {"tests", "tests.services", "tests.services.netbox", "tests.services.netbox.common"}:
        raise
    from services.netbox.common import clear_nb_cache, get_nb_version
```

The fallback supports both repo-root invocation and `cd tests` invocation.

## Refactoring Guidelines

Split a test file when one of these is true:

- The file is difficult to navigate or review.
- Classes already form clear task groups.
- The file mixes independent service areas such as BGP, IPAM, CRUD, cache, and sync.
- Targeted runs are becoming awkward.

When splitting a service suite:

1. Keep existing `Test...` classes when they already group behavior well.
2. Move shared helpers into a service common module, such as `tests/services/netbox/common.py`.
3. Keep helper imports explicit.
4. Add a file-level service marker.
5. Add `<service>_<task>` markers only to tests tied to a specific NorFab task.
6. Register new service or task markers in `pyproject.toml`.
7. Preserve `cd tests && poetry run pytest ...` compatibility.
8. Update the related document in `docs/testing/`.

Do not split small service files into tiny fragments just to make the tree symmetrical. A small service folder with one or two focused files is fine while it stays easy to scan.

## Response Assertions

Service tests usually receive a worker-keyed dictionary:

```python
{
    "worker-name": {
        "errors": [],
        "failed": False,
        "result": {},
        "messages": [],
    }
}
```

Common assertion patterns:

```python
assert not res["errors"], f"{worker} returned errors"
assert res["failed"] is False, f"{worker} failed"
assert "expected_key" in res["result"]
```

Use direct NetBox or service API reads only when the test must verify external state, such as object creation, deletion, or idempotency.

## Cleanup

Tests that create external state must clean it up. Prefer `try/finally` when a test creates data before assertions.

```python
def test_create_and_cleanup(self, nfclient):
    branch = "test-branch"
    try:
        ret = nfclient.run_job("netbox", "create_branch", kwargs={"branch": branch})
        assert ret
    finally:
        delete_branch(branch, nfclient)
```

Cleanup helpers for NetBox tests belong in `tests/services/netbox/common.py`.

## Troubleshooting

- If imports fail, make sure Poetry installed the needed extras for the service under test.
- If workers do not appear, inspect broker state with `nfclient.mmi("mmi.service.broker", "show_workers")`.
- If NetBox tests fail with connection errors, check `tests/netbox_data.py` and `tests/nf_tests_inventory/netbox/common.yaml`.
- If cache behavior looks stale, use the service cache clear task or helper before running assertions.
- If a test run leaves runtime data behind, check `tests/nf_tests_inventory/__norfab__/` and worker logs.

## Related Documentation

- [NetBox Service Tests](netbox_service_tests.md)
- [NORFAB Getting Started](../norfab_getting_started.md)
- [NORFAB Architecture](../reference_architecture_norfab.md)
- [Services and Workers Documentation](../services_overview.md)
- [Service Plugin Development](../customization/service_plugin_overview.md)
