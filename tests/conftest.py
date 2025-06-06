import pytest
import time
import yaml
import builtins
import unittest
import unittest.mock
import sys
from norfab.core.nfapi import NorFab
from norfab.clients.picle_shell_client import mount_shell_plugins, NorFabShell
from picle import App


@pytest.fixture(scope="class")
def nfclient():
    """
    Fixture to start NorFab and return client object,
    once tests done destroys NorFab
    """
    nf = NorFab(inventory="./nf_tests_inventory/inventory.yaml")
    nf.start()
    time.sleep(3)  # wait for workers to start
    yield nf.make_client()  # return nf client
    nf.destroy()  # teardown


@pytest.fixture(scope="class")
def nfclient_dict_inventory():
    """
    Fixture to start NorFab and return client object,
    once tests done destroys NorFab
    """
    data = {
        "broker": {
            "endpoint": "tcp://127.0.0.1:5555",
            "shared_key": "s6/nI}VEKn4eW$z)$w:yqe^)r)gD{d+it%10>xm0",
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


@pytest.fixture(scope="class")
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
