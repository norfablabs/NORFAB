import pytest
from pydantic import ValidationError

from norfab.clients.nfweb.config import NFWebConfig, NFWebFooterConfig
from norfab.clients.nfweb.topology.config import TopologyConfig


def test_nfweb_config_separates_runtime_and_topology_settings() -> None:
    config = NFWebConfig()

    assert config.port == 9005
    assert str(config.footer.fastapi_url) == "http://127.0.0.1:8000/docs"
    assert config.topology.retention_minutes == 180
    assert config.topology.layers.inventory is True
    assert set(NFWebConfig.model_fields) == {
        "port",
        "open_browser",
        "footer",
        "topology",
    }


def test_nfweb_config_rejects_remote_host_and_long_history() -> None:
    with pytest.raises(ValidationError):
        NFWebConfig.model_validate({"host": "0.0.0.0"})
    with pytest.raises(ValidationError):
        TopologyConfig(retention_minutes=181)


def test_nfweb_footer_config_is_strict_and_bounds_the_message() -> None:
    footer = NFWebFooterConfig.model_validate(
        {
            "message": "Lab topology",
            "fastapi_url": None,
            "docs_url": "https://docs.norfablabs.com/",
        }
    )

    assert footer.message == "Lab topology"
    assert footer.fastapi_url is None
    with pytest.raises(ValidationError):
        NFWebFooterConfig(message="x" * 201)
    with pytest.raises(ValidationError):
        NFWebFooterConfig.model_validate({"unsupported": True})
