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

pytestmark = pytest.mark.fastapi


class TestFastAPIServer:
    def test_job_run(self, nfclient):
        token = get_token(nfclient)
        resp = requests.post(
            url="http://127.0.0.1:8000/api/job/run",
            headers={"Authorization": f"Bearer {token}"},
            json=(
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
            json=(
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
        wait_for_endpoint(nfclient, "/api/nornir/", 30)
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
