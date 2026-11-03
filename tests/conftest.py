import builtins
import os
import socket
import sys
import time
import unittest
import unittest.mock
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from picle import App

from norfab.clients.nfcli_shell.nfcli_shell_client import (
    NorFabShell,
    mount_shell_plugins,
)
from norfab.core.client import NFPClient
from norfab.core.nfapi import NorFab
from tests.services.netbox.common import get_pynetbox


def pytest_configure(config: pytest.Config) -> None:
    """Register service and task markers for the test suite.

    Args:
        config: Pytest configuration receiving the marker descriptions.
    """
    for marker in [
        "core: NORFAB core component tests",
        "nornir: Nornir service tests",
        "netbox: NetBox service tests",
        "containerlab: Containerlab service tests",
        "fakenos: FakeNOS service tests",
        "fastapi: FastAPI service tests",
        "fastmcp: FastMCP service tests",
        "filesharing: FileSharing service tests",
        "filesharing_git: File Sharing authenticated Git remote tests",
        "filesharing_get_remotes: FileSharing get_remotes task tests",
        "filesharing_create_remote_git: FileSharing create_remote_git task tests",
        "filesharing_delete_remote_git: FileSharing delete_remote_git task tests",
        "filesharing_git_clone: FileSharing git_clone task tests",
        "filesharing_resolve_git_url: FileSharing resolve_git_url task tests",
        "workflow: Workflow service tests",
        "dummy: dummy plugin service tests",
        "clientagent: Client agent tests",
        "nfcli: NFCLI shell client tests",
        "nornir_cfg: Nornir cfg task tests",
        "nornir_cli: Nornir CLI task tests",
        "nornir_fakenos: Tests that use FakeNOS-backed devices through Nornir",
        "nornir_file_copy: Nornir file_copy task tests",
        "nornir_network: Nornir network task tests",
        "nornir_parse: Nornir parse task tests",
        "nornir_runtime_inventory: Nornir runtime_inventory task tests",
        "nornir_netconf: Nornir NETCONF task tests",
        "nornir_gnmi: Nornir gNMI task tests",
        "nornir_snmp: Nornir snmp task tests",
        "nornir_task: Nornir task task tests",
        "nornir_test: Nornir test task tests",
        "netbox_cache_clear: NetBox cache_clear task tests",
        "netbox_cache_get: NetBox cache_get task tests",
        "netbox_cache_list: NetBox cache_list task tests",
        "netbox_check_device_sync: NetBox check_device_sync task tests",
        "netbox_create_bgp_peering: NetBox create_bgp_peering task tests",
        "netbox_create_asn: NetBox create_asn task tests",
        "netbox_design_deploy: NetBox design_deploy task tests",
        "netbox_create_device_interfaces: NetBox create_device_interfaces task tests",
        "netbox_move_ip: NetBox move_ip task tests",
        "netbox_create_ip: NetBox create_ip task tests",
        "netbox_create_ip_bulk: NetBox create_ip_bulk task tests",
        "netbox_create_prefix: NetBox create_prefix task tests",
        "netbox_create_vlan: NetBox create_vlan task tests",
        "netbox_crud: NetBox CRUD task tests",
        "netbox_crud_create: NetBox crud_create task tests",
        "netbox_crud_delete: NetBox crud_delete task tests",
        "netbox_crud_get_changelogs: NetBox crud_get_changelogs task tests",
        "netbox_crud_list_objects: NetBox crud_list_objects task tests",
        "netbox_crud_read: NetBox crud_read task tests",
        "netbox_crud_search: NetBox crud_search task tests",
        "netbox_crud_update: NetBox crud_update task tests",
        "netbox_get_bgp_peerings: NetBox get_bgp_peerings task tests",
        "netbox_get_circuits: NetBox get_circuits task tests",
        "netbox_get_connections: NetBox get_connections task tests",
        "netbox_get_containerlab_inventory: NetBox get_containerlab_inventory task tests",
        "netbox_get_devices: NetBox get_devices task tests",
        "netbox_get_interfaces: NetBox get_interfaces task tests",
        "netbox_get_nornir_inventory: NetBox get_nornir_inventory task tests",
        "netbox_get_topology: NetBox get_topology task tests",
        "netbox_graphql: NetBox graphql task tests",
        "netbox_sync_all: NetBox sync_all task tests",
        "netbox_sync_bgp_asn: NetBox sync_bgp_asn task tests",
        "netbox_sync_bgp_community: NetBox sync_bgp_community task tests",
        "netbox_sync_bgp_peerings: NetBox sync_bgp_peerings task tests",
        "netbox_sync_device_interfaces: NetBox sync_device_interfaces task tests",
        "netbox_sync_vlans: NetBox sync_vlans task tests",
        "netbox_sync_vrrp: NetBox sync_vrrp task tests",
        "netbox_sync_vrfs: NetBox sync_vrfs task tests",
        "netbox_sync_device_inventory: NetBox sync_device_inventory task tests",
        "netbox_sync_device_ip: NetBox sync_device_ip task tests",
        "netbox_sync_device_prefixes: NetBox sync_device_prefixes task tests",
        "netbox_sync_mac_addresses: NetBox sync_mac_addresses task tests",
        "netbox_update_bgp_peering: NetBox update_bgp_peering task tests",
        "netbox_update_interfaces_description: NetBox update_interfaces_description task tests",
        "containerlab_deploy: Containerlab deploy task tests",
        "containerlab_deploy_netbox: Containerlab deploy_netbox task tests",
        "containerlab_get_nornir_inventory: Containerlab get_nornir_inventory task tests",
        "containerlab_inspect: Containerlab inspect task tests",
        "containerlab_restart_lab: Containerlab restart_lab task tests",
        "containerlab_save: Containerlab save task tests",
        "fakenos_get_nornir_inventory: FakeNOS get_nornir_inventory task tests",
        "fakenos_auto_start: FakeNOS inventory auto_start tests",
        "fakenos_inspect_networks: FakeNOS inspect_networks task tests",
        "fakenos_restart: FakeNOS restart task tests",
        "fakenos_start: FakeNOS start task tests",
        "fakenos_stop: FakeNOS stop task tests",
        "fastmcp_get_prompts: FastMCP get_prompts task tests",
        "fastmcp_get_tools: FastMCP get_tools task tests",
        "filesharing_fetch_file: FileSharing fetch_file task tests",
        "filesharing_file_details: FileSharing file_details task tests",
        "filesharing_list_files: FileSharing list_files task tests",
        "filesharing_walk: FileSharing walk task tests",
        "workflow_run: Workflow run task tests",
    ]:
        config.addinivalue_line("markers", marker)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Add test setup and teardown timestamps to JUnit properties."""
    outcome = yield
    report = outcome.get_result()
    if call.when == "setup":
        item.user_properties.append(
            ("started", datetime.fromtimestamp(call.start, tz=timezone.utc).isoformat())
        )
    elif call.when == "teardown":
        report.user_properties.append(
            ("completed", datetime.fromtimestamp(call.stop, tz=timezone.utc).isoformat())
        )


def _get_test_workers(nf: NorFab) -> list | bool:
    """Return the Docker-requested worker subset, preserving topology metadata."""
    requested = [
        name.strip()
        for name in os.environ.get("NORFAB_TEST_WORKERS", "").split(",")
        if name.strip()
    ]
    if not requested:
        return True

    topology_workers = {}
    for worker in nf.inventory.topology.get("workers", []):
        worker_name = next(iter(worker)) if isinstance(worker, dict) else worker
        topology_workers[worker_name] = worker

    # Built-in workers such as filesharing are added by NorFab during start-up
    # and therefore are not necessarily present in the original topology.
    return [topology_workers.get(worker_name, worker_name) for worker_name in requested]


@pytest.fixture(scope="module")
def nfclient():
    """
    Fixture to start NorFab and return client object,
    once tests done destroys NorFab
    """
    nf = NorFab(inventory="./nf_tests_inventory/inventory.yaml")
    try:
        nf.start(run_workers=_get_test_workers(nf))
        time.sleep(3)  # wait for workers to start
        yield nf.make_client()  # return nf client
    finally:
        nf.destroy()  # teardown


@pytest.fixture(scope="module")
def netbox():
    """Return a direct pynetbox client for test setup and cleanup."""
    api = get_pynetbox(None)
    try:
        yield api
    finally:
        api.http_session.close()


@pytest.fixture(scope="module")
def nfclient_dict_inventory():
    """
    Fixture to start NorFab and return client object,
    once tests done destroys NorFab
    """
    data = {
        "broker": {
            "endpoint": "tcp://127.0.0.1:7777",
            "shared_key": "D>[[2]NH9#dN5?!o5DtibYYvV)ev?oRl}#P[>(q3",
        },
        "topology": {"broker": True, "workers": ["nornir-worker-1", "nornir-worker-2"]},
        "workers": {
            "nornir-*": [
                {
                    "service": "nornir",
                    "watchdog_interval": 30,
                    "runner": {
                        "plugin": "RetryRunner",
                        "options": {
                            "num_workers": 100,
                            "num_connectors": 10,
                        },
                    },
                },
                "nornir/common.yaml",
            ],
            "nornir-worker-1*": ["nornir/nornir-worker-1.yaml"],
            "nornir-worker-2": [
                "nornir/nornir-worker-2.yaml",
                "nornir/nornir-worker-2-extra.yaml",
            ],
        },
    }

    nf = NorFab(inventory_data=data, base_dir="./nf_tests_inventory/")
    nf.start()
    time.sleep(3)  # wait for workers to start
    yield nf.make_client()  # return nf client
    nf.destroy()  # teardown


@pytest.fixture(scope="module")
def picle_shell():
    mock_stdin = unittest.mock.create_autospec(sys.stdin)
    mock_stdout = unittest.mock.create_autospec(sys.stdout)
    nf = NorFab(inventory="./nf_tests_inventory/inventory.yaml")
    nf.start()
    time.sleep(3)  # wait for workers to start
    NFCLIENT = nf.make_client()
    builtins.NFCLIENT = NFCLIENT
    # make PICLE  shell
    shell = App(NorFabShell, stdin=mock_stdin, stdout=mock_stdout)
    mount_shell_plugins(shell, nf.inventory)
    yield shell, mock_stdout
    nf.destroy()


@pytest.fixture(scope="module")
def transfer_client(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[tuple[NFPClient, Path]]:
    root = tmp_path_factory.mktemp("file-transfer")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    inventory = {
        "broker": {"endpoint": f"tcp://127.0.0.1:{port}", "zmq_auth": False},
        "topology": {"broker": True, "workers": ["transfer-a", "transfer-b"]},
        "workers": {"transfer-*": [{"service": "workflow"}]},
    }
    nf = NorFab(inventory_data=inventory, base_dir=str(root))
    try:
        nf.start()
        yield nf.make_client(), root
    finally:
        nf.destroy()
