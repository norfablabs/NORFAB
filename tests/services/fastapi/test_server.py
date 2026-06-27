import json
import pprint
import pytest

import requests

try:
    from tests.services.fastapi.common import (
        get_token,
        wait_for_endpoint,
    )
except ModuleNotFoundError as exc:
    if exc.name not in {
        "tests",
        "tests.services",
        "tests.services.fastapi",
        "tests.services.fastapi.common",
    }:
        raise
    from services.fastapi.common import (
        get_token,
        wait_for_endpoint,
    )

pytestmark = [pytest.mark.fastapi, pytest.mark.server, pytest.mark.task_fastapi_server]


@pytest.mark.task_fastapi_server
class TestFastAPIServer:
    def test_job_post(self, nfclient):
        token = get_token(nfclient)
        resp = requests.post(
            url="http://127.0.0.1:8000/api/job",
            headers={"Authorization": f"Bearer {token}"},
            data=json.dumps(
                {
                    "service": "nornir",
                    "task": "cli",
                    "kwargs": {
                        "commands": ["show clock", "show hostname"],
                        "FC": "spine",
                    },
                }
            ),
        )
        resp.raise_for_status()
        res = resp.json()
        pprint.pprint(res)

        assert res["errors"] == [], f"Having errors: '{res['errors']}'"
        assert res["status"] == "200", f"Unexpected status: '{res['status']}'"
        assert res["uuid"], f"Unexpected uuid value '{res['uuid']}'"
        assert len(res["workers"]) > 0, "No workers targeted"

    def test_job_post_noargs_nokwargs(self, nfclient):
        token = get_token(nfclient)
        resp = requests.post(
            url="http://127.0.0.1:8000/api/job",
            data=json.dumps({"service": "nornir", "task": "get_version"}),
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        res = resp.json()
        pprint.pprint(res)

        assert res["errors"] == [], f"Having errors: '{res['errors']}'"
        assert res["status"] == "200", f"Unexpected status: '{res['status']}'"
        assert res["uuid"], f"Unexpected uuid value '{res['uuid']}'"
        assert len(res["workers"]) > 0, "No workers targeted"

    def test_job_get(self, nfclient):
        # post the job first
        token = get_token(nfclient)
        post_resp = requests.post(
            url="http://127.0.0.1:8000/api/job",
            data=json.dumps({"service": "nornir", "task": "get_version"}),
            headers={"Authorization": f"Bearer {token}"},
        )
        post_resp.raise_for_status()
        post_res = post_resp.json()
        pprint.pprint(post_res)

        uuid = post_res["uuid"]

        # get the job
        get_resp = requests.get(
            url="http://127.0.0.1:8000/api/job",
            data=json.dumps({"service": "nornir", "uuid": uuid}),
            headers={"Authorization": f"Bearer {token}"},
        )
        get_resp.raise_for_status()
        get_res = get_resp.json()
        pprint.pprint(get_res)

        assert get_res["errors"] == []
        assert get_res["status"] == "200"
        assert get_res["workers"]["dispatched"] != []
        assert get_res["workers"]["done"] != []
        assert get_res["workers"]["pending"] == []

        for wname, wres in get_res["results"].items():
            assert wres["errors"] == [], f"{wname} having errors '{wres['errors']}'"
            assert wres["failed"] == False, f"{wname} failed to run job"
            assert wres["result"], f"{wname} no results provided"

    def test_job_run(self, nfclient):
        token = get_token(nfclient)
        resp = requests.post(
            url="http://127.0.0.1:8000/api/job/run",
            headers={"Authorization": f"Bearer {token}"},
            data=json.dumps(
                {
                    "service": "nornir",
                    "task": "cli",
                    "kwargs": {
                        "commands": ["show clock", "show hostname"],
                        "FC": "spine",
                    },
                }
            ),
        )
        resp.raise_for_status()
        res = resp.json()
        pprint.pprint(res)

        for wname, wres in res.items():
            assert wres["errors"] == [], f"{wname} having errors '{wres['errors']}'"
            assert wres["failed"] == False, f"{wname} failed to run job"
            assert "result" in wres, f"{wname} no results provided"

    def test_job_run_specific_worker(self, nfclient):
        token = get_token(nfclient)
        resp = requests.post(
            url="http://127.0.0.1:8000/api/job/run",
            headers={"Authorization": f"Bearer {token}"},
            data=json.dumps(
                {
                    "service": "nornir",
                    "task": "cli",
                    "workers": ["nornir-worker-1"],
                    "kwargs": {
                        "commands": ["show clock", "show hostname"],
                        "FC": "spine",
                    },
                }
            ),
        )
        resp.raise_for_status()
        res = resp.json()
        pprint.pprint(res)

        assert len(res) == 1
        for wname, wres in res.items():
            assert wres["errors"] == [], f"{wname} having errors '{wres['errors']}'"
            assert wres["failed"] == False, f"{wname} failed to run job"
            assert "result" in wres, f"{wname} no results provided"

    def test_openapi_endpoint_discovery(self, nfclient):
        token = get_token(nfclient)
        resp = requests.get(
            url="http://127.0.0.1:8000/openapi.json",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        res = resp.json()
        pprint.pprint(res)

        assert (
            len(res["paths"]) > 3
        ), "Path number should be more then 3 if api endpoints dynamically discovered"
        assert any(
            "nornir" in k for k in res["paths"]
        ), "No nornir service tasks API endpoints discovered"

    def test_api_nornir_test(self, nfclient):
        token = get_token(nfclient)

        wait_for_endpoint(nfclient, "/api/nornir/", 30)

        resp = requests.post(
            "http://127.0.0.1:8000/api/nornir/test/",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "accept": "application/json",
            },
            data=json.dumps(
                {
                    "suite": "nf://nornir_test_suites/suite_1.txt",
                    "FC": "spine",
                    "workers": "nornir-worker-1",
                }
            ),
        )

        resp.raise_for_status()

        pprint.pprint(resp.json())

        for wname, wres in resp.json().items():
            assert wres["failed"] == True, f"{wname} - should have failed tests"
            assert "ceos-spine-1" in wres["result"]
            assert "ceos-spine-2" in wres["result"]
            assert wres["status"] == "completed"
