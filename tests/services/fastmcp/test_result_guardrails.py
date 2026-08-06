import asyncio
import copy
import re
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import orjson
import pytest
from pydantic import ValidationError

from norfab.models import Result
from norfab.workers.fastmcp_worker.fastmcp_models import TaskMCPResultGuardrail
from norfab.workers.fastmcp_worker.fastmcp_worker import (
    FastMCPWorker,
    apply_task_result_guardrails,
    service_tasks_discovery,
)
from norfab.workers.nornir_worker.cli_task import MCP_RESULT_GUARDRAILS

try:
    from tests.services.fastmcp.common import (
        call_mcp_tool,
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
    from services.fastmcp.common import (
        call_mcp_tool,
        ensure_tool_discovered,
        mcp_url,  # noqa: F401 - imported pytest fixture
    )

pytestmark = pytest.mark.fastmcp


def worker_result(result, diff=None):
    return Result(
        result=result,
        diff=diff,
        juuid="00000000000000000000000000000001",
        task="cli",
        service="nornir",
        status="completed",
        messages=["existing message"],
        errors=["existing error"],
        resources=["router-1"],
    ).model_dump()


def apply(raw_result, guardrails):
    return apply_task_result_guardrails(
        "service_nornir__task_cli",
        "nornir",
        "cli",
        raw_result,
        guardrails,
    )


def discovery_worker(task_mcp, tools=None):
    task = {
        "name": "cli",
        "description": "Run CLI commands",
        "inputSchema": {"type": "object", "properties": {}},
        "outputSchema": {"type": "object"},
        "mcp": task_mcp,
    }
    client = Mock()
    client.mmi.return_value = {"results": [{"service": "nornir"}]}
    client.run_job.return_value = {"worker": {"result": [task]}}
    worker = SimpleNamespace(
        client=client,
        exit_event=threading.Event(),
        fastmcp_inventory={"tools": tools or {}},
        norfab_services_tasks={},
        norfab_services_prompts={},
    )
    return worker, task


@pytest.mark.parametrize(
    "rule",
    [
        {"type": "limit", "limit": 100},
        {"type": "replace", "match": "secret", "replace": "[redacted]"},
        {"type": "regex", "match": ["unsafe"], "message": "Content blocked."},
    ],
)
def test_result_guardrail_model_accepts_supported_rules(rule):
    assert TaskMCPResultGuardrail.model_validate(rule).type == rule["type"]


@pytest.mark.parametrize(
    "rule",
    [
        {"type": "unknown"},
        {"type": "limit", "limit": 0},
        {"type": "replace", "match": "secret"},
        {"type": "regex", "match": []},
        {"type": "regex", "match": "unsafe", "messages": []},
    ],
)
def test_result_guardrail_model_rejects_invalid_rules(rule):
    with pytest.raises(ValidationError):
        TaskMCPResultGuardrail.model_validate(rule)


@pytest.mark.parametrize(
    "rule",
    [
        {"type": "regex", "match": "("},
        {"type": "replace", "match": "(x)", "replace": r"\2"},
    ],
)
def test_result_guardrail_model_compiles_regex(rule):
    with pytest.raises(re.error):
        TaskMCPResultGuardrail.model_validate(rule)


def test_discovery_combines_task_and_matching_inventory_rules(monkeypatch):
    task_mcp = {"result_guardrails": [{"type": "limit", "limit": 100}]}
    worker, task = discovery_worker(
        task_mcp,
        {
            "result_guardrails": [
                {
                    "service": "nor*",
                    "task": "c?i",
                    "type": "replace",
                    "match": "secret",
                    "replace": "[redacted]",
                },
                {
                    "service": "netbox",
                    "task": "*",
                    "type": "limit",
                    "limit": 1,
                },
            ]
        },
    )
    monkeypatch.setattr(
        "norfab.workers.fastmcp_worker.fastmcp_worker.time.sleep", lambda _: None
    )

    service_tasks_discovery(worker, cycles=1)

    tool_data = worker.norfab_services_tasks["nornir"]["service_nornir__task_cli"]
    assert [rule["type"] for rule in tool_data["result_guardrails"]] == [
        "limit",
        "replace",
    ]
    assert "result_guardrails" not in tool_data["tool"].model_dump()
    assert task["mcp"] == task_mcp


def test_discovery_can_disable_task_result_guardrails(monkeypatch):
    worker, _ = discovery_worker(
        {"result_guardrails": [{"type": "limit", "limit": 100}]},
        {
            "disable_builtin_guardrails": True,
            "result_guardrails": [
                {
                    "service": "*",
                    "task": "*",
                    "type": "limit",
                    "limit": 200,
                }
            ],
        },
    )
    monkeypatch.setattr(
        "norfab.workers.fastmcp_worker.fastmcp_worker.time.sleep", lambda _: None
    )

    service_tasks_discovery(worker, cycles=1)

    tool_data = worker.norfab_services_tasks["nornir"]["service_nornir__task_cli"]
    assert tool_data["result_guardrails"] == [{"type": "limit", "limit": 200}]


def test_get_tools_includes_result_guardrails():
    worker = FastMCPWorker.__new__(FastMCPWorker)
    worker.name = "fastmcp-worker"
    worker.norfab_services_tasks = {
        "nornir": {
            "service_nornir__task_cli": {
                "tool": Mock(model_dump=Mock(return_value={"name": "cli"})),
                "result_guardrails": [{"type": "limit", "limit": 100}],
            }
        }
    }

    result = worker.get_tools().result["service_nornir__task_cli"]

    assert result["result_guardrails"] == [{"type": "limit", "limit": 100}]


def test_replace_updates_nested_strings_without_mutating_raw_result():
    raw = {
        "worker": worker_result(
            {"devices": [{"password": "password=FAKE_SECRET", "count": 1}]},
            {"before": "token=FAKE_SECRET"},
        )
    }
    original = copy.deepcopy(raw)
    rule = {
        "type": "replace",
        "match": [r"(password=)\S+", r"(token=)\S+"],
        "replace": r"\1REDACTED",
    }

    delivered = apply(raw, [rule])["worker"]

    assert delivered["result"]["devices"][0]["password"] == "password=REDACTED"
    assert delivered["diff"]["before"] == "token=REDACTED"
    assert delivered["result"]["devices"][0]["count"] == 1
    assert delivered["messages"] == ["existing message"]
    assert raw == original


@pytest.mark.parametrize(
    "result, secret",
    [
        (
            "username admin privilege 15 secret sha512 $6$ARISTA_SECRET",
            "$6$ARISTA_SECRET",
        ),
        ("username admin secret 9 $9$CISCO_IOS_SECRET", "$9$CISCO_IOS_SECRET"),
        (
            "secret 5 $1$abcd$XXXXXXXXXXXXXXXXXXXXXXXXX",
            "$1$abcd$XXXXXXXXXXXXXXXXXXXXXXXXX",
        ),
        ("password 7 030752180500", "030752180500"),
        ("username admin\n secret 10 $6$CISCO_XR_SECRET", "$6$CISCO_XR_SECRET"),
        (
            'set system login user admin authentication encrypted-password "$9$JUNOS_SECRET"',
            "$9$JUNOS_SECRET",
        ),
        (
            "root:$y$j9T$linux-shadow-secret:19800:0:99999:7:::",
            "$y$j9T$linux-shadow-secret",
        ),
        (
            "-----BEGIN PRIVATE KEY-----\nprivate-key-secret\n-----END PRIVATE KEY-----",
            "private-key-secret",
        ),
        ("snmp-server community norfab rw", "norfab"),
        (
            "snmp-server user admin network-admin v3 auth sha auth-secret priv aes 128 priv-secret",
            "auth-secret",
        ),
        (
            "snmp-server user admin network-admin v3 auth sha auth-secret priv aes 128 priv-secret",
            "priv-secret",
        ),
        ("set snmp community junos-secret authorization read-write", "junos-secret"),
        ('set password "fortios-secret"', "fortios-secret"),
        (
            "local-user admin password irreversible-cipher huawei-secret",
            "huawei-secret",
        ),
        (
            "radius-server shared-key cipher huawei-radius-secret",
            "huawei-radius-secret",
        ),
        (
            "hwtacacs-server shared-key cipher huawei-tacacs-secret",
            "huawei-tacacs-secret",
        ),
        (
            "crypto isakmp key 6 cisco-isakmp-secret address 192.0.2.1",
            "cisco-isakmp-secret",
        ),
        ("Authorization: Bearer bearer-secret", "bearer-secret"),
        ("https://admin:url-secret@example.test/api", "url-secret"),
        ("https://example.test/api?access_token=query-secret", "query-secret"),
    ],
)
def test_cli_result_guardrails_redact_platform_secrets(result, secret):
    raw = {"worker": worker_result(result)}

    delivered = apply(raw, MCP_RESULT_GUARDRAILS)["worker"]["result"]

    assert secret not in delivered
    assert "REDACTED" in delivered


def test_cli_result_guardrails_preserve_snmp_access():
    raw = {"worker": worker_result("snmp-server community norfab rw")}

    delivered = apply(raw, MCP_RESULT_GUARDRAILS)["worker"]["result"]

    assert delivered == "snmp-server community REDACTED rw"


def test_regex_replaces_only_the_matching_worker_field():
    raw = {
        "worker-1": worker_result({"text": "FAKE_UNSAFE_INSTRUCTION"}, "safe"),
        "worker-2": worker_result("safe", "FAKE_UNSAFE_INSTRUCTION"),
        "worker-3": worker_result("safe", "safe"),
    }
    rule = {
        "type": "regex",
        "match": "FAKE_UNSAFE_INSTRUCTION",
        "message": "Unsafe content was blocked.",
    }

    delivered = apply(raw, [rule])

    assert delivered["worker-1"]["result"] == "Unsafe content was blocked."
    assert delivered["worker-1"]["diff"] == "safe"
    assert delivered["worker-2"]["result"] == "safe"
    assert delivered["worker-2"]["diff"] == "Unsafe content was blocked."
    assert delivered["worker-3"] == raw["worker-3"]
    assert "FAKE_UNSAFE_INSTRUCTION" not in orjson.dumps(delivered).decode()


def test_limit_reconstructs_base_results():
    raw = {"worker": worker_result("large result", {"old": "value"})}
    size = len(orjson.dumps(raw))

    delivered = apply(
        raw,
        [{"type": "limit", "limit": size - 1, "message": "Result is too large."}],
    )

    assert delivered["result"] == "Result is too large."
    assert delivered["juuid"] == "00000000000000000000000000000001"
    assert delivered["failed"] is False
    assert delivered["diff"] is None
    assert delivered["errors"] == []
    assert delivered["messages"] == []
    assert delivered["task"] is None
    assert delivered["service"] is None


def test_limit_allows_results_at_the_exact_boundary():
    raw = {"worker": worker_result("small")}

    delivered = apply(raw, [{"type": "limit", "limit": len(orjson.dumps(raw))}])

    assert delivered == raw


def test_rules_run_in_authored_order():
    raw = {"worker": worker_result("unsafe")}
    replace = {"type": "replace", "match": "unsafe", "replace": "safe"}
    block = {"type": "regex", "match": "unsafe", "message": "Content blocked."}

    assert apply(raw, [replace, block])["worker"]["result"] == "safe"
    assert apply(raw, [block, replace])["worker"]["result"] == "Content blocked."


def test_limit_runs_in_authored_order():
    raw = {"worker": worker_result("x")}
    raw_size = len(orjson.dumps(raw))
    limit = {"type": "limit", "limit": raw_size, "message": "Result is too large."}
    replace = {"type": "replace", "match": "x", "replace": "a larger replacement"}

    assert apply(raw, [limit, replace])["worker"]["result"] == "a larger replacement"
    assert apply(raw, [replace, limit])["result"] == "Result is too large."


class TestFastMCPResultGuardrailsIntegration:
    tools_discovered = {}

    def test_cli_redacts_secret(self, nfclient, mcp_url):
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
