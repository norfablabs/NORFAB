import pprint
import pytest
import random
import requests
import json


class TestWorker:
    def test_get_inventory(self, nfclient):
        ret = nfclient.run_job("containerlab", "get_inventory")
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert all(
                k in data["result"] for k in ["service"]
            ), f"{worker_name} inventory incomplete"

    def test_get_version(self, nfclient):
        ret = nfclient.run_job("containerlab", "get_version")
        pprint.pprint(ret)

        assert isinstance(ret, dict), f"Expected dictionary but received {type(ret)}"
        for worker_name, version_report in ret.items():
            for package, version in version_report["result"].items():
                assert version != "", f"{worker_name}:{package} version is empty"


class TestDeployTask:
    def test_deploy(self, nfclient):
        ret_destroy = ret = nfclient.run_job("containerlab", "destroy", kwargs={"lab_name": "three-routers-lab"})
        ret_deploy = nfclient.run_job("containerlab", "deploy", kwargs={"lab_name": "three-routers-lab"})

        print("Lab destroyed:")
        pprint.pprint(ret_destroy)

        print("Lab deployed:")
        pprint.pprint(ret_deploy)

        for worker_name, data in ret_deploy.items():
            pass


class TestGetNornirInventoryTask:
    def get_nornir_inventory(self, nfclient):
        ret = nfclient.run_job("containerlab", "get_nornir_inventory", kwargs={"lab_name": ""})
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            pass