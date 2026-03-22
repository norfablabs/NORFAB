"""
NorFab TUI apps package.

To add a new app:
  1. Create apps/my_app.py with a @nf_screen decorated Screen subclass.
  2. Add `from . import my_app` below — that is all.
"""

from . import monitoring  # noqa: F401
