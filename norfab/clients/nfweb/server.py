"""Tornado host shared by NFWeb applications."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import orjson
import tornado.web

from norfab.clients.nfweb.application import NFWebApplicationModule
from norfab.clients.nfweb.config import NFWebFooterConfig


def _json(value: Any) -> bytes:
    """Serialize NFWeb values, including Pydantic models, to JSON bytes."""
    return orjson.dumps(
        value,
        default=lambda item: item.model_dump(mode="json"),
    )


class NFWebJSONHandler(tornado.web.RequestHandler):
    """Base class for NFWeb JSON routes."""

    def set_default_headers(self) -> None:
        """Apply JSON content and browser-safety headers to every response."""
        self.set_header("Cache-Control", "no-store")
        self.set_header("Content-Type", "application/json; charset=UTF-8")
        self.set_header("X-Content-Type-Options", "nosniff")
        self.set_header("Referrer-Policy", "no-referrer")

    def write_json(self, value: Any, status: int = 200) -> None:
        """Finish a response using NORFAB's fast JSON serializer."""
        self.set_status(status)
        self.finish(_json(value))


class NFWebHealthHandler(NFWebJSONHandler):
    def initialize(self, applications: tuple[NFWebApplicationModule, ...]) -> None:
        """Attach the NFWeb application modules whose health is reported."""
        self.applications = applications

    def get(self) -> None:
        """Return aggregate and per-application health status."""
        health = {
            application.name: application.health() for application in self.applications
        }
        status = (
            "ok"
            if all(application.get("status") == "ok" for application in health.values())
            else "degraded"
        )
        self.write_json({"status": status, "applications": health})


class NFWebConfigHandler(NFWebJSONHandler):
    """Expose only display-safe shared configuration to the browser."""

    def initialize(self, footer: NFWebFooterConfig) -> None:
        """Attach the display-safe footer configuration."""
        self.footer = footer

    def get(self) -> None:
        """Return configuration that the browser is allowed to consume."""
        self.write_json({"footer": self.footer})


class NFWebStaticHandler(tornado.web.StaticFileHandler):
    """Serve bundled assets with a restrictive browser policy."""

    def set_extra_headers(self, path: str) -> None:
        """Apply security and asset-specific caching headers."""
        websocket_source = f"ws://{self.request.host}"
        self.set_header("X-Content-Type-Options", "nosniff")
        self.set_header("Referrer-Policy", "no-referrer")
        self.set_header("Cross-Origin-Opener-Policy", "same-origin")
        self.set_header(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            f"connect-src 'self' {websocket_source}; "
            "font-src 'self'; "
            "object-src 'none'; "
            "base-uri 'none'; "
            "frame-ancestors 'none'",
        )
        if path.startswith("assets/"):
            self.set_header("Cache-Control", "public, max-age=31536000, immutable")
        else:
            self.set_header("Cache-Control", "no-cache")


def make_nfweb_application(
    applications: Iterable[NFWebApplicationModule],
    static_path: str | Path | None = None,
    footer: NFWebFooterConfig | None = None,
) -> tornado.web.Application:
    """Build NFWeb without starting its network listener."""
    installed = tuple(applications)
    names = [application.name for application in installed]
    if len(names) != len(set(names)):
        raise ValueError("NFWeb application names must be unique")

    assets = Path(static_path or Path(__file__).parent / "static").resolve()
    if not (assets / "index.html").is_file():
        raise FileNotFoundError(f"NFWeb frontend is not built: {assets / 'index.html'}")

    routes: list[Any] = [
        (
            r"/api/v1/health",
            NFWebHealthHandler,
            {"applications": installed},
        ),
        (
            r"/api/v1/config",
            NFWebConfigHandler,
            {"footer": footer or NFWebFooterConfig()},
        ),
    ]
    for application in installed:
        routes.extend(application.routes())
    routes.append(
        (
            r"/(.*)",
            NFWebStaticHandler,
            {"path": str(assets), "default_filename": "index.html"},
        )
    )
    return tornado.web.Application(routes, compress_response=True)
