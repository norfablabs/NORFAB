import pprint
import pytest

pytestmark = [
    pytest.mark.nornir,
    pytest.mark.file_copy,
    pytest.mark.task_nornir_file_copy,
]


@pytest.mark.task_nornir_file_copy
class TestNornirFileCopy:
    def test_file_copy_dry_run(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "file_copy",
            workers=["nornir-worker-1"],
            kwargs={
                "source_file": "nf://nornir/files/file_copy_test.txt",
                "dry_run": True,
                "FC": "spine",
                "enable": True,
            },
        )

        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            for host, res in results["result"].items():
                assert "spine" in host
                assert "socket_timeout" in res["file_copy_dry_run"]
                assert "source_file" in res["file_copy_dry_run"]
                assert "dest_file" in res["file_copy_dry_run"]

    def test_file_copy(self, nfclient):
        # delete file first
        file_delete = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-1"],
            kwargs={
                "commands": "delete file_copy_test.txt",
                "FC": "spine",
                "enable": True,
            },
        )
        print("File delete result:")
        pprint.pprint(file_delete)

        # copy file
        file_copy = nfclient.run_job(
            "nornir",
            "file_copy",
            workers=["nornir-worker-1"],
            kwargs={
                "source_file": "nf://nornir/files/file_copy_test.txt",
                "FC": "spine",
                "FM": "arista_eos",
            },
        )
        print("File copy result:")
        pprint.pprint(file_copy)

        # verify file copied
        file_dir = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-1"],
            kwargs={"commands": "dir", "FC": "spine", "enable": True},
        )
        print("File dir result:")
        pprint.pprint(file_dir)

        for worker, results in file_delete.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"

        for worker, results in file_copy.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            for host, res in results["result"].items():
                assert "spine" in host
                assert res["netmiko_file_transfer"] == True

        for worker, results in file_dir.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            for host, res in results["result"].items():
                assert "file_copy_test.txt" in res["dir"], f"{host} - file not copied"

    def test_file_copy_non_existing_file(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "file_copy",
            workers=["nornir-worker-1"],
            kwargs={
                "source_file": "nf://nornir/files/file_not_exist.txt",
                "FC": "spine",
                "FM": "arista_eos",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"] is None, f"{worker} returned results"
            assert results["failed"] is True, f"{worker} did not fail to run the task"
            assert "fetch file failed" in results["errors"][0]


# ----------------------------------------------------------------------------
# NORNIR RUNTIME INVENTORY TESTS
# ----------------------------------------------------------------------------
