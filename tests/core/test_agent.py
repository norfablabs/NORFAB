import asyncio
import copy
import json
import socket
import sqlite3
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import Callable
from unittest.mock import Mock, patch

import pytest
import yaml
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from picle import App
from picle.chat import ChatSession

from norfab.clients.nfcli_shell.client_agent.client_agent_picle_shell import (
    AgentProgressPrinter,
    ChatShellCommands,
    current_agent,
)
from norfab.clients.nfcli_shell.nfcli_shell_client import NorFabShell
from norfab.core.agent import AgentProgress, NFAgent
from norfab.core.client import NFPClient
from norfab.core.nfapi import NorFab
from norfab.workers.agent_worker.agent_worker import AgentWorker

pytestmark = pytest.mark.clientagent


def test_chat_progress_from_callback_thread() -> None:
    async def run() -> None:
        chat = ChatSession()
        chat._loop = asyncio.get_running_loop()
        callback = AgentProgress(AgentProgressPrinter(chat))
        await asyncio.to_thread(callback.on_chat_model_start, {}, [])
        await asyncio.to_thread(callback.on_tool_start, {"name": "inspect"}, "")
        await asyncio.to_thread(callback.on_tool_error, RuntimeError("unavailable"))
        assert [chat._events.get_nowait() for _ in range(5)] == [
            ("status", "thinking...", True),
            ("status", "", False),
            ("write", "calling inspect"),
            ("status", "", False),
            ("write", "tool failed: unavailable"),
        ]

    asyncio.run(run())


def test_agent_reports_tool_errors() -> None:
    client = SimpleNamespace(
        run_job=Mock(side_effect=RuntimeError("device unavailable"))
    )
    event = Mock()
    model = FakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "inspect", "args": {}, "id": "inspect"}],
            )
        ]
    )
    with (
        patch("norfab.core.agent._make_llm", return_value=model),
        patch.object(FakeMessagesListChatModel, "bind_tools", return_value=model),
    ):
        agent = NFAgent(
            client,
            {
                "tools": {
                    "norfab_services": False,
                    "inspect": {
                        "description": "Inspect a device",
                        "norfab": {"service": "dummy", "task": "inspect"},
                    },
                }
            },
        )
        with pytest.raises(RuntimeError, match="device unavailable"):
            agent.invoke("check device", callbacks=[AgentProgress(event)])
    event.assert_any_call("thinking...", severity="INFO")
    event.assert_any_call("calling inspect", severity="INFO")
    event.assert_any_call("tool failed: device unavailable", severity="ERROR")
    assert not any("completed" in call.args[0] for call in event.call_args_list)


@pytest.mark.parametrize("entry", ["client", "worker"])
@pytest.mark.parametrize("custom", [False, True])
def test_shared_agent_calls_native_task(
    entry: str, custom: bool, tmp_path: Path
) -> None:
    definition = {
        "llm": {"provider": "ollama", "model": "test"},
        "system_prompt": "Use the tool and report the result.",
        "tools": {"norfab_services": not custom},
    }
    schema = {
        "type": "object",
        "properties": {"target": {"type": "string"}},
        "required": ["target"],
    }
    if custom:
        definition["tools"]["inspect"] = {
            "description": "Inspect a target",
            "input_schema": schema,
            "norfab": {
                "service": "dummy",
                "task": "inspect",
                "kwargs": {"job_data": {"fixed": "kept"}},
                "job_data": ["target"],
            },
        }
    original = copy.deepcopy(definition)
    client = NFPClient.__new__(NFPClient)
    client.agents = {}
    client.inventory = SimpleNamespace(
        client={"agent_profiles": {"default": definition}}, base_dir=str(tmp_path)
    )
    client.mmi = Mock(return_value={"status": "200", "results": [{"service": "dummy"}]})
    tasks = [
        {"name": "inspect", "description": "Inspect", "inputSchema": schema},
        {"name": "hidden", "agent": False},
        {"name": "disabled", "agent": {"enabled": False}},
    ]
    client.run_job = Mock(
        side_effect=([{"worker": {"result": tasks}}] if not custom else [])
        + [{"worker": {"result": "healthy"}}]
        + ([{"worker": {"result": tasks}}] if entry == "worker" and not custom else [])
        + [{"worker": {"result": "healthy"}}]
    )
    tool_name = "inspect" if custom else "service_dummy__task_inspect"
    model = FakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {"name": tool_name, "args": {"target": "r1"}, "id": "call-1"}
                ],
            ),
            AIMessage(content="healthy"),
            AIMessage(
                content="",
                tool_calls=[
                    {"name": tool_name, "args": {"target": "r1"}, "id": "call-2"}
                ],
            ),
            AIMessage(content="healthy"),
        ]
    )
    job = Mock()
    worker = AgentWorker.__new__(AgentWorker)
    worker.name = "test-agent"
    worker.client = client
    worker.agent_inventory = {"default_llm": definition["llm"]}
    worker.fetch_file = Mock(return_value=yaml.safe_dump(definition))
    with (
        patch("norfab.core.agent._make_llm", return_value=model),
        patch.object(FakeMessagesListChatModel, "bind_tools", return_value=model),
    ):
        if entry == "client":
            agent = client.get_agent()
            assert client.get_agent() is agent
            assert agent.invoke("inspect r1") == "healthy"
            payload = agent.invoke("inspect r1 again", verbose_result=True)
            assert len(agent.list_tools()) == 1
            assert len([m for m in payload["messages"] if m.type == "human"]) == 2
            agent.reset()
            assert not agent._agent.get_state(agent._run_config(None)).values
        else:
            name = "nf://agent.yaml" if custom else "NorFab"
            payload = worker.invoke(
                job=job, instructions="inspect r1", name=name, verbose_result=True
            ).result
            assert job.event.call_count >= 4
            messages = [call.args[0] for call in job.event.call_args_list]
            assert messages == [
                f"getting {name} agent ready",
                "thinking...",
                f"calling {tool_name}",
                f"tool {tool_name} completed",
                "thinking...",
            ]
            other_job = Mock()
            event_count = job.event.call_count
            payload = worker.invoke(
                job=other_job, instructions="inspect r1", name=name, verbose_result=True
            ).result
            assert len([m for m in payload["messages"] if m.type == "human"]) == 1
            assert job.event.call_count == event_count
            assert other_job.event.call_count >= 4
    assert payload["messages"][-1].content == "healthy"
    assert any(
        isinstance(message, ToolMessage) and "healthy" in message.content
        for message in payload["messages"]
    )
    expected = (
        {"job_data": {"fixed": "kept", "target": "r1"}} if custom else {"target": "r1"}
    )
    assert client.run_job.call_args.kwargs == {
        "service": "dummy",
        "task": "inspect",
        "kwargs": expected,
    }
    assert definition == original
    assert schema["type"] == "object"


@pytest.mark.parametrize("custom", [False, True])
def test_agent_executes_local_worker_task(custom: bool, tmp_path: Path) -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    config = {"llm": {"provider": "ollama", "model": "test"}}
    if custom:
        config["tools"] = {
            "norfab_services": False,
            "echo": {
                "description": "Echo task arguments",
                "norfab": {
                    "service": "filesharing",
                    "task": "echo",
                    "kwargs": {"sleep": 0},
                },
            },
        }
    model = FakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "echo" if custom else "service_filesharing__task_echo",
                        "args": {} if custom else {"sleep": 0},
                        "id": "status-call",
                    }
                ],
            ),
            AIMessage(content="worker is healthy"),
        ]
    )
    nf = NorFab(
        inventory_data={
            "broker": {"endpoint": f"tcp://127.0.0.1:{port}", "zmq_auth": False},
            "client": {"agent_profiles": {"default": config}},
            "topology": {"broker": True, "workers": []},
        },
        base_dir=str(tmp_path),
    )
    try:
        nf.start()
        client = nf.make_client()
        with (
            patch("norfab.core.agent._make_llm", return_value=model),
            patch.object(FakeMessagesListChatModel, "bind_tools", return_value=model),
            patch.object(client, "run_job", wraps=client.run_job) as dispatch,
        ):
            payload = client.get_agent().invoke(
                "check worker status", verbose_result=True
            )
        results = [m for m in payload["messages"] if isinstance(m, ToolMessage)]
        assert len(results) == 1
        response = json.loads(results[0].content)["filesharing-worker-1"]
        assert not response["failed"], response["errors"]
        assert '"task": "echo"' in results[0].content
        assert dispatch.call_args.kwargs["kwargs"] == {"sleep": 0}
        assert payload["messages"][-1].content == "worker is healthy"
    finally:
        nf.destroy()


def test_agent_preserves_explicit_null_and_schema_title() -> None:
    schema = {
        "title": "InspectionArguments",
        "type": "object",
        "properties": {
            "target": {"type": ["string", "null"]},
            "label": {"type": "string", "default": "task default"},
            "service": {"type": "string"},
        },
        "required": ["target"],
    }
    config = {
        "tools": {
            "norfab_services": False,
            "inspect": {
                "description": "Inspect a target",
                "input_schema": schema,
                "norfab": {"service": "dummy", "task": "inspect"},
            },
        }
    }
    original = copy.deepcopy(config)
    client = Mock()
    client.run_job.return_value = {"worker": {"result": "done"}}
    model = FakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "inspect",
                        "args": {"target": None, "service": "nornir"},
                        "id": "null",
                    }
                ],
            ),
            AIMessage(content="done"),
        ]
    )
    with (
        patch("norfab.core.agent._make_llm", return_value=model),
        patch.object(FakeMessagesListChatModel, "bind_tools", return_value=model),
    ):
        agent = NFAgent(client, config)
        assert convert_to_openai_tool(agent.tools[0])["function"]["parameters"] == {
            key: value for key, value in schema.items() if key != "title"
        }
        assert agent.invoke("inspect the default target") == "done"
    client.run_job.assert_called_once_with(
        service="dummy", task="inspect", kwargs={"target": None, "service": "nornir"}
    )
    assert config == original


def test_missing_profile_file_does_not_run_default_agent(tmp_path: Path) -> None:
    client = NFPClient.__new__(NFPClient)
    client.agents = {}
    client.inventory = SimpleNamespace(
        client={
            "agent_profiles": {
                "default": {"tools": {"norfab_services": False}},
                "focused": {"from_yaml_file": str(tmp_path / "missing.yaml")},
            }
        }
    )
    model = FakeMessagesListChatModel(responses=[AIMessage(content="default")])
    with patch("norfab.core.agent._make_llm", return_value=model):
        with pytest.raises(FileNotFoundError):
            client.get_agent("focused")
    assert not client.agents


def test_agent_returns_text_from_model_content_blocks() -> None:
    model = FakeMessagesListChatModel(
        responses=[AIMessage(content=[{"type": "text", "text": "healthy"}])]
    )
    with patch("norfab.core.agent._make_llm", return_value=model):
        agent = NFAgent(Mock(), {"tools": {"norfab_services": False}})
        assert agent.invoke("check status") == "healthy"
        agent.reset()
        assert "".join(agent.stream("check status")) == "healthy"


def test_client_agent_conversations_survive_restart(tmp_path: Path) -> None:
    inventory = {
        "broker": {"endpoint": "tcp://127.0.0.1:59999", "zmq_auth": False},
        "client": {
            "agent_profiles": {
                "default": {
                    "tools": {"norfab_services": False},
                    "memory": {"enabled": True, "backend": "sqlite"},
                },
                "other": {},
            }
        },
    }
    for restart in (False, True):
        nf = NorFab(
            inventory_data=inventory,
            base_dir=str(tmp_path),
            run_broker=False,
            run_workers=False,
        )
        nf.make_client(name="saved-chat")
        model = FakeMessagesListChatModel(responses=[AIMessage(content="noted")])
        try:
            with patch("norfab.core.agent._make_llm", return_value=model):
                agent = nf.client.get_agent()
                if not restart:
                    agent.invoke("r1 is the branch router", thread_id="old-name")
                    agent.resume("old-name")
                    agent.rename("branch-a")
                    with pytest.raises(ValueError, match="not found"):
                        agent.resume("old-name")
                    agent.invoke("r2 is unrelated", thread_id="branch-b")
                    with pytest.raises(ValueError, match="already exists"):
                        agent.rename("branch-b")
                    with pytest.raises(ValueError, match="cannot be empty"):
                        agent.rename(" ")
                else:
                    conversations = agent.list_conversations()
                    assert {row["thread_id"] for row in conversations} == {
                        "branch-a",
                        "branch-b",
                    }
                    assert conversations[0]["title"] == "r2 is unrelated"
                    agent.resume("branch-a")
                    with pytest.raises(ValueError, match="not found"):
                        agent.resume("unknown")
                    assert agent.thread_id == "branch-a"
                    payload = agent.invoke("which router?", verbose_result=True)
                    assert [
                        m.text for m in payload["messages"] if m.type == "human"
                    ] == ["r1 is the branch router", "which router?"]
                    assert nf.client.get_agent("other").list_conversations() == []
                connection = agent._memory_connection
        finally:
            nf.destroy()
        with pytest.raises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")


@pytest.mark.parametrize("exit_signal", ["/exit", EOFError])
def test_chat_resume_before_first_message_uses_selected_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    exit_signal: str | type[Exception],
) -> None:
    nf = NorFab(
        inventory_data={
            "broker": {"endpoint": "tcp://127.0.0.1:59999", "zmq_auth": False},
            "client": {
                "agent_profiles": {
                    "default": {"tools": {"norfab_services": False}},
                    "focused": {},
                }
            },
        },
        base_dir=str(tmp_path),
        run_broker=False,
        run_workers=False,
    )
    nf.make_client(name="chat-shell")
    monkeypatch.setattr("builtins.NFCLIENT", nf.client, raising=False)
    token = current_agent.set(None)
    model = FakeMessagesListChatModel(
        responses=[AIMessage(content="saved"), AIMessage(content="continued")]
    )
    output = StringIO()
    try:
        with patch("norfab.core.agent._make_llm", return_value=model):
            agent = nf.client.get_agent("focused")
            agent.invoke("remember branch-a", thread_id="branch-a")
            shell = App(NorFabShell, stdout=output)
            previous_shell = shell.shell

            def resume_chat(
                run_function: Callable, kw: dict, picle_config: object
            ) -> None:
                shell.onecmd("resume")
                assert ChatShellCommands.source_resume() == ["branch-a"]
                shell.onecmd("resume branch-a")
                assert (
                    run_function("follow up", chat=Mock(spec=ChatSession), **kw)
                    == "continued"
                )
                if exit_signal == "/exit":
                    shell.do_exit("")

            with patch.object(shell._chat_shell, "run", side_effect=resume_chat):
                shell.onecmd("client-agent chat agent-name focused thread-id different")
            messages = agent._agent.get_state(agent._run_config("branch-a")).values[
                "messages"
            ]
            assert [m.text for m in messages if m.type == "human"] == [
                "remember branch-a",
                "follow up",
            ]
            assert nf.client.get_agent().list_conversations() == []
            if exit_signal is EOFError:
                shell.onecmd("exit")

            def empty_chat(
                run_function: Callable, kw: dict, picle_config: object
            ) -> None:
                shell.onecmd("resume")
                shell.onecmd("resume missing")
                shell.do_exit("")

            with patch.object(shell._chat_shell, "run", side_effect=empty_chat):
                shell.onecmd("client-agent chat")
        captured = output.getvalue() + capsys.readouterr().out
        assert "branch-a" in captured
        assert "remember branch-a" in captured
        assert "resumed conversation" in captured.lower()
        assert "No saved conversations" in captured
        assert "not found" in captured
        assert current_agent.get() is None
        assert shell.shell is previous_shell
    finally:
        current_agent.reset(token)
        nf.destroy()


@pytest.mark.parametrize("progress", [True, False])
def test_client_chat_reports_model_and_tool_progress(
    progress: bool, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    client = NFPClient.__new__(NFPClient)
    client.agents = {}
    client.inventory = SimpleNamespace(
        client={
            "agent_profiles": {
                "default": {
                    "tools": {
                        "norfab_services": False,
                        "inspect": {
                            "description": "Inspect a device",
                            "norfab": {"service": "dummy", "task": "inspect"},
                        },
                    },
                }
            }
        }
    )
    client.run_job = Mock(return_value={"worker": {"result": "healthy"}})
    monkeypatch.setattr("builtins.NFCLIENT", client, raising=False)
    model = FakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "inspect", "args": {}, "id": "inspect"}],
            ),
            AIMessage(content="healthy"),
        ]
    )
    output = StringIO()
    token = current_agent.set(None)
    try:
        with (
            patch("norfab.core.agent._make_llm", return_value=model),
            patch.object(FakeMessagesListChatModel, "bind_tools", return_value=model),
        ):
            agent = client.get_agent()
            shell = App(NorFabShell, stdout=output)
            chat = Mock(spec=ChatSession)

            def progress_chat(
                run_function: Callable, kw: dict, picle_config: object
            ) -> None:
                assert run_function("check device", chat=chat, **kw) == "healthy"
                shell.onecmd("rename branch-a")
                assert run_function("follow up", chat=chat, **kw) == "healthy"
                shell.do_exit("")

            with patch.object(shell._chat_shell, "run", side_effect=progress_chat):
                shell.onecmd(
                    "client-agent chat" + ("" if progress else " progress false")
                )
            captured = output.getvalue() + capsys.readouterr().out
            assert "renamed conversation to branch-a" in captured
            assert agent.thread_id == "branch-a"
            completion_token = current_agent.set(agent)
            try:
                assert ChatShellCommands.source_resume() == ["branch-a"]
            finally:
                current_agent.reset(completion_token)
            assert [row["thread_id"] for row in agent.list_conversations()] == [
                "branch-a"
            ]
            chat.set_footer.assert_called_with("profile: default | thread: branch-a")
            if progress:
                chat.set_status.assert_any_call("thinking...", spinner=True)
                chat.write.assert_any_call("calling inspect")
                chat.write.assert_any_call("tool inspect completed")
            else:
                chat.set_status.assert_not_called()
                chat.write.assert_not_called()
            agent.reset()
            assert agent.invoke("check device again") == "healthy"
            assert capsys.readouterr().out == ""
    finally:
        current_agent.reset(token)
