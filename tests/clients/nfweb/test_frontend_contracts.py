import re
from importlib.resources import files
from pathlib import Path

from norfab.clients.nfweb.topology.models import (
    TopologyCollectionError,
    TopologyCollectionEvent,
    TopologyDeviceOption,
    TopologyLink,
    TopologyLogEntry,
    TopologyNode,
    TopologySnapshot,
)

FRONTEND = Path(__file__).parents[3] / "norfab" / "clients" / "nfweb" / "frontend"


def _interface_fields(source: str, name: str) -> set[str]:
    match = re.search(
        rf"export interface {name}(?: extends (?P<parent>\w+))?\s*{{(?P<body>.*?)^}}",
        source,
        re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"TypeScript interface {name} was not found"
    fields = set(re.findall(r"^\s{2}([a-zA-Z_][a-zA-Z0-9_]*)\??:", match["body"], re.MULTILINE))
    if match["parent"]:
        fields.update(_interface_fields(source, match["parent"]))
    return fields


def test_typescript_contract_fields_match_pydantic_models() -> None:
    source = (FRONTEND / "src" / "types.ts").read_text(encoding="utf-8")
    contracts = {
        "TopologyNode": TopologyNode,
        "TopologyLink": TopologyLink,
        "CollectionError": TopologyCollectionError,
        "CollectionEvent": TopologyCollectionEvent,
        "DeviceOption": TopologyDeviceOption,
        "TopologyLogEntry": TopologyLogEntry,
        "TopologySnapshot": TopologySnapshot,
    }

    for interface, model in contracts.items():
        assert _interface_fields(source, interface) == set(model.model_fields), interface


def test_built_frontend_assets_are_packaged_and_local() -> None:
    static = files("norfab.clients.nfweb").joinpath("static")
    index = static.joinpath("index.html")

    assert index.is_file()
    html = index.read_text(encoding="utf-8")
    references = re.findall(r'(?:src|href)="([^"]+)"', html)
    assert references
    assert all(not reference.startswith(("http://", "https://", "//")) for reference in references)
    for reference in references:
        assert static.joinpath(reference.lstrip("/")).is_file(), reference
