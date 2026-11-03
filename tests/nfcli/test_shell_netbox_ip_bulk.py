from unittest.mock import Mock

import pytest
from picle.models import Outputters

from norfab.clients.nfcli_shell.netbox import netbox_picle_shell_create_ip_bulk

pytestmark = pytest.mark.nfcli


@pytest.mark.parametrize(
    "interface_kwargs,expected",
    [
        ({}, {}),
        ({"interface_list": None}, {"interface_list": None}),
        ({"interface_list": "Loopback0"}, {"interface_list": ["Loopback0"]}),
        ({"interface_list": '["Loopback0"]'}, {"interface_list": ["Loopback0"]}),
        ({"interface_list": ["Loopback0"]}, {"interface_list": ["Loopback0"]}),
    ],
)
def test_create_ip_bulk_interface_list(
    monkeypatch: pytest.MonkeyPatch, interface_kwargs: dict, expected: dict
) -> None:
    submit = Mock(return_value="queued")
    monkeypatch.setattr(netbox_picle_shell_create_ip_bulk, "run_future_job", submit)

    result = netbox_picle_shell_create_ip_bulk.CreateIpBulk.run(
        prefix="192.0.2.0/24", devices="device-1", nowait=True, **interface_kwargs
    )

    assert result == ("queued", Outputters.outputter_nested)
    submit.assert_called_once_with(
        "netbox",
        "create_ip_bulk",
        workers="any",
        args=(),
        kwargs={"prefix": "192.0.2.0/24", "devices": ["device-1"], **expected},
        timeout=600,
        nowait=True,
    )
