import os
import pprint

import pytest

pytestmark = [
    pytest.mark.filesharing,
    pytest.mark.fetch_file,
    pytest.mark.task_filesharing_fetch_file,
]


@pytest.mark.task_filesharing_fetch_file
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

        assert ret["status"] == "200", "failed to fetch file"
        assert ret["content"], "no file path returned"
        assert os.path.exists(ret["content"]), "file does not exist"

    def test_fetch_file_read(self, nfclient):
        """Test fetching a small file in one chunk"""
        nfclient.delete_fetched_files(filepath="*test_file_1.txt")
        ret = nfclient.fetch_file(url="nf://filesharing/test_file_1.txt", read=True)
        pprint.pprint(ret)

        assert ret["status"] == "200", "failed to fetch file"
        assert (
            ret["content"]
            == "This is test file 1 content.\nLine 2 of test file 1.\nLine 3 of test file 1.\n"
        ), "file content is workng"

    def test_fetch_file_with_pipeline(self, nfclient):
        """Test fetching a small file in one chunk"""
        nfclient.delete_fetched_files(filepath="*test_file_1.txt")
        ret = nfclient.fetch_file(
            url="nf://filesharing/test_file_1.txt",
            chunk_size=10,
            pipeline=5,
        )
        pprint.pprint(ret)

        assert ret["status"] == "200", "failed to fetch file"
        assert ret["content"], "no file path returned"
        assert os.path.exists(ret["content"]), "file does not exist"

    def test_fetch_file_non_existent(self, nfclient):
        """Test fetching a non-existent file"""
        ret = nfclient.fetch_file(url="nf://filesharing/non_existent_file.txt")
        pprint.pprint(ret)

        assert ret["status"] == "404", "file fetch status is wrong"
        assert ret["content"] == None, "content should be empty"
        assert ret["error"], "expected error"

    def test_fetch_file_invalid_url_format(self, nfclient):
        """Test fetch_file with invalid URL format"""
        ret = nfclient.fetch_file(url="http://invalid")
        pprint.pprint(ret)

        assert ret["status"] == "500", "file fetch status is wrong"
        assert ret["content"] == None, "content should be empty"
        assert ret["error"], "expected error"

    def test_fetch_file_nested_file(self, nfclient):
        """Test fetching a file from a subdirectory"""
        nfclient.delete_fetched_files(filepath="*nested_file.txt")
        ret = nfclient.fetch_file(url="nf://filesharing/subdir1/nested_file.txt")
        pprint.pprint(ret)

        assert ret["status"] == "200", "failed to fetch file"
        assert ret["content"], "no file path returned"
        assert os.path.exists(ret["content"]), "file does not exist"

    def test_fetch_file_large_file_with_small_chunks(self, nfclient):
        """Test fetching a large file with small 25-byte chunks"""
        nfclient.delete_fetched_files(filepath="*large_file.txt")
        ret = nfclient.fetch_file(url="nf://filesharing/large_file.txt", chunk_size=25)
        pprint.pprint(ret)

        assert ret["status"] == "200", "failed to fetch file"
        assert ret["content"], "no file path returned"
        assert os.path.exists(ret["content"]), "file does not exist"

    @pytest.mark.parametrize(
        "url",
        [
            "nf://../pyproject.toml",
            "nf://..\\pyproject.toml",
            "nf://filesharing/../../pyproject.toml",
            "nf://filesharing/..\\..\\pyproject.toml",
        ],
    )
    def test_fetch_file_rejects_path_traversal(self, nfclient, url):
        """Client should reject nf:// paths that escape fetchedfiles root."""
        ret = nfclient.fetch_file(url=url)
        pprint.pprint(ret)

        assert ret["status"] == "500", "expected client-side rejection"
        assert ret["content"] is None, "content should be empty"
        assert ret["error"], "expected error"
        assert "Invalid url path" in ret["error"], "wrong error message"
