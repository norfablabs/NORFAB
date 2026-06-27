import pprint
import pytest

pytestmark = [pytest.mark.fastapi, pytest.mark.worker, pytest.mark.task_fastapi_worker]


@pytest.mark.task_fastapi_worker
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
