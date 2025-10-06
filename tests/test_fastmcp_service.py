import pprint
import pytest
import random
import requests
import json
import time


class TestFastMCPWorker:
    def test_get_fastmcp_inventory(self, nfclient):
        ret = nfclient.run_job("fastmcp", "get_inventory")
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert all(
                k in data["result"] for k in ["fastmcp", "service"]
            ), f"{worker_name} inventory incomplete"

    def test_get_fastmcp_version(self, nfclient):
        ret = nfclient.run_job("fastmcp", "get_version")
        pprint.pprint(ret)

        assert isinstance(ret, dict), f"Expected dictionary but received {type(ret)}"
        for worker_name, version_report in ret.items():
            for package, version in version_report["result"].items():
                assert version != "", f"{worker_name}:{package} version is empty"

    def test_get_fastmcp_status(self, nfclient):
        ret = nfclient.run_job("fastmcp", "get_status")
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert all(
                data["result"][k] for k in ["name", "url", "tools_count"]
            ), f"{worker_name} status data incomplete"


class TestGetTools:

    def test_get_tools(self, nfclient):
        time.sleep(5)
        ret = nfclient.run_job("fastmcp", "get_tools", kwargs={})
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert isinstance(data["result"], dict)
            assert len(data["result"]) > 0, f"{worker_name} no tools returned"

    def test_get_tools_brief(self, nfclient):
        time.sleep(5)
        ret = nfclient.run_job("fastmcp", "get_tools", kwargs={"brief": True})
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert isinstance(data["result"], list)
            assert len(data["result"]) > 0, f"{worker_name} no tools returned"

    def test_get_tools_brief_service_filter(self, nfclient):
        time.sleep(5)
        ret = nfclient.run_job(
            "fastmcp", "get_tools", kwargs={"brief": True, "service": "nornir"}
        )
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert data["result"] and isinstance(data["result"], list)
            assert all(
                "nornir" in tool_name for tool_name in data["result"]
            ), f"{worker_name} service filter did not work"

    def test_get_tools_brief_tool_name_filter(self, nfclient):
        time.sleep(5)
        ret = nfclient.run_job(
            "fastmcp", "get_tools", kwargs={"brief": True, "name": "*cli"}
        )
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert data["result"] == ["service_nornir__task_cli"]

    def test_get_tools_tool_name_filter(self, nfclient):
        time.sleep(5)
        ret = nfclient.run_job("fastmcp", "get_tools", kwargs={"name": "*cli"})
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert len(data["result"]) == 1
            assert all(
                k in data["result"]["service_nornir__task_cli"]
                for k in ["description", "annotations", "inputSchema", "outputSchema"]
            )
