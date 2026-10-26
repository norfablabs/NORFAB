import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from git import Actor, Repo

from norfab.core.client import NFPClient

pytestmark = [
    pytest.mark.filesharing,
    pytest.mark.filesharing_git,
]

WORKER = "filesharing-worker-1"
REMOTE = "norfab-gitsync-test-main"
SECONDARY_REMOTE = "norfab-gitsync-test-secondary"
PUBLIC_REMOTE = "norfab-gitsync-test-public"


@pytest.fixture
def local_git_remote(nfclient: NFPClient, tmp_path: Path) -> Iterator[dict[str, str]]:
    """Register a test-owned local repository through the real worker API."""
    source = tmp_path / "repository"
    actor = Actor("NORFAB tests", "tests@example.com")
    with Repo.init(source, initial_branch="main") as repository:
        (source / "a.txt").write_text("first Git file", encoding="utf-8")
        (source / "b.txt").write_text("second Git file", encoding="utf-8")
        repository.index.add(["a.txt", "b.txt"])
        repository.index.commit("test files", author=actor, committer=actor)
    name = f"fetch-batch-{uuid4().hex}"
    mount = f"filesharing/{name}"
    response = nfclient.run_job(
        "filesharing",
        "create_remote_git",
        workers=[WORKER],
        kwargs={
            "name": name,
            "url": source.as_posix(),
            "type": "git",
            "mount": mount,
            "branch": "main",
            "auto_sync": False,
        },
    )[WORKER]
    assert response["failed"] is False, response
    try:
        yield {"name": name, "mount": mount, "source": str(source)}
    finally:
        deleted = nfclient.run_job(
            "filesharing", "delete_remote_git", workers=[WORKER], kwargs={"name": name}
        )[WORKER]
        assert deleted["failed"] is False, deleted
        nfclient.delete_fetched_files(filepath=mount)


@pytest.mark.filesharing_resolve_git_url
class TestResolveGitUrl:
    def test_resolve_git_url_validates_and_resolves_custom_mount(
        self, nfclient: NFPClient, local_git_remote: dict[str, str]
    ) -> None:
        name = local_git_remote["name"]
        mount = local_git_remote["mount"]
        resolved = nfclient.run_job(
            "filesharing",
            "resolve_git_url",
            workers=[WORKER],
            kwargs={"url": f"git://{name}/a.txt"},
        )[WORKER]
        unsafe = nfclient.run_job(
            "filesharing",
            "resolve_git_url",
            workers=[WORKER],
            kwargs={"url": f"git://{name}/../../outside.txt"},
        )[WORKER]

        assert resolved["failed"] is False
        assert resolved["result"] == f"nf://{mount}/a.txt"
        assert unsafe["failed"] is True
        assert unsafe["errors"] == [
            f"'git://{name}/../../outside.txt' - invalid Git URL path"
        ]
        fetched = nfclient.fetch_file(f"git://{name}/a.txt", read=True)
        assert fetched == {"status": "200", "content": "first Git file", "error": None}

    def test_resolve_git_url_supports_client_fetch(self, nfclient: Any) -> None:
        fetched = nfclient.fetch_file(url=f"git://{REMOTE}/README.md", read=True)

        assert fetched["status"] == "200"
        assert "norfab-gitsync-test" in fetched["content"]

    def test_resolve_git_url_returns_published_url(self, nfclient: Any) -> None:
        ret = nfclient.run_job(
            "filesharing",
            "resolve_git_url",
            workers=[WORKER],
            kwargs={"url": f"git://{REMOTE}/README.md"},
        )[WORKER]

        assert ret["failed"] is False
        assert ret["result"] == f"nf://{REMOTE}/README.md"


@pytest.mark.filesharing_get_remotes
class TestGetRemotes:
    def test_get_remotes(self, nfclient: Any) -> None:
        ret = nfclient.run_job("filesharing", "get_remotes", workers=[WORKER])
        result = ret[WORKER]
        remotes = {remote["name"]: remote for remote in result["result"]}

        assert result["failed"] is False
        assert remotes[REMOTE]["url"] == (
            "https://github.com/norfablabs/norfab-gitsync-test.git"
        )
        assert remotes[REMOTE]["branch"] == "main"
        assert remotes[REMOTE]["mount"] == f"nf://{REMOTE}"
        assert remotes[REMOTE]["type"] == "git"
        assert remotes[REMOTE]["status"] in {"unsynchronized", "cloned", "unchanged"}
        assert "last_sync_attempt" in remotes[REMOTE]
        assert remotes[REMOTE]["password"] == "***"
        assert remotes[PUBLIC_REMOTE]["username"] is None
        assert remotes[PUBLIC_REMOTE]["password"] is None
        assert remotes[PUBLIC_REMOTE]["mount"] == f"nf://{PUBLIC_REMOTE}"

    def test_get_remotes_by_name(self, nfclient: Any) -> None:
        ret = nfclient.run_job(
            "filesharing",
            "get_remotes",
            workers=[WORKER],
            kwargs={"name": PUBLIC_REMOTE},
        )[WORKER]

        assert ret["failed"] is False
        assert [remote["name"] for remote in ret["result"]] == [PUBLIC_REMOTE]


class TestGetInventory:
    def test_get_inventory_redacts_remote_tokens(self, nfclient: Any) -> None:
        ret = nfclient.run_job("filesharing", "get_inventory", workers=[WORKER])
        result = ret[WORKER]

        assert result["failed"] is False
        remotes = {remote["name"]: remote for remote in result["result"]["remotes"]}

        assert len(remotes) == 3
        assert remotes[REMOTE]["password"] == "***"
        assert remotes[SECONDARY_REMOTE]["password"] == "***"
        assert remotes[PUBLIC_REMOTE]["password"] is None


@pytest.mark.filesharing_create_remote_git
class TestCreateRemoteGit:
    def test_create_remote_git_initializes_local_repositories(
        self, nfclient: Any
    ) -> None:
        for name in [REMOTE, SECONDARY_REMOTE, PUBLIC_REMOTE]:
            nfclient.run_job(
                "filesharing",
                "delete_remote_git",
                workers=[WORKER],
                kwargs={"name": name},
            )
            ret = nfclient.run_job(
                "filesharing",
                "create_remote_git",
                workers=[WORKER],
                kwargs={
                    "name": name,
                    "url": "https://github.com/norfablabs/norfab-gitsync-test.git",
                    "branch": "main",
                    "type": "git",
                    "username": (
                        None if name == PUBLIC_REMOTE else os.environ["GITHUB_USERNAME"]
                    ),
                    "password": (
                        None if name == PUBLIC_REMOTE else os.environ["GITHUB_TOKEN"]
                    ),
                },
            )
            result = ret[WORKER]

            assert result["failed"] is False
            assert result["result"]["status"] == "unsynchronized"

    def test_create_remote_git_rejects_unsupported_type(self, nfclient: Any) -> None:
        ret = nfclient.run_job(
            "filesharing",
            "create_remote_git",
            workers=[WORKER],
            kwargs={
                "name": "unsupported",
                "url": "https://example.com/repository",
                "type": "unsupported",
            },
        )

        assert ret[WORKER]["failed"] is True
        assert ret[WORKER]["errors"] == ["Remote 'unsupported' is not a git remote"]


@pytest.mark.filesharing_git_clone
class TestGitClone:
    def test_git_clone_and_fetch(self, nfclient: Any) -> None:
        ret = nfclient.run_job(
            "filesharing",
            "git_clone",
            workers=[WORKER],
            kwargs={"name": REMOTE},
        )
        result = ret[WORKER]

        assert result["failed"] is False
        assert result["result"]["status"] == "cloned"

        fetched = nfclient.fetch_file(url=f"nf://{REMOTE}/README.md", read=True)
        assert fetched["status"] == "200"
        assert "norfab-gitsync-test" in fetched["content"]

    def test_git_clone_returns_unchanged(self, nfclient: Any) -> None:
        ret = nfclient.run_job(
            "filesharing",
            "git_clone",
            workers=[WORKER],
            kwargs={"name": REMOTE},
        )

        assert ret[WORKER]["failed"] is False
        assert ret[WORKER]["result"]["status"] == "unchanged"

    def test_git_clone_public_repository_without_credentials(
        self, nfclient: Any
    ) -> None:
        ret = nfclient.run_job(
            "filesharing",
            "git_clone",
            workers=[WORKER],
            kwargs={"name": PUBLIC_REMOTE},
        )
        result = ret[WORKER]

        assert result["failed"] is False
        assert result["result"]["status"] == "cloned"

        fetched = nfclient.fetch_file(url=f"nf://{PUBLIC_REMOTE}/README.md", read=True)
        assert fetched["status"] == "200"
        assert "norfab-gitsync-test" in fetched["content"]

    def test_git_clone_rejects_unknown_remote(self, nfclient: Any) -> None:
        ret = nfclient.run_job(
            "filesharing",
            "git_clone",
            workers=[WORKER],
            kwargs={"name": "unknown"},
        )

        assert ret[WORKER]["failed"] is True
        assert ret[WORKER]["errors"] == ["Remote 'unknown' is not configured"]


@pytest.mark.filesharing_delete_remote_git
class TestDeleteRemoteGit:
    def test_delete_and_create_remote_git(self, nfclient: Any) -> None:
        deleted = nfclient.run_job(
            "filesharing",
            "delete_remote_git",
            workers=[WORKER],
            kwargs={"name": REMOTE},
        )[WORKER]
        remotes = nfclient.run_job(
            "filesharing",
            "get_remotes",
            workers=[WORKER],
        )[
            WORKER
        ]["result"]
        created = nfclient.run_job(
            "filesharing",
            "create_remote_git",
            workers=[WORKER],
            kwargs={
                "name": REMOTE,
                "url": "https://github.com/norfablabs/norfab-gitsync-test.git",
                "branch": "main",
                "type": "git",
                "username": os.environ["GITHUB_USERNAME"],
                "password": os.environ["GITHUB_TOKEN"],
            },
        )[WORKER]

        assert deleted["failed"] is False
        assert deleted["result"] is True
        assert REMOTE not in {remote["name"] for remote in remotes}
        assert created["failed"] is False
        assert created["result"]["status"] == "unsynchronized"

    def test_delete_remote_git_rejects_unknown_remote(self, nfclient: Any) -> None:
        ret = nfclient.run_job(
            "filesharing",
            "delete_remote_git",
            workers=[WORKER],
            kwargs={"name": "unknown"},
        )

        assert ret[WORKER]["failed"] is True
        assert ret[WORKER]["errors"] == ["Remote 'unknown' is not configured"]


@pytest.mark.filesharing_resolve_git_url
class TestResolveGitUrlBatch:
    def test_batch_synchronizes_remote_once_and_preserves_errors(
        self, nfclient: NFPClient, local_git_remote: dict[str, str]
    ) -> None:
        name, mount = local_git_remote["name"], local_git_remote["mount"]
        urls = [
            f"git://{name}/a.txt",
            f"git://{name}/b.txt",
            f"git://{name}/missing",
            f"git://{name}/../../outside",
            f"git://{name}-unknown/file",
        ]
        future = nfclient.submit_job(
            "filesharing", "resolve_git_url", workers=[WORKER], kwargs={"url": urls}
        )
        response = future.result()[WORKER]
        events = list(future.events(timeout=1))

        assert response["failed"] is False
        entries = response["result"]
        assert response["errors"] == [
            error for entry in entries.values() for error in entry["errors"]
        ]
        assert entries[urls[0]]["result"] == f"nf://{mount}/a.txt"
        assert entries[urls[1]]["result"] == f"nf://{mount}/b.txt"
        assert all(
            entries[url]["failed"] and entries[url]["errors"] for url in urls[2:]
        )
        assert (
            sum(
                f"synchronizing Git remote '{name}'" in event["message"]
                for event in events
            )
            == 1
        )

    def test_mixed_urls_keep_worker_and_reuse_published_alias(
        self, nfclient: NFPClient, local_git_remote: dict[str, str]
    ) -> None:
        name, mount = local_git_remote["name"], local_git_remote["mount"]
        urls = [
            f"git://{name}/a.txt",
            f"nf://{mount}/a.txt",
            f"git://{name}/b.txt",
            f"git://{name}-unknown/file",
        ]
        before = set(nfclient.job_futures)
        results = nfclient.fetch_file(urls, read=True)
        jobs = [
            nfclient.job_db.get_job(uuid) for uuid in set(nfclient.job_futures) - before
        ]

        assert [entry["content"] for entry in results] == [
            "first Git file",
            "first Git file",
            "second Git file",
            None,
        ]
        assert [entry["status"] for entry in results] == ["200", "200", "200", "404"]
        assert [job["task"] for job in jobs].count("resolve_git_url") == 1
        assert [job["task"] for job in jobs].count("file_stat") == 1
        assert [job["task"] for job in jobs].count("serve_file") == 2
        for job in jobs:
            if job["task"] == "serve_file":
                assert job["workers_requested"] == [WORKER]
            else:
                assert job["workers_requested"] == "all"
                assert sorted(job["workers_dispatched"]) == [
                    WORKER,
                    "filesharing-worker-2",
                ]
        assert nfclient.file_transfers == {}

    def test_failed_remote_does_not_discard_other_remote_results(
        self, nfclient: NFPClient, local_git_remote: dict[str, str]
    ) -> None:
        good = local_git_remote["name"]
        bad = f"{good}-bad"
        created = nfclient.run_job(
            "filesharing",
            "create_remote_git",
            workers=[WORKER],
            kwargs={
                "name": bad,
                "url": Path(local_git_remote["source"]).as_posix(),
                "type": "git",
                "branch": "missing-branch",
                "auto_sync": False,
            },
        )[WORKER]
        assert created["failed"] is False, created
        try:
            urls = [f"git://{bad}/a.txt", f"git://{bad}/b.txt", f"git://{good}/a.txt"]
            future = nfclient.submit_job(
                "filesharing", "resolve_git_url", workers=[WORKER], kwargs={"url": urls}
            )
            response = future.result()[WORKER]
            events = list(future.events(timeout=1))
            entries = response["result"]

            assert entries[urls[0]]["failed"] is True
            assert entries[urls[1]]["failed"] is True
            assert entries[urls[0]]["errors"] == entries[urls[1]]["errors"]
            assert (
                entries[urls[2]]["result"] == f"nf://{local_git_remote['mount']}/a.txt"
            )
            for name in [bad, good]:
                assert (
                    sum(
                        f"synchronizing Git remote '{name}'" in event["message"]
                        for event in events
                    )
                    == 1
                )
        finally:
            deleted = nfclient.run_job(
                "filesharing",
                "delete_remote_git",
                workers=[WORKER],
                kwargs={"name": bad},
            )[WORKER]
            assert deleted["failed"] is False, deleted

    def test_empty_batch_resolves_no_files(self, nfclient: NFPClient) -> None:
        response = nfclient.run_job(
            "filesharing", "resolve_git_url", workers=[WORKER], kwargs={"url": []}
        )[WORKER]
        assert response["failed"] is False
        assert response["result"] == {}

    def test_fetch_uses_each_workers_git_mount(
        self, nfclient: NFPClient, local_git_remote: dict[str, str]
    ) -> None:
        worker = "filesharing-worker-2"
        name = local_git_remote["name"]
        mount = f"filesharing/{name}-second"
        response = nfclient.run_job(
            "filesharing",
            "create_remote_git",
            workers=[worker],
            kwargs={
                "name": name,
                "url": local_git_remote["source"],
                "type": "git",
                "mount": mount,
                "branch": "main",
                "auto_sync": False,
            },
        )[worker]
        assert response["failed"] is False, response
        try:
            before = set(nfclient.job_futures)
            results = nfclient.fetch_file(
                [f"git://{name}/a.txt", f"git://{name}/b.txt"], read=True
            )
            jobs = [
                nfclient.job_db.get_job(uuid)
                for uuid in nfclient.job_futures
                if uuid not in before
            ]
            transfers = [job for job in jobs if job["task"] == "serve_file"]
            assert [entry["content"] for entry in results] == [
                "first Git file",
                "second Git file",
            ]
            assert [job["workers_requested"] for job in transfers] == [
                [WORKER],
                [worker],
            ]
            assert [job["kwargs"]["path"] for job in transfers] == [
                f"nf://{local_git_remote['mount']}/a.txt",
                f"nf://{mount}/b.txt",
            ]
        finally:
            deleted = nfclient.run_job(
                "filesharing",
                "delete_remote_git",
                workers=[worker],
                kwargs={"name": name},
            )[worker]
            assert deleted["failed"] is False, deleted
            nfclient.delete_fetched_files(filepath=mount)
