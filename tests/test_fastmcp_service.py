import pprint
import pytest
import random
import requests
import json
import time
import asyncio
import time
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


@pytest.fixture
def mcp_url():
    """Global MCP URL fixture for all test classes"""
    return "http://127.0.0.1:8001/mcp/"


def ensure_tool_discovered(
    tests_class: object, nfclient: object, service: str, task: str, timeout: int = 30
):
    tool_name = f"service_{service}__task_{task}"
    if tool_name in tests_class.tools_discovered:
        return
    start = time.time()
    while time.time() - start < timeout:
        result = nfclient.run_job(
            "fastmcp",
            "discover",
            workers=["fastmcp-worker-1"],
            kwargs={"service": service},
        )
        pprint.pprint(result)
        if service in result["fastmcp-worker-1"]["result"]:
            if tool_name in result["fastmcp-worker-1"]["result"][service]:
                tests_class.tools_discovered = result["fastmcp-worker-1"]["result"][
                    service
                ]
                break
        time.sleep(1)


async def call_mcp_tool(mcp_url: str, tool_name: str, arguments: dict = None):
    """Global helper function to call MCP tools"""
    arguments = arguments or {}
    async with streamable_http_client(mcp_url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            print(f"\nCalling tool '{tool_name}' with arguments: {arguments}")
            result = await session.call_tool(tool_name, arguments=arguments)
            assert not result.isError, f"Tool call returned an error: {result}"
            ret = json.loads(result.content[0].text)
            pprint.pprint(ret)
            for wname, wres in ret.items():
                assert wres["failed"] == False, f"{wname} - {tool_name} returned errors"

            return ret


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


class TestToolsCallNornir:
    """Test MCP tool calls for Nornir service"""

    tools_discovered = {}

    def test_call_refresh_nornir(self, nfclient, mcp_url):
        ensure_tool_discovered(self, nfclient, "nornir", "refresh_nornir")

        async def run_test():
            tool_name = "service_nornir__task_refresh_nornir"
            kwargs = {"progress": False}
            await call_mcp_tool(mcp_url, tool_name, kwargs)

        asyncio.run(run_test())

    def test_call_get_nornir_hosts(self, nfclient, mcp_url):
        ensure_tool_discovered(self, nfclient, "nornir", "get_nornir_hosts")

        async def run_test():
            tool_name = "service_nornir__task_get_nornir_hosts"
            kwargs = {}
            await call_mcp_tool(mcp_url, tool_name, kwargs)

        asyncio.run(run_test())

    def test_call_get_version(self, nfclient, mcp_url):
        ensure_tool_discovered(self, nfclient, "nornir", "get_version")

        async def run_test():
            tool_name = "service_nornir__task_get_version"
            kwargs = {}
            await call_mcp_tool(mcp_url, tool_name, kwargs)

        asyncio.run(run_test())

    def test_call_get_inventory(self, nfclient, mcp_url):
        ensure_tool_discovered(self, nfclient, "nornir", "get_inventory")

        async def run_test():
            tool_name = "service_nornir__task_get_inventory"
            kwargs = {}
            await call_mcp_tool(mcp_url, tool_name, kwargs)

        asyncio.run(run_test())

    def test_call_get_watchdog_stats(self, nfclient, mcp_url):
        ensure_tool_discovered(self, nfclient, "nornir", "get_watchdog_stats")

        async def run_test():
            tool_name = "service_nornir__task_get_watchdog_stats"
            kwargs = {}
            await call_mcp_tool(mcp_url, tool_name, kwargs)

        asyncio.run(run_test())

    def test_call_get_watchdog_configuration(self, nfclient, mcp_url):
        ensure_tool_discovered(self, nfclient, "nornir", "get_watchdog_configuration")

        async def run_test():
            tool_name = "service_nornir__task_get_watchdog_configuration"
            kwargs = {}
            await call_mcp_tool(mcp_url, tool_name, kwargs)

        asyncio.run(run_test())

    def test_call_get_watchdog_connections(self, nfclient, mcp_url):
        ensure_tool_discovered(self, nfclient, "nornir", "get_watchdog_connections")

        async def run_test():
            tool_name = "service_nornir__task_get_watchdog_connections"
            kwargs = {}
            await call_mcp_tool(mcp_url, tool_name, kwargs)

        asyncio.run(run_test())

    def test_call_cli(self, nfclient, mcp_url):
        ensure_tool_discovered(self, nfclient, "nornir", "cli")

        async def run_test():
            tool_name = "service_nornir__task_cli"
            kwargs = {"commands": ["show version"], "FC": "spine", "dry_run": True}
            await call_mcp_tool(mcp_url, tool_name, kwargs)

        asyncio.run(run_test())

    def test_call_test(self, nfclient, mcp_url):
        ensure_tool_discovered(self, nfclient, "nornir", "test")

        async def run_test():
            tool_name = "service_nornir__task_test"
            kwargs = {
                "suite": "nf://nornir_test_suites/suite_1.txt",
                "FC": "spine",
                "dry_run": True,
            }
            await call_mcp_tool(mcp_url, tool_name, kwargs)

        asyncio.run(run_test())

    def test_call_cfg(self, nfclient, mcp_url):
        ensure_tool_discovered(self, nfclient, "nornir", "cfg")

        async def run_test():
            tool_name = "service_nornir__task_cfg"
            kwargs = {"config": "hostname test-device", "FC": "spine", "dry_run": True}
            await call_mcp_tool(mcp_url, tool_name, kwargs)

        asyncio.run(run_test())

    def test_call_network(self, nfclient, mcp_url):
        ensure_tool_discovered(self, nfclient, "nornir", "network")

        async def run_test():
            tool_name = "service_nornir__task_network"
            kwargs = {"fun": "ping", "FC": "spine"}
            await call_mcp_tool(mcp_url, tool_name, kwargs)

        asyncio.run(run_test())


class TestToolsCallNetbox:
    """Test MCP tool calls for Netbox service"""

    tools_discovered = {}

    def test_call_get_version(self, nfclient, mcp_url):
        ensure_tool_discovered(self, nfclient, "netbox", "get_version")

        async def run_test():
            tool_name = "service_netbox__task_get_version"
            kwargs = {}
            await call_mcp_tool(mcp_url, tool_name, kwargs)

        asyncio.run(run_test())

    def test_call_get_inventory(self, nfclient, mcp_url):
        ensure_tool_discovered(self, nfclient, "netbox", "get_inventory")

        async def run_test():
            tool_name = "service_netbox__task_get_inventory"
            kwargs = {}
            await call_mcp_tool(mcp_url, tool_name, kwargs)

        asyncio.run(run_test())

    def test_call_get_netbox_status(self, nfclient, mcp_url):
        ensure_tool_discovered(self, nfclient, "netbox", "get_netbox_status")

        async def run_test():
            tool_name = "service_netbox__task_get_netbox_status"
            kwargs = {}
            await call_mcp_tool(mcp_url, tool_name, kwargs)

        asyncio.run(run_test())

    def test_call_get_compatibility(self, nfclient, mcp_url):
        ensure_tool_discovered(self, nfclient, "netbox", "get_compatibility")

        async def run_test():
            tool_name = "service_netbox__task_get_compatibility"
            kwargs = {}
            await call_mcp_tool(mcp_url, tool_name, kwargs)

        asyncio.run(run_test())

    def test_call_cache_list(self, nfclient, mcp_url):
        ensure_tool_discovered(self, nfclient, "netbox", "cache_list")

        async def run_test():
            tool_name = "service_netbox__task_cache_list"
            kwargs = {}
            await call_mcp_tool(mcp_url, tool_name, kwargs)

        asyncio.run(run_test())


class TestToolsCallContainerlab:
    """Test MCP tool calls for Containerlab service"""

    tools_discovered = {}

    def test_call_get_version(self, nfclient, mcp_url):
        ensure_tool_discovered(self, nfclient, "containerlab", "get_version")

        async def run_test():
            tool_name = "service_containerlab__task_get_version"
            kwargs = {}
            await call_mcp_tool(mcp_url, tool_name, kwargs)

        asyncio.run(run_test())

    def test_call_get_inventory(self, nfclient, mcp_url):
        ensure_tool_discovered(self, nfclient, "containerlab", "get_inventory")

        async def run_test():
            tool_name = "service_containerlab__task_get_inventory"
            kwargs = {}
            await call_mcp_tool(mcp_url, tool_name, kwargs)

        asyncio.run(run_test())

    def test_call_get_containerlab_status(self, nfclient, mcp_url):
        ensure_tool_discovered(
            self, nfclient, "containerlab", "get_containerlab_status"
        )

        async def run_test():
            tool_name = "service_containerlab__task_get_containerlab_status"
            kwargs = {}
            await call_mcp_tool(mcp_url, tool_name, kwargs)

        asyncio.run(run_test())

    def test_call_get_running_labs(self, nfclient, mcp_url):
        ensure_tool_discovered(self, nfclient, "containerlab", "get_running_labs")

        async def run_test():
            tool_name = "service_containerlab__task_get_running_labs"
            kwargs = {"timeout": 60}
            await call_mcp_tool(mcp_url, tool_name, kwargs)

        asyncio.run(run_test())


class TestToolsCallWorkflow:
    """Test MCP tool calls for Workflow service"""

    tools_discovered = {}

    def test_call_get_version(self, nfclient, mcp_url):
        ensure_tool_discovered(self, nfclient, "workflow", "get_version")

        async def run_test():
            tool_name = "service_workflow__task_get_version"
            kwargs = {}
            await call_mcp_tool(mcp_url, tool_name, kwargs)

        asyncio.run(run_test())

    def test_call_get_inventory(self, nfclient, mcp_url):
        ensure_tool_discovered(self, nfclient, "workflow", "get_inventory")

        async def run_test():
            tool_name = "service_workflow__task_get_inventory"
            kwargs = {}
            await call_mcp_tool(mcp_url, tool_name, kwargs)

        asyncio.run(run_test())
