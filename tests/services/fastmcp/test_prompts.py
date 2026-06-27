import asyncio
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import McpError

from norfab.workers.fastmcp_worker.fastmcp_worker import (
    FastMCPWorker,
    make_task_prompt,
    service_tasks_discovery,
)

try:
    from tests.services.fastmcp.common import (
        get_mcp_prompt,
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
        get_mcp_prompt,
        mcp_url,
    )

pytestmark = [
    pytest.mark.fastmcp,
    pytest.mark.prompts,
    pytest.mark.task_fastmcp_prompts,
]


@pytest.mark.task_fastmcp_prompts
class TestPromptMetadata:
    @staticmethod
    def make_discovery_task():
        return {
            "name": "cli",
            "description": "Run CLI commands",
            "inputSchema": {"type": "object", "properties": {}},
            "outputSchema": {"type": "object"},
            "mcp": {
                "prompts": [
                    {
                        "name": "collect",
                        "title": "Collect",
                        "description": "Collect operational data",
                        "arguments": [],
                        "messages": [
                            {
                                "role": "user",
                                "content": {
                                    "type": "text",
                                    "text": "Collect operational data",
                                },
                            }
                        ],
                    },
                    {
                        "name": "troubleshoot",
                        "title": "Troubleshoot",
                        "description": "Troubleshoot a device",
                        "arguments": [],
                        "messages": [
                            {
                                "role": "user",
                                "content": {
                                    "type": "text",
                                    "text": "Troubleshoot a device",
                                },
                            }
                        ],
                    },
                ]
            },
        }

    def test_make_and_render_task_prompt(self):
        task = {"service": "nornir", "name": "cli"}
        prompt_data = make_task_prompt(
            task,
            {
                "name": "collect",
                "title": "Collect",
                "description": "Collect device data",
                "arguments": [
                    {
                        "name": "request",
                        "description": "Collection request",
                        "required": True,
                    },
                    {
                        "name": "targets",
                        "description": "Optional targets",
                        "required": False,
                    },
                ],
                "messages": [
                    {
                        "role": "user",
                        "content": {
                            "type": "text",
                            "text": "{{ request }} on {{ targets }}",
                        },
                    }
                ],
            },
        )

        worker = FastMCPWorker.__new__(FastMCPWorker)
        result = worker.render_task_prompt(
            prompt_data,
            {"request": "{{ 7 * 7 }}", "targets": "spine"},
        )

        assert prompt_data["prompt"].name == "service_nornir__task_cli__prompt_collect"
        assert result.messages[0].content.text == "{{ 7 * 7 }} on spine"

    def test_render_task_prompt_validates_arguments(self):
        task = {"service": "nornir", "name": "cli"}
        prompt_data = make_task_prompt(
            task,
            {
                "name": "collect",
                "title": "Collect",
                "description": "Collect device data",
                "arguments": [
                    {
                        "name": "request",
                        "description": "Collection request",
                        "required": True,
                    }
                ],
                "messages": [
                    {
                        "role": "user",
                        "content": {"type": "text", "text": "{{ request }}"},
                    }
                ],
            },
        )

        worker = FastMCPWorker.__new__(FastMCPWorker)
        with pytest.raises(McpError):
            worker.render_task_prompt(prompt_data, {})
        with pytest.raises(McpError):
            worker.render_task_prompt(
                prompt_data,
                {"request": "show", "unknown": "x"},
            )
        with pytest.raises(McpError):
            worker.render_task_prompt(
                prompt_data,
                {"request": ["show version"]},
            )

    def test_discovery_registers_prompts_and_applies_task_policy(self, monkeypatch):
        client = Mock()
        client.mmi.return_value = {"results": [{"service": "nornir"}]}
        client.run_job.return_value = {
            "nornir-worker": {"result": [self.make_discovery_task()]}
        }
        worker = SimpleNamespace(
            client=client,
            exit_event=threading.Event(),
            fastmcp_inventory={"tools": {}},
            norfab_services_tasks={},
            norfab_services_prompts={},
        )
        monkeypatch.setattr(
            "norfab.workers.fastmcp_worker.fastmcp_worker.time.sleep",
            lambda seconds: None,
        )

        service_tasks_discovery(worker, cycles=1)

        assert list(worker.norfab_services_tasks["nornir"]) == [
            "service_nornir__task_cli"
        ]
        assert list(worker.norfab_services_prompts["nornir"]) == [
            "service_nornir__task_cli__prompt_collect",
            "service_nornir__task_cli__prompt_troubleshoot",
        ]

        worker.fastmcp_inventory["tools"]["policy"] = [
            {"service": "nornir", "tasks": ["cli"], "action": "reject"}
        ]
        worker.norfab_services_tasks = {}
        worker.norfab_services_prompts = {}

        service_tasks_discovery(worker, cycles=1)

        assert worker.norfab_services_tasks == {}
        assert worker.norfab_services_prompts == {}


class TestGetPrompts:
    collect_prompt = "service_nornir__task_cli__prompt_collect_operational_data"
    troubleshoot_prompt = "service_nornir__task_cli__prompt_troubleshoot"

    def test_get_prompts(self, nfclient):
        time.sleep(5)
        ret = nfclient.run_job("fastmcp", "get_prompts")

        for worker_name, data in ret.items():
            assert self.collect_prompt in data["result"], worker_name
            assert self.troubleshoot_prompt in data["result"], worker_name
            collect_prompt = data["result"][self.collect_prompt]
            assert collect_prompt["messages"]
            assert "{{ request }}" in collect_prompt["messages"][0]["content"]["text"]

    def test_get_prompts_filters(self, nfclient):
        ret = nfclient.run_job(
            "fastmcp",
            "get_prompts",
            kwargs={"brief": True, "service": "nornir", "name": "*troubleshoot"},
        )

        for worker_name, data in ret.items():
            assert data["result"] == [self.troubleshoot_prompt], worker_name

    def test_mcp_list_prompts(self, nfclient, mcp_url):
        nfclient.run_job(
            "fastmcp",
            "discover",
            workers=["fastmcp-worker-1"],
            kwargs={"service": "nornir"},
        )

        async def run_test():
            async with streamable_http_client(mcp_url) as (
                read_stream,
                write_stream,
                _,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.list_prompts()
                    prompt_names = [prompt.name for prompt in result.prompts]
                    assert self.collect_prompt in prompt_names
                    assert self.troubleshoot_prompt in prompt_names

        asyncio.run(run_test())

    def test_mcp_get_prompt(self, nfclient, mcp_url):
        nfclient.run_job(
            "fastmcp",
            "discover",
            workers=["fastmcp-worker-1"],
            kwargs={"service": "nornir"},
        )

        result = asyncio.run(
            get_mcp_prompt(
                mcp_url,
                self.collect_prompt,
                {
                    "request": "Check software versions",
                    "targets": "spine devices",
                    "commands": "show version",
                },
            )
        )

        assert "Check software versions" in result.messages[0].content.text
        assert "spine devices" in result.messages[0].content.text
        assert "show version" in result.messages[0].content.text

    def test_mcp_get_prompt_missing_argument(self, nfclient, mcp_url):
        nfclient.run_job(
            "fastmcp",
            "discover",
            workers=["fastmcp-worker-1"],
            kwargs={"service": "nornir"},
        )

        async def run_test():
            async with streamable_http_client(mcp_url) as (
                read_stream,
                write_stream,
                _,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    with pytest.raises(McpError, match="request: Field required"):
                        await session.get_prompt(self.collect_prompt, arguments={})

        asyncio.run(run_test())
