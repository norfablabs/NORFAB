from pytest import MonkeyPatch

from norfab.clients.nfcli_shell.fastmcp.fastmcp_picle_shell import (
    FastMCPShowGuardrailsModel,
)


def test_show_fastmcp_guardrails_includes_result_guardrails(
    monkeypatch: MonkeyPatch,
) -> None:
    job_result = {
        "fastmcp-worker-1": {
            "result": {
                "service_nornir__task_cli": {
                    "guardrails": [{"type": "regex"}],
                    "result_guardrails": [{"type": "replace"}],
                },
                "service_netbox__task_get_devices": {
                    "result_guardrails": [{"type": "limit"}],
                },
                "service_nornir__task_parse": {},
            }
        }
    }

    monkeypatch.setattr(
        "norfab.clients.nfcli_shell.fastmcp.fastmcp_picle_shell.run_future_job",
        lambda *args, **kwargs: job_result,
    )
    monkeypatch.setattr(
        "norfab.clients.nfcli_shell.fastmcp.fastmcp_picle_shell.log_error_or_result",
        lambda result, **kwargs: result,
    )

    result = FastMCPShowGuardrailsModel.run()

    tools = result["fastmcp-worker-1"]["result"]
    assert tools == {
        "service_nornir__task_cli": {
            "guardrails": [{"type": "regex"}],
            "result_guardrails": [{"type": "replace"}],
        },
        "service_netbox__task_get_devices": {
            "guardrails": [],
            "result_guardrails": [{"type": "limit"}],
        },
    }
