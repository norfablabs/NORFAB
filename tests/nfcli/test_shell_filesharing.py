import builtins
from types import SimpleNamespace

import pytest

from norfab.clients.nfcli_shell.filesharing import filesharing_picle_shell as shell

pytestmark = pytest.mark.nfcli


@pytest.mark.parametrize(
    "model", [shell.ListFilesModel, shell.CopyFileModel, shell.FileDetailsModel]
)
def test_url_completion_combines_workers(monkeypatch, model):
    def run_job(service, task, workers, kwargs):
        assert (service, task, workers, kwargs) == (
            "filesharing",
            "walk",
            "all",
            {"url": "nf://"},
        )
        return {
            "failed": {"failed": True, "result": None},
            "one": {"result": ["nf://cfg/a.txt"]},
            "two": {"result": ["nf://cfg/a.txt", "nf://cfg/b.txt"]},
        }

    monkeypatch.setattr(
        builtins, "NFCLIENT", SimpleNamespace(run_job=run_job), raising=False
    )
    assert model.source_url("nf://cfg/") == ["nf://cfg/a.txt", "nf://cfg/b.txt"]
    assert shell.DeleteFetchedFiles.source_filepath("cfg/") == [
        "cfg/a.txt",
        "cfg/b.txt",
    ]


@pytest.mark.parametrize("reverse", [False, True])
def test_directory_listing_combines_successes(monkeypatch, reverse):
    responses = [
        ("bad", {"failed": True, "result": None}),
        ("one", {"failed": False, "result": ["a", "shared"]}),
        ("two", {"failed": False, "result": ["shared", "b"]}),
    ]

    def run_job(service, task, workers, args, kwargs):
        assert (service, task, workers, kwargs) == (
            "filesharing",
            "list_files",
            "all",
            {"url": "nf://"},
        )
        return dict(reversed(responses) if reverse else responses)

    monkeypatch.setattr(shell, "run_future_job", run_job)
    assert sorted(shell.ListFilesModel.run(url="nf://")) == ["a", "b", "shared"]


@pytest.mark.parametrize(
    "response", [None, {}, {"bad": {"failed": True, "result": None}}]
)
def test_directory_listing_total_failure(monkeypatch, response):
    monkeypatch.setattr(shell, "run_future_job", lambda *a, **kw: response)
    with pytest.raises(RuntimeError, match="no successful"):
        shell.ListFilesModel.run(url="nf://")


def test_empty_directory_is_success(monkeypatch):
    monkeypatch.setattr(
        shell,
        "run_future_job",
        lambda *a, **kw: {"one": {"failed": False, "result": []}},
    )
    assert shell.ListFilesModel.run(url="nf://") == []


def test_details_preserve_worker_results(monkeypatch):
    response = {
        "one": {"failed": False, "result": {"md5hash": "a"}},
        "two": {"failed": False, "result": {"md5hash": "b"}},
        "bad": {"failed": True, "result": None, "errors": ["missing"]},
    }

    def run_job(service, task, workers, args, kwargs):
        assert (service, task, workers) == ("filesharing", "file_details", "all")
        return response

    monkeypatch.setattr(shell, "run_future_job", run_job)
    assert shell.FileDetailsModel.run(url="nf://same.txt") == response
