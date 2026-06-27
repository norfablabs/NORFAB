import pprint

import pytest

pytestmark = [pytest.mark.netbox, pytest.mark.designs]


@pytest.mark.task_create_design
class TestCreateDesign:
    nb_version = None

    def test_design_create(self, nfclient):
        res = nfclient.run_job(
            "netbox",
            "create_design",
            workers="any",
            kwargs={
                "design_data": "nf://netbox/designs/base_design.yaml",
                "dry_run": True,
            },
        )
        print("created design:")
        pprint.pprint(res, width=200)


# ---------------------------------------------------------------------------
# BGP PEERINGS TESTS
# ---------------------------------------------------------------------------
