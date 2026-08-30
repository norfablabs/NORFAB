"""NFWeb runtime shutdown behavior tests."""

import asyncio
import signal
from unittest.mock import AsyncMock, Mock, patch

import pytest

from norfab.clients.nfweb.runtime import _ShutdownSignals, _access_url, serve


def test_wildcard_bind_uses_local_ip_in_access_url() -> None:
    with patch(
        "norfab.clients.nfweb.runtime._local_ip_address",
        return_value="192.168.10.25",
    ):
        assert _access_url("0.0.0.0", 9005) == "http://192.168.10.25:9005"


def test_specific_ipv6_bind_is_formatted_for_browser_url() -> None:
    assert _access_url("2001:db8::10", 9005) == "http://[2001:db8::10]:9005"


def test_serve_binds_all_interfaces_from_default_config() -> None:
    inventory = Mock(
        client={"nfweb": {"open_browser": False}},
        base_dir="/tmp/nfweb-test",
    )
    client = Mock()
    nf = Mock(inventory=inventory)
    nf.make_client.return_value = client
    application = Mock(name="topology")
    application.start = AsyncMock()
    application.stop = AsyncMock()
    monitoring = Mock(name="monitoring")
    monitoring.start = AsyncMock()
    monitoring.stop = AsyncMock()
    server = Mock()
    server.close_all_connections = AsyncMock()
    stop_event = Mock()
    stop_event.wait = AsyncMock()
    shutdown_signals = Mock()

    with (
        patch("norfab.clients.nfweb.runtime.NorFab", return_value=nf),
        patch(
            "norfab.clients.nfweb.runtime.TopologyApplication.create",
            return_value=application,
        ),
        patch(
            "norfab.clients.nfweb.runtime.MonitoringApplication.create",
            return_value=monitoring,
        ),
        patch(
            "norfab.clients.nfweb.runtime.make_nfweb_application",
            return_value=Mock(),
        ),
        patch(
            "norfab.clients.nfweb.runtime.tornado.httpserver.HTTPServer",
            return_value=server,
        ),
        patch("norfab.clients.nfweb.runtime.asyncio.Event", return_value=stop_event),
        patch(
            "norfab.clients.nfweb.runtime._ShutdownSignals",
            return_value=shutdown_signals,
        ),
        patch(
            "norfab.clients.nfweb.runtime._local_ip_address",
            return_value="192.168.10.25",
        ),
    ):
        asyncio.run(serve("inventory.yaml"))

    server.listen.assert_called_once_with(9005, address="0.0.0.0")
    application.start.assert_awaited_once()
    monitoring.start.assert_awaited_once()
    server.stop.assert_called_once()
    server.close_all_connections.assert_awaited_once()
    application.stop.assert_awaited_once()
    monitoring.stop.assert_awaited_once()
    client.destroy.assert_called_once()


def test_first_interrupt_requests_cleanup_and_second_forces_exit(
    capsys: pytest.CaptureFixture[str],
) -> None:
    loop = Mock()
    stop_event = Mock()
    exit_codes: list[int] = []
    shutdown = _ShutdownSignals(loop, stop_event, exit_codes.append)

    with patch("norfab.clients.nfweb.runtime.signal.signal") as set_handler:
        shutdown.request_stop(signal.SIGINT, None)
        armed_force_handler = set_handler.call_args.args[1]
        armed_force_handler(signal.SIGINT, None)

    set_handler.assert_called_once_with(signal.SIGINT, shutdown.force_stop)
    loop.call_soon_threadsafe.assert_called_once_with(stop_event.set)
    assert exit_codes == [130]
    output = capsys.readouterr().out
    assert "Stopping NFWeb gracefully" in output
    assert "Second Ctrl+C received" in output


def test_signal_handlers_are_restored_after_graceful_shutdown() -> None:
    loop = Mock()
    stop_event = Mock()
    shutdown = _ShutdownSignals(loop, stop_event)

    with (
        patch(
            "norfab.clients.nfweb.runtime.signal.getsignal",
            side_effect=[signal.SIG_DFL, signal.SIG_IGN],
        ),
        patch("norfab.clients.nfweb.runtime.signal.signal") as set_handler,
    ):
        shutdown.install()
        shutdown.restore()

    assert set_handler.call_args_list[-2].args == (signal.SIGINT, signal.SIG_DFL)
    assert set_handler.call_args_list[-1].args == (signal.SIGTERM, signal.SIG_IGN)
