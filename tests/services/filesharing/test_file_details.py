import hashlib
import os
import pprint

import pytest

pytestmark = [
    pytest.mark.filesharing,
    pytest.mark.file_details,
    pytest.mark.task_filesharing_file_details,
]


@pytest.mark.task_filesharing_file_details
class TestFileDetails:
    """Test file_details task functionality"""

    def test_file_details_existing_file(self, nfclient):
        """Test getting details of an existing file"""
        ret = nfclient.run_job(
            "filesharing",
            "file_details",
            workers=["filesharing-worker-1"],
            kwargs={"url": "nf://filesharing/test_file_1.txt"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"] is not None, f"{worker} returned None result"
            assert results["failed"] is False, f"{worker} failed to get file details"
            assert "md5hash" in results["result"], f"{worker} missing md5hash in result"
            assert (
                "size_bytes" in results["result"]
            ), f"{worker} missing size_bytes in result"
            assert "exists" in results["result"], f"{worker} missing exists in result"
            assert results["result"]["exists"] is True, f"{worker} file should exist"
            assert (
                results["result"]["md5hash"] is not None
            ), f"{worker} md5hash should not be None"
            assert (
                results["result"]["size_bytes"] > 0
            ), f"{worker} file size should be greater than 0"

    def test_file_details_verify_md5hash(self, nfclient):
        """Test that md5hash is calculated correctly"""
        # Read the actual file and calculate MD5
        file_path = os.path.join("nf_tests_inventory", "filesharing", "test_file_1.txt")
        with open(file_path, "rb") as f:
            content = f.read()
        expected_md5 = hashlib.md5(content).hexdigest()

        ret = nfclient.run_job(
            "filesharing",
            "file_details",
            workers=["filesharing-worker-1"],
            kwargs={"url": "nf://filesharing/test_file_1.txt"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert (
                results["result"]["md5hash"] == expected_md5
            ), f"{worker} MD5 hash mismatch"

    def test_file_details_non_existent_file(self, nfclient):
        """Test getting details of a non-existent file"""
        ret = nfclient.run_job(
            "filesharing",
            "file_details",
            workers=["filesharing-worker-1"],
            kwargs={"url": "nf://filesharing/non_existent_file.txt"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is True, f"{worker} did not fail as expected"
            assert (
                "file not found" in results["errors"][0]
            ), f"{worker} returned wrong error message"

    def test_file_details_invalid_url_format(self, nfclient):
        """Test file_details with invalid URL format"""
        ret = nfclient.run_job(
            "filesharing",
            "file_details",
            workers=["filesharing-worker-1"],
            kwargs={"url": "ftp://invalid"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is True, f"{worker} did not fail as expected"
            assert (
                "invalid URL format" in results["errors"][0]
            ), f"{worker} returned wrong error message"

    def test_file_details_nested_file(self, nfclient):
        """Test getting details of a file in a subdirectory"""
        ret = nfclient.run_job(
            "filesharing",
            "file_details",
            workers=["filesharing-worker-1"],
            kwargs={"url": "nf://filesharing/subdir1/nested_file.txt"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"] is not None, f"{worker} returned None result"
            assert results["failed"] is False, f"{worker} failed to get file details"
            assert (
                results["result"]["exists"] is True
            ), f"{worker} nested file should exist"
            assert (
                results["result"]["md5hash"] is not None
            ), f"{worker} md5hash should not be None"

    @pytest.mark.parametrize(
        "url",
        [
            "nf://../pyproject.toml",
            "nf://..\\pyproject.toml",
            "nf://filesharing/../../pyproject.toml",
            "nf://filesharing/..\\..\\pyproject.toml",
        ],
    )
    def test_file_details_rejects_path_traversal(self, nfclient, url):
        """Worker should reject nf:// paths that escape base_dir."""
        ret = nfclient.run_job(
            "filesharing",
            "file_details",
            workers=["filesharing-worker-1"],
            kwargs={"url": url},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is True, f"{worker} did not fail as expected"
            assert results.get("errors"), f"{worker} expected errors"
            assert (
                "invalid URL path" in results["errors"][0]
                or "invalid URL format" in results["errors"][0]
            ), f"{worker} returned wrong error message: {results['errors']}"


# ----------------------------------------------------------------------------
# WALK TESTS
# ----------------------------------------------------------------------------
