import asyncio
import json
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import ElicitResult
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

pytestmark = pytest.mark.fastmcp


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
        "commands, message",
        [
            (["reload"], "reboot, reload, or restart command"),
            (["conf t"], "configuration mode command"),
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
            async with streamable_http_client(mcp_url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    response = await session.call_tool(
                        "service_nornir__task_cli",
                        arguments={
                            "commands": commands,
                            "FL": ["ceos-spine-1"],
                            "dry_run": True,
                        },
                    )
                    assert not response.isError
                    result = json.loads(response.content[0].text)
                    assert set(result) == {"fastmcp-worker-1"}
                    result = result["fastmcp-worker-1"]
                    assert result["service"] == "fastmcp"
                    assert result["result"] == {}
                    assert result["failed"] is False
                    assert len(result["errors"]) == 1
                    assert message in result["errors"][0]

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
                    response = await session.call_tool(tool_name, arguments=kwargs)
                    assert not response.isError
                    result = json.loads(response.content[0].text)
                    assert set(result) == {"fastmcp-worker-1"}
                    result = result["fastmcp-worker-1"]
                    assert result["service"] == "fastmcp"
                    assert result["result"] == {}
                    assert result["failed"] is False
                    assert len(result["errors"]) == 1
                    assert message in result["errors"][0]

        asyncio.run(run_test())

    @pytest.mark.parametrize(
        "command, expected",
        [
            ("password hunter42", "password REDACTED"),
            ("secret 5 $6$salt$syntheticpasswordhash", "secret 5 REDACTED"),
            ('"password": "hunter 42"', '"password": "REDACTED"'),
            ("DB_PASSWORD=hunter42", "DB_PASSWORD=REDACTED"),
            ("clientSecret: hunter42", "clientSecret: REDACTED"),
            ("api_key=hunter42", "api_key=REDACTED"),
            ("access_token=hunter42", "access_token=REDACTED"),
            ("Authorization: Bearer hunter42", "Authorization: REDACTED"),
            ("Cookie: session=hunter42", "Cookie: REDACTED"),
            ("https://user:hunter42@example.com", "https://user:REDACTED@example.com"),
            (
                "https://example.com/?token=hunter42",
                "https://example.com/?token=REDACTED",
            ),
            ("snmp-server community hunter42 RO", "snmp-server community REDACTED RO"),
            ("radius-server key 7 hunter42", "radius-server key 7 REDACTED"),
            ("<password>hunter42</password>", "<password>REDACTED</password>"),
            ("ghp_" + "a" * 36, "REDACTED"),
            ("sk-proj-" + "a" * 30, "REDACTED"),
            (
                "-----BEGIN PRIVATE KEY-----\nsecretbody\n-----END PRIVATE KEY-----",
                "REDACTED",
            ),
            ("public_key=example", "public_key=example"),
            ("client_id=example", "client_id=example"),
            ("token_count=100", "token_count=100"),
            ("password REDACTED", "password REDACTED"),
        ],
    )
    def test_default_result_redaction_integration(
        self, nfclient, mcp_url, command, expected
    ):
        ensure_tool_discovered(self, nfclient, "nornir", "task")

        async def run_test():
            async with streamable_http_client(mcp_url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    response = await session.call_tool(
                        "service_nornir__task_task",
                        arguments={
                            "plugin": "nornir_salt.plugins.tasks.nr_test",
                            "commands": [command],
                            "FL": ["ceos-spine-1"],
                        },
                    )
                    assert not response.isError
                    result = json.loads(response.content[0].text)
                    assert result["nornir-worker-1"]["failed"] is False
                    assert result["nornir-worker-1"]["result"]["ceos-spine-1"] == {
                        "nr_test": {"commands": [expected]}
                    }

        asyncio.run(run_test())

    @pytest.mark.parametrize("size", [100, 100100])
    def test_default_result_character_limit_integration(self, nfclient, mcp_url, size):
        ensure_tool_discovered(self, nfclient, "nornir", "task")

        async def run_test():
            async with streamable_http_client(mcp_url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    response = await session.call_tool(
                        "service_nornir__task_task",
                        arguments={
                            "plugin": "nornir_salt.plugins.tasks.nr_test",
                            "commands": ["x" * size],
                            "FL": ["ceos-spine-1"],
                        },
                    )
                    assert not response.isError
                    result = json.loads(response.content[0].text)
                    if size > 100000:
                        assert "nornir-worker-1" in result
                        for worker_result in result.values():
                            assert worker_result["service"] == "nornir"
                            assert worker_result["result"] == {}
                            assert worker_result["failed"] is False
                            assert len(worker_result["errors"]) == 1
                            assert "fastmcp-worker-1" in worker_result["errors"][0]
                            assert "100000 characters" in worker_result["errors"][0]
                            assert (
                                "disable_builtin_guardrails"
                                in worker_result["errors"][0]
                            )
                    else:
                        assert result["nornir-worker-1"]["failed"] is False
                        assert result["nornir-worker-1"]["result"]["ceos-spine-1"] == {
                            "nr_test": {"commands": ["x" * size]}
                        }

        asyncio.run(run_test())

    @pytest.mark.parametrize(
        "action, approve", [("decline", False), ("accept", False), ("accept", True)]
    )
    def test_task_approval_integration(self, nfclient, mcp_url, action, approve):
        ensure_tool_discovered(self, nfclient, "nornir", "task")
        before = nfclient.run_job(
            "nornir", "job_list", workers=["nornir-worker-1"], kwargs={"task": "task"}
        )["nornir-worker-1"]["result"]
        requests = []

        async def elicit(context, params):
            requests.append(params)
            assert params.message == (
                "service: nornir\ntask: task\nApprove this integration test task?"
            )
            assert params.requestedSchema["required"] == ["approve"]
            return ElicitResult(
                action=action,
                content={"approve": approve} if action == "accept" else None,
            )

        async def run_test():
            async with streamable_http_client(mcp_url) as (read, write, _):
                async with ClientSession(
                    read, write, elicitation_callback=elicit
                ) as session:
                    await session.initialize()
                    response = await session.call_tool(
                        "service_nornir__task_task",
                        arguments={
                            "plugin": "nornir_salt.plugins.tasks.nr_test",
                            "commands": ["mcp-approval-test"],
                            "FL": ["ceos-spine-1"],
                        },
                    )
                    assert not response.isError
                    return json.loads(response.content[0].text)

        result = asyncio.run(run_test())
        assert len(requests) == 1
        after = nfclient.run_job(
            "nornir", "job_list", workers=["nornir-worker-1"], kwargs={"task": "task"}
        )["nornir-worker-1"]["result"]
        if approve:
            assert result["nornir-worker-1"]["failed"] is False
            assert result["nornir-worker-1"]["result"]["ceos-spine-1"] == {
                "nr_test": {"commands": ["mcp-approval-test"]}
            }
            assert len(after) == len(before) + 1
        else:
            assert set(result) == {"fastmcp-worker-1"}
            result = result["fastmcp-worker-1"]
            assert result["service"] == "fastmcp"
            assert result["result"] == {}
            assert result["failed"] is False
            assert len(result["errors"]) == 1
            assert "approval was not granted" in result["errors"][0]
            assert after == before
