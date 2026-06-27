import json
import pprint
import time

import pytest
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


async def get_mcp_prompt(mcp_url: str, prompt_name: str, arguments: dict = None):
    """Retrieve one MCP prompt."""
    async with streamable_http_client(mcp_url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            return await session.get_prompt(prompt_name, arguments=arguments)
