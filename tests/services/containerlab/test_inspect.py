import pprint
import pytest

try:
    from tests.services.containerlab.common import (
        wait_for_containerlab_worker,
    )
except ModuleNotFoundError as exc:
    if exc.name not in {
        "tests",
        "tests.services",
        "tests.services.containerlab",
        "tests.services.containerlab.common",
    }:
        raise
    from services.containerlab.common import (
        wait_for_containerlab_worker,
    )

pytestmark = [
    pytest.mark.containerlab,
    pytest.mark.inspect,
    pytest.mark.task_containerlab_inspect,
]


@pytest.mark.task_containerlab_inspect
class TestInspectTask:
    def test_inspect_all(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        ret = nfclient.run_job("containerlab", "inspect")
        pprint.pprint(ret)

        for w, r in ret.items():
            assert r["failed"] == False, f"{w} - failed to inspect labs"
            assert (
                len(list(r["result"].keys())) > 0
            ), f"{w} - no containerlab labs details returned"
            for lab_name, containers in r["result"].items():
                assert (
                    len(containers) > 0
                ), f"{w} - no container {lab_name} lab has no containers"

    def test_inspect_by_lab_name(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        ret = nfclient.run_job(
            "containerlab", "inspect", kwargs={"lab_name": "three-routers-lab"}
        )
        pprint.pprint(ret)

        for w, r in ret.items():
            assert r["failed"] == False, f"{w} - failed to inspect labs"
            assert (
                len(list(r["result"].keys())) > 0
            ), f"{w} - no containerlab labs details returned"
            assert all(
                "clab-three-routers" in cntr["name"]
                for cntr in r["result"]["three-routers-lab"]
            ), f"{w} - did not filter container by lab name properly"

    def test_inspect_details(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        ret = nfclient.run_job(
            "containerlab",
            "inspect",
            kwargs={"lab_name": "three-routers-lab", "details": True},
        )
        pprint.pprint(ret)

        for w, r in ret.items():
            assert r["failed"] == False, f"{w} - failed to inspect labs"
            assert len(r["result"]) > 0, f"{w} - no container details returned"
            assert (
                len(list(r["result"].keys())) > 0
            ), f"{w} - no containerlab labs details returned"
            for lab_name, containers in r["result"].items():
                assert (
                    len(containers) > 0
                ), f"{w} - no container {lab_name} lab has no containers"
                assert all(
                    k in containers[0]
                    for k in ["ID", "Labels", "Mounts", "Names", "NetworkSettings"]
                ), f"{w} - no container missing details, lab {lab_name}"

    def test_inspect_nonexist_lab(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        ret = nfclient.run_job(
            "containerlab", "inspect", kwargs={"lab_name": "nonexist"}
        )
        pprint.pprint(ret)

        for w, r in ret.items():
            assert r["failed"] == True, f"{w} - should have failed"
