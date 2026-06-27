import pprint

import pytest

pytestmark = [
    pytest.mark.filesharing,
    pytest.mark.walk,
    pytest.mark.task_filesharing_walk,
]


@pytest.mark.task_filesharing_walk
class TestWalk:
    """Test walk task functionality"""

    def test_walk_root_directory(self, nfclient):
        """Test walking root directory recursively"""
        ret = nfclient.run_job(
            "filesharing",
            "walk",
            workers=["filesharing-worker-1"],
            kwargs={"url": "nf://filesharing/"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"] is not None, f"{worker} returned None result"
            assert isinstance(
                results["result"], list
            ), f"{worker} did not return a list"
            assert results["failed"] is False, f"{worker} failed to walk directory"
            # Check that all files are present
            for f in [
                "nf://filesharing/large_file.txt",
                "nf://filesharing/test_file_1.txt",
                "nf://filesharing/test_file_2.txt",
                "nf://filesharing/subdir1/nested_file.txt",
                "nf://filesharing/subdir2/another_nested.txt",
            ]:

                assert (
                    f in results["result"]
                ), f"{worker} missing {f} nested file in subdir2"

    def test_walk_subdirectory(self, nfclient):
        """Test walking a specific subdirectory"""
        ret = nfclient.run_job(
            "filesharing",
            "walk",
            workers=["filesharing-worker-1"],
            kwargs={"url": "nf://filesharing/subdir1"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"] is not None, f"{worker} returned None result"
            assert isinstance(
                results["result"], list
            ), f"{worker} did not return a list"
            assert results["failed"] is False, f"{worker} failed to walk directory"
            assert (
                "nf://filesharing/subdir1/nested_file.txt" in results["result"]
            ), f"{worker} nf://filesharing/subdir1/nested_file.txt"

    def test_walk_invalid_url_format(self, nfclient):
        """Test walk with invalid URL format"""
        ret = nfclient.run_job(
            "filesharing",
            "walk",
            workers=["filesharing-worker-1"],
            kwargs={"url": "http://invalid"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is True, f"{worker} did not fail as expected"
            assert (
                "invalid URL format" in results["errors"][0]
            ), f"{worker} returned wrong error message"

    def test_walk_non_existent_directory(self, nfclient):
        """Test walk with non-existent directory"""
        ret = nfclient.run_job(
            "filesharing",
            "walk",
            workers=["filesharing-worker-1"],
            kwargs={"url": "nf://filesharing/does_not_exist"},
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
    def test_walk_rejects_path_traversal(self, nfclient, url):
        """Worker should reject nf:// paths that escape base_dir."""
        ret = nfclient.run_job(
            "filesharing",
            "walk",
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
# FETCH FILE TESTS
# ----------------------------------------------------------------------------
