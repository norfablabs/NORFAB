"""NFWeb runtime started by ``nfcli --web-ui``."""

from __future__ import annotations

import asyncio
import logging
import signal
import webbrowser
from pathlib import Path

import tornado.httpserver

from norfab.clients.nfweb.application import NFWebApplicationModule
from norfab.clients.nfweb.config import NFWebConfig
from norfab.clients.nfweb.server import make_nfweb_application
from norfab.clients.nfweb.topology.application import TopologyApplication
from norfab.core.nfapi import NorFab

log = logging.getLogger(__name__)


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
    try:
        database_path = (
            Path(nf.inventory.base_dir) / "__norfab__" / "nfweb" / "nfweb.sqlite"
        )
        applications.append(
            TopologyApplication.create(client, config.topology, database_path)
        )
        web_application = make_nfweb_application(applications)
        server = tornado.httpserver.HTTPServer(web_application)
        server.listen(config.port, address="127.0.0.1")

        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()

        def request_stop(*_: object) -> None:
            loop.call_soon_threadsafe(stop_event.set)

        for signal_name in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(signal_name, request_stop)
            except (NotImplementedError, RuntimeError):
                signal.signal(signal_name, request_stop)

        for application in applications:
            await application.start()

        url = f"http://127.0.0.1:{config.port}"
        log.info("NFWeb client listening on %s", url)
        print(f"NFWeb client listening on {url}")
        if config.open_browser:
            webbrowser.open(url)
        await stop_event.wait()
    finally:
        if server is not None:
            server.stop()
            await server.close_all_connections()
        for application in reversed(applications):
            try:
                await application.stop()
            except Exception:
                log.exception("Failed to stop NFWeb application '%s'", application.name)
        client.destroy()
