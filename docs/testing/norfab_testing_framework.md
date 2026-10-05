# NORFAB Testing Framework

## TL;DR

For local debugging, run pytest from `tests/` with the required services available:

```bash
# Enter the test root so relative pytest paths resolve.
cd tests
# Run the Nornir worker tests locally.
poetry run pytest services/nornir/test_worker.py
```

For isolated Docker runs, return to the repository root and use Invoke:

```bash
# Build the Docker images used by the test suites.
poetry run inv docker-tests-build
# Run only the Nornir suite in Docker.
poetry run inv docker-tests-nornir
# Run all regular suites and write one consolidated report.
poetry run inv docker-tests-all
```

Choose a suite run or the all-suites run. Invoke prints `Docker test report: <path>`; open that file under `docker/norfab-docker-tests/reports/` for the final result.

## Tests and local pytest

Tests follow the code layout: `tests/core/`, `tests/services/<service>/`, `tests/clients/`, and `tests/nfcli/`. Shared fixtures are in `tests/conftest.py`; integration test inventory is in `tests/nf_tests_inventory/`. NetBox test helpers are in `tests/services/netbox/common.py`, with seed data in `tests/netbox_data.py`.

Run pytest through Poetry from `tests/`:

```bash
# Enter the test root so relative pytest paths resolve.
cd tests
# Run the full Nornir test directory.
poetry run pytest services/nornir
# Run one NetBox test class.
poetry run pytest services/netbox/test_interfaces.py::TestGetInterfaces
# Run only NetBox get_interfaces tests.
poetry run pytest services/netbox -m "netbox and netbox_get_interfaces"
# Run NFCLI tests with printed output and individual test names.
poetry run pytest nfcli -s -v
```

Use a directory, file, class, or method path to narrow collection; use `-m` for registered service or task markers. Local integration tests start NorFab through fixtures and need their configured external services. Local pytest shows its results in the terminal and does not create an Invoke Markdown report.

### Available pytest markers

| Service | Marker | Description |
|---|---|---|
| Core | `core` | NORFAB core component tests |
| Nornir | `nornir` | Nornir service tests |
| NetBox | `netbox` | NetBox service tests |
| Containerlab | `containerlab` | Containerlab service tests |
| FakeNOS | `fakenos` | FakeNOS service tests |
| FastAPI | `fastapi` | FastAPI service tests |
| FastMCP | `fastmcp` | FastMCP service tests |
| FileSharing | `filesharing` | FileSharing service tests |
| FileSharing | `filesharing_git` | File Sharing authenticated Git remote tests |
| FileSharing | `filesharing_get_remotes` | FileSharing get_remotes task tests |
| FileSharing | `filesharing_create_remote_git` | FileSharing create_remote_git task tests |
| FileSharing | `filesharing_delete_remote_git` | FileSharing delete_remote_git task tests |
| FileSharing | `filesharing_git_clone` | FileSharing git_clone task tests |
| FileSharing | `filesharing_resolve_git_url` | FileSharing resolve_git_url task tests |
| Workflow | `workflow` | Workflow service tests |
| Dummy | `dummy` | dummy plugin service tests |
| Client agent | `clientagent` | Client agent tests |
| NFCLI | `nfcli` | NFCLI shell client tests |
| Nornir | `nornir_cfg` | Nornir cfg task tests |
| Nornir | `nornir_cli` | Nornir CLI task tests |
| Nornir | `nornir_fakenos` | Tests that use FakeNOS-backed devices through Nornir |
| Nornir | `nornir_file_copy` | Nornir file_copy task tests |
| Nornir | `nornir_network` | Nornir network task tests |
| Nornir | `nornir_parse` | Nornir parse task tests |
| Nornir | `nornir_runtime_inventory` | Nornir runtime_inventory task tests |
| Nornir | `nornir_snmp` | Nornir snmp task tests |
| Nornir | `nornir_task` | Nornir task task tests |
| Nornir | `nornir_test` | Nornir test task tests |
| NetBox | `netbox_cache_clear` | NetBox cache_clear task tests |
| NetBox | `netbox_cache_get` | NetBox cache_get task tests |
| NetBox | `netbox_cache_list` | NetBox cache_list task tests |
| NetBox | `netbox_check_device_sync` | NetBox check_device_sync task tests |
| NetBox | `netbox_create_bgp_peering` | NetBox create_bgp_peering task tests |
| NetBox | `netbox_create_asn` | NetBox create_asn task tests |
| NetBox | `netbox_design_deploy` | NetBox design_deploy task tests |
| NetBox | `netbox_create_device_interfaces` | NetBox create_device_interfaces task tests |
| NetBox | `netbox_create_ip` | NetBox create_ip task tests |
| NetBox | `netbox_create_ip_bulk` | NetBox create_ip_bulk task tests |
| NetBox | `netbox_create_prefix` | NetBox create_prefix task tests |
| NetBox | `netbox_create_vlan` | NetBox create_vlan task tests |
| NetBox | `netbox_crud` | NetBox CRUD task tests |
| NetBox | `netbox_crud_create` | NetBox crud_create task tests |
| NetBox | `netbox_crud_delete` | NetBox crud_delete task tests |
| NetBox | `netbox_crud_get_changelogs` | NetBox crud_get_changelogs task tests |
| NetBox | `netbox_crud_list_objects` | NetBox crud_list_objects task tests |
| NetBox | `netbox_crud_read` | NetBox crud_read task tests |
| NetBox | `netbox_crud_search` | NetBox crud_search task tests |
| NetBox | `netbox_crud_update` | NetBox crud_update task tests |
| NetBox | `netbox_get_bgp_peerings` | NetBox get_bgp_peerings task tests |
| NetBox | `netbox_get_circuits` | NetBox get_circuits task tests |
| NetBox | `netbox_get_connections` | NetBox get_connections task tests |
| NetBox | `netbox_get_containerlab_inventory` | NetBox get_containerlab_inventory task tests |
| NetBox | `netbox_get_devices` | NetBox get_devices task tests |
| NetBox | `netbox_get_interfaces` | NetBox get_interfaces task tests |
| NetBox | `netbox_get_nornir_inventory` | NetBox get_nornir_inventory task tests |
| NetBox | `netbox_get_topology` | NetBox get_topology task tests |
| NetBox | `netbox_graphql` | NetBox graphql task tests |
| NetBox | `netbox_sync_all` | NetBox sync_all task tests |
| NetBox | `netbox_sync_bgp_asn` | NetBox sync_bgp_asn task tests |
| NetBox | `netbox_sync_bgp_community` | NetBox sync_bgp_community task tests |
| NetBox | `netbox_sync_bgp_peerings` | NetBox sync_bgp_peerings task tests |
| NetBox | `netbox_sync_device_interfaces` | NetBox sync_device_interfaces task tests |
| NetBox | `netbox_sync_vlans` | NetBox sync_vlans task tests |
| NetBox | `netbox_sync_vrrp` | NetBox sync_vrrp task tests |
| NetBox | `netbox_sync_vrfs` | NetBox sync_vrfs task tests |
| NetBox | `netbox_sync_device_inventory` | NetBox sync_device_inventory task tests |
| NetBox | `netbox_sync_device_ip` | NetBox sync_device_ip task tests |
| NetBox | `netbox_sync_device_prefixes` | NetBox sync_device_prefixes task tests |
| NetBox | `netbox_sync_mac_addresses` | NetBox sync_mac_addresses task tests |
| NetBox | `netbox_update_bgp_peering` | NetBox update_bgp_peering task tests |
| NetBox | `netbox_update_interfaces_description` | NetBox update_interfaces_description task tests |
| Containerlab | `containerlab_deploy` | Containerlab deploy task tests |
| Containerlab | `containerlab_deploy_netbox` | Containerlab deploy_netbox task tests |
| Containerlab | `containerlab_get_nornir_inventory` | Containerlab get_nornir_inventory task tests |
| Containerlab | `containerlab_inspect` | Containerlab inspect task tests |
| Containerlab | `containerlab_restart_lab` | Containerlab restart_lab task tests |
| Containerlab | `containerlab_save` | Containerlab save task tests |
| FakeNOS | `fakenos_get_nornir_inventory` | FakeNOS get_nornir_inventory task tests |
| FakeNOS | `fakenos_auto_start` | FakeNOS inventory auto_start tests |
| FakeNOS | `fakenos_inspect_networks` | FakeNOS inspect_networks task tests |
| FakeNOS | `fakenos_restart` | FakeNOS restart task tests |
| FakeNOS | `fakenos_start` | FakeNOS start task tests |
| FakeNOS | `fakenos_stop` | FakeNOS stop task tests |
| FastMCP | `fastmcp_get_prompts` | FastMCP get_prompts task tests |
| FastMCP | `fastmcp_get_tools` | FastMCP get_tools task tests |
| FileSharing | `filesharing_fetch_file` | FileSharing fetch_file task tests |
| FileSharing | `filesharing_file_details` | FileSharing file_details task tests |
| FileSharing | `filesharing_list_files` | FileSharing list_files task tests |
| FileSharing | `filesharing_walk` | FileSharing walk task tests |
| Workflow | `workflow_run` | Workflow run task tests |

Group tests in `Test...` classes. Exercise real services through the public client interface and the `nfclient` fixture. Keep test data explicit, clean up only data created by the test, and make cleanup safe after partial failures. Put service markers on test files and register new task markers in `pyproject.toml`.

### NetBox test data ownership

[tests/netbox_data_manifest.json](../../tests/netbox_data_manifest.json) records which NetBox objects each test area reads or changes. It is a reference for test authors and agents; pytest does not load it. Read and update it whenever adding or changing tests that use NetBox data. Mutating tests must use records and address space distinct from other test areas and clean up only their own objects. Put persistent shared data in `tests/netbox_data.py`; read-only tests may use that data.

## Docker test environment

Invoke runs pytest in isolated Docker Compose containers using the shared test inventory. Run these commands from the repository root:

```bash
# List all available Invoke commands.
poetry run inv --list

# Check the Docker Compose test configuration without starting containers.
poetry run inv docker-tests-config
# Build images for every test suite.
poetry run inv docker-tests-build

# Build only the Nornir test image.
poetry run inv docker-tests-build --suite=nornir
# Rebuild the Nornir image before running its suite.
poetry run inv docker-tests-nornir --build

# Run all tests in the Nornir suite.
poetry run inv docker-tests-nornir
# Run one Nornir test file in the suite container.
poetry run inv docker-tests-nornir --selector=tests/services/nornir/test_worker.py
# Run only NetBox get_devices tests.
poetry run inv docker-tests-netbox --marker="netbox and netbox_get_devices"

# Run the NetBox CRUD file in a dedicated container.
poetry run inv docker-tests-netbox-crud
# Run Nornir files in separate containers, at most two concurrently.
poetry run inv docker-tests-nornir --parallel-runs=2
```

Suite names are `core`, `nornir`, `netbox`, `fakenos`, `containerlab`, `workflow`, `agent`, `fastmcp`, `fastapi`, `filesharing`, `dummy`, and `nfcli`. `docker-tests-all` runs the regular suites concurrently; run `docker-tests-containerlab` separately. The distributed topology uses `docker-tests-distributed`. The default suite run collects its test directory and applies its service marker. `--selector` accepts a directory, file, or pytest node ID; `--marker`, `--keyword`, and `--pytest-args` narrow the run. The default NetBox suite runs each `test_*.py` file in a dedicated container. See `poetry run inv --help docker-tests-nornir` for all options.

### Run Compose directly

From `docker/norfab-docker-tests/`, you can build and run a Compose service without Invoke:

```bash
# Enter the Docker test environment directory.
cd docker/norfab-docker-tests
# Build the Nornir test image with Compose.
docker compose build nornir-service-tests
# Run the Nornir service's default pytest command.
docker compose run --rm nornir-service-tests
# Override that command to run one file with the Nornir marker.
docker compose run --rm nornir-service-tests -m nornir tests/services/nornir/test_worker.py
```

Arguments after the service name replace its default Compose command, so include `-m nornir` when selecting tests this way. Compose writes JUnit XML under `nornir-service-tests/__norfab__/artifacts/`, but does not create the Invoke Markdown summary. The container exit status indicates whether the direct run passed.

### Read Invoke reports

Each Invoke test run prints the path of its timestamped Markdown report in `docker/norfab-docker-tests/reports/`. Reports are named `docker-tests-<suite>-<timestamp>.md` or `docker-tests-all-<timestamp>.md`.

- The summary table shows passed, failed, errors, skipped, duration, and suite status.
- `Failures and report problems` shows failing tests and error details.
- `JUnit artifacts` lists XML files produced by that run. JUnit files and worker logs are under the suite's ignored `docker/norfab-docker-tests/<compose-service>/__norfab__/` tree; NetBox group and file-parallel runs use `groups/` and `parallel/` subdirectories.
- `NO REPORT` means no JUnit file was produced; `INVALID REPORT` means the XML could not be parsed. Check the container output and runtime logs.

Individual suite and NetBox file tasks report failures but do not return a failing Invoke status. Always check their report. `docker-tests-all` returns a nonzero status if a suite fails. Reports use only JUnit files created or updated during that run.

See `docker/norfab-docker-tests/README.md` for service prerequisites and detailed container setup.
