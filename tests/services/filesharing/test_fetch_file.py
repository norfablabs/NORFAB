import hashlib
import os
import pprint
from typing import Any

import pytest

from norfab.core.client import NFPClient

pytestmark = [
    pytest.mark.filesharing,
    pytest.mark.filesharing_fetch_file,
]


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

    def test_fetch_file_invalid_git_url_format(self, nfclient):
        """Test that a Git URL includes both a remote and file path."""
        ret = nfclient.fetch_file(url="git://filesharing")

        assert ret["status"] == "404", "file fetch status is wrong"
        assert ret["content"] is None, "content should be empty"
        assert ret["error"] == "Git URL resolution failed"

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
            "git://filesharing/../../pyproject.toml",
            "git://filesharing/..\\..\\pyproject.toml",
        ],
    )
    def test_fetch_file_rejects_path_traversal(self, nfclient, url):
        """Client should reject file URLs that escape fetchedfiles root."""
        ret = nfclient.fetch_file(url=url)
        pprint.pprint(ret)

        expected_status = "404" if url.startswith("git://") else "500"
        assert ret["status"] == expected_status, "expected unsafe path rejection"
        assert ret["content"] is None, "content should be empty"
        assert ret["error"], "expected error"
        if url.startswith("git://"):
            assert ret["error"] == "Git URL resolution failed"
        else:
            assert "Invalid url path" in ret["error"], "wrong error message"


class TestFetchFileGitUrl:
    def test_fetch_git_url_resolves_custom_mount(self, tmp_path: Any) -> None:
        """Client should sync a remote and fetch from its owning worker and mount."""
        client = NFPClient.__new__(NFPClient)
        client.base_dir = str(tmp_path)
        client.file_transfers = {}
        destination = (
            tmp_path / "fetchedfiles" / "repositories" / "network-assets" / "README.md"
        )
        destination.parent.mkdir(parents=True)
        content = "Git-backed file content"
        destination.write_text(content, encoding="utf-8")
        md5hash = hashlib.md5(content.encode()).hexdigest()
        calls = []

        class JobDatabase:
            @staticmethod
            def get_job(_uuid: str) -> None:
                return None

        def run_job(**kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            worker = "filesharing-worker-1"
            if kwargs["task"] == "resolve_git_url":
                return {
                    worker: {
                        "failed": False,
                        "result": "nf://repositories/network-assets/README.md",
                    }
                }
            if kwargs["task"] == "file_details":
                return {
                    worker: {
                        "failed": False,
                        "result": {
                            "md5hash": md5hash,
                            "size_bytes": len(content),
                            "exists": True,
                        },
                    }
                }
            raise AssertionError(f"Unexpected task {kwargs['task']}")

        client.job_db = JobDatabase()
        client.run_job = run_job

        result = client.fetch_file("git://network-assets/README.md", read=True)

        assert result == {"status": "200", "content": content, "error": None}
        assert [call["task"] for call in calls] == [
            "resolve_git_url",
            "file_details",
        ]
        assert calls[-1]["workers"] == ["filesharing-worker-1"]
        assert calls[-1]["kwargs"]["url"] == (
            "nf://repositories/network-assets/README.md"
        )
