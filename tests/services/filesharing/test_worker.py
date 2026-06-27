import pprint
import pytest

pytestmark = [
    pytest.mark.filesharing,
    pytest.mark.worker,
    pytest.mark.task_filesharing_worker,
]


@pytest.mark.task_filesharing_worker
class TestFileSharingWorker:
    """Test basic FileSharingWorker functionality"""

    def test_get_version(self, nfclient):
        """Test get_version task returns version information"""
        ret = nfclient.run_job("filesharing", "get_version")
        pprint.pprint(ret)

        assert isinstance(ret, dict), f"Expected dictionary but received {type(ret)}"
        for worker_name, version_report in ret.items():
            assert (
                version_report["result"] is not None
            ), f"{worker_name} returned None result"
            assert isinstance(
                version_report["result"], dict
            ), f"{worker_name} did not return a dictionary"
            assert (
                "python" in version_report["result"]
            ), f"{worker_name} missing python version"
            assert (
                "platform" in version_report["result"]
            ), f"{worker_name} missing platform info"

    def test_get_inventory(self, nfclient):
        """Test get_inventory task returns worker inventory"""
        ret = nfclient.run_job("filesharing", "get_inventory")
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert data["result"] is not None, f"{worker_name} returned None inventory"
            assert isinstance(
                data["result"], dict
            ), f"{worker_name} inventory is not a dictionary"
            assert (
                "base_dir" in data["result"]
            ), f"{worker_name} inventory missing base_dir"

    def test_get_status(self, nfclient):
        """Test get_status task returns OK status"""
        ret = nfclient.run_job("filesharing", "get_status")
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert data["result"] == "OK", f"{worker_name} status is not OK"
            assert data["failed"] is False, f"{worker_name} failed to get status"


# ----------------------------------------------------------------------------
# LIST FILES TESTS
# ----------------------------------------------------------------------------
