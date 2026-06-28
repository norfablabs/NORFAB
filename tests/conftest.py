import builtins
import sys
import time
import unittest
import unittest.mock

import pytest
from picle import App

from norfab.clients.nfcli_shell.nfcli_shell_client import (
    NorFabShell,
    mount_shell_plugins,
)
from norfab.core.nfapi import NorFab


@pytest.fixture(scope="module")
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
