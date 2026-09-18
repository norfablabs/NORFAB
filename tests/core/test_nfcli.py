import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from norfab.utils.nfcli import _resolve_inventory, nfcli

pytestmark = pytest.mark.core


def test_resolve_inventory_from_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("NORFAB_INVENTORY_DIR", str(tmp_path))

    inventory, base_dir = _resolve_inventory(None)

    assert inventory == os.path.join(str(tmp_path.resolve()), "inventory.yaml")
    assert base_dir == str(tmp_path.resolve())


def test_explicit_inventory_overrides_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("NORFAB_INVENTORY_DIR", str(tmp_path))

    assert _resolve_inventory("custom/inventory.yaml") == (
        "custom/inventory.yaml",
        None,
    )


def test_resolve_inventory_retains_current_directory_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NORFAB_INVENTORY_DIR", raising=False)

    assert _resolve_inventory(None) == ("inventory.yaml", None)


def test_client_uses_environment_inventory_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("NORFAB_INVENTORY_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["nfcli", "-c"])

    with patch(
        "norfab.clients.nfcli_shell.nfcli_shell_client.start_picle_shell"
    ) as start_shell:
        nfcli()

    start_shell.assert_called_once_with(
        inventory=os.path.join(str(tmp_path.resolve()), "inventory.yaml"),
        base_dir=str(tmp_path.resolve()),
        run_workers=False,
        run_broker=False,
        log_level=None,
    )
