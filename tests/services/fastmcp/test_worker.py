import pprint

import pytest

try:
    from tests.services.fastmcp.common import ensure_tool_discovered
except ModuleNotFoundError as exc:
    if exc.name not in {
        "tests",
        "tests.services",
        "tests.services.fastmcp",
        "tests.services.fastmcp.common",
    }:
        raise
    from services.fastmcp.common import ensure_tool_discovered

pytestmark = [pytest.mark.fastmcp, pytest.mark.worker, pytest.mark.task_fastmcp_worker]


@pytest.mark.task_fastmcp_worker
class TestFastMCPWorker:
    tools_discovered = {}

    def test_get_fastmcp_inventory(self, nfclient):
        ret = nfclient.run_job("fastmcp", "get_inventory")
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert all(
                k in data["result"] for k in ["fastmcp", "service"]
            ), f"{worker_name} inventory incomplete"

    def test_get_fastmcp_version(self, nfclient):
        ret = nfclient.run_job("fastmcp", "get_version")
        pprint.pprint(ret)

        assert isinstance(ret, dict), f"Expected dictionary but received {type(ret)}"
        for worker_name, version_report in ret.items():
            for package, version in version_report["result"].items():
                assert version != "", f"{worker_name}:{package} version is empty"

    def test_get_fastmcp_status(self, nfclient):
        ensure_tool_discovered(self, nfclient, "nornir", "cli")
        ret = nfclient.run_job("fastmcp", "get_status")
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert all(
                data["result"][k]
                for k in ["name", "url", "tools_count", "prompts_count"]
            ), f"{worker_name} status data incomplete"

    def test_bearer_token_store_check_list_delete(self, nfclient):
        username = "test_fastmcp_bearer_token"
        token = "fastmcp-token-1"

        nfclient.run_job(
            "fastmcp",
            "bearer_token_delete",
            kwargs={"username": username},
        )

        stored = nfclient.run_job(
            "fastmcp",
            "bearer_token_store",
            kwargs={"username": username, "token": token, "expire": 60},
        )
        pprint.pprint(stored)
        for worker_name, results in stored.items():
            assert results["result"] == True, f"{worker_name} failed storing token"

        checked = nfclient.run_job(
            "fastmcp", "bearer_token_check", kwargs={"token": token}
        )
        pprint.pprint(checked)
        for worker_name, results in checked.items():
            assert results["result"] == True, f"{worker_name} token is not valid"

        listed = nfclient.run_job(
            "fastmcp", "bearer_token_list", kwargs={"username": username}
        )
        pprint.pprint(listed)
        for worker_name, results in listed.items():
            assert results["result"][0]["username"] == username
            assert results["result"][0]["token"] == token

        deleted = nfclient.run_job(
            "fastmcp", "bearer_token_delete", kwargs={"token": token}
        )
        pprint.pprint(deleted)
        for worker_name, results in deleted.items():
            assert results["result"] == True, f"{worker_name} failed deleting token"
