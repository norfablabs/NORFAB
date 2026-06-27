# NetBox Service Tests

## Overview

NetBox service tests validate NORFAB's NetBox worker, task input models, NetBox API interactions, cache behavior, synchronization tasks, and related integrations.

The NetBox suite is split under `tests/services/netbox/`. The old monolithic `tests/test_netbox_service.py` file has been removed, and CRUD tests now live in `tests/services/netbox/test_crud.py` instead of the old root-level `tests/test_netbox_service_crud_tasks.py` location. Shared helpers live in `tests/services/netbox/common.py`, while test data and population helpers remain in `tests/netbox_data.py`.

Run NetBox tests from the `tests/` directory:

```bash
cd tests
poetry run pytest services/netbox
```

## File Layout

| File | Area | Classes |
|------|------|---------|
| `services/netbox/common.py` | Shared NetBox test helpers | Helper functions only |
| `services/netbox/test_worker.py` | Service health and inventory | `TestNetboxWorker` |
| `services/netbox/test_graphql.py` | GraphQL task | `TestNetboxGrapQL` |
| `services/netbox/test_interfaces.py` | Interface get/update/create/sync tasks | `TestGetInterfaces`, `TestUpdateInterfacesDescription`, `TestSyncDeviceInterfaces`, `TestCreateDeviceInterfaces` |
| `services/netbox/test_devices.py` | Device queries | `TestGetDevices` |
| `services/netbox/test_connections.py` | Connections and topology | `TestGetConnections`, `TestGetTopology` |
| `services/netbox/test_inventory.py` | Nornir inventory and inventory models | `TestGetNornirInventory`, `TestInventoryPatternMap`, `TestDeviceInventoryRecords`, `TestSyncDeviceInventoryInput`, `TestSyncAllInput`, `TestInventoryRecordFilters`, `TestSyncDeviceInventory` |
| `services/netbox/test_circuits.py` | Circuit queries | `TestGetCircuits` |
| `services/netbox/test_bgp.py` | BGP query/create/update/sync tasks | `TestGetBgpPeerings`, `TestSyncBgpPeerings`, `TestCreateBgpPeering`, `TestUpdateBgpPeering` |
| `services/netbox/test_ipam.py` | IP and prefix tasks | `TestSyncDeviceIP`, `TestCreateIP`, `TestCreatePrefix`, `TestCreateIPBulk` |
| `services/netbox/test_cache.py` | Cache tasks | `TestNetboxCache` |
| `services/netbox/test_containerlab.py` | Containerlab inventory generation | `TestGetContainerlabInventory` |
| `services/netbox/test_designs.py` | Design creation | `TestCreateDesign` |
| `services/netbox/test_crud.py` | Generic CRUD tasks | `TestCrudListObjects`, `TestCrudSearch`, `TestCrudRead`, `TestCrudCreate`, `TestCrudUpdate`, `TestCrudDelete`, `TestCrudGetChangelogs` |
| `services/netbox/test_sync.py` | MAC/check/sync-all tasks | `TestSyncMacAddresses`, `TestCheckDeviceSync`, `TestSyncAll` |

## Markers

Every NetBox test file should have a file-level `netbox` marker and an area marker:

```python
pytestmark = [pytest.mark.netbox, pytest.mark.interfaces]
```

Every task-oriented class should have a task marker:

```python
@pytest.mark.task_get_interfaces
class TestGetInterfaces:
    ...
```

Registered NetBox markers include:

- Area markers: `netbox`, `graphql`, `interfaces`, `devices`, `connections`, `inventory`, `circuits`, `bgp`, `ipam`, `cache`, `containerlab`, `designs`, `sync`, `crud`.
- Task markers: `task_get_inventory`, `task_graphql`, `task_get_interfaces`, `task_update_interfaces_description`, `task_get_devices`, `task_get_connections`, `task_get_topology`, `task_get_nornir_inventory`, `task_get_circuits`, `task_get_bgp_peerings`, `task_inventory_models`, `task_sync_device_inventory`, `task_sync_device_interfaces`, `task_create_device_interfaces`, `task_sync_device_ip`, `task_create_ip`, `task_cache`, `task_get_containerlab_inventory`, `task_create_prefix`, `task_create_ip_bulk`, `task_create_design`, `task_sync_bgp_peerings`, `task_create_bgp_peering`, `task_update_bgp_peering`, `task_sync_mac_addresses`, `task_check_device_sync`, `task_sync_all`, `task_crud_list_objects`, `task_crud_search`, `task_crud_read`, `task_crud_create`, `task_crud_update`, `task_crud_delete`, `task_crud_get_changelogs`.

Add new markers to `pyproject.toml` before using them.

## Running Tests

Run all NetBox tests:

```bash
cd tests
poetry run pytest services/netbox
```

Run one area:

```bash
cd tests
poetry run pytest services/netbox/test_interfaces.py
poetry run pytest services/netbox -m interfaces
```

Run one class:

```bash
cd tests
poetry run pytest services/netbox/test_interfaces.py::TestGetInterfaces
```

Run one method:

```bash
cd tests
poetry run pytest services/netbox/test_interfaces.py::TestGetInterfaces::test_get_interfaces
```

Run one task marker:

```bash
cd tests
poetry run pytest services/netbox -m task_get_interfaces
poetry run pytest services/netbox -m task_sync_bgp_peerings
poetry run pytest services/netbox -m task_inventory_models
```

Run with output while debugging worker behavior:

```bash
cd tests
poetry run pytest -s -v services/netbox/test_worker.py::TestNetboxWorker
```

## Configuration

NetBox tests depend on:

- `tests/netbox_data.py` for `NB_URL`, `NB_API_TOKEN`, and seed data helpers.
- `tests/nf_tests_inventory/netbox/common.yaml` for NetBox worker configuration.
- The shared `nfclient` fixture from `tests/conftest.py`.

Most tests are integration tests and require a reachable NetBox instance plus a startable NORFAB test inventory.

## Shared Helpers

Put NetBox helper functions in `tests/services/netbox/common.py`. Current helpers include:

- `get_nb_version(nfclient, instance=None)`
- `get_pynetbox(nfclient)`
- `clear_nb_cache(keys, nfclient)`
- `delete_branch(branch, nfclient)`
- `delete_interfaces(nfclient, device, interface)`
- `delete_interfaces_with_description(nfclient, devices, description_contains)`
- `delete_prefixes_within(prefix, nfclient)`
- `delete_ips(prefix, nfclient)`
- `delete_ip_address(nfclient, address)`
- `delete_mac_addresses_from_interface(nfclient, device, interface)`
- `delete_all_mac_addresses(nfclient, devices)`
- `delete_test_sync_ips(nfclient, devices)`

Import helpers explicitly. Do not use `import *`. Keep `pytest`, `pprint`, Pydantic models, and worker functions in the test files that use them; `services/netbox/common.py` should contain shared NetBox helper functions and constants only.

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

The fallback supports both of these execution styles:

```bash
poetry run pytest tests/services/netbox/test_interfaces.py
cd tests && poetry run pytest services/netbox/test_interfaces.py
```

## Adding New NetBox Tests

Follow this pattern:

1. Put the test in the file that matches the task area.
2. Create a new file only when the area is new or the existing file is becoming hard to navigate.
3. Keep or create a `Test...` class named after the NORFAB task or behavior.
4. Add a file-level `pytestmark` with `netbox` and an area marker.
5. Add a class-level task marker.
6. Register new markers in `pyproject.toml`.
7. Put reusable cleanup and NetBox API helpers in `tests/services/netbox/common.py`.
8. Import helper names explicitly.
9. Make cleanup idempotent and safe to run after partial failures.

Example:

```python
import pprint

import pytest

try:
    from tests.services.netbox.common import clear_nb_cache
except ModuleNotFoundError as exc:
    if exc.name not in {"tests", "tests.services", "tests.services.netbox", "tests.services.netbox.common"}:
        raise
    from services.netbox.common import clear_nb_cache

pytestmark = [pytest.mark.netbox, pytest.mark.interfaces]


@pytest.mark.task_get_interfaces
class TestGetInterfaces:
    def test_get_interfaces(self, nfclient):
        clear_nb_cache("get_interfaces*", nfclient)
        ret = nfclient.run_job(
            "netbox",
            "get_interfaces",
            workers="any",
            kwargs={"devices": ["ceos1"]},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} returned errors"
            assert "ceos1" in res["result"]
```

## Future Refactoring Guidelines

Use the NetBox split as the model for future large service refactors:

- Keep small service suites as flat `tests/test_<service>_service.py` files.
- Split only when a file is large enough that task-level navigation and marker runs are valuable.
- Split by user-facing task area, not by arbitrary unit/integration labels.
- Preserve class names when they already describe behavior well.
- Keep shared helpers in one common module per service.
- Avoid compatibility shim files where possible; update imports directly.
- Avoid broad imports and file-wide lint suppressions.
- Update docs and `pyproject.toml` markers in the same change.

## Troubleshooting

- If pytest cannot import `tests.services.netbox.common`, confirm the fallback import exists and that the test is being run either from repo root or from `tests/`.
- If NetBox connection tests fail, verify `NB_URL`, `NB_API_TOKEN`, and worker inventory settings.
- If a test is order-sensitive, add explicit setup/cleanup instead of relying on existing NetBox state.
- If cache-related tests fail unexpectedly, clear cache keys with `clear_nb_cache()` before asserting.
- If marker selection returns no tests, check both the class marker and `pyproject.toml` marker registration.

## Related Documentation

- [NORFAB Testing Framework](norfab_testing_framework.md)
- [NetBox Service Overview](../workers/netbox/services_netbox_service.md)
- [NetBox Service Tasks](../workers/netbox/services_netbox_service_tasks_rest.md)
- [NetBox Worker API Reference](../workers/netbox/api_reference_workers_netbox_worker.md)
