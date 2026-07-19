import asyncio

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import McpError

try:
    from tests.services.fastmcp.common import (
        call_mcp_tool,
        ensure_tool_discovered,
        mcp_url,
    )
except ModuleNotFoundError as exc:
    if exc.name not in {
        "tests",
        "tests.services",
        "tests.services.fastmcp",
        "tests.services.fastmcp.common",
    }:
        raise
    from services.fastmcp.common import (
        call_mcp_tool,
        ensure_tool_discovered,
        mcp_url,
    )

pytestmark = [
    pytest.mark.fastmcp,
    pytest.mark.tools_call,
    pytest.mark.task_fastmcp_tools_call,
]


@pytest.mark.task_fastmcp_tools_call
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

    def test_call_cli_redacts_secrets(self, nfclient, mcp_url):
        ensure_tool_discovered(self, nfclient, "nornir", "cli")

        async def run_test():
            result = await call_mcp_tool(
                mcp_url,
                "service_nornir__task_cli",
                {
                    "commands": ["show run | inc secret"],
                    "FL": ["ceos-spine-1"],
                },
            )
            output = result["nornir-worker-1"]["result"]["ceos-spine-1"][
                "show run | inc secret"
            ]
            assert "REDACTED" in output
            assert "$6$" not in output

        asyncio.run(run_test())

    @pytest.mark.parametrize(
        "commands, message",
        [
            (["reload"], "reboot, reload, or restart command"),
            (["show version", "conf t"], "configuration mode command"),
            (["delete flash:test.txt"], "destructive or state-changing command"),
            (["bash"], "shell mode command"),
            (["boot system flash:image.bin"], "OS/image/package operation command"),
            (["ssh admin@192.0.2.1"], "outbound session command"),
        ],
    )
    def test_call_cli_rejects_guardrails(self, nfclient, mcp_url, commands, message):
        ensure_tool_discovered(self, nfclient, "nornir", "cli")

        async def run_test():
            tool_name = "service_nornir__task_cli"
            kwargs = {"commands": commands, "FC": "spine", "dry_run": True}
            async with streamable_http_client(mcp_url) as (
                read_stream,
                write_stream,
                _,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    try:
                        result = await session.call_tool(tool_name, arguments=kwargs)
                    except McpError as exc:
                        assert message in str(exc)
                    else:
                        assert result.isError
                        assert message in result.content[0].text

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

    @pytest.mark.parametrize(
        "config, message",
        [
            (["reload"], "reboot, reload, or restart command"),
            (["do show version"], "operational command in configuration input"),
            (["delete flash:test.txt"], "delete or erase command"),
            (["ssh admin@192.0.2.1"], "outbound session command"),
        ],
    )
    def test_call_cfg_rejects_guardrails(self, nfclient, mcp_url, config, message):
        ensure_tool_discovered(self, nfclient, "nornir", "cfg")

        async def run_test():
            tool_name = "service_nornir__task_cfg"
            kwargs = {"config": config, "FC": "spine", "dry_run": True}
            async with streamable_http_client(mcp_url) as (
                read_stream,
                write_stream,
                _,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    try:
                        result = await session.call_tool(tool_name, arguments=kwargs)
                    except McpError as exc:
                        assert message in str(exc)
                    else:
                        assert result.isError
                        assert message in result.content[0].text

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
