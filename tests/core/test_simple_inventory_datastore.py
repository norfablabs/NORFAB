import pytest
import pprint
import json
import os
import yaml

from norfab.core.inventory import NorFabInventory
from norfab.core.worker import NFPWorker

os.environ["TERMINAL_LOGGING_LEVEL"] = "INFO"
os.environ["NORNIR_USERNAME"] = "foo"


class TestInventoryLoad:
    inventory = NorFabInventory(path="./nf_tests_inventory/inventory.yaml")

    def test_broker_inventory(self):
        assert self.inventory.broker, "No broker data"
        assert isinstance(self.inventory.broker, dict), "Broker data not a dictionary"
        assert (
            "endpoint" in self.inventory.broker
        ), "Broker inventory has no 'endpoint' data"

    def test_workers_inventory(self):
        assert self.inventory.workers.data, "No workers data"
        assert isinstance(
            self.inventory.workers.data, dict
        ), "Workers data not a dictionary"
        assert isinstance(
            self.inventory.workers.path, str
        ), "Workers inventory path not a string"

    def test_jinja2_rendering(self):
        # inventory.yaml has logging section populated with logging levels for file and terminal
        # using jinja2 env context variables, this test verifies that terminal logging variable properly source from
        # TERMINAL_LOGGING_LEVEL variable set above, while file logging level stays intact since FILE_LOGGING_LEVEL
        # environment variable not set
        assert (
            self.inventory.logging["handlers"]["terminal"]["level"] == "INFO"
        ), "It seem env variable not sourced"
        assert (
            self.inventory.logging["handlers"]["file"]["level"] == "INFO"
        ), "It seem env variable not sourced"
        os.environ.pop("TERMINAL_LOGGING_LEVEL", None)  # clean up env variable


class TestWorkersInventory:
    inventory = NorFabInventory(path="./nf_tests_inventory/inventory.yaml")

    def test_get_item(self):
        nornir_worker_1 = self.inventory.workers["nornir-worker-1"]
        assert isinstance(
            nornir_worker_1, dict
        ), "No dictionary data for nornir-worker-1"

    def test_nornir_worker_1_common_data(self):
        nornir_worker_1 = self.inventory.workers["nornir-worker-1"]
        assert "service" in nornir_worker_1, "No 'service' in inventory"
        assert nornir_worker_1["service"] == "nornir", "'service' is not 'nornir'"
        assert "runner" in nornir_worker_1, "No 'runner' in inventory"
        assert isinstance(nornir_worker_1["runner"], dict), "Runner is not a dictionary"
        assert "plugin" in nornir_worker_1["runner"]

    def test_nornir_worker_1_nornir_inventory(self):
        nornir_worker_1 = self.inventory.workers["nornir-worker-1"]
        assert "hosts" in nornir_worker_1, "No 'hosts' in inventory"
        assert len(nornir_worker_1["hosts"]) > 0, "hosts' inventory is empty"
        assert "groups" in nornir_worker_1, "No 'groups' in inventory"
        assert "defaults" in nornir_worker_1, "No 'defaults' in inventory"

    def test_non_existing_worker_inventory(self):
        with pytest.raises(KeyError):
            nornir_worker_1 = self.inventory.workers["some-worker-111"]

    def test_non_existing_file(self):
        with pytest.raises(FileNotFoundError):
            nornir_worker_3 = self.inventory.workers["nornir-worker-3"]

    def test_list_expansion(self):
        nornir_worker_2 = self.inventory.workers["nornir-worker-2"]

        assert len(nornir_worker_2["hosts"]) == 3

    def test_dict_merge(self):
        nornir_worker_2 = self.inventory.workers["nornir-worker-2"]

        assert "foo" in nornir_worker_2["groups"], "'foo' group missing"
        assert (
            "foobar" in nornir_worker_2["groups"]
        ), "'foobar' group data was not merged"

    def test_value_overwirte(self):
        nornir_worker_2 = self.inventory.workers["nornir-worker-2"]

        assert (
            nornir_worker_2["groups"]["valueoverwrite"]["port"] == 777
        ), "'valueoverwrite.port' not overriden by nested group"

    def test_jinja2_rendering(self):
        # nornir/common.yaml has default section populated with username and password sourced
        # using jinja2 env context variable, this test verifies that username properly source from
        # NORNIR_USERNAME variable set above, while password stays intact since NORNIR_PASSWORD
        # environment variable not set
        nornir_worker_1 = self.inventory.workers["nornir-worker-1"]
        assert nornir_worker_1["defaults"]["username"] == "foo"
        assert nornir_worker_1["defaults"]["password"] == "password"


class TestInventoryLoadFromDictionary:
    data = {
        "broker": {
            "endpoint": "tcp://127.0.0.1:5555",
            "shared_key": "5z1:yW}]n?UXhGmz+5CeHN1>:S9k!eCh6JyIhJqO",
        },
        "topology": {
            "broker": True,
            "workers": [
                "nornir-worker-1",
                "nornir-worker-2",
            ],
        },
        "workers": {
            "nornir-*": [
                # this portion of inventory is a dictionary and should be handled properly
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
                }
            ],
            "nornir-worker-1*": ["nornir/nornir-worker-1.yaml"],
            "nornir-worker-2": [
                "nornir/nornir-worker-2.yaml",
                "nornir/nornir-worker-2-extra.yaml",
            ],
        },
    }

    inventory = NorFabInventory(data=data, base_dir="./nf_tests_inventory/")

    def test_broker_inventory(self):
        assert self.inventory.broker, "No broker data"
        assert isinstance(self.inventory.broker, dict), "Broker data not a dictionary"
        assert (
            "endpoint" in self.inventory.broker
        ), "Broker inventory has no 'endpoint' data"

    def test_workers_inventory(self):
        assert self.inventory.workers.data, "No workers data"
        assert isinstance(
            self.inventory.workers.data, dict
        ), "Workers data not a dictionary"
        assert isinstance(
            self.inventory.workers.path, str
        ), "Workers inventory path not a string"

    def test_worker_inventory_access(self):
        wkr = self.inventory["nornir-worker-1"]
        assert (
            wkr["runner"]["options"]["num_connectors"] == 10
        ), "DIctionary item not loaded properly"
        assert (
            "ceos-spine-2" in wkr["hosts"] and "ceos-spine-1" in wkr["hosts"]
        ), "Hosts inventory not correct"


class TestHooksInventory:
    inventory = NorFabInventory("./nf_tests_inventory/inventory.yaml")

    def test_hooks_load(self):
        assert self.inventory.hooks, "no hooks loaded"

        for attachpoint, hook_data in self.inventory.hooks.items():
            for hook in hook_data:
                assert all(
                    k in hook for k in ["function", "args", "kwargs"]
                ), f"Hook definition missing some params: {attachpoint} - {hook}"
                assert callable(hook["function"])


class TestPluginsInventory:
    inventory = NorFabInventory("./nf_tests_inventory/inventory.yaml")

    def test_plugins_load(self):
        assert self.inventory.plugins, "No plugins loaded"

        for service_name, service_data in self.inventory.plugins.items():
            assert all(
                k in service_data for k in ["worker", "nfcli"]
            ), f"{service_name} plugin definition missing some params"
            plugin = self.inventory.load_plugin(service_name)
            assert issubclass(plugin[service_name]["worker"], NFPWorker)
