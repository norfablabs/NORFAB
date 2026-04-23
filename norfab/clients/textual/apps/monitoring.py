"""
NorFab TUI — Monitoring Dashboard.

Self-contained: panel base class, all panel widgets, and the screen
are all defined here. No external primitives module needed.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from rich.table import Table
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, Label, Select, Static

from ..app import nf_screen

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Base panel
# ---------------------------------------------------------------------------


class BasePanel(Widget):
    """
    Base class for monitoring panels.

    Subclasses implement ``fetch_data()`` (background thread) and
    ``render_data(data)`` (UI thread).
    """

    DEFAULT_CSS = """
    BasePanel {
        border: solid #00aa22;
        padding: 0 1;
        height: 1fr;
        margin: 0 1 1 0;
        overflow-y: auto;
    }
    BasePanel .panel-title {
        color: #00ff41;
        text-style: bold;
        padding-bottom: 1;
        height: auto;
    }
    BasePanel .panel-content {
        height: auto;
    }
    """

    def __init__(
        self,
        title: str = "",
        nfclient: Any = None,
        refresh_interval: int = 5,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self.title = title
        self.nfclient = nfclient
        self.refresh_interval = refresh_interval
        self._content = Static(classes="panel-content")

    def compose(self) -> ComposeResult:
        if self.title:
            yield Label(self.title, classes="panel-title")
        yield self._content

    def on_mount(self) -> None:
        # Synchronous initial paint — avoids race between background thread and mount
        try:
            self.render_data(self.fetch_data())
        except Exception as exc:
            log.warning(f"{self.__class__.__name__} initial render error: {exc}")
        self._timer = self.set_interval(self.refresh_interval, self._do_refresh)

    def set_refresh_interval(self, seconds: int) -> None:
        self.refresh_interval = seconds
        if hasattr(self, "_timer"):
            self._timer.stop()
        self._timer = self.set_interval(seconds, self._do_refresh)

    def on_unmount(self) -> None:
        if hasattr(self, "_timer"):
            self._timer.stop()

    async def _do_refresh(self) -> None:
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, self.fetch_data)
        except Exception as exc:
            log.warning(f"{self.__class__.__name__} fetch error: {exc}")
            data = {"__error__": str(exc)}
        try:
            self.render_data(data)
        except Exception as exc:
            log.warning(f"{self.__class__.__name__} render error: {exc}")

    def fetch_data(self) -> Any:  # noqa: ANN401
        return {}

    def render_data(self, data: Any) -> None:  # noqa: ANN401
        if isinstance(data, dict) and "__error__" in data:
            self._content.update(f"[red]Error:[/red] {data['__error__']}")


# ---------------------------------------------------------------------------
# WorkerStatsPanel
# ---------------------------------------------------------------------------


class WorkerStatsPanel(BasePanel):
    """Per-worker RAM and uptime, polled via get_watchdog_stats."""

    DEFAULT_CSS = BasePanel.DEFAULT_CSS + """
    WorkerStatsPanel {
        height: 100%;
        margin-bottom: 0;
        min-width: 48;
    }
    """

    def __init__(
        self,
        services: list[str],
        nfclient: Any = None,
        refresh_interval: int = 5,
        workers: str = "all",
        warn_ram_mb: float = 512.0,
        **kwargs: object,
    ) -> None:
        super().__init__(
            title="Worker Stats",
            nfclient=nfclient,
            refresh_interval=refresh_interval,
            **kwargs,
        )
        self.services = services
        self.target_workers = workers
        self.warn_ram_mb = warn_ram_mb

    def fetch_data(self) -> list:
        raw = self.nfclient.run_job(
            service="all", workers="all", task="get_watchdog_stats"
        )
        rows = []
        for worker_name, job in (raw or {}).items():
            if job.get("failed"):
                rows.append(
                    {
                        "worker": worker_name,
                        "service": job.get("service") or "\u2014",
                        "ram_mb": None,
                        "uptime": None,
                        "error": "ERROR",
                    }
                )
            else:
                result = job.get("result") or {}
                rows.append(
                    {
                        "worker": worker_name,
                        "service": job.get("service") or "\u2014",
                        "ram_mb": result.get("worker_ram_usage_mbyte"),
                        "uptime": result.get("uptime", "\u2014"),
                        "error": None,
                    }
                )
        return rows

    def render_data(self, data: list) -> None:
        if isinstance(data, list) and data and data[0].get("__no_client__"):
            self._content.update("[dim]No client connected.[/dim]")
            return
        if isinstance(data, dict) and "__error__" in data:
            self._content.update(f"[red]Error:[/red] {data['__error__']}")
            return

        table = Table(show_header=True, expand=True, box=None)
        table.add_column("Worker", style="#00cc33", no_wrap=True)
        table.add_column("Service", style="#007a1f")
        table.add_column("RAM (MB)", justify="right")
        table.add_column("Uptime", style="#00aa22")

        for row in sorted(data or [], key=lambda r: r.get("worker", "")):
            if row.get("error"):
                table.add_row(
                    f"[red]{row['worker']}[/red]",
                    str(row["service"]),
                    "\u2014",
                    f"[red]{row['error'][:40]}[/red]",
                )
            else:
                ram = row.get("ram_mb") or 0
                ram_str = f"{ram:.1f}"
                ram_display = (
                    f"[red]{ram_str}[/red]"
                    if ram > self.warn_ram_mb
                    else f"[#00ff41]{ram_str}[/#00ff41]"
                )
                table.add_row(
                    row["worker"],
                    str(row["service"]),
                    ram_display,
                    str(row.get("uptime", "\u2014")),
                )

        self._content.update(table)


# ---------------------------------------------------------------------------
# ClientDBPanel
# ---------------------------------------------------------------------------


class ClientDBPanel(BasePanel):
    """Local client DB stats: job counts, event severity. No network calls."""

    DEFAULT_CSS = BasePanel.DEFAULT_CSS + """
    ClientDBPanel {
        height: 3fr;
        margin-bottom: 0;
        min-width: 36;
    }
    """

    def __init__(
        self, nfclient: object, refresh_interval: int = 5, **kwargs: object
    ) -> None:
        super().__init__(
            title="Client DB Stats",
            nfclient=nfclient,
            refresh_interval=refresh_interval,
            **kwargs,
        )

    def fetch_data(self) -> dict:
        return self.nfclient.job_db.jobs_stats()

    def render_data(self, data: dict) -> None:
        if "__error__" in data:
            self._content.update(f"[red]Error:[/red] {data['__error__']}")
            return
        if data.get("__no_client__"):
            self._content.update("[dim]No client connected.[/dim]")
            return

        table = Table(show_header=False, expand=True, box=None)
        table.add_column("Key", style="dim", no_wrap=True)
        table.add_column("Value", justify="right")

        table.add_row("[bold]Jobs[/bold]", "")
        table.add_row("  Total", str(data.get("total_jobs", 0)))
        table.add_row("  Last 24h", str(data.get("jobs_last_24h", 0)))
        avg = data.get("avg_completion_seconds")
        table.add_row(
            "  Avg completion", f"{avg:.1f}s" if avg is not None else "\u2014"
        )
        for status, count in sorted((data.get("jobs_by_status") or {}).items()):
            color = {
                "COMPLETED": "green",
                "FAILED": "red",
                "STALE": "yellow",
                "NEW": "cyan",
                "SUBMITTING": "blue",
            }.get(status, "white")
            table.add_row(f"  [{color}]{status}[/{color}]", str(count))

        table.add_row("[bold]Events[/bold]", "")
        table.add_row("  Total", str(data.get("total_events", 0)))
        sev_colors = {
            "INFO": "blue",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "bright_red",
            "DEBUG": "dim",
        }
        for sev, count in sorted((data.get("events_by_severity") or {}).items()):
            color = sev_colors.get(sev.upper(), "white")
            table.add_row(f"  [{color}]{sev}[/{color}]", str(count))

        table.add_row("[bold]Services[/bold]", "")
        for svc, count in sorted((data.get("jobs_by_service") or {}).items()):
            table.add_row(f"  {svc}", str(count))

        self._content.update(table)


# ---------------------------------------------------------------------------
# BrokerPanel
# ---------------------------------------------------------------------------


class BrokerPanel(BasePanel):
    """Broker status via MMI show_broker."""

    DEFAULT_CSS = BasePanel.DEFAULT_CSS + """
    BrokerPanel {
        height: 1fr;
        margin-top: 0;
        margin-bottom: 0;
        min-width: 36;
    }
    """

    def __init__(
        self, nfclient: Any = None, refresh_interval: int = 5, **kwargs: object
    ) -> None:
        super().__init__(
            title="Broker",
            nfclient=nfclient,
            refresh_interval=refresh_interval,
            **kwargs,
        )

    def fetch_data(self) -> dict:
        if self.nfclient is None:
            return {"__no_client__": True}
        try:
            result = self.nfclient.mmi("mmi.service.broker", "show_broker")
            if result.get("status") == "200":
                return result.get("results", {})
            return {
                "__error__": f"MMI status {result.get('status')} errors: {result.get('errors')}"
            }
        except Exception as exc:
            return {"__error__": str(exc)}

    def render_data(self, data: dict) -> None:
        if "__error__" in data:
            self._content.update(f"[red]Error:[/red] {data['__error__']}")
            return
        if data.get("__no_client__"):
            self._content.update("[dim]No client connected.[/dim]")
            return

        table = Table(show_header=False, expand=True, box=None)
        table.add_column("Key", style="dim", no_wrap=True)
        table.add_column("Value", justify="right", no_wrap=False)
        dash = "\u2014"

        table.add_row("Endpoint", str(data.get("endpoint", dash)))
        status = data.get("status", dash)
        status_color = "green" if status == "active" else "red"
        table.add_row("Status", f"[{status_color}]{status}[/{status_color}]")
        table.add_row("Workers", str(data.get("workers count", dash)))
        table.add_row("Services", str(data.get("services count", dash)))

        ka = data.get("keepalives", {})
        table.add_row("KA interval", str(ka.get("interval", dash)))
        table.add_row("KA multiplier", str(ka.get("multiplier", dash)))

        sec = data.get("security", {})
        if sec:
            table.add_row("[bold]Security[/bold]", "")
            zmq_auth = sec.get("zmq-auth", dash)
            auth_color = "green" if zmq_auth is True else "red"
            table.add_row("  ZMQ auth", f"[{auth_color}]{zmq_auth}[/{auth_color}]")

        self._content.update(table)


# ---------------------------------------------------------------------------
# MonitoringScreen
# ---------------------------------------------------------------------------

INTERVAL_PRESETS = [("5 sec", 5), ("15 sec", 15), ("30 sec", 30), ("60 sec", 60)]

MONITORING_CSS = """
MonitoringScreen {
    width: 100%;
    height: 100%;
    layout: vertical;
    background: #0a0a0a;
}

MonitoringScreen #control-bar {
    height: auto;
    width: 100%;
    padding: 0 1;
    background: #091209;
    border-bottom: solid #00aa22;
    align: left middle;
}

MonitoringScreen #control-bar Label {
    color: #00aa22;
    margin-right: 1;
    height: 3;
    content-align: left middle;
}

MonitoringScreen #refresh-select {
    width: 14;
}

MonitoringScreen #refresh-btn {
    min-width: 14;
    height: 3;
    margin-left: 1;
    background: #091209;
    color: #00ff41;
}

MonitoringScreen #refresh-btn:hover {
    background: #0d2a0d;
}

MonitoringScreen #panels-body {
    width: 100%;
    height: 1fr;
    layout: horizontal;
}

MonitoringScreen #left-col {
    width: 1fr;
    height: 100%;
}

MonitoringScreen #right-col {
    width: 44;
    height: 100%;
}
"""


@nf_screen(label="\U0001f4ca Monitor", id="monitor")
class MonitoringScreen(Widget):
    """Live monitoring dashboard: workers, client DB, broker."""

    DEFAULT_CSS = MONITORING_CSS

    def __init__(self, nfclient: Any = None, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.nfclient = nfclient
        self._current_interval: int = 5

    def compose(self) -> ComposeResult:
        with Horizontal(id="control-bar"):
            yield Button("Refresh", id="refresh-btn")
            yield Select(
                INTERVAL_PRESETS,
                value=self._current_interval,
                id="refresh-select",
                allow_blank=False,
            )
        with Horizontal(id="panels-body"):
            with Vertical(id="left-col"):
                yield WorkerStatsPanel(
                    services=["nornir", "netbox"],
                    nfclient=self.nfclient,
                    refresh_interval=self._current_interval,
                    warn_ram_mb=512,
                )
            with Vertical(id="right-col"):
                yield ClientDBPanel(
                    nfclient=self.nfclient, refresh_interval=self._current_interval
                )
                yield BrokerPanel(
                    nfclient=self.nfclient, refresh_interval=self._current_interval
                )

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "refresh-select":
            return
        secs = int(event.value)
        self._current_interval = secs
        for panel in self.query(BasePanel):
            panel.set_refresh_interval(secs)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "refresh-btn":
            return
        for panel in self.query(BasePanel):
            self.run_worker(panel._do_refresh(), exclusive=False)
