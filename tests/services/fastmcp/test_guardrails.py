import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import McpError
from pydantic import ValidationError

from norfab.workers.fastmcp_worker.fastmcp_models import TaskMCPGuardrail
from norfab.workers.fastmcp_worker.fastmcp_worker import service_tasks_discovery

try:
    from tests.services.fastmcp.common import (
        ensure_tool_discovered,
        mcp_url,  # noqa: F401 - imported pytest fixture
    )
except ModuleNotFoundError as exc:
    if exc.name not in {
        "tests",
        "tests.services",
        "tests.services.fastmcp",
        "tests.services.fastmcp.common",
    }:
        raise
    from services.fastmcp.common import ensure_tool_discovered, mcp_url  # noqa: F401

pytestmark = [
    pytest.mark.fastmcp,
    pytest.mark.guardrails,
]


@pytest.mark.task_fastmcp_guardrails
class TestFastMCPGuardrails:
    tools_discovered = {}

    @staticmethod
    def make_task_guardrail():
        return {
            "description": "Reject reboot commands.",
            "field": "commands",
            "type": "regex",
            "match": r"(?i)^\s*reboot\b.*",
            "message": "Rejected reboot command.",
        }

    def make_discovery_task(self):
        return {
            "name": "cli",
            "description": "Run CLI commands",
            "inputSchema": {"type": "object", "properties": {}},
            "outputSchema": {"type": "object"},
            "mcp": {"guardrails": [self.make_task_guardrail()]},
        }

    def make_worker(self, fastmcp_inventory):
        client = Mock()
        client.mmi.return_value = {"results": [{"service": "nornir"}]}
        client.run_job.return_value = {
            "nornir-worker": {"result": [self.make_discovery_task()]}
        }
        return SimpleNamespace(
            client=client,
            exit_event=threading.Event(),
            fastmcp_inventory=fastmcp_inventory,
            norfab_services_tasks={},
            norfab_services_prompts={},
        )

    def test_guardrail_metadata_validation(self):
        guardrail = self.make_task_guardrail()

        validated = TaskMCPGuardrail.model_validate(guardrail).model_dump()

        assert validated["field"] == "commands"
        assert validated["type"] == "regex"

    @pytest.mark.parametrize(
        "guardrail",
        [None, False, {"field": "commands"}, ()],
    )
    def test_guardrail_metadata_rejects_invalid_values(self, guardrail):
        with pytest.raises(ValidationError):
            TaskMCPGuardrail.model_validate(guardrail)

    def test_guardrail_metadata_rejects_invalid_regex(self):
        guardrail = self.make_task_guardrail()
        guardrail["match"] = "["

        with pytest.raises(ValidationError, match="Invalid guardrail regex match"):
            TaskMCPGuardrail.model_validate(guardrail)

    def test_discovery_registers_task_and_inventory_guardrails(self, monkeypatch):
        worker = self.make_worker(
            {
                "tools": {
                    "guardrails": [
                        {
                            "service": "nornir",
                            "task": "cli",
                            "description": "Reject reload commands.",
                            "field": "commands",
                            "type": "regex",
                            "match": r"(?i)^\s*reload\b.*",
                            "message": "Rejected reload command.",
                        }
                    ]
                }
            }
        )
        monkeypatch.setattr(
            "norfab.workers.fastmcp_worker.fastmcp_worker.time.sleep",
            lambda seconds: None,
        )

        service_tasks_discovery(worker, cycles=1)

        tool_data = worker.norfab_services_tasks["nornir"]["service_nornir__task_cli"]
        assert [item["message"] for item in tool_data["guardrails"]] == [
            "Rejected reboot command.",
            "Rejected reload command.",
        ]
        assert "guardrails" not in tool_data["tool"].model_dump()

    def test_discovery_can_disable_builtin_guardrails(self, monkeypatch):
        worker = self.make_worker(
            {
                "tools": {
                    "disable_builtin_guardrails": True,
                    "guardrails": [
                        {
                            "service": "nornir",
                            "task": "cli",
                            "description": "Reject reload commands.",
                            "field": "commands",
                            "type": "regex",
                            "match": r"(?i)^\s*reload\b.*",
                            "message": "Rejected reload command.",
                        }
                    ],
                }
            }
        )
        monkeypatch.setattr(
            "norfab.workers.fastmcp_worker.fastmcp_worker.time.sleep",
            lambda seconds: None,
        )

        service_tasks_discovery(worker, cycles=1)

        tool_data = worker.norfab_services_tasks["nornir"]["service_nornir__task_cli"]
        assert [item["message"] for item in tool_data["guardrails"]] == [
            "Rejected reload command.",
        ]

    @pytest.mark.parametrize(
        "command, message",
        [
            ("reload", "reboot, reload, or restart command"),
            ("conf t", "configuration mode command"),
            ("delete flash:test.txt", "destructive or state-changing command"),
            ("bash", "shell mode command"),
            ("boot system flash:image.bin", "OS/image/package operation command"),
            ("ssh admin@192.0.2.1", "outbound session command"),
        ],
    )
    def test_cli_rejects_unsafe_command_integration(
        self, nfclient, mcp_url, command, message
    ):
        ensure_tool_discovered(self, nfclient, "nornir", "cli")

        async def run_test():
            async with streamable_http_client(mcp_url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    try:
                        result = await session.call_tool(
                            "service_nornir__task_cli",
                            arguments={
                                "commands": [command],
                                "FL": ["ceos-spine-1"],
                                "dry_run": True,
                            },
                        )
                    except McpError as exc:
                        response = str(exc)
                    else:
                        assert result.isError
                        response = result.content[0].text

                    assert message in response

        asyncio.run(run_test())
