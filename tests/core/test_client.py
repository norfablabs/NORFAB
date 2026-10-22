import pprint
import queue
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import pytest

from norfab.core import NFP
from norfab.core.client import (
    ClientJobDatabase,
    JobStatus,
    NFPClient,
    NFPJobFuture,
    handle_event,
    handle_response,
    poll_active_jobs,
)
from norfab.core.monitoring import ProcessMonitor
from norfab.core.nfapi import NorFab

pytestmark = pytest.mark.core


class TestDedicatedNfApiClient:
    def test_standalone_client(self, nfclient: NFPClient, tmp_path: Path) -> None:
        inventory_data = {"broker": dict(nfclient.inventory.broker)}
        client_name = f"test_dedicated_client_{uuid4().hex}"
        nf = NorFab(
            inventory_data=inventory_data,
            base_dir=str(tmp_path),
            run_broker=False,
            run_workers=False,
        )
        client = None

        try:
            client = nf.make_client(name=client_name)

            ret = client.run_job(
                "nornir",
                "echo",
                workers="nornir-worker-1",
                kwargs={"source": "dedicated nfapi client"},
                timeout=30,
            )

            pprint.pprint(ret)
            assert client is not nfclient
            assert client.name == client_name
            assert "nornir-worker-1" in ret

            result = ret["nornir-worker-1"]
            assert result["failed"] is False
            assert result["result"]["client_address"] == client_name
            assert result["result"]["task"] == "echo"
            assert result["result"]["kwargs"] == {"source": "dedicated nfapi client"}
        finally:
            if client is not None:
                client.destroy()
                nf.client = None
                client = None


class TestRemoteBrokerClient:
    def test_list_workers_mmi_remote_broker(self, tmp_path: Path) -> None:
        inventory_data = {
            "broker": {
                "endpoint": "tcp://192.168.1.220:5555",
                "shared_key": "!P#yCKn52*Wz#pJuXh!CVdNin^L*&=>IY#/f/DNr",
                "zmq_auth": True,
            }
        }
        endpoint = inventory_data["broker"]["endpoint"]
        broker_address = urlsplit(endpoint)
        try:
            with socket.create_connection(
                (broker_address.hostname, broker_address.port), timeout=5
            ):
                pass
        except OSError as exc:
            pytest.skip(f"remote broker TCP connection to {endpoint} failed: {exc}")

        client_name = f"test_remote_broker_client_{uuid4().hex}"
        nf = NorFab(
            inventory_data=inventory_data,
            base_dir=str(tmp_path),
            run_broker=False,
            run_workers=False,
        )
        client = None

        try:
            client = nf.make_client(name=client_name)
            reply = client.mmi("mmi.service.broker", "show_workers", timeout=30)

            pprint.pprint(reply)
            assert client.name == client_name
            assert reply["status"] == "200"
            assert reply["errors"] == []
            assert reply["results"], "No workers status returned"
            for worker in reply["results"]:
                assert all(
                    k in worker for k in ["holdtime", "name", "service", "status"]
                )
        finally:
            if client is not None:
                client.destroy()
                nf.client = None
                client = None


class TestClientApi:
    def test_mmi_show_workers(self, nfclient):
        reply = nfclient.mmi(b"mmi.service.broker", "show_workers")

        ret = reply["results"]
        pprint.pprint(ret)

        assert ret, "No workers status returned"
        for worker in ret:
            assert all(k in worker for k in ["holdtime", "name", "service", "status"])

    def test_mmi_show_workers_nornir(self, nfclient):
        reply = nfclient.mmi(
            b"mmi.service.broker", "show_workers", kwargs={"service": "nornir"}
        )

        ret = reply["results"]
        pprint.pprint(ret)

        assert ret, "No workers status returned"
        for worker in ret:
            assert all(k in worker for k in ["holdtime", "name", "service", "status"])

    def test_mmi_get_broker_stats(self, nfclient):
        reply = nfclient.mmi("mmi.service.broker", "get_stats")

        ret = reply["results"]
        pprint.pprint(ret)

        for k in [
            "endpoint",
            "keepalive_interval_ms",
            "service_count",
            "status",
            "worker_count",
            "process",
            "messaging",
        ]:
            assert k in ret, "Not all broker params returned"
            assert ret[k], "Some broker params seems wrong"

        client_stats = nfclient.get_stats()
        assert isinstance(client_stats, dict)
        assert client_stats["role"] == "client"
        assert client_stats["process"]["memory_rss_mbyte"] > 0
        assert client_stats["process"]["threads"] > 0
        assert (
            client_stats["process"]["tcp_sockets"] is None
            or client_stats["process"]["tcp_sockets"] >= 0
        )
        assert (
            client_stats["process"]["open_file_descriptors"] is None
            or client_stats["process"]["open_file_descriptors"] >= 0
        )
        assert client_stats["messaging"]["sent"] > 0
        assert client_stats["messaging"]["received"] > 0
        assert client_stats["reconnects"] > 0

        client_status = nfclient.get_status()
        assert client_status["role"] == "client"
        assert client_status["status"] == "active"
        assert client_status["directories"]["base_dir"]
        assert client_status["security"]["zmq_auth"] is False
        assert client_status["security"]["client_private_key_file"] is None

    def test_mmi_show_broker_version(self, nfclient):
        reply = nfclient.mmi("mmi.service.broker", "show_broker_version")

        ret = reply["results"]
        pprint.pprint(ret)

        for k in [
            "norfab",
            "python",
            "platform",
        ]:
            assert k in ret, "Not all broker params returned"
            assert ret[k], "Some broker params seems wrong"

    def test_mmi_show_broker_inventory(self, nfclient):
        reply = nfclient.mmi("mmi.service.broker", "show_broker_inventory")

        ret = reply["results"]
        pprint.pprint(ret)

        for k in ["broker", "logging", "workers", "topology"]:
            assert k in ret, "Not all broker params returned"
            assert ret[k], "Some broker params seems wrong"

    def test_mmi_sid_inventory(self, nfclient):
        reply = nfclient.mmi(
            "sid.service.broker", "get_inventory", kwargs={"name": "nornir-worker-1"}
        )

        ret = reply["results"]
        pprint.pprint(ret)

        assert ret, "nornir-worker-1 inventory not returned"
        for k in ["defaults", "groups", "hosts", "service"]:
            assert k in ret, "Not all worker params returned"
            assert ret[k], "Some worker inventory params seems wrong"


class TestClientRunJob:
    def collect_events_until(self, future, event_type, timeout=15):
        events = []
        matched_event = None
        deadline = time.time() + timeout
        while time.time() < deadline and matched_event is None:
            for event in future.events(timeout=1):
                events.append(event)
                if event.get("event_type") == event_type:
                    matched_event = event
                    break

        return events, matched_event

    def test_generic_markdown_output(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "get_inventory",
            markdown=True,
        )
        print(ret)
        assert "Overall Summary" in ret
        assert "Worker:" in ret
        assert "Results" in ret

    def test_future_input_request_response(self, nfclient):
        future = nfclient.submit_job(
            "DummyService",
            "input_request_task",
            workers="dummy-worker-1",
            timeout=30,
        )

        events, input_event = self.collect_events_until(future, "input_request")

        assert input_event is not None
        input_request = input_event["extras"]["input_request"]

        assert input_request["question"] == "approve dummy task?"
        assert input_request["default"] == "no"
        assert input_request["metadata"] == {"task": "input_request_task"}

        future.send_response(
            input_id=input_request["id"],
            value="yes",
            worker=input_event["worker"],
        )

        result = future.result(timeout=30)
        events.extend(list(future.events(timeout=1)))

        assert result["dummy-worker-1"]["failed"] is False
        assert result["dummy-worker-1"]["result"] == {"response": "yes"}

        response_events = [
            event for event in events if event.get("event_type") == "input_response"
        ]
        assert response_events
        assert response_events[-1]["status"] == "received"

        job = nfclient.job_db.get_job(future.uuid)
        assert job["status"] == JobStatus.COMPLETED

    def test_future_progress_event(self, nfclient):
        future = nfclient.submit_job(
            "DummyService",
            "event_task",
            workers="dummy-worker-1",
            timeout=30,
        )

        events, progress_event = self.collect_events_until(future, "progress")
        result = future.result(timeout=30)
        events.extend(list(future.events(timeout=1)))

        assert progress_event is not None
        assert any(
            event.get("message") == "dummy progress event"
            and event.get("event_type") == "progress"
            and event.get("resource") == ["dummy-resource"]
            for event in events
        )
        assert result["dummy-worker-1"]["failed"] is False
        assert result["dummy-worker-1"]["result"] == "event done"

    def test_future_input_request_cancel(self, nfclient):
        future = nfclient.submit_job(
            "DummyService",
            "input_request_task",
            workers="dummy-worker-1",
            timeout=30,
        )
        events, input_event = self.collect_events_until(future, "input_request")

        assert input_event is not None
        input_request = input_event["extras"]["input_request"]

        future.send_response(
            input_id=input_request["id"],
            value=None,
            worker=input_event["worker"],
            cancel=True,
        )

        result = future.result(timeout=30)
        events.extend(list(future.events(timeout=1)))

        assert result["dummy-worker-1"]["failed"] is True
        assert "Client cancelled input" in result["dummy-worker-1"]["messages"][0]
        assert any(
            event.get("event_type") == "input_response"
            and event.get("status") == "cancelled"
            for event in events
        )

    def test_future_input_request_timeout(self, nfclient):
        future = nfclient.submit_job(
            "DummyService",
            "input_request_timeout_task",
            workers="dummy-worker-1",
            timeout=30,
        )
        events, input_event = self.collect_events_until(future, "input_request")

        assert input_event is not None

        result = future.result(timeout=30)
        events.extend(list(future.events(timeout=1)))

        assert result["dummy-worker-1"]["failed"] is True
        assert "Client input timed out" in result["dummy-worker-1"]["messages"][0]
        assert any(
            event.get("event_type") == "input_response"
            and event.get("status") == "timeout"
            for event in events
        )


class TestClientCompletionEvents:
    @pytest.mark.parametrize("task", ["dummy_task", "input_request_timeout_task"])
    def test_completion_without_recovery_get(
        self, nfclient: NFPClient, task: str
    ) -> None:
        """Saved results, including failures, arrive without periodic GETs."""
        original_interval = nfclient.poll_interval
        nfclient.poll_interval = 3600
        try:
            future = nfclient.submit_job(
                "DummyService", task, workers=["dummy-worker-1"], timeout=15
            )
            result = future.result(timeout=15)
            job = nfclient.job_db.get_job(future.uuid)
            assert job["status"] == JobStatus.COMPLETED
            assert result["dummy-worker-1"]["failed"] == (
                task == "input_request_timeout_task"
            )
            assert any(
                event.get("event_type") == "result_ready"
                for event in future.events(timeout=1)
            )
            assert time.time() - job["last_poll_timestamp"] < nfclient.poll_interval
        finally:
            nfclient.poll_interval = original_interval

    def test_multiworker_completion_preserves_dispatch(
        self, nfclient: NFPClient
    ) -> None:
        """Targeted GET acknowledgements cannot shrink the expected worker set."""
        original_interval = nfclient.poll_interval
        nfclient.poll_interval = 3600
        try:
            future = nfclient.submit_job(
                "nornir",
                "get_version",
                workers=["nornir-worker-1", "nornir-worker-2"],
                timeout=20,
            )
            result = future.result(timeout=20)
            expected = {"nornir-worker-1", "nornir-worker-2"}
            assert set(result) == expected
            assert all(not entry["failed"] for entry in result.values())
            assert (
                set(nfclient.job_db.get_job(future.uuid)["workers_dispatched"])
                == expected
            )
        finally:
            nfclient.poll_interval = original_interval

    def test_deadlines_ignore_recovery_age_and_batch(self, nfclient: NFPClient) -> None:
        """Overdue jobs beyond a batch expire while recent polls remain throttled."""
        jobs = []
        for _ in range(nfclient.dispatch_batch_size + 1):
            juuid = uuid4().hex
            nfclient.job_db.add_job(
                uuid=juuid,
                service="DummyService",
                task="dummy_task",
                workers=["dummy-worker-1"],
                args=[],
                kwargs={},
                timeout=1,
                deadline=time.time() - 1,
            )
            nfclient.job_db.update_job(
                juuid,
                status=JobStatus.STARTED,
                workers_dispatched=["dummy-worker-1", "missing-worker"],
                workers_completed=["dummy-worker-1"],
                result_data={"dummy-worker-1": {"result": "preserved"}},
                last_poll_ts=time.time(),
            )
            jobs.append(juuid)
        poll_active_jobs(nfclient)
        poll_active_jobs(nfclient)
        for juuid in jobs:
            job = nfclient.job_db.get_job(juuid)
            assert job["status"] == JobStatus.STALE
            assert job["result_data"]["dummy-worker-1"]["result"] == "preserved"
            assert job["result_data"]["missing-worker"]["status"] == "timeout"

    def test_restart_recovers_result_without_resubmission(
        self, nfclient: NFPClient
    ) -> None:
        """A client offline at completion retrieves the saved worker result."""
        name = f"completion-restart-{uuid4().hex}"
        client = NFPClient(nfclient.inventory, nfclient.broker, name)
        try:
            future = client.submit_job(
                "DummyService",
                "input_request_timeout_task",
                workers=["dummy-worker-1"],
                timeout=20,
            )
            for event in future.events(timeout=5):
                if event.get("event_type") == "input_request":
                    break
            else:
                pytest.fail("worker did not request input")
            original = client.job_db.get_job(future.uuid)
            assert original["workers_dispatched"] == ["dummy-worker-1"]
            client.destroy()
            time.sleep(2)  # The worker's one-second input wait finishes while offline.
            client = NFPClient(nfclient.inventory, nfclient.broker, name)
            assert client.zmq_name == name
            assert (
                client.job_db.get_job(future.uuid)["created_at"]
                == original["created_at"]
            )
            result = client.job_futures[future.uuid].result(timeout=10)
            assert result["dummy-worker-1"]["failed"] is True
            assert "Client input timed out" in result["dummy-worker-1"]["messages"][0]
        finally:
            client.destroy()

    def test_late_acknowledgements_preserve_workers_and_input(
        self, nfclient: NFPClient
    ) -> None:
        """Targeted GET acknowledgements and worker replies preserve pending input."""
        juuid = uuid4().hex
        nfclient.job_db.add_job(
            uuid=juuid,
            service="DummyService",
            task="dummy_task",
            workers=["first", "second"],
            args=[],
            kwargs={},
            timeout=60,
            deadline=time.time() + 60,
        )
        future = NFPJobFuture(
            nfclient, juuid, "DummyService", "dummy_task", ["first", "second"], 60, {}
        )
        nfclient.job_futures[juuid] = future
        future.pending_inputs["second"] = "input-id"
        nfclient.job_db.update_job(
            juuid,
            status=JobStatus.WAITING_CLIENT_INPUT,
            workers_dispatched=["first", "second"],
        )
        try:
            handle_response(nfclient, juuid, "202", {"workers": ["first"]})
            handle_response(nfclient, juuid, "201", {"worker": "first"})
            handle_response(nfclient, juuid, "200", {"first": {"result": "done"}})
            handle_response(nfclient, juuid, "300", {"worker": "first"})
            job = nfclient.job_db.get_job(juuid)
            assert job["workers_dispatched"] == ["first", "second"]
            assert job["status"] == JobStatus.WAITING_CLIENT_INPUT
            assert job["result_data"] == {"first": {"result": "done"}}
            assert not future.done_event.is_set()
        finally:
            nfclient.job_db.update_job(juuid, status=JobStatus.FAILED)
            nfclient.job_futures.pop(juuid)


class TestClientSocketWakeup:
    def test_idle_send_burst_and_multiple_producers(self, nfclient: NFPClient) -> None:
        """An idle owner wakes, drains multiple batches, and handles broker replies."""
        client = NFPClient(nfclient.inventory, nfclient.broker, f"wakeup-{uuid4().hex}")
        try:
            assert (
                client.mmi("mmi.service.broker", "show_broker_version", timeout=10)[
                    "status"
                ]
                == "200"
            )
            request = client.ensure_bytes(
                {"task": "show_broker_version", "args": [], "kwargs": {}}
            )
            identifiers = [
                uuid4().hex.encode()
                for _ in range(NFP.ZMQ_SEND_RECV_DRAIN_LIMIT * 2 + 3)
            ]
            # Queue more than two drain batches, then wake the owner through normal sends.
            for juuid in identifiers:
                client.outbound_queue.put_nowait(
                    client.build_message.client_to_broker_mmi(
                        command=NFP.MMI,
                        service=b"mmi.service.broker",
                        workers=b"all",
                        uuid=juuid,
                        request=request,
                    )
                )
            producer_ids = [uuid4().hex.encode() for _ in range(16)]
            with ThreadPoolExecutor(max_workers=4) as producers:
                sends = [
                    producers.submit(
                        client.send_to_broker,
                        NFP.MMI,
                        b"mmi.service.broker",
                        b"all",
                        juuid,
                        request,
                    )
                    for juuid in producer_ids
                ]
                for send in sends:
                    send.result(timeout=10)
            expected = set(identifiers + producer_ids)
            received = set()
            deadline = time.time() + 20
            while received != expected and time.time() < deadline:
                reply = client.mmi_queue.get(timeout=max(0.1, deadline - time.time()))
                assert reply[5] == b"200"
                received.add(reply[4])
            assert received == expected
            assert client.outbound_queue.empty()
            assert client.recv_thread.is_alive()
        finally:
            client.destroy()

    def test_external_exit_and_repeated_shutdown(self, nfclient: NFPClient) -> None:
        """External exit wakes an idle owner and shutdown closes resources once."""
        exit_event = threading.Event()
        client = NFPClient(
            nfclient.inventory, nfclient.broker, f"exit-{uuid4().hex}", exit_event
        )
        try:
            assert (
                client.mmi("mmi.service.broker", "show_broker_version", timeout=10)[
                    "status"
                ]
                == "200"
            )
            exit_event.set()
            client.dispatcher_thread.join(timeout=5)
            client.recv_thread.join(timeout=5)
            assert not client.dispatcher_thread.is_alive()
            assert not client.recv_thread.is_alive()
            client.destroy()
            client.destroy()
            assert client.wakeup_reader.fileno() == -1
            assert client.wakeup_writer.fileno() == -1
            assert client.ctx.closed
        finally:
            client.destroy()


class TestAddJobDb:
    """Test suite for ClientJobDatabase.add_job method"""

    def test_add_job_basic(self, nfclient):
        """Test adding a basic job to database"""
        job_uuid = uuid4().hex
        nfclient.job_db.add_job(
            uuid=job_uuid,
            service="nornir",
            task="echo",
            workers=["nornir-worker-1", "nornir-worker-2"],
            args=[],
            kwargs={},
            timeout=600,
            deadline=time.time() + 600,
        )

        # Retrieve and verify job was added
        job = nfclient.job_db.get_job(job_uuid)
        assert job is not None
        assert job["uuid"] == job_uuid
        assert job["service"] == "nornir"
        assert job["task"] == "echo"
        assert job["status"] == JobStatus.NEW
        assert set(job["workers_requested"]) == {"nornir-worker-1", "nornir-worker-2"}

    def test_add_job_with_args_kwargs(self, nfclient):
        """Test adding job with arguments and keyword arguments"""
        job_uuid = uuid4().hex
        test_args = ["arg1", "arg2", 123]
        test_kwargs = {"FC": "value1", "key2": 456, "nested": {"a": "b"}}

        nfclient.job_db.add_job(
            uuid=job_uuid,
            service="nornir",
            task="echo",
            workers="all",
            args=test_args,
            kwargs=test_kwargs,
            timeout=300,
            deadline=time.time() + 300,
        )

        job = nfclient.job_db.get_job(job_uuid)
        assert job["args"] == test_args
        assert job["kwargs"] == test_kwargs
        assert job["timeout"] == 300

    def test_add_job_with_single_worker(self, nfclient):
        """Test adding job with single worker string"""
        job_uuid = uuid4().hex
        nfclient.job_db.add_job(
            uuid=job_uuid,
            service="nornir",
            task="echo",
            workers="nornir-worker-1",
            args=[],
            kwargs={},
            timeout=600,
            deadline=time.time() + 600,
        )

        job = nfclient.job_db.get_job(job_uuid)
        assert job["workers_requested"] == "nornir-worker-1"


class TestGetJobDb:
    """Test suite for ClientJobDatabase.get_job method"""

    def test_get_job_existing(self, nfclient):
        """Test retrieving an existing job"""
        job_uuid = uuid4().hex
        nfclient.job_db.add_job(
            uuid=job_uuid,
            service="nornir",
            task="echo",
            workers=["nornir-worker-1"],
            args=[],
            kwargs={"param": "value"},
            timeout=600,
            deadline=time.time() + 600,
        )

        job = nfclient.job_db.get_job(job_uuid)
        assert job is not None
        assert job["uuid"] == job_uuid
        assert job["service"] == "nornir"
        assert job["task"] == "echo"
        assert job["kwargs"]["param"] == "value"

    def test_get_job_nonexistent(self, nfclient):
        """Test retrieving a non-existent job returns None"""
        fake_uuid = uuid4().hex
        job = nfclient.job_db.get_job(fake_uuid)
        assert job is None

    def test_get_job_with_compression(self, nfclient):
        """Test job retrieval with compressed data"""
        job_uuid = uuid4().hex
        large_kwargs = {f"key_{i}": f"value_{i}" * 100 for i in range(50)}

        nfclient.job_db.add_job(
            uuid=job_uuid,
            service="nornir",
            task="echo",
            workers=["nornir-worker-1"],
            args=[],
            kwargs=large_kwargs,
            timeout=600,
            deadline=time.time() + 600,
        )

        job = nfclient.job_db.get_job(job_uuid)
        assert job is not None
        assert job["kwargs"] == large_kwargs


class TestUpdateJobDb:
    """Test suite for ClientJobDatabase.update_job method"""

    def test_update_job_status(self, nfclient):
        """Test updating job status"""
        job_uuid = uuid4().hex
        nfclient.job_db.add_job(
            uuid=job_uuid,
            service="nornir",
            task="echo",
            workers=["nornir-worker-1"],
            args=[],
            kwargs={},
            timeout=600,
            deadline=time.time() + 600,
        )

        nfclient.job_db.update_job(job_uuid, status=JobStatus.DISPATCHED)
        job = nfclient.job_db.get_job(job_uuid)
        assert job["status"] == JobStatus.DISPATCHED

    def test_update_job_workers_dispatched(self, nfclient):
        """Test updating workers dispatched list"""
        job_uuid = uuid4().hex
        nfclient.job_db.add_job(
            uuid=job_uuid,
            service="nornir",
            task="echo",
            workers=["nornir-worker-1", "nornir-worker-2"],
            args=[],
            kwargs={},
            timeout=600,
            deadline=time.time() + 600,
        )

        nfclient.job_db.update_job(
            job_uuid, workers_dispatched=["nornir-worker-1", "nornir-worker-2"]
        )
        job = nfclient.job_db.get_job(job_uuid)
        assert set(job["workers_dispatched"]) == {"nornir-worker-1", "nornir-worker-2"}

    def test_update_job_workers_started(self, nfclient):
        """Test updating workers started list"""
        job_uuid = uuid4().hex
        nfclient.job_db.add_job(
            uuid=job_uuid,
            service="nornir",
            task="echo",
            workers=["nornir-worker-1", "nornir-worker-2"],
            args=[],
            kwargs={},
            timeout=600,
            deadline=time.time() + 600,
        )

        nfclient.job_db.update_job(job_uuid, workers_started=["nornir-worker-1"])
        job = nfclient.job_db.get_job(job_uuid)
        assert job["workers_started"] == ["nornir-worker-1"]

    def test_update_job_workers_completed(self, nfclient):
        """Test updating workers completed list"""
        job_uuid = uuid4().hex
        nfclient.job_db.add_job(
            uuid=job_uuid,
            service="nornir",
            task="echo",
            workers=["nornir-worker-1", "nornir-worker-2"],
            args=[],
            kwargs={},
            timeout=600,
            deadline=time.time() + 600,
        )

        nfclient.job_db.update_job(job_uuid, workers_completed=["nornir-worker-1"])
        job = nfclient.job_db.get_job(job_uuid)
        assert job["workers_completed"] == ["nornir-worker-1"]

    def test_update_job_result_data(self, nfclient):
        """Test updating job result data"""
        job_uuid = uuid4().hex
        nfclient.job_db.add_job(
            uuid=job_uuid,
            service="nornir",
            task="echo",
            workers=["nornir-worker-1"],
            args=[],
            kwargs={},
            timeout=600,
            deadline=time.time() + 600,
        )

        result_data = {"nornir-worker-1": {"result": "success", "data": [1, 2, 3]}}
        nfclient.job_db.update_job(job_uuid, result_data=result_data)
        job = nfclient.job_db.get_job(job_uuid)
        assert job["result_data"] == result_data

    def test_update_job_errors(self, nfclient):
        """Test updating job errors"""
        job_uuid = uuid4().hex
        nfclient.job_db.add_job(
            uuid=job_uuid,
            service="nornir",
            task="echo",
            workers=["nornir-worker-1"],
            args=[],
            kwargs={},
            timeout=600,
            deadline=time.time() + 600,
        )

        errors = ["Error 1", "Error 2"]
        nfclient.job_db.update_job(job_uuid, errors=errors)
        job = nfclient.job_db.get_job(job_uuid)
        assert job["errors"] == errors

    def test_update_job_append_errors(self, nfclient):
        """Test appending errors to existing errors list"""
        job_uuid = uuid4().hex
        nfclient.job_db.add_job(
            uuid=job_uuid,
            service="nornir",
            task="echo",
            workers=["nornir-worker-1"],
            args=[],
            kwargs={},
            timeout=600,
            deadline=time.time() + 600,
        )

        nfclient.job_db.update_job(job_uuid, errors=["Error 1"])
        nfclient.job_db.update_job(job_uuid, append_errors=["Error 2", "Error 3"])

        job = nfclient.job_db.get_job(job_uuid)
        assert len(job["errors"]) == 3
        assert "Error 1" in job["errors"]
        assert "Error 2" in job["errors"]
        assert "Error 3" in job["errors"]

    def test_update_job_last_poll_timestamp(self, nfclient):
        """Test updating last poll timestamp"""
        job_uuid = uuid4().hex
        nfclient.job_db.add_job(
            uuid=job_uuid,
            service="nornir",
            task="echo",
            workers=["nornir-worker-1"],
            args=[],
            kwargs={},
            timeout=600,
            deadline=time.time() + 600,
        )

        poll_time = time.time()
        nfclient.job_db.update_job(job_uuid, last_poll_ts=poll_time)
        job = nfclient.job_db.get_job(job_uuid)
        assert job["last_poll_timestamp"] == poll_time

    def test_update_job_multiple_fields(self, nfclient):
        """Test updating multiple fields at once"""
        job_uuid = uuid4().hex
        nfclient.job_db.add_job(
            uuid=job_uuid,
            service="nornir",
            task="echo",
            workers=["nornir-worker-1"],
            args=[],
            kwargs={},
            timeout=600,
            deadline=time.time() + 600,
        )

        nfclient.job_db.update_job(
            job_uuid,
            status=JobStatus.COMPLETED,
            workers_completed=["nornir-worker-1"],
            result_data={"nornir-worker-1": {"result": "done"}},
            completed_ts=time.ctime(),
        )

        job = nfclient.job_db.get_job(job_uuid)
        assert job["status"] == JobStatus.COMPLETED
        assert job["workers_completed"] == ["nornir-worker-1"]
        assert job["result_data"]["nornir-worker-1"]["result"] == "done"
        assert job["completed_timestamp"] is not None


class TestFetchJobs:
    """Test suite for ClientJobDatabase.fetch_jobs method"""

    def test_fetch_jobs_all(self, nfclient):
        """Test fetching all jobs without filters"""
        # Create multiple jobs
        job_uuids = []
        for i in range(5):
            job_uuid = uuid4().hex
            job_uuids.append(job_uuid)
            nfclient.job_db.add_job(
                uuid=job_uuid,
                service="nornir",
                task="echo",
                workers=["nornir-worker-1"],
                args=[],
                kwargs={},
                timeout=600,
                deadline=time.time() + 600,
            )

        jobs = nfclient.job_db.fetch_jobs(last=10)
        assert len(jobs) >= 5
        fetched_uuids = [j["uuid"] for j in jobs]
        for uuid in job_uuids:
            assert uuid in fetched_uuids

    def test_fetch_jobs_by_status(self, nfclient):
        """Test fetching jobs by status"""
        # Create jobs with different statuses
        new_uuid = uuid4().hex
        dispatched_uuid = uuid4().hex

        nfclient.job_db.add_job(
            uuid=new_uuid,
            service="nornir",
            task="echo",
            workers=["nornir-worker-1"],
            args=[],
            kwargs={},
            timeout=600,
            deadline=time.time() + 600,
        )

        nfclient.job_db.add_job(
            uuid=dispatched_uuid,
            service="nornir",
            task="echo",
            workers=["nornir-worker-1"],
            args=[],
            kwargs={},
            timeout=600,
            deadline=time.time() + 600,
        )
        nfclient.job_db.update_job(dispatched_uuid, status=JobStatus.DISPATCHED)

        # Fetch only NEW jobs
        new_jobs = nfclient.job_db.fetch_jobs(statuses=[JobStatus.NEW], last=10)
        new_job_uuids = [j["uuid"] for j in new_jobs]
        assert new_uuid in new_job_uuids
        assert dispatched_uuid not in new_job_uuids

    def test_fetch_jobs_last_one(self, nfclient):
        """Test fetching only the last job"""
        # Create multiple jobs
        job_uuids = []
        for i in range(3):
            job_uuid = uuid4().hex
            job_uuids.append(job_uuid)
            nfclient.job_db.add_job(
                uuid=job_uuid,
                service="nornir",
                task="echo",
                workers=["nornir-worker-1"],
                args=[],
                kwargs={},
                timeout=600,
                deadline=time.time() + 600,
            )
            time.sleep(0.01)  # Ensure different creation times

        jobs = nfclient.job_db.fetch_jobs(last=1)
        assert len(jobs) == 1
        # Last job created should be returned (most recent)
        assert jobs[0]["uuid"] == job_uuids[-1]

    def test_fetch_jobs_last_three(self, nfclient):
        """Test fetching last 3 jobs"""
        # Create multiple jobs
        job_uuids = []
        for i in range(5):
            job_uuid = uuid4().hex
            job_uuids.append(job_uuid)
            nfclient.job_db.add_job(
                uuid=job_uuid,
                service="nornir",
                task="echo",
                workers=["nornir-worker-1"],
                args=[],
                kwargs={},
                timeout=600,
                deadline=time.time() + 600,
            )
            time.sleep(0.01)

        jobs = nfclient.job_db.fetch_jobs(last=3)
        assert len(jobs) == 3
        fetched_uuids = [j["uuid"] for j in jobs]
        # Should return the 3 most recent jobs
        for uuid in job_uuids[-3:]:
            assert uuid in fetched_uuids

    def test_fetch_jobs_by_service(self, nfclient):
        """Test fetching jobs filtered by service name"""

        nornir_jobs = nfclient.job_db.fetch_jobs(service="nornir", last=10)
        pprint.pprint(nornir_jobs)

        assert nornir_jobs
        for j in nornir_jobs:
            assert j["service"] == "nornir", j

    def test_fetch_jobs_by_task(self, nfclient):
        """Test fetching jobs filtered by task name"""
        get_version_uuid = uuid4().hex
        echo_uuid = uuid4().hex

        nfclient.job_db.add_job(
            uuid=get_version_uuid,
            service="nornir",
            task="get_version",
            workers=["nornir-worker-1"],
            args=[],
            kwargs={},
            timeout=600,
            deadline=time.time() + 600,
        )

        nfclient.job_db.add_job(
            uuid=echo_uuid,
            service="nornir",
            task="echo",
            workers=["nornir-worker-1"],
            args=[],
            kwargs={},
            timeout=600,
            deadline=time.time() + 600,
        )

        get_version_jobs = nfclient.job_db.fetch_jobs(task="get_version", last=10)
        get_version_uuids = [j["uuid"] for j in get_version_jobs]
        assert get_version_uuid in get_version_uuids
        assert echo_uuid not in get_version_uuids

    def test_fetch_jobs_with_limit(self, nfclient):
        """Test fetching jobs with limit"""
        for i in range(10):
            nfclient.job_db.add_job(
                uuid=uuid4().hex,
                service="nornir",
                task="echo",
                workers=["nornir-worker-1"],
                args=[],
                kwargs={},
                timeout=600,
                deadline=time.time() + 600,
            )

        jobs = nfclient.job_db.fetch_jobs(limit=5)
        assert len(jobs) <= 5

    def test_fetch_jobs_by_workers_completed(self, nfclient):
        """Test fetching jobs filtered by completed workers"""
        job1_uuid = uuid4().hex
        job2_uuid = uuid4().hex

        nfclient.job_db.add_job(
            uuid=job1_uuid,
            service="nornir",
            task="echo",
            workers=["nornir-worker-1", "nornir-worker-2"],
            args=[],
            kwargs={},
            timeout=600,
            deadline=time.time() + 600,
        )
        nfclient.job_db.update_job(
            job1_uuid, workers_completed=["nornir-worker-1", "nornir-worker-2"]
        )

        nfclient.job_db.add_job(
            uuid=job2_uuid,
            service="nornir",
            task="echo",
            workers=["nornir-worker-2"],
            args=[],
            kwargs={},
            timeout=600,
            deadline=time.time() + 600,
        )
        nfclient.job_db.update_job(job2_uuid, workers_completed=["nornir-worker-2"])

        jobs = nfclient.job_db.fetch_jobs(
            workers_completed=["nornir-worker-1"], last=10
        )
        job_uuids = [j["uuid"] for j in jobs]
        assert job1_uuid in job_uuids

    def test_fetch_jobs_combined_filters(self, nfclient):
        """Test fetching jobs with multiple filters combined"""
        job_uuid = uuid4().hex

        nfclient.job_db.add_job(
            uuid=job_uuid,
            service="nornir",
            task="cli",
            workers=["nornir-worker-1"],
            args=[],
            kwargs={},
            timeout=600,
            deadline=time.time() + 600,
        )
        nfclient.job_db.update_job(job_uuid, status=JobStatus.COMPLETED)

        jobs = nfclient.job_db.fetch_jobs(
            statuses=[JobStatus.COMPLETED], service="nornir", task="cli", last=10
        )

        job_uuids = [j["uuid"] for j in jobs]
        assert job_uuid in job_uuids


class TestAddEvent:
    """Test suite for ClientJobDatabase.add_event method"""

    def test_add_event_basic(self, nfclient):
        """Test adding a basic event"""
        job_uuid = uuid4().hex
        nfclient.job_db.add_job(
            uuid=job_uuid,
            service="nornir",
            task="echo",
            workers=["nornir-worker-1"],
            args=[],
            kwargs={},
            timeout=600,
            deadline=time.time() + 600,
        )

        nfclient.job_db.add_event(
            job_uuid=job_uuid, message="Test event message", severity="INFO"
        )

        # Event added successfully (no exception raised)
        assert True

    def test_add_event_with_severity_levels(self, nfclient):
        """Test adding events with different severity levels"""
        job_uuid = uuid4().hex
        nfclient.job_db.add_job(
            uuid=job_uuid,
            service="nornir",
            task="echo",
            workers=["nornir-worker-1"],
            args=[],
            kwargs={},
            timeout=600,
            deadline=time.time() + 600,
        )

        for severity in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            nfclient.job_db.add_event(
                job_uuid=job_uuid,
                message=f"Message with {severity} severity",
                severity=severity,
            )

        # Events added successfully
        assert True

    def test_add_event_with_task(self, nfclient):
        """Test adding event with task information"""
        job_uuid = uuid4().hex
        nfclient.job_db.add_job(
            uuid=job_uuid,
            service="nornir",
            task="echo",
            workers=["nornir-worker-1"],
            args=[],
            kwargs={},
            timeout=600,
            deadline=time.time() + 600,
        )

        nfclient.job_db.add_event(
            job_uuid=job_uuid,
            message="Task started",
            severity="INFO",
            task="echo",
        )

        assert True

    def test_add_event_with_event_data(self, nfclient):
        """Test adding event with additional event data"""
        job_uuid = uuid4().hex
        nfclient.job_db.add_job(
            uuid=job_uuid,
            service="nornir",
            task="echo",
            workers=["nornir-worker-1"],
            args=[],
            kwargs={},
            timeout=600,
            deadline=time.time() + 600,
        )

        event_data = {
            "worker": "nornir-worker-1",
            "host": "device-1",
            "duration": 1.23,
            "status": "success",
        }

        nfclient.job_db.add_event(
            job_uuid=job_uuid,
            message="Job completed on host",
            severity="INFO",
            task="cli",
            event_data=event_data,
        )

        assert True

    def test_add_multiple_events_for_same_job(self, nfclient):
        """Test adding multiple events for the same job"""
        job_uuid = uuid4().hex
        nfclient.job_db.add_job(
            uuid=job_uuid,
            service="nornir",
            task="echo",
            workers=["nornir-worker-1"],
            args=[],
            kwargs={},
            timeout=600,
            deadline=time.time() + 600,
        )

        # Add multiple events
        for i in range(5):
            nfclient.job_db.add_event(
                job_uuid=job_uuid,
                message=f"Event {i}",
                severity="INFO",
            )

        assert True


class TestJobStatusTransitions:
    """Test suite for job status transitions"""

    def test_job_lifecycle_new_to_completed(self, nfclient):
        """Test complete job lifecycle from NEW to COMPLETED"""
        job_uuid = uuid4().hex

        # Add job (NEW status)
        nfclient.job_db.add_job(
            uuid=job_uuid,
            service="nornir",
            task="echo",
            workers=["nornir-worker-1"],
            args=[],
            kwargs={},
            timeout=600,
            deadline=time.time() + 600,
        )
        job = nfclient.job_db.get_job(job_uuid)
        assert job["status"] == JobStatus.NEW

        # Transition to DISPATCHED
        nfclient.job_db.update_job(
            job_uuid,
            status=JobStatus.DISPATCHED,
            workers_dispatched=["nornir-worker-1"],
            started_ts=time.ctime(),
        )
        job = nfclient.job_db.get_job(job_uuid)
        assert job["status"] == JobStatus.DISPATCHED

        # Transition to STARTED
        nfclient.job_db.update_job(
            job_uuid, status=JobStatus.STARTED, workers_started=["nornir-worker-1"]
        )
        job = nfclient.job_db.get_job(job_uuid)
        assert job["status"] == JobStatus.STARTED

        # Transition to COMPLETED
        nfclient.job_db.update_job(
            job_uuid,
            status=JobStatus.COMPLETED,
            workers_completed=["nornir-worker-1"],
            result_data={"nornir-worker-1": {"result": "success"}},
            completed_ts=time.ctime(),
        )
        job = nfclient.job_db.get_job(job_uuid)
        assert job["status"] == JobStatus.COMPLETED

    def test_job_lifecycle_new_to_failed(self, nfclient):
        """Test job lifecycle from NEW to FAILED"""
        job_uuid = uuid4().hex

        nfclient.job_db.add_job(
            uuid=job_uuid,
            service="nornir",
            task="echo",
            workers=["nornir-worker-1"],
            args=[],
            kwargs={},
            timeout=600,
            deadline=time.time() + 600,
        )

        # Transition directly to FAILED
        nfclient.job_db.update_job(
            job_uuid,
            status=JobStatus.FAILED,
            errors=["Connection timeout"],
            completed_ts=time.ctime(),
        )

        job = nfclient.job_db.get_job(job_uuid)
        assert job["status"] == JobStatus.FAILED
        assert "Connection timeout" in job["errors"]

    def test_job_with_multiple_workers(self, nfclient):
        """Test job with multiple workers progression"""
        job_uuid = uuid4().hex
        workers = ["nornir-worker-1", "nornir-worker-2"]

        nfclient.job_db.add_job(
            uuid=job_uuid,
            service="nornir",
            task="echo",
            workers=workers,
            args=[],
            kwargs={},
            timeout=600,
            deadline=time.time() + 600,
        )

        # Dispatch to all workers
        nfclient.job_db.update_job(
            job_uuid, status=JobStatus.DISPATCHED, workers_dispatched=workers
        )

        # Worker 1 starts
        nfclient.job_db.update_job(
            job_uuid, status=JobStatus.STARTED, workers_started=["nornir-worker-1"]
        )
        job = nfclient.job_db.get_job(job_uuid)
        assert len(job["workers_started"]) == 1

        # Worker 1 completes
        nfclient.job_db.update_job(
            job_uuid,
            workers_completed=["nornir-worker-1"],
            result_data={"nornir-worker-1": {"result": "done"}},
        )

        # Worker 2 completes
        nfclient.job_db.update_job(
            job_uuid,
            workers_completed=["nornir-worker-1", "nornir-worker-2"],
            result_data={
                "nornir-worker-1": {"result": "done"},
                "nornir-worker-2": {"result": "done"},
            },
        )

        job = nfclient.job_db.get_job(job_uuid)
        assert len(job["workers_completed"]) == 2

    def test_future_prefers_final_job_snapshot(self, nfclient):
        """A completed snapshot remains authoritative over mutable database state."""
        job_uuid = uuid4().hex
        expected_result = {"nornir-worker-1": {"result": "success"}}
        nfclient.job_db.add_job(
            uuid=job_uuid,
            service="nornir",
            task="echo",
            workers=["nornir-worker-1"],
            args=[],
            kwargs={},
            timeout=600,
            deadline=time.time() + 600,
        )
        nfclient.job_db.update_job(job_uuid, status=JobStatus.STARTED)

        future = NFPJobFuture(
            client=nfclient,
            uuid=job_uuid,
            service="nornir",
            task="echo",
            workers=["nornir-worker-1"],
            timeout=600,
            kwargs={},
        )
        final_job_snapshot = nfclient.job_db.get_job(job_uuid)
        final_job_snapshot["status"] = JobStatus.COMPLETED
        final_job_snapshot["result_data"] = expected_result
        future.mark_done(final_job_snapshot)

        assert future.result(timeout=1) == expected_result

    @pytest.mark.parametrize(
        ("terminal_status", "later_status"),
        [
            (JobStatus.COMPLETED, JobStatus.STARTED),
            (JobStatus.COMPLETED, JobStatus.FAILED),
            (JobStatus.FAILED, JobStatus.STARTED),
            (JobStatus.FAILED, JobStatus.COMPLETED),
            (JobStatus.STALE, JobStatus.STARTED),
            (JobStatus.STALE, JobStatus.COMPLETED),
        ],
    )
    def test_database_rejects_transition_from_terminal_status(
        self, nfclient, terminal_status, later_status
    ):
        """Database updates cannot replace a terminal status."""
        job_uuid = uuid4().hex
        nfclient.job_db.add_job(
            uuid=job_uuid,
            service="nornir",
            task="echo",
            workers=["nornir-worker-1"],
            args=[],
            kwargs={},
            timeout=600,
            deadline=time.time() + 600,
        )
        nfclient.job_db.update_job(job_uuid, status=terminal_status)

        nfclient.job_db.update_job(job_uuid, status=later_status)

        assert nfclient.job_db.get_job(job_uuid)["status"] == terminal_status

    @pytest.mark.parametrize(
        "terminal_status", [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.STALE]
    )
    @pytest.mark.parametrize(
        ("response_status", "payload"),
        [
            ("202", {"workers": ["nornir-worker-1"]}),
            ("201", {"worker": "nornir-worker-1"}),
            ("102", {"worker": "nornir-worker-1"}),
            ("300", {"worker": "nornir-worker-1"}),
            ("200", {"nornir-worker-1": {"result": "late"}}),
            ("500", {"error": "late error"}),
        ],
    )
    def test_terminal_job_ignores_late_responses(
        self, nfclient, terminal_status, response_status, payload
    ):
        """Late responses cannot transition a finished job to another state."""
        job_uuid = uuid4().hex
        original_result = {"nornir-worker-1": {"result": "original"}}
        nfclient.job_db.add_job(
            uuid=job_uuid,
            service="nornir",
            task="echo",
            workers=["nornir-worker-1"],
            args=[],
            kwargs={},
            timeout=600,
            deadline=time.time() + 600,
        )
        nfclient.job_db.update_job(
            job_uuid,
            status=terminal_status,
            workers_dispatched=["nornir-worker-1"],
            workers_completed=["nornir-worker-1"],
            result_data=original_result,
            completed_ts=time.ctime(),
        )

        handle_response(nfclient, job_uuid, response_status, payload)

        job = nfclient.job_db.get_job(job_uuid)
        assert job["status"] == terminal_status
        assert job["result_data"] == original_result


class TestClientMessaging:
    @pytest.mark.parametrize("full_notification_buffer", [False, True])
    def test_send_to_broker_queues_prepared_message(
        self, full_notification_buffer: bool
    ) -> None:
        client = NFPClient.__new__(NFPClient)
        client.name = "test-client"
        client.destroy_event = threading.Event()
        client.outbound_queue = queue.Queue(maxsize=NFP.OUTBOUND_QUEUE_SIZE)
        client.build_message = NFP.MessageBuilder()
        client.wakeup_reader, client.wakeup_writer = socket.socketpair()
        client.wakeup_reader.setblocking(False)
        client.wakeup_writer.setblocking(False)

        if full_notification_buffer:
            # A full notification channel must not prevent queueing a message.
            with pytest.raises(BlockingIOError):
                while True:
                    client.wakeup_writer.send(b"\x00" * 4096)

        client.send_to_broker(
            NFP.GET,
            b"service",
            b"worker",
            b"uuid",
            b'{"task":"show"}',
        )

        assert client.outbound_queue.qsize() == 1
        msg = client.outbound_queue.get_nowait()
        assert msg[1] == NFP.CLIENT
        assert msg[2] == NFP.GET
        assert client.wakeup_reader.recv(1) == b"\x00"
        client.wakeup_reader.close()
        client.wakeup_writer.close()

    def test_result_ready_queues_only_missing_worker(self, tmp_path: Path) -> None:
        """Only a saved-result marker queues GET; duplicates after collection do not."""
        client = NFPClient.__new__(NFPClient)
        client.name = "test-completion"
        client.wakeup_reader, client.wakeup_writer = socket.socketpair()
        client.wakeup_reader.setblocking(False)
        client.wakeup_writer.setblocking(False)
        client.destroy_event = threading.Event()
        client.outbound_queue = queue.Queue()
        client.build_message = NFP.MessageBuilder()
        client.job_futures = {}
        client.monitoring = ProcessMonitor()
        client.job_db = ClientJobDatabase(str(tmp_path / "events.db"))
        juuid = uuid4().hex
        client.job_db.add_job(
            uuid=juuid,
            service="dummy",
            task="echo",
            workers=["first", "second"],
            args=[],
            kwargs={},
            timeout=60,
            deadline=time.time() + 60,
        )
        client.job_db.update_job(
            juuid,
            status=JobStatus.STARTED,
            workers_dispatched=["first", "second"],
            last_poll_ts=123,
        )
        try:
            handle_event(client, juuid, {"worker": "first", "status": "completed"}, [])
            assert client.outbound_queue.empty()
            notification = {"worker": "first", "event_type": "result_ready"}
            handle_event(client, juuid, notification, [])
            message = client.outbound_queue.get_nowait()
            assert message[2] == NFP.GET
            assert b'["first"]' in message
            assert client.job_db.get_job(juuid)["last_poll_timestamp"] == 123
            handle_response(client, juuid, "200", {"first": {"result": "done"}})
            handle_event(client, juuid, notification, [])
            assert client.outbound_queue.empty()
            handle_event(
                client,
                juuid,
                {"worker": "unknown", "event_type": "result_ready"},
                [],
            )
            assert client.outbound_queue.empty()
            client.job_db.update_job(juuid, status=JobStatus.STALE)
            handle_event(
                client,
                juuid,
                {"worker": "second", "event_type": "result_ready"},
                [],
            )
            assert client.outbound_queue.empty()
        finally:
            client.job_db.close()
            client.wakeup_reader.close()
            client.wakeup_writer.close()
