import logging

from textual.app import App, ComposeResult
from textual import on
from textual.widgets import Header, RichLog, Footer, Input
from textual.binding import Binding

NFCLIENT = None
log = logging.getLogger(__name__)


class NorFabSuggester(Suggester):

    async def get_suggestion(self, value):
        return ["nornir", "netbox", "fastapi"]


class NorFabApp(App):
    TITLE = "NORFAB"
    BINDINGS = [Binding("ctrl+q", "quit", "Quit", show=True, priority=True)]

    def compose(self) -> ComposeResult:
        yield Header()
        yield RichLog()
        yield Input(
            placeholder="Enter NorFab command",
            type="text",
            suggester=NorFabSuggester(case_sensitive=True),
        )
        yield Footer()

    @on(Input.Submitted)
    def run_command(self, event: Input.Submitted) -> None:
        self.query_one(Input).clear()
        self.query_one(RichLog).write(event.value)


if __name__ == "__main__":
    app = NorFabApp()
    app.run()
