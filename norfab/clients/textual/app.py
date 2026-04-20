"""
NorFab Textual TUI — framework core.

Provides:
  - APPS registry and @nf_screen decorator
  - AppSidebar navigation widget
  - NorFabApp root application
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.theme import Theme
from textual.widget import Widget
from textual.widgets import Footer, Header, Label, ListItem, ListView, Static

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)

HACKER_GREEN = Theme(
    name="hacker-green",
    dark=True,
    background="#0a0a0a",
    surface="#0d1a0d",
    panel="#091209",
    primary="#00ff41",
    secondary="#008f11",
    accent="#00ff41",
    foreground="#00e836",
    success="#00ff41",
    warning="#aaff00",
    error="#ff3300",
)

# ---------------------------------------------------------------------------
# App registry
# ---------------------------------------------------------------------------

# Each entry: {"id": str, "label": str, "screen_cls": type[Widget]}
APPS: list[dict] = []


def nf_screen(label: str, id: str):  # noqa: A002
    """Decorator that registers a Widget subclass in the APPS list."""

    def decorator(cls: type[Widget]) -> type[Widget]:
        if not any(e["id"] == id for e in APPS):
            APPS.append({"id": id, "label": label, "screen_cls": cls})
        return cls

    return decorator


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

SIDEBAR_CSS = """
AppSidebar {
    width: 22;
    background: $panel;
    border-right: solid #00aa22;
    padding: 0 1;
}

AppSidebar ListView {
    background: transparent;
}

AppSidebar ListItem {
    padding: 0 1;
}

AppSidebar #sidebar-title {
    text-align: center;
    color: #00ff41;
    text-style: bold;
    padding: 1 0;
}
"""


class AppSidebar(Static):
    """Left navigation panel that renders the APPS list."""

    DEFAULT_CSS = SIDEBAR_CSS

    def compose(self) -> ComposeResult:
        yield Label("≡ NorFab TUI", id="sidebar-title")
        items = [
            ListItem(Label(entry["label"]), id=f"nav-{entry['id']}") for entry in APPS
        ]
        yield ListView(*items, id="nav-list")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id  # "nav-<app_id>"
        if item_id and item_id.startswith("nav-"):
            app_id = item_id[4:]
            self.app.switch_to_app(app_id)


# ---------------------------------------------------------------------------
# NorFabApp
# ---------------------------------------------------------------------------

APP_CSS = """
#app-body {
    width: 100%;
    height: 1fr;
}

#main-content {
    width: 1fr;
    height: 100%;
}
"""


class NorFabApp(App):
    """Root Textual application for NorFab TUI."""

    TITLE = "NorFab TUI"
    CSS = APP_CSS
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=True, priority=True),
        Binding("ctrl+r", "refresh", "Refresh", show=True),
    ]

    def __init__(self, nfclient=None, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.nfclient = nfclient
        # Trigger app registration (safe to call multiple times — nf_screen deduplicates)
        from norfab.clients.textual import apps as _  # noqa: F401

        self._current_app_id: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="app-body"):
            yield AppSidebar()
            yield Vertical(id="main-content")
        yield Footer()

    def on_mount(self) -> None:
        self.register_theme(HACKER_GREEN)
        self.theme = "hacker-green"
        # Navigate to the first registered app automatically
        if APPS:
            self.switch_to_app(APPS[0]["id"])

    def switch_to_app(self, app_id: str) -> None:
        entry = next((e for e in APPS if e["id"] == app_id), None)
        if entry is None:
            return
        self._current_app_id = app_id
        screen_cls = entry["screen_cls"]
        # Instantiate the screen, injecting nfclient
        screen = screen_cls(nfclient=self.nfclient)
        container = self.query_one("#main-content", Vertical)
        container.remove_children()
        container.mount(screen)

    def action_refresh(self) -> None:
        pass  # reserved for future use
