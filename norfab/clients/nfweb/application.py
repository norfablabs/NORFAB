"""Application contract used by the shared NFWeb runtime."""

from typing import Any, Protocol


class NFWebApplicationModule(Protocol):
    """One focused application hosted by the local NFWeb client."""

    name: str

    def routes(self) -> list[Any]:
        """Return Tornado route specifications owned by the application."""

    def health(self) -> dict[str, Any]:
        """Return application health for the shared health endpoint."""

    async def start(self) -> None:
        """Start application-owned background work."""

    async def stop(self) -> None:
        """Stop background work and release application resources."""
