"""NFWeb runtime shutdown behavior tests."""

import signal
from unittest.mock import Mock, patch

import pytest

from norfab.clients.nfweb.runtime import _ShutdownSignals


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
