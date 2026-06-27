import pprint
import time
import pytest

pytestmark = [
    pytest.mark.fastmcp,
    pytest.mark.tools,
    pytest.mark.task_fastmcp_get_tools,
]


@pytest.mark.task_fastmcp_get_tools
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
