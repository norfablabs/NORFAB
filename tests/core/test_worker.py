import copy
import os
import pprint
import sys
import threading
import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from norfab.core import NFP
from norfab.core.client import NFPClient
from norfab.core.worker import Task

pytestmark = pytest.mark.core


def make_task_prompt():
    return {
        "name": "collect",
        "title": "Collect",
        "description": "Collect operational data",
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
                "content": {
                    "type": "text",
                    "text": "{{ request }}",
                },
            }
        ],
    }


class TestWorkersListTasks:
    def test_task_validates_mcp_prompts(self):
        prompt = make_task_prompt()

        task = Task(mcp={"prompts": [prompt]})

        assert task.mcp["prompts"] == [prompt]

    @pytest.mark.parametrize(
        "prompts",
        [None, False, {"name": "collect"}, ()],
    )
    def test_task_rejects_invalid_prompts_container(self, prompts):
        with pytest.raises(ValidationError):
            Task(mcp={"prompts": prompts})

    def test_task_rejects_invalid_prompt_templates(self):
        prompt = make_task_prompt()
        prompt["messages"][0]["content"]["text"] = "{{ undeclared }}"

        with pytest.raises(ValidationError, match="undeclared arguments"):
            Task(mcp={"prompts": [prompt]})

        prompt = make_task_prompt()
        prompt["messages"][0]["content"]["text"] = "{{ request | unknown_filter }}"

        with pytest.raises(ValidationError, match="Invalid prompt Jinja2 template"):
            Task(mcp={"prompts": [prompt]})

    def test_task_rejects_duplicate_prompt_and_argument_names(self):
        duplicate_argument_prompt = make_task_prompt()
        duplicate_argument_prompt["arguments"].append(
            copy.deepcopy(duplicate_argument_prompt["arguments"][0])
        )
        with pytest.raises(ValidationError, match="duplicate arguments"):
            Task(mcp={"prompts": [duplicate_argument_prompt]})

        prompt = make_task_prompt()
        with pytest.raises(ValidationError, match="duplicate MCP prompt names"):
            Task(mcp={"prompts": [prompt, copy.deepcopy(prompt)]})

    def test_list_tasks_and_monitoring_stats(self, nfclient):
        ret = nfclient.run_job("nornir", "list_tasks", workers="any")

        pprint.pprint(ret, width=200)
        for worker, res in ret.items():
            assert res["failed"] is False, f"{worker} failed to run the task"
            assert len(res["result"]) > 0, f"{worker} returned no task details"
            for t in res["result"]:
                assert all(
                    k in t
                    for k in [
                        "description",
                        "name",
                        "inputSchema",
                        "outputSchema",
                        "fastapi",
                        "mcp",
                    ]
                )

        ret = nfclient.run_job(
            "all",
            "get_stats",
            workers="all",
            timeout=30,
        )

        assert ret, "No worker statistics returned"
        for worker, response in ret.items():
            assert response["failed"] is False, worker
            stats = response["result"]
            assert stats["role"] == "worker", worker
            assert stats["process"]["cpu_percent"] >= 0, worker
            assert stats["process"]["memory_rss_mbyte"] > 0, worker
            assert (
                stats["process"]["open_file_descriptors"] is None
                or stats["process"]["open_file_descriptors"] >= 0
            ), worker
            assert stats["process"]["uptime_seconds"] >= 0, worker
            assert stats["process"]["threads"] > 0, worker
            assert (
                stats["process"]["tcp_sockets"] is None
                or stats["process"]["tcp_sockets"] >= 0
            ), worker
            assert stats["messaging"]["received"] > 0, worker
            assert "details" not in stats, worker
            if stats["service"] == "nornir":
                assert stats["nornir_hosts"] > 0, worker
                assert stats["dead_connections_cleaned"] >= 0, worker
                assert stats["idle_connections_cleaned"] >= 0, worker

        status_ret = nfclient.run_job(
            "all",
            "get_worker_status",
            workers="all",
            timeout=30,
        )
        assert status_ret, "No worker status returned"
        for worker, response in status_ret.items():
            assert response["failed"] is False, worker
            status = response["result"]
            assert status["role"] == "worker", worker
            assert status["status"] == "active", worker
            assert status["directories"]["base_dir"], worker
            assert "zmq_auth" in status["security"], worker
            assert "worker_private_key_file" in status["security"], worker

    def test_list_tasks_brief(self, nfclient):
        ret = nfclient.run_job(
            "nornir", "list_tasks", workers="any", kwargs={"brief": True}
        )

        pprint.pprint(ret, width=200)
        for worker, res in ret.items():
            assert res["failed"] is False, f"{worker} failed to run the task"
            assert len(res["result"]) > 0, f"{worker} returned no task details"
            for t in res["result"]:
                assert isinstance(t, str)

    def test_list_tasks_name(self, nfclient):
        ret = nfclient.run_job(
            "nornir", "list_tasks", workers="any", kwargs={"name": "get_version"}
        )

        pprint.pprint(ret, width=200)
        for worker, res in ret.items():
            assert res["failed"] is False, f"{worker} failed to run the task"
            assert (
                len(res["result"]) == 1
            ), f"{worker} returned more than 1 task details"
            assert (
                res["result"][0]["name"] == "get_version"
            ), f"{worker} did not return get_version task"

    def test_list_tasks_cli_prompts(self, nfclient):
        ret = nfclient.run_job(
            "nornir", "list_tasks", workers="any", kwargs={"name": "cli"}
        )

        for worker, res in ret.items():
            assert res["failed"] is False, f"{worker} failed to list CLI task"
            prompts = res["result"][0]["mcp"]["prompts"]
            assert [prompt["name"] for prompt in prompts] == [
                "collect_operational_data",
                "troubleshoot",
            ]


class TestWorkersEcho:
    def test_echo_service_nornir_workers_all(self, nfclient):
        ret = nfclient.run_job("nornir", "echo", workers="all")

        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] is False, f"{worker} failed to run the task"
            assert "client_address" in res["result"]
            assert "juuid" in res
            assert "task" in res["result"]
            assert "args" in res["result"]
            assert "kwargs" in res["result"]
            assert "task_started" in res
            assert "task_completed" in res

    def test_echo_service_nornir_workers_any(self, nfclient):
        ret = nfclient.run_job("nornir", "echo", workers="any")

        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] is False, f"{worker} failed to run the task"
            assert "client_address" in res["result"]
            assert "juuid" in res
            assert "task" in res["result"]
            assert "args" in res["result"]
            assert "kwargs" in res["result"]
            assert "task_started" in res
            assert "task_completed" in res

    def test_echo_service_all_workers_all(self, nfclient):
        ret = nfclient.run_job("all", "echo", workers="all")

        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] is False, f"{worker} failed to run the task"
            assert "client_address" in res["result"]
            assert "juuid" in res
            assert "task" in res["result"]
            assert "args" in res["result"]
            assert "kwargs" in res["result"]
            assert "task_started" in res
            assert "task_completed" in res

    def test_echo_service_all_workers_any(self, nfclient):
        ret = nfclient.run_job("all", "echo", workers="any")

        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] is False, f"{worker} failed to run the task"
            assert "client_address" in res["result"]
            assert "juuid" in res
            assert "task" in res["result"]
            assert "args" in res["result"]
            assert "kwargs" in res["result"]
            assert "task_started" in res
            assert "task_completed" in res

    def test_echo_service_all_worker(self, nfclient):
        ret = nfclient.run_job("all", "echo", workers="nornir-worker-1")

        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] is False, f"{worker} failed to run the task"
            assert "client_address" in res["result"]
            assert "juuid" in res
            assert "task" in res["result"]
            assert "args" in res["result"]
            assert "kwargs" in res["result"]
            assert "task_started" in res
            assert "task_completed" in res

    def test_echo_service_all_workers_list(self, nfclient):
        ret = nfclient.run_job(
            "all", "echo", workers=["nornir-worker-1", "nornir-worker-2"]
        )

        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] is False, f"{worker} failed to run the task"
            assert "client_address" in res["result"]
            assert "juuid" in res
            assert "task" in res["result"]
            assert "args" in res["result"]
            assert "kwargs" in res["result"]
            assert "task_started" in res
            assert "task_completed" in res

    def test_echo_raise_error(self, nfclient):
        ret = nfclient.run_job(
            "nornir", "echo", kwargs={"raise_error": "Give me error"}
        )

        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] is True, f"{worker} did not fail to run the task"
            assert "Give me error" in res["errors"][0]

    def test_echo_sleep(self, nfclient):
        start = time.time()
        ret = nfclient.run_job(
            "nornir", "echo", kwargs={"sleep": 5}, workers=["nornir-worker-1"]
        )
        end = time.time()

        duration = end - start

        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] is False, f"{worker} failed to run the task"
            assert "client_address" in res["result"]
            assert "juuid" in res
            assert "task" in res["result"]
            assert "args" in res["result"]
            assert "kwargs" in res["result"]
            assert "task_started" in res
            assert "task_completed" in res
            assert duration > 5, f"{worker} did not sleep for 5 seconds"


class TestWorkersRunShellCommand:
    def test_run_shell_cmd_ping_localhost(self, nfclient):
        command = (
            "ping -n 1 127.0.0.1"
            if sys.platform.startswith("win")
            else "ping -c 1 127.0.0.1"
        )
        ret = nfclient.run_job(
            "nornir",
            "run_shell_cmd",
            workers="nornir-worker-1",
            kwargs={"command": command, "timeout": 10},
            timeout=30,
        )

        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] is False, f"{worker} failed to run shell command"
            assert res["result"]["command"] == command
            assert res["result"]["returncode"] == 0
            assert res["result"]["timed_out"] is False
            assert "127.0.0.1" in res["result"]["stdout"]
            assert res["result"]["stderr"] == ""


class TestWorkerJobsApi:
    def test_job_list(self, nfclient):
        ret = nfclient.run_job("nornir", "job_list")

        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            for res in results["result"]:
                assert "client_address" in res
                assert "uuid" in res
                assert "task" in res
                assert "status" in res
                assert "received_timestamp" in res
                assert "completed_timestamp" in res

    def test_job_list_pending_only(self, nfclient):
        ret = nfclient.run_job(
            "nornir", "job_list", kwargs={"pending": True, "completed": False}
        )

        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            for res in results["result"]:
                assert res["status"] == "PENDING"

    def test_job_list_filter_by_task_name(self, nfclient):
        # run task
        get_inventory_ret = nfclient.run_job("nornir", "get_inventory", kwargs={})
        # query job for the task
        ret = nfclient.run_job("nornir", "job_list", kwargs={"task": "get_inventory"})

        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            for res in results["result"]:
                assert (
                    res["task"] == "get_inventory"
                ), f"{worker} - Job with none 'get_inventory' task returned: {res}"

    def test_job_list_last_1(self, nfclient):
        ret = nfclient.run_job("nornir", "job_list", kwargs={"last": 2})

        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            assert (
                len(results["result"]) == 2
            ), f"{worker} - Expected 2 results, got {len(results['result'])}"

    def test_job_details(self, nfclient):
        # run cli task with events
        cli_result = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-1"],
            kwargs={"commands": "show clock", "FC": "spine", "progress": True},
        )
        print(">>> cli_result:")
        pprint.pprint(cli_result)

        # grab job uuid for last CLI task
        job_summary = nfclient.run_job(
            "nornir",
            "job_list",
            workers=["nornir-worker-1"],
            kwargs={"last": 1, "completed": True, "pending": False, "task": "cli"},
        )
        print(">>> job_summary:")
        pprint.pprint(job_summary)
        for worker, results in job_summary.items():
            job_id = results["result"][0]["uuid"]

        # retrieve job details - job data, job result
        ret = nfclient.run_job(
            "nornir",
            "job_details",
            workers=["nornir-worker-1"],
            kwargs={"uuid": job_id},
        )
        print(">>> job_details:")
        pprint.pprint(ret, width=150)
        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            assert "client_address" in results["result"]
            assert "uuid" in results["result"]
            assert "status" in results["result"]
            assert "received_timestamp" in results["result"]
            assert "completed_timestamp" in results["result"]
            assert "result_data" in results["result"]
            assert results["result"]["result_data"]
            assert "args" in results["result"]
            assert "task" in results["result"]
            assert "kwargs" in results["result"]
            assert "job_events" in results["result"]
            assert len(results["result"]["job_events"]) > 0

    def test_job_details_no_events_result_data(self, nfclient):
        # run cli task with events
        cli_result = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-1"],
            kwargs={"commands": "show clock", "FC": "spine", "progress": True},
        )
        print(">>> cli_result:")
        pprint.pprint(cli_result)

        # grab job uuid for last CLI task
        job_summary = nfclient.run_job(
            "nornir",
            "job_list",
            workers=["nornir-worker-1"],
            kwargs={"last": 1, "completed": True, "pending": False, "task": "cli"},
        )
        print(">>> job_summary:")
        pprint.pprint(job_summary)
        for worker, results in job_summary.items():
            job_id = results["result"][0]["uuid"]

        # retrieve job details - job data, job result
        ret = nfclient.run_job(
            "nornir",
            "job_details",
            workers=["nornir-worker-1"],
            kwargs={"uuid": job_id, "events": False, "result": False},
        )
        print(">>> job_details:")
        pprint.pprint(ret, width=150)
        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            assert results["result"]["result_data"] == None
            assert results["result"]["job_events"] == []


class TestWorkerMessaging:
    def test_worker_sends_burst_results_and_events(self, nfclient: NFPClient) -> None:
        futures = [
            nfclient.submit_job("DummyService", "event_task", workers="dummy-worker-1")
            for _ in range(110)
        ]
        for future in futures:
            result = future.result(timeout=30)["dummy-worker-1"]
            assert not result["failed"], result
            events = list(future.events(timeout=1))
            assert any(event["message"] == "dummy progress event" for event in events)
            assert any(event["event_type"] == "result_ready" for event in events)

    def test_worker_heartbeats_continue_while_idle(self, nfclient: NFPClient) -> None:
        worker = "dummy-worker-1"
        before = nfclient.run_job("DummyService", "get_stats", workers=worker)[worker][
            "result"
        ]
        result = nfclient.run_job(
            "DummyService", "echo", workers=worker, kwargs={"sleep": 6}
        )[worker]
        assert not result["failed"], result
        after = nfclient.run_job("DummyService", "get_stats", workers=worker)[worker][
            "result"
        ]
        assert after["keepalives_sent"] > before["keepalives_sent"]
        assert after["keepalives_received"] > before["keepalives_received"]
        assert after["reconnects"] == before["reconnects"]


class TestWorkerFileTransfer:
    def test_job_pulls_relative_file_and_worker_pulls_from_worker(
        self, transfer_client: tuple[NFPClient, Path], tmp_path: Path
    ) -> None:
        client, _ = transfer_client
        source = tmp_path / "relative.txt"
        source.write_text("receiver requests this file", encoding="utf-8")
        url = "file://" + os.path.relpath(source).replace(os.sep, "/")
        result = client.run_job(
            "workflow",
            "receive_file",
            workers=["transfer-a"],
            kwargs={"url": url, "chunk_size": 7},
            timeout=20,
        )
        assert not result["transfer-a"]["failed"], result
        remote = result["transfer-a"]["result"]
        result = client.run_job(
            "workflow",
            "receive_file",
            workers=["transfer-b"],
            kwargs={"url": remote, "source_worker": "transfer-a", "chunk_size": 5},
            timeout=20,
        )
        assert not result["transfer-b"]["failed"], result
        target = client.fetch_file(result["transfer-b"]["result"], worker="transfer-b")[
            "content"
        ]
        assert Path(target).read_bytes() == source.read_bytes()

    def test_one_job_can_upload_to_multiple_workers(
        self, transfer_client: tuple[NFPClient, Path], tmp_path: Path
    ) -> None:
        client, _ = transfer_client
        source = tmp_path / "fanout.bin"
        source.write_bytes(bytes(range(128)))
        replies = client.run_job(
            "workflow",
            "receive_file",
            workers=["transfer-a", "transfer-b"],
            kwargs={"url": source.as_uri(), "chunk_size": 11},
            timeout=10,
        )
        assert set(replies) == {"transfer-a", "transfer-b"}
        for reply in replies.values():
            assert not reply["failed"], reply
            assert Path(reply["result"]).read_bytes() == source.read_bytes()

    def test_local_url_is_not_fetched_until_requested(
        self, transfer_client: tuple[NFPClient, Path]
    ) -> None:
        client, _ = transfer_client
        result = client.run_job(
            "workflow",
            "echo",
            workers=["transfer-a"],
            kwargs={"file": "file://does-not-exist"},
            timeout=10,
        )
        assert not result["transfer-a"]["failed"], result

    def test_upload_uses_job_uuid_and_keeps_socket_and_input_separate(
        self,
        transfer_client: tuple[NFPClient, Path],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        client, _ = transfer_client
        source = tmp_path / "slow-input.bin"
        source.write_bytes(b"binary input" * 10)
        reading, release = threading.Event(), threading.Event()
        from norfab.core import client as client_module

        original_open, original_send = open, client.send_to_broker
        stream_ids = []

        def slow_open(path: str, mode: str, *args: object, **kwargs: object) -> object:
            if str(path) == str(source) and mode == "rb":
                reading.set()
                assert release.wait(5)
            return original_open(path, mode, *args, **kwargs)

        def capture_send(
            command: bytes, service: bytes, workers: bytes, uuid: bytes, request: bytes
        ) -> None:
            if command == NFP.STREAM:
                stream_ids.append(uuid)
            original_send(command, service, workers, uuid, request)

        monkeypatch.setattr(client_module, "open", slow_open, raising=False)
        monkeypatch.setattr(client, "send_to_broker", capture_send)
        future = client.submit_job(
            "workflow",
            "receive_file",
            workers=["transfer-a"],
            kwargs={"url": source.as_uri(), "chunk_size": 17},
            timeout=10,
        )
        try:
            assert reading.wait(5)
            # An ordinary input message must not be mistaken for file bytes.
            future.send_response("independent-input", "text", worker="transfer-a")
            # MMI reception must work while the dispatcher is blocked on disk.
            assert (
                client.mmi("mmi.service.broker", "show_workers", timeout=2)["status"]
                == "200"
            )
        finally:
            release.set()
        result = future.result(timeout=10)["transfer-a"]
        assert not result["failed"], result
        assert set(stream_ids) == {future.uuid.encode()}
        assert Path(result["result"]).read_bytes() == source.read_bytes()

    def test_upload_rejects_corruption(
        self,
        transfer_client: tuple[NFPClient, Path],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        client, _ = transfer_client
        source = tmp_path / "corrupt-upload.bin"
        source.write_bytes(b"original data" * 10)
        original = client.send_to_broker

        def corrupt(
            command: bytes, service: bytes, workers: bytes, uuid: bytes, payload: bytes
        ) -> None:
            if command == NFP.STREAM and payload:
                payload = bytes([payload[0] ^ 1]) + payload[1:]
            original(command, service, workers, uuid, payload)

        monkeypatch.setattr(client, "send_to_broker", corrupt)
        reply = client.upload_file(source.as_uri(), "transfer-a", chunk_size=19)
        assert reply["transfer-a"]["failed"], reply
        assert "MD5 hash mismatch" in str(reply["transfer-a"]["errors"])

    def test_native_serving_rejects_unsafe_published_paths(
        self, transfer_client: tuple[NFPClient, Path]
    ) -> None:
        client, _ = transfer_client
        for worker, path in [
            ("filesharing-worker-1", "nf://../outside.txt"),
            ("transfer-a", "nf://published.txt"),
        ]:
            reply = client.run_job(
                "all", "serve_file", workers=[worker], kwargs={"path": path}, timeout=2
            )
            assert reply[worker]["failed"], reply

    def test_native_directory_tasks(
        self, transfer_client: tuple[NFPClient, Path], tmp_path: Path
    ) -> None:
        client, _ = transfer_client
        (tmp_path / "visible.txt").write_text("content", encoding="utf-8")
        (tmp_path / ".hidden").write_text("hidden", encoding="utf-8")
        (tmp_path / "nested").mkdir()
        (tmp_path / "nested" / "child.txt").write_text("child", encoding="utf-8")
        listed = client.run_job(
            "all",
            "list_files",
            workers=["transfer-a"],
            kwargs={"url": tmp_path.as_uri()},
        )["transfer-a"]
        assert not listed["failed"], listed
        assert set(listed["result"]) == {"visible.txt", ".hidden", "nested"}
        walked = client.run_job(
            "all", "walk", workers=["transfer-a"], kwargs={"url": str(tmp_path)}
        )["transfer-a"]
        assert not walked["failed"], walked
        assert set(walked["result"]) == {
            str(tmp_path / "visible.txt"),
            str(tmp_path / "nested" / "child.txt"),
        }
        fetched = client.fetch_file(walked["result"], worker="transfer-a", read=True)
        assert {entry["content"] for entry in fetched} == {"content", "child"}
        for task in ("list_files", "walk"):
            for url in ("nf://", str(tmp_path / "missing")):
                reply = client.run_job(
                    "all", task, workers=["transfer-a"], kwargs={"url": url}
                )["transfer-a"]
                assert reply["failed"], reply
