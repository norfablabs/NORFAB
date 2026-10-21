import os
import pprint
import shutil
import threading
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

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
        ), "file content is wrong"

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
        assert ret["content"] is None, "content should be empty"
        assert ret["error"], "expected error"

    def test_fetch_file_invalid_url_format(self, nfclient):
        """Test fetch_file with invalid URL format"""
        ret = nfclient.fetch_file(url="http://invalid")
        pprint.pprint(ret)

        assert ret["status"] == "500", "file fetch status is wrong"
        assert ret["content"] is None, "content should be empty"
        assert ret["error"], "expected error"

    def test_fetch_file_invalid_git_url_format(self, nfclient):
        """Test that a Git URL includes both a remote and file path."""
        ret = nfclient.fetch_file(url="git://filesharing")

        assert ret["status"] == "404", "file fetch status is wrong"
        assert ret["content"] is None, "content should be empty"
        assert ret["error"] == "file not found"

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
            assert ret["error"] == "file not found"
        else:
            assert "Invalid url path" in ret["error"], "wrong error message"


@pytest.fixture
def published_files(nfclient: NFPClient) -> Iterator[tuple[Path, str]]:
    """Publish test-owned files through the real FileSharing worker."""
    root = (Path(nfclient.inventory.base_dir) / "filesharing").resolve()
    directory = root / f"fetch-batch-{uuid4().hex}"
    directory.mkdir()
    try:
        yield directory, f"nf://filesharing/{directory.name}"
    finally:
        nfclient.delete_fetched_files(filepath=f"filesharing/{directory.name}")
        assert directory.resolve().parent == root
        shutil.rmtree(directory)
        mirror = root / "worker2" / "filesharing" / directory.name
        if mirror.exists():
            assert (
                mirror.resolve().parent == (root / "worker2" / "filesharing").resolve()
            )
            shutil.rmtree(mirror)


class TestFetchFileBatch:
    def test_cached_batch_uses_one_metadata_job(
        self, nfclient: NFPClient, published_files: tuple[Path, str]
    ) -> None:
        source, prefix = published_files
        urls = []
        for index in range(101):
            name = f"file{index}.txt"
            (source / name).write_text(str(index), encoding="utf-8")
            cached = (
                Path(nfclient.base_dir)
                / "fetchedfiles"
                / "filesharing"
                / source.name
                / name
            )
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_text(str(index), encoding="utf-8")
            urls.append(f"{prefix}/{name}")
        requested = urls + urls[:2]
        before = set(nfclient.job_futures)
        results = nfclient.fetch_file(requested, read=True)
        jobs = [
            nfclient.job_db.get_job(uuid) for uuid in set(nfclient.job_futures) - before
        ]

        assert [entry["content"] for entry in results] == [
            str(i) for i in range(101)
        ] + ["0", "1"]
        assert all(entry["status"] == "200" for entry in results)
        assert results[0] is not results[-2]
        assert len(jobs) == 1
        assert jobs[0]["task"] == "file_details"
        assert jobs[0]["kwargs"]["url"] == requested
        assert jobs[0]["workers_requested"] == "all"
        assert nfclient.file_transfers == {}

    def test_batch_streams_changed_empty_and_multichunk_files(
        self, nfclient: NFPClient, published_files: tuple[Path, str]
    ) -> None:
        source, prefix = published_files
        changed = source / "changed.txt"
        changed.write_text("old contents", encoding="utf-8")
        assert (
            nfclient.fetch_file(f"{prefix}/changed.txt", read=True)["content"]
            == "old contents"
        )
        contents = {
            "changed.txt": "new contents",
            "empty.txt": "",
            "large.txt": "abcdefgh" * 20,
        }
        for name, content in contents.items():
            (source / name).write_text(content, encoding="utf-8")
        results = nfclient.fetch_file(
            [f"{prefix}/{name}" for name in contents],
            chunk_size=7,
            pipeline=3,
            read=True,
        )

        assert [entry["content"] for entry in results] == list(contents.values())
        assert all(entry["status"] == "200" for entry in results)
        assert nfclient.file_transfers == {}

    def test_batch_preserves_success_among_missing_and_unsafe_files(
        self, nfclient: NFPClient, published_files: tuple[Path, str]
    ) -> None:
        source, prefix = published_files
        (source / "good.txt").write_text("ok", encoding="utf-8")
        results = nfclient.fetch_file(
            [
                f"{prefix}/missing",
                f"{prefix}/good.txt",
                "nf://../../outside",
                "http://invalid",
            ],
            read=True,
        )

        assert [entry["status"] for entry in results] == ["404", "200", "500", "500"]
        assert results[1]["content"] == "ok"
        assert all(entry["error"] for index, entry in enumerate(results) if index != 1)

    def test_empty_and_invalid_inputs_submit_no_jobs(self, nfclient: NFPClient) -> None:
        before = set(nfclient.job_futures)
        assert nfclient.fetch_file([]) == []
        for invalid in [None, 1, ("nf://file.txt",), ["nf://file.txt", None]]:
            with pytest.raises(TypeError):
                nfclient.fetch_file(invalid)
        assert set(nfclient.job_futures) == before

    def test_batch_raises_on_local_write_failure(
        self, nfclient: NFPClient, published_files: tuple[Path, str]
    ) -> None:
        source, prefix = published_files
        for name in ["bad", "good"]:
            (source / name).write_text(name, encoding="utf-8")
        blocked = (
            Path(nfclient.base_dir)
            / "fetchedfiles"
            / "filesharing"
            / source.name
            / "bad"
        )
        blocked.mkdir(parents=True)
        with pytest.raises(OSError):
            nfclient.fetch_file([f"{prefix}/bad", f"{prefix}/good"], read=True)
        assert nfclient.file_transfers == {}
        blocked.rmdir()
        assert nfclient.fetch_file(f"{prefix}/bad", read=True)["content"] == "bad"

    def test_batch_rotates_workers_and_skips_missing_files(
        self, nfclient: NFPClient, published_files: tuple[Path, str]
    ) -> None:
        source, prefix = published_files
        mirror = source.parent / "worker2" / "filesharing" / source.name
        mirror.mkdir(parents=True)
        for directory, names in [
            (source, ["first", "shared1", "shared2"]),
            (mirror, ["second", "shared1", "shared2"]),
        ]:
            for name in names:
                (directory / name).write_text(name, encoding="utf-8")
        before = set(nfclient.job_futures)
        names = ["second", "first", "shared1", "shared2", "missing"]
        results = nfclient.fetch_file([f"{prefix}/{name}" for name in names], read=True)
        jobs = [
            nfclient.job_db.get_job(uuid)
            for uuid in nfclient.job_futures
            if uuid not in before
        ]
        assert [entry["content"] for entry in results] == names[:-1] + [None]
        assert [entry["status"] for entry in results] == ["200"] * 4 + ["404"]
        assert sorted(jobs[0]["workers_dispatched"]) == [
            "filesharing-worker-1",
            "filesharing-worker-2",
        ]
        assert [
            job["workers_requested"] for job in jobs if job["task"] == "fetch_file"
        ] == [
            ["filesharing-worker-2"],
            ["filesharing-worker-1"],
            ["filesharing-worker-2"],
            ["filesharing-worker-1"],
        ]

    def test_discovery_timeout_returns_missing_file(self, nfclient: NFPClient) -> None:
        result = nfclient.fetch_file("nf://filesharing/test_file_1.txt", timeout=0)
        assert result["status"] == "404"
        assert result == {"status": "404", "content": None, "error": "file not found"}

    def test_failed_stream_preserves_worker_error(
        self, nfclient: NFPClient, published_files: tuple[Path, str]
    ) -> None:
        source, prefix = published_files
        published = source / "interrupted.txt"
        published.write_bytes(b"x" * 1024 * 1024)
        stopped = threading.Event()
        truncated = threading.Event()

        def truncate_during_transfer() -> None:
            while not stopped.wait(0.001):
                for state in list(nfclient.file_transfers.values()):
                    if (
                        Path(state["destination"].name).name == published.name
                        and state["total_bytes_received"] > 0
                    ):
                        published.write_bytes(b"")
                        truncated.set()
                        return

        thread = threading.Thread(target=truncate_during_transfer)
        thread.start()
        try:
            result = nfclient.fetch_file(f"{prefix}/{published.name}", chunk_size=32)
            assert truncated.is_set()
            assert result["status"] == "404"
            assert "chunk timeout" in str(result["error"])
            assert "MD5 hash mismatch" not in str(result["error"])
            assert nfclient.file_transfers == {}
        finally:
            stopped.set()
            thread.join(timeout=2)
