"""NFWeb runtime started by ``nfcli --web-ui``."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import webbrowser
from pathlib import Path
from types import FrameType
from typing import Callable

import tornado.httpserver

from norfab.clients.nfweb.application import NFWebApplicationModule
from norfab.clients.nfweb.config import NFWebConfig
from norfab.clients.nfweb.server import make_nfweb_application
from norfab.clients.nfweb.topology.application import TopologyApplication
from norfab.core.nfapi import NorFab

log = logging.getLogger(__name__)


class _ShutdownSignals:
    """Coordinate graceful shutdown followed by a forced second interrupt."""

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        stop_event: asyncio.Event,
        force_exit: Callable[[int], object] = os._exit,
    ) -> None:
        self.loop = loop
        self.stop_event = stop_event
        self.force_exit = force_exit
        self.shutdown_requested = False
        self.original_handlers: dict[signal.Signals, object] = {}

    def install(self) -> None:
        """Install process-level handlers that work on Windows and POSIX."""
        for signal_name in (signal.SIGINT, signal.SIGTERM):
            try:
                original_handler = signal.getsignal(signal_name)
                signal.signal(signal_name, self.request_stop)
            except (OSError, RuntimeError, ValueError):
                log.debug("Could not install NFWeb handler for %s", signal_name)
            else:
                self.original_handlers[signal_name] = original_handler

    def restore(self) -> None:
        """Restore handlers owned by the caller, including ``asyncio.run``."""
        for signal_name, original_handler in self.original_handlers.items():
            try:
                signal.signal(signal_name, original_handler)
            except (OSError, RuntimeError, TypeError, ValueError):
                log.debug("Could not restore handler for %s", signal_name)

    def request_stop(
        self,
        signal_number: int,
        _frame: FrameType | None,
    ) -> None:
        """Request cleanup once and force exit when another signal arrives."""
        if self.shutdown_requested:
            self.force_stop(signal_number, _frame)
            return

        self.shutdown_requested = True
        try:
            signal.signal(signal_number, self.force_stop)
        except (OSError, RuntimeError, ValueError):
            pass

        if signal_number == signal.SIGINT:
            message = "\nStopping NFWeb gracefully. Press Ctrl+C again to force exit."
        else:
            message = (
                "\nStopping NFWeb gracefully. Send the signal again to force exit."
            )
        print(message, flush=True)
        self.loop.call_soon_threadsafe(self.stop_event.set)

    def force_stop(
        self,
        signal_number: int,
        _frame: FrameType | None,
    ) -> None:
        """Terminate immediately when graceful cleanup is interrupted again."""
        if signal_number == signal.SIGINT:
            message = "\nSecond Ctrl+C received; forcing NFWeb to stop."
        else:
            message = "\nSecond termination signal received; forcing NFWeb to stop."
        print(message, flush=True)
        self.force_exit(128 + signal_number)


async def serve(
    inventory: str,
    log_level: str | None = None,
) -> None:
    """Run NFWeb until interrupted and release every local resource."""
    nf = NorFab(
        inventory=inventory,
        log_level=log_level,
        configure_logging=True,
        logging_name="nfweb",
    )
    config = NFWebConfig.model_validate(nf.inventory.client.get("nfweb", {}))
    client = nf.make_client(name="nfweb")
    if client is None:
        raise RuntimeError("Could not create the native NORFAB client")

    applications: list[NFWebApplicationModule] = []
    server: tornado.httpserver.HTTPServer | None = None
    shutdown_signals: _ShutdownSignals | None = None
    try:
        database_path = (
            Path(nf.inventory.base_dir) / "__norfab__" / "nfweb" / "nfweb.sqlite"
        )
        applications.append(
            TopologyApplication.create(client, config.topology, database_path)
        )
        web_application = make_nfweb_application(applications, footer=config.footer)
        server = tornado.httpserver.HTTPServer(web_application)
        server.listen(config.port, address="127.0.0.1")

        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        shutdown_signals = _ShutdownSignals(loop, stop_event)
        shutdown_signals.install()

        for application in applications:
            await application.start()

        url = f"http://127.0.0.1:{config.port}"
        log.info("NFWeb client listening on %s", url)
        print(f"NFWeb client listening on {url}")
        if config.open_browser:
            webbrowser.open(url)
        await stop_event.wait()
    finally:
        try:
            if server is not None:
                server.stop()
                await server.close_all_connections()
            for application in reversed(applications):
                try:
                    await application.stop()
                except Exception:
                    log.exception(
                        "Failed to stop NFWeb application '%s'", application.name
                    )
            client.destroy()
        finally:
            if shutdown_signals is not None:
                shutdown_signals.restore()
