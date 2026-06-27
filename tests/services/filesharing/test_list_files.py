import pprint

import pytest

pytestmark = [
    pytest.mark.filesharing,
    pytest.mark.list_files,
    pytest.mark.task_filesharing_list_files,
]


@pytest.mark.task_filesharing_list_files
class TestListFiles:
    """Test list_files task functionality"""

    def test_list_files_root_directory(self, nfclient):
        """Test listing files in root directory"""
        ret = nfclient.run_job(
            "filesharing",
            "list_files",
            workers=["filesharing-worker-1"],
            kwargs={"url": "nf://filesharing/"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"] is not None, f"{worker} returned None result"
            assert isinstance(
                results["result"], list
            ), f"{worker} did not return a list"
            assert results["failed"] is False, f"{worker} failed to list files"
            # Check that our test files are present
            assert (
                "test_file_1.txt" in results["result"]
            ), f"{worker} missing test_file_1.txt"
            assert (
                "test_file_2.txt" in results["result"]
            ), f"{worker} missing test_file_2.txt"

    def test_list_files_subdirectory(self, nfclient):
        """Test listing files in a subdirectory"""
        ret = nfclient.run_job(
            "filesharing",
            "list_files",
            workers=["filesharing-worker-1"],
            kwargs={"url": "nf://filesharing/subdir1"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"] is not None, f"{worker} returned None result"
            assert isinstance(
                results["result"], list
            ), f"{worker} did not return a list"
            assert results["failed"] is False, f"{worker} failed to list files"
            assert (
                "nested_file.txt" in results["result"]
            ), f"{worker} missing nested_file.txt in subdir1"

    def test_list_files_invalid_url_format(self, nfclient):
        """Test list_files with invalid URL format"""
        ret = nfclient.run_job(
            "filesharing",
            "list_files",
            workers=["filesharing-worker-1"],
            kwargs={"url": "http://invalid"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is True, f"{worker} did not fail as expected"
            assert (
                "invalid URL format" in results["errors"][0]
            ), f"{worker} returned wrong error message"

    def test_list_files_non_existent_directory(self, nfclient):
        """Test list_files with non-existent directory"""
        ret = nfclient.run_job(
            "filesharing",
            "list_files",
            workers=["filesharing-worker-1"],
            kwargs={"url": "nf://filesharing/non_existent_dir"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is True, f"{worker} did not fail as expected"
            assert (
                "Directory Not Found" in results["errors"]
            ), f"{worker} returned wrong error message"

    @pytest.mark.parametrize(
        "url",
        [
            "nf://../pyproject.toml",
            "nf://..\\pyproject.toml",
            "nf://filesharing/../../pyproject.toml",
            "nf://filesharing/..\\..\\pyproject.toml",
        ],
    )
    def test_list_files_rejects_path_traversal(self, nfclient, url):
        """Worker should reject nf:// paths that escape base_dir."""
        ret = nfclient.run_job(
            "filesharing",
            "list_files",
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
# FILE DETAILS TESTS
# ----------------------------------------------------------------------------
