import pprint
import json
import time
import pytest
from uuid import uuid4
from norfab.core.client import JobStatus


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

    def test_mmi_show_broker(self, nfclient):
        reply = nfclient.mmi("mmi.service.broker", "show_broker")

        ret = reply["results"]
        pprint.pprint(ret)

        for k in [
            "endpoint",
            "keepalives",
            "services count",
            "status",
            "workers count",
        ]:
            assert k in ret, "Not all broker params returned"
            assert ret[k], "Some broker params seems wrong"

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
                task=f"echo",
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
