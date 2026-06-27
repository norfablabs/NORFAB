import asyncio
from datetime import datetime

import pytest
from diskcache import FanoutCache

from norfab.workers.fastmcp_worker.fastmcp_worker import DiskcacheBearerTokenVerifier

pytestmark = [pytest.mark.fastmcp, pytest.mark.auth, pytest.mark.task_fastmcp_auth]


@pytest.mark.task_fastmcp_auth
class TestFastMCPBearerVerifier:
    def test_diskcache_bearer_token_verifier(self, tmp_path):
        cache = FanoutCache(directory=str(tmp_path / "cache"))
        cache.set(
            "bearer_token::valid-token",
            {
                "token": "valid-token",
                "username": "pytest",
                "created": str(datetime.now()),
            },
            expire=60,
            tag="pytest",
        )

        verifier = DiskcacheBearerTokenVerifier(cache, scopes=["norfab"])

        valid = asyncio.run(verifier.verify_token("valid-token"))
        assert valid is not None
        assert valid.client_id == "pytest"
        assert valid.scopes == ["norfab"]

        assert asyncio.run(verifier.verify_token("missing-token")) is None
        cache.close()
