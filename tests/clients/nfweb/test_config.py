import pytest
from pydantic import ValidationError

from norfab.clients.nfweb.config import NFWebConfig
from norfab.clients.nfweb.topology.config import TopologyConfig


def test_nfweb_config_separates_runtime_and_topology_settings() -> None:
    config = NFWebConfig()

    assert config.port == 8080
    assert config.topology.retention_minutes == 180
    assert config.topology.layers.inventory is True
    assert set(NFWebConfig.model_fields) == {"port", "open_browser", "topology"}


def test_nfweb_config_rejects_remote_host_and_long_history() -> None:
    with pytest.raises(ValidationError):
        NFWebConfig.model_validate({"host": "0.0.0.0"})
    with pytest.raises(ValidationError):
        TopologyConfig(retention_minutes=181)
