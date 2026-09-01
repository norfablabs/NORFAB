import os
from typing import Any

import pytest

from norfab.models import Result
from norfab.workers.filesharing_worker.filesharing_worker import FileSharingWorker

pytestmark = [
    pytest.mark.filesharing,
    pytest.mark.filesharing_git,
]

WORKER = "filesharing-worker-1"
REMOTE = "norfab-gitsync-test-main"
SECONDARY_REMOTE = "norfab-gitsync-test-secondary"
PUBLIC_REMOTE = "norfab-gitsync-test-public"


@pytest.mark.filesharing_resolve_git_url
class TestResolveGitUrl:
    def test_resolve_git_url_validates_and_resolves_custom_mount(
        self, tmp_path: Any
    ) -> None:
        worker = FileSharingWorker.__new__(FileSharingWorker)
        worker.base_dir = str(tmp_path)
        worker.remotes = {
            "network-assets": {
                "type": "git",
                "mount": "nf://repositories/network-assets",
            }
        }
        published_file = (
            tmp_path / "repositories" / "network-assets" / "templates" / "base.j2"
        )
        published_file.parent.mkdir(parents=True)
        published_file.write_text("template", encoding="utf-8")
        synchronized = []

        def git_clone(_job: Any, name: str) -> Result:
            synchronized.append(name)
            return Result(result={"status": "unchanged"})

        worker.git_clone = git_clone

        resolved = worker.resolve_git_url(
            None, "git://network-assets/templates/base.j2"
        )
        unsafe = worker.resolve_git_url(None, "git://network-assets/../../outside.txt")

        assert resolved.failed is False
        assert resolved.result == "nf://repositories/network-assets/templates/base.j2"
        assert unsafe.failed is True
        assert unsafe.errors == [
            "'git://network-assets/../../outside.txt' - invalid Git URL path"
        ]
        assert synchronized == ["network-assets"]

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
