import pprint
import pytest
import random
import requests
import json
import time


def get_token(nfclient):
    token = "1111111111111111111111111111111111111111111"
    nfclient.run_job(
        "fastapi", "bearer_token_store", kwargs={"token": token, "username": "pytest"}
    )
    return token


def wait_for_endpoint(nfclient, endpoint, timeout=30):
    # wait forfastapi to discover endpoints
    token = get_token(nfclient)
    start_time = time.time()
    while not time.time() - start_time > timeout:
        openapi_spec = requests.get(
            url="http://127.0.0.1:8000/openapi.json",
            headers={"Authorization": f"Bearer {token}"},
        )
        spec = openapi_spec.json()
        # pprint.pprint(list(spec["paths"].keys()))
        if not any(endpoint in k for k in spec["paths"]):
            time.sleep(1)
        else:
            break


class TestFastAPIWorker:
    def test_get_fastapi_inventory(self, nfclient):
        ret = nfclient.run_job("fastapi", "get_inventory")
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert all(
                k in data["result"] for k in ["fastapi", "uvicorn", "service"]
            ), f"{worker_name} inventory incomplete"

    def test_get_fastapi_version(self, nfclient):
        ret = nfclient.run_job("fastapi", "get_version")
        pprint.pprint(ret)

        assert isinstance(ret, dict), f"Expected dictionary but received {type(ret)}"
        for worker_name, version_report in ret.items():
            for package, version in version_report["result"].items():
                assert version != "", f"{worker_name}:{package} version is empty"

    def test_bearer_token_store(self, nfclient):
        ret = nfclient.run_job(
            "fastapi",
            "bearer_token_store",
            kwargs={
                "token": "token",
                "username": "test_bearer_token_store",
                "expire": 60,
            },
        )
        pprint.pprint(ret)

        for worker_name, results in ret.items():
            assert results["result"] == True, f"{worker_name} failed storing token"

    def test_bearer_token_list(self, nfclient):
        # delete first
        nfclient.run_job(
            "fastapi",
            "bearer_token_delete",
            kwargs={"username": "test_bearer_token_store"},
        )

        # create tokens
        tokens_to_create = ["token1", "token2", "token3"]
        for t in tokens_to_create:
            nfclient.run_job(
                "fastapi",
                "bearer_token_store",
                kwargs={
                    "token": t,
                    "username": "test_bearer_token_store",
                    "expire": 60,
                },
            )

        # list tokens
        tokens = nfclient.run_job(
            "fastapi",
            "bearer_token_list",
            kwargs={"username": "test_bearer_token_store"},
        )
        print("Created tokens:")
        pprint.pprint(tokens)
        for worker_name, results in tokens.items():
            for token in results["result"]:
                assert token["token"] in tokens_to_create
                assert all(
                    k in token
                    for k in ["token", "username", "age", "creation", "expires"]
                )

    def test_bearer_token_delete_by_username(self, nfclient):
        """Test to verify deletion of all tokens for given user"""
        # delete first
        nfclient.run_job(
            "fastapi",
            "bearer_token_delete",
            kwargs={"username": "test_bearer_token_store"},
        )

        # create tokens
        tokens_to_create = ["token1", "token2", "token3"]
        for t in tokens_to_create:
            nfclient.run_job(
                "fastapi",
                "bearer_token_store",
                kwargs={
                    "token": t,
                    "username": "test_bearer_token_store",
                    "expire": 60,
                },
            )

        # list tokens
        tokens = nfclient.run_job(
            "fastapi",
            "bearer_token_list",
            kwargs={"username": "test_bearer_token_store"},
        )
        print("Created tokens:")
        pprint.pprint(tokens)
        for worker_name, results in tokens.items():
            for token in results["result"]:
                assert token["token"] in tokens_to_create

        # delete all tokens
        deleted = nfclient.run_job(
            "fastapi",
            "bearer_token_delete",
            kwargs={"username": "test_bearer_token_store"},
        )
        print("Deleted tokens:")
        pprint.pprint(deleted)
        for worker_name, results in deleted.items():
            assert results["result"] == True

        tokens_after_delete = nfclient.run_job(
            "fastapi",
            "bearer_token_list",
            kwargs={"username": "test_bearer_token_store"},
        )
        print("tokens_after_delete:")
        pprint.pprint(tokens_after_delete)
        for worker_name, results in tokens_after_delete.items():
            assert results["result"][0]["token"] == ""

    def test_bearer_token_delete_by_token(self, nfclient):
        # delete first
        nfclient.run_job(
            "fastapi",
            "bearer_token_delete",
            kwargs={"username": "test_bearer_token_store"},
        )

        # create tokens
        tokens_to_create = ["token1", "token2", "token3"]
        for t in tokens_to_create:
            nfclient.run_job(
                "fastapi",
                "bearer_token_store",
                kwargs={
                    "token": t,
                    "username": "test_bearer_token_store",
                    "expire": 60,
                },
            )

        # list tokens
        tokens = nfclient.run_job(
            "fastapi",
            "bearer_token_list",
            kwargs={"username": "test_bearer_token_store"},
        )
        print("Created tokens:")
        pprint.pprint(tokens)
        for worker_name, results in tokens.items():
            for token in results["result"]:
                assert token["token"] in tokens_to_create

        # delete specific token
        deleted = nfclient.run_job(
            "fastapi", "bearer_token_delete", kwargs={"token": "token1"}
        )
        print("Deleted tokens:")
        pprint.pprint(deleted)
        for worker_name, results in deleted.items():
            assert results["result"] == True

        tokens_after_delete = nfclient.run_job(
            "fastapi",
            "bearer_token_list",
            kwargs={"username": "test_bearer_token_store"},
        )
        print("tokens_after_delete:")
        pprint.pprint(tokens_after_delete)
        for worker_name, results in tokens_after_delete.items():
            assert len(results["result"]) == 2
            for token in results["result"]:
                assert token["token"] in tokens_to_create

    def test_bearer_token_check(self, nfclient):
        # delete first
        nfclient.run_job(
            "fastapi",
            "bearer_token_delete",
            kwargs={"username": "test_bearer_token_store"},
        )

        # create token
        tokens_to_create = ["token1"]
        for t in tokens_to_create:
            nfclient.run_job(
                "fastapi",
                "bearer_token_store",
                kwargs={
                    "token": t,
                    "username": "test_bearer_token_store",
                    "expire": 60,
                },
            )

        # list tokens
        token_check = nfclient.run_job(
            "fastapi", "bearer_token_check", kwargs={"token": "token1"}
        )
        print("token_check:")
        pprint.pprint(token_check)
        for worker_name, results in token_check.items():
            results["result"] == True, f"{worker_name} token1 is not valid"

    def test_get_fastapi_openapi_schema(self, nfclient):
        ret = nfclient.run_job("fastapi", "get_openapi_schema")
        pprint.pprint(ret)

        for worker_name, results in ret.items():
            assert results["result"], f"{worker_name} No Openapi schema returned"
            assert results["result"][
                "paths"
            ], f"{worker_name} Openapi schema has no route paths"


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
        assert len(res["workers"]) > 0, f"No workers targeted"

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
        assert len(res["workers"]) > 0, f"No workers targeted"

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
        assert get_res["status"] == "202"
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
                {"suite": "nf://nornir_test_suites/suite_1.txt", "FC": "spine", "workers": "nornir-worker-1"}
            ),
        )

        resp.raise_for_status()

        pprint.pprint(resp.json())

        for wname, wres in resp.json().items():
            assert wres["failed"] == True, f"{wname} - should have failed tests"
            assert "ceos-spine-1" in wres["result"]
            assert "ceos-spine-2" in wres["result"]
            assert wres["status"] == "completed"
