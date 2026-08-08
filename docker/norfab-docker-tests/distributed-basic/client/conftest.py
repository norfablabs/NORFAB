import os
import time

import pytest

from norfab.core.nfapi import NorFab


def _wait_for_workers(client, expected_workers: set[str], timeout: int = 60) -> None:
    deadline = time.time() + timeout
    last_workers = []

    while time.time() < deadline:
        try:
            reply = client.mmi("mmi.service.broker", "show_workers", timeout=5)
            last_workers = reply.get("results", []) if reply else []
            worker_names = {worker.get("name") for worker in last_workers}
            if expected_workers.issubset(worker_names):
                return
        except Exception:
            pass
        time.sleep(2)

    raise RuntimeError(
        f"Distributed workers did not become ready: expected {expected_workers}, "
        f"last seen {last_workers}"
    )


@pytest.fixture(scope="module")
def nfclient():
    nf = NorFab(inventory="./inventory.yaml", run_broker=False, run_workers=False)
    client = nf.make_client(name="distributed-core-tests")

    expected_workers = {
        worker.strip()
        for worker in os.getenv("NORFAB_DISTRIBUTED_EXPECTED_WORKERS", "").split(",")
        if worker.strip()
    }
    if expected_workers:
        _wait_for_workers(client, expected_workers)

    yield client
    nf.destroy()


@pytest.fixture(scope="module")
def nfclient_dict_inventory():
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
                "/workspace/tests/nf_tests_inventory/nornir/common.yaml",
            ],
            "nornir-worker-1*": [
                "/workspace/tests/nf_tests_inventory/nornir/nornir-worker-1.yaml"
            ],
            "nornir-worker-2": [
                "/workspace/tests/nf_tests_inventory/nornir/nornir-worker-2.yaml",
                "/workspace/tests/nf_tests_inventory/nornir/nornir-worker-2-extra.yaml",
            ],
        },
    }

    nf = NorFab(inventory_data=data, base_dir="./")
    nf.start()
    time.sleep(3)
    yield nf.make_client()
    nf.destroy()
