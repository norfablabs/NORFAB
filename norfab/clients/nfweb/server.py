"""Loopback-only Tornado host shared by NFWeb applications."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

import orjson
import tornado.web

from norfab.clients.nfweb.application import NFWebApplicationModule

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost"}


def _json(value: Any) -> bytes:
    return orjson.dumps(
        value,
        default=lambda item: item.model_dump(mode="json"),
    )


def is_loopback_host(host: str) -> bool:
    """Return whether an HTTP host value names NFWeb's loopback listener."""
    return (urlparse(f"//{host}").hostname or "").casefold() in _LOOPBACK_HOSTS


class NFWebJSONHandler(tornado.web.RequestHandler):
    """Base class for NFWeb JSON routes."""

    def prepare(self) -> None:
        if not is_loopback_host(self.request.host):
            raise tornado.web.HTTPError(403, reason="invalid NFWeb host")

    def set_default_headers(self) -> None:
        self.set_header("Cache-Control", "no-store")
        self.set_header("Content-Type", "application/json; charset=UTF-8")
        self.set_header("X-Content-Type-Options", "nosniff")
        self.set_header("Referrer-Policy", "no-referrer")

    def write_json(self, value: Any, status: int = 200) -> None:
        """Finish a response using NORFAB's fast JSON serializer."""
        self.set_status(status)
        self.finish(_json(value))

    def is_local_post(self, marker: str) -> bool:
        """Validate NFWeb's same-origin marker for a state-changing request."""
        origin = self.request.headers.get("Origin")
        parsed = urlparse(origin) if origin else None
        return bool(
            is_loopback_host(self.request.host)
            and self.request.headers.get("X-NFWeb-Request") == marker
            and parsed is not None
            and parsed.scheme == "http"
            and is_loopback_host(parsed.netloc)
            and parsed.netloc == self.request.host
        )


class NFWebHealthHandler(NFWebJSONHandler):
    def initialize(self, applications: tuple[NFWebApplicationModule, ...]) -> None:
        self.applications = applications

    def get(self) -> None:
        health = {
            application.name: application.health()
            for application in self.applications
        }
        status = (
            "ok"
            if all(application.get("status") == "ok" for application in health.values())
            else "degraded"
        )
        self.write_json({"status": status, "applications": health})


class NFWebStaticHandler(tornado.web.StaticFileHandler):
    """Serve locally bundled assets with a restrictive browser policy."""

    def prepare(self) -> None:
        if not is_loopback_host(self.request.host):
            raise tornado.web.HTTPError(403, reason="invalid NFWeb host")

    def set_extra_headers(self, path: str) -> None:
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
) -> tornado.web.Application:
    """Build NFWeb without starting its loopback listener."""
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
        )
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
