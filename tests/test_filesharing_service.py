import pprint
import pytest
import hashlib
import os

# ----------------------------------------------------------------------------
# FILESHARING WORKER TESTS
# ----------------------------------------------------------------------------


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


# ----------------------------------------------------------------------------
# FILE DETAILS TESTS
# ----------------------------------------------------------------------------


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


# ----------------------------------------------------------------------------
# WALK TESTS
# ----------------------------------------------------------------------------


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
                "nf://filesharing//large_file.txt",
                "nf://filesharing//test_file_1.txt",
                "nf://filesharing//test_file_2.txt",
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


# ----------------------------------------------------------------------------
# FETCH FILE TESTS
# ----------------------------------------------------------------------------


class TestFetchFile:
    """Test fetch_file task functionality"""

    def test_fetch_file(self, nfclient):
        """Test fetching a small file in one chunk"""
        nfclient.delete_fetched_files(filepath="*test_file_1.txt")
        ret = nfclient.fetch_file(
            url="nf://filesharing/test_file_1.txt",
            chunk_size=1024,
        )
        pprint.pprint(ret)

        assert ret["status"] == "200", f"failed to fetch file"
        assert ret["content"], f"no file path returned"
        assert os.path.exists(ret["content"]), f"file does not exist"

    def test_fetch_file_read(self, nfclient):
        """Test fetching a small file in one chunk"""
        nfclient.delete_fetched_files(filepath="*test_file_1.txt")
        ret = nfclient.fetch_file(url="nf://filesharing/test_file_1.txt", read=True)
        pprint.pprint(ret)

        assert ret["status"] == "200", f"failed to fetch file"
        assert (
            ret["content"]
            == "This is test file 1 content.\nLine 2 of test file 1.\nLine 3 of test file 1.\n"
        ), f"file content is workng"

    def test_fetch_file_with_pipeline(self, nfclient):
        """Test fetching a small file in one chunk"""
        nfclient.delete_fetched_files(filepath="*test_file_1.txt")
        ret = nfclient.fetch_file(
            url="nf://filesharing/test_file_1.txt",
            chunk_size=10,
            pipeline=5,
        )
        pprint.pprint(ret)

        assert ret["status"] == "200", f"failed to fetch file"
        assert ret["content"], f"no file path returned"
        assert os.path.exists(ret["content"]), f"file does not exist"

    def test_fetch_file_non_existent(self, nfclient):
        """Test fetching a non-existent file"""
        ret = nfclient.fetch_file(url="nf://filesharing/non_existent_file.txt")
        pprint.pprint(ret)

        assert ret["status"] == "404", f"file fetch status is wrong"
        assert ret["content"] == None, f"content should be empty"
        assert ret["error"], f"expected error"

    def test_fetch_file_invalid_url_format(self, nfclient):
        """Test fetch_file with invalid URL format"""
        ret = nfclient.fetch_file(url="http://invalid")
        pprint.pprint(ret)

        assert ret["status"] == "500", f"file fetch status is wrong"
        assert ret["content"] == None, f"content should be empty"
        assert ret["error"], f"expected error"

    def test_fetch_file_nested_file(self, nfclient):
        """Test fetching a file from a subdirectory"""
        nfclient.delete_fetched_files(filepath="*nested_file.txt")
        ret = nfclient.fetch_file(url="nf://filesharing/subdir1/nested_file.txt")
        pprint.pprint(ret)

        assert ret["status"] == "200", f"failed to fetch file"
        assert ret["content"], f"no file path returned"
        assert os.path.exists(ret["content"]), f"file does not exist"

    def test_fetch_file_large_file_with_small_chunks(self, nfclient):
        """Test fetching a large file with small 25-byte chunks"""
        nfclient.delete_fetched_files(filepath="*large_file.txt")
        ret = nfclient.fetch_file(url="nf://filesharing/large_file.txt", chunk_size=25)
        pprint.pprint(ret)

        assert ret["status"] == "200", f"failed to fetch file"
        assert ret["content"], f"no file path returned"
        assert os.path.exists(ret["content"]), f"file does not exist"
