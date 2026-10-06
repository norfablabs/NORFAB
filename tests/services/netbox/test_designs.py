"""NetBox design deployment integration tests."""

from typing import Any

import pynetbox
import pytest

try:
    from tests.netbox_data import NB_API_TOKEN, NB_URL
except ModuleNotFoundError as exc:
    if exc.name not in {"tests", "tests.netbox_data"}:
        raise
    from netbox_data import NB_API_TOKEN, NB_URL

pytestmark = [pytest.mark.netbox, pytest.mark.netbox_design_deploy]


class TestDesignDeploy:
    def test_peer_group_dry_run(self, nfclient: Any) -> None:
        """Plan a peer group without writing it to NetBox."""
        nb = pynetbox.api(url=NB_URL, token=NB_API_TOKEN)
        name = "NORFAB DESIGN BGP DRY RUN PEERS"
        if nb.plugins.bgp.peer_group.get(name=name):
            pytest.skip("dry-run peer group already exists")
        response = nfclient.run_job(
            "netbox",
            "design_deploy",
            workers="any",
            kwargs={"design": {"peer_groups": [{"name": name}]}, "dry_run": True},
        )
        for result in response.values():
            assert not result["failed"], result
            assert result["result"]["peer_groups"] == {
                "created": [name],
                "updated": [],
            }
        assert nb.plugins.bgp.peer_group.get(name=name) is None

    @pytest.mark.parametrize(
        "function_backed", [False, True], ids=["static", "function"]
    )
    def test_dry_run_skips_missing_device_local_context(
        self, nfclient: Any, function_backed: bool
    ) -> None:
        """Do not report local-context updates for devices absent in a dry run."""
        nb = pynetbox.api(url=NB_URL, token=NB_API_TOKEN)
        device_name = "norfab-design-missing-local-context-device"
        if nb.dcim.devices.get(name=device_name):
            pytest.skip("missing local-context test device already exists")
        local_data = (
            {"custom_function": "calculate_acme_device_context", "profile": "test"}
            if function_backed
            else {"profile": "test"}
        )
        design = {
            "custom_functions": {
                "calculate_acme_device_context": "nf://netbox/designs/calculate_acme_device_context.py"
            },
            "local_context_data": [
                {
                    "device": device_name,
                    "site": "norfab-design-missing-local-context-site",
                    "local_context_data": local_data,
                }
            ],
        }
        response = nfclient.run_job(
            "netbox",
            "design_deploy",
            workers="any",
            kwargs={"design": design, "dry_run": True},
        )
        for result in response.values():
            assert not result["failed"], result
            assert result["result"]["local_context_data"] == {
                "created": [],
                "updated": [],
            }

    def test_custom_function_in_every_collection(self, nfclient: Any) -> None:
        """Run custom records in every ordinary design collection."""
        collections = [
            "tenants",
            "regions",
            "manufacturers",
            "platforms",
            "device_types",
            "device_roles",
            "sites",
            "rack_roles",
            "racks",
            "roles",
            "rirs",
            "asn_ranges",
            "asns",
            "vlan_groups",
            "vlans",
            "route_targets",
            "vrfs",
            "l2vpns",
            "prefixes",
            "devices",
            "interfaces",
            "l2vpn_terminations",
            "power_ports",
            "console_ports",
            "power_outlets",
            "console_server_ports",
            "connections",
            "vrrp_groups",
            "ip_addresses",
            "vrrp_group_assignments",
            "primary_ip",
            "bgp_communities",
            "routing_policies",
            "peer_groups",
            "bgp_peerings",
            "config_context",
        ]
        design = {
            "custom_functions": {
                "echo_design_record": "nf://netbox/designs/echo_design_record.py"
            },
            **{
                name: [{"custom_function": "echo_design_record", "marker": name}]
                for name in collections
            },
        }
        design["asns"][0]["sites"] = ["custom site"]
        design["vlans"][0]["vid"] = 120
        design["interfaces"][0]["tagged_vlans"] = [{"label": "custom vlan"}]
        design["prefixes"][0]["vlan"] = {"group": "custom group"}
        design["l2vpn_terminations"][0]["group"] = "custom group"
        response = nfclient.run_job(
            "netbox",
            "design_deploy",
            workers="any",
            kwargs={"design": design, "context": {"request": "test"}, "dry_run": True},
        )
        for result in response.values():
            assert not result["failed"], result
            for name in collections:
                assert result["result"][name]["custom"] == [
                    {
                        "function": "echo_design_record",
                        "result": {
                            "context": {"request": "test"},
                            "dry_run": True,
                            "arguments": {
                                key: value
                                for key, value in design[name][0].items()
                                if key != "custom_function"
                            },
                        },
                    }
                ]

    def test_custom_records_are_not_flattened(self, nfclient: Any) -> None:
        """Pass custom records through flattening without changing their arguments."""
        payloads = {
            "route_targets": {
                "range_name": "range1",
                "devices": ["device1", "device2"],
            },
            "vrrp_groups": {
                "vip": "192.0.2.1/32",
                "assignments": [{"device": "device1"}],
            },
            "power_ports": {
                "connection": {"device": "device2", "power_outlet": "PSU1"}
            },
            "console_ports": {
                "connection": {"device": "device2", "console_server_port": "Console1"}
            },
            "power_outlets": {
                "connection": {"device": "device2", "power_port": "PSU1"}
            },
            "console_server_ports": {
                "connection": {"device": "device2", "console_port": "Console1"}
            },
        }
        design = {
            "custom_functions": {
                "echo_design_record": "nf://netbox/designs/echo_design_record.py"
            },
            "route_targets": [
                {"custom_function": "echo_design_record", **payloads["route_targets"]}
            ],
            "vrrp_groups": [
                {"custom_function": "echo_design_record", **payloads["vrrp_groups"]}
            ],
            "power_ports": [
                {"custom_function": "echo_design_record", **payloads["power_ports"]}
            ],
            "console_ports": [
                {"custom_function": "echo_design_record", **payloads["console_ports"]}
            ],
            "power_outlets": [
                {"custom_function": "echo_design_record", **payloads["power_outlets"]}
            ],
            "console_server_ports": [
                {
                    "custom_function": "echo_design_record",
                    **payloads["console_server_ports"],
                }
            ],
        }
        response = nfclient.run_job(
            "netbox",
            "design_deploy",
            workers="any",
            kwargs={"design": design, "context": {"request": "test"}, "dry_run": True},
        )
        for result in response.values():
            assert not result["failed"], result
            for collection, arguments in payloads.items():
                assert result["result"][collection]["custom"] == [
                    {
                        "function": "echo_design_record",
                        "result": {
                            "context": {"request": "test"},
                            "dry_run": True,
                            "arguments": arguments,
                        },
                    }
                ]

    def test_vlan_updates_add_tags_and_custom_field_values(self, nfclient: Any) -> None:
        """Preserve VLAN array members when a design adds tags and site references."""
        nb = pynetbox.api(url=NB_URL, token=NB_API_TOKEN)
        group_name = "NORFAB DESIGN ADDITIVE VLAN GROUP"
        field_name = "norfab_design_vlan_sites"
        object_field = "norfab_design_vlan_site"
        tag_names = ["norfab-design-vlan-a", "norfab-design-vlan-b"]
        site_names = ["NORFAB DESIGN VLAN SITE A", "NORFAB DESIGN VLAN SITE B"]
        if (
            nb.ipam.vlan_groups.get(name=group_name)
            or nb.extras.custom_fields.get(name=field_name)
            or nb.extras.custom_fields.get(name=object_field)
            or any(nb.extras.tags.get(name=name) for name in tag_names)
            or any(nb.dcim.sites.get(name=name) for name in site_names)
        ):
            pytest.skip("design VLAN array test objects already exist")

        try:
            nb.ipam.vlan_groups.create(
                {"name": group_name, "slug": "norfab-design-additive-vlan-group"}
            )
            nb.extras.tags.create(
                [
                    {"name": tag_names[0], "slug": tag_names[0]},
                    {"name": tag_names[1], "slug": tag_names[1]},
                ]
            )
            sites = nb.dcim.sites.create(
                [
                    {"name": site_names[0], "slug": "norfab-design-vlan-site-a"},
                    {"name": site_names[1], "slug": "norfab-design-vlan-site-b"},
                ]
            )
            nb.extras.custom_fields.create(
                [
                    {
                        "name": field_name,
                        "type": "multiobject",
                        "object_types": ["ipam.vlan"],
                        "related_object_type": "dcim.site",
                    },
                    {
                        "name": object_field,
                        "type": "object",
                        "object_types": ["ipam.vlan"],
                        "related_object_type": "dcim.site",
                    },
                ]
            )
            for requested_tags, requested_sites in (
                ([tag_names[0]], [site_names[0]]),
                ([tag_names[1]], [site_names[1]]),
                ([], []),
            ):
                response = nfclient.run_job(
                    "netbox",
                    "design_deploy",
                    workers="any",
                    kwargs={
                        "design": {
                            "vlans": [
                                {
                                    "group": group_name,
                                    "vid": 3201,
                                    "name": "NORFAB DESIGN ARRAY VLAN",
                                    "tags": requested_tags,
                                    "custom_fields": {
                                        field_name: requested_sites,
                                        object_field: site_names[
                                            0 if requested_tags == [tag_names[0]] else 1
                                        ],
                                    },
                                }
                            ]
                        }
                    },
                )
                for result in response.values():
                    assert not result["failed"], result
                group = nb.ipam.vlan_groups.get(name=group_name)
                vlan = nb.ipam.vlans.get(group_id=group.id, vid=3201)
                expected_tags = (
                    tag_names[:1] if requested_tags == [tag_names[0]] else tag_names
                )
                expected_sites = (
                    [sites[0].id]
                    if requested_tags == [tag_names[0]]
                    else [site.id for site in sites]
                )
                assert {tag.name for tag in vlan.tags} == set(expected_tags)
                assert {site["id"] for site in vlan.custom_fields[field_name]} == set(
                    expected_sites
                )
                assert vlan.custom_fields[object_field]["id"] == (
                    sites[0].id if requested_tags == [tag_names[0]] else sites[1].id
                )
        finally:
            group = nb.ipam.vlan_groups.get(name=group_name)
            if group:
                for vlan in nb.ipam.vlans.filter(group_id=group.id):
                    vlan.delete()
                group.delete()
            for name in (field_name, object_field):
                field = nb.extras.custom_fields.get(name=name)
                if field:
                    field.delete()
            for name in tag_names:
                tag = nb.extras.tags.get(name=name)
                if tag:
                    tag.delete()
            for name in site_names:
                site = nb.dcim.sites.get(name=name)
                if site:
                    site.delete()

    def test_prefix_updates_add_tags_and_custom_field_values(
        self, nfclient: Any
    ) -> None:
        """Preserve prefix array members when a design adds tags and sites."""
        nb = pynetbox.api(url=NB_URL, token=NB_API_TOKEN)
        prefix_value = "198.19.253.0/24"
        field_name = "norfab_design_prefix_sites"
        object_field = "norfab_design_prefix_site"
        tag_names = ["norfab-design-prefix-a", "norfab-design-prefix-b"]
        site_names = ["NORFAB DESIGN PREFIX SITE A", "NORFAB DESIGN PREFIX SITE B"]
        if (
            list(nb.ipam.prefixes.filter(prefix=prefix_value))
            or nb.extras.custom_fields.get(name=field_name)
            or nb.extras.custom_fields.get(name=object_field)
            or any(nb.extras.tags.get(name=name) for name in tag_names)
            or any(nb.dcim.sites.get(name=name) for name in site_names)
        ):
            pytest.skip("design prefix array test objects already exist")

        prefix_id = None
        try:
            nb.extras.tags.create(
                [
                    {"name": tag_names[0], "slug": tag_names[0]},
                    {"name": tag_names[1], "slug": tag_names[1]},
                ]
            )
            sites = nb.dcim.sites.create(
                [
                    {"name": site_names[0], "slug": "norfab-design-prefix-site-a"},
                    {"name": site_names[1], "slug": "norfab-design-prefix-site-b"},
                ]
            )
            nb.extras.custom_fields.create(
                [
                    {
                        "name": field_name,
                        "type": "multiobject",
                        "object_types": ["ipam.prefix"],
                        "related_object_type": "dcim.site",
                    },
                    {
                        "name": object_field,
                        "type": "object",
                        "object_types": ["ipam.prefix"],
                        "related_object_type": "dcim.site",
                    },
                ]
            )
            for requested_tags, requested_sites in (
                ([tag_names[0]], [site_names[0]]),
                ([tag_names[1]], [site_names[1]]),
                ([], []),
            ):
                response = nfclient.run_job(
                    "netbox",
                    "design_deploy",
                    workers="any",
                    kwargs={
                        "design": {
                            "prefixes": [
                                {
                                    "prefix": prefix_value,
                                    "tags": requested_tags,
                                    "custom_fields": {
                                        field_name: requested_sites,
                                        object_field: site_names[
                                            0 if requested_tags == [tag_names[0]] else 1
                                        ],
                                    },
                                }
                            ]
                        }
                    },
                )
                for result in response.values():
                    assert not result["failed"], result
                prefix = nb.ipam.prefixes.get(prefix=prefix_value)
                prefix_id = prefix.id
                expected_tags = (
                    tag_names[:1] if requested_tags == [tag_names[0]] else tag_names
                )
                expected_sites = (
                    [sites[0].id]
                    if requested_tags == [tag_names[0]]
                    else [site.id for site in sites]
                )
                assert {tag.name for tag in prefix.tags} == set(expected_tags)
                assert {site["id"] for site in prefix.custom_fields[field_name]} == set(
                    expected_sites
                )
                assert prefix.custom_fields[object_field]["id"] == (
                    sites[0].id if requested_tags == [tag_names[0]] else sites[1].id
                )
        finally:
            prefix = (
                nb.ipam.prefixes.get(prefix_id)
                if prefix_id
                else nb.ipam.prefixes.get(prefix=prefix_value)
            )
            if prefix:
                prefix.delete()
            for name in (field_name, object_field):
                field = nb.extras.custom_fields.get(name=name)
                if field:
                    field.delete()
            for name in tag_names:
                tag = nb.extras.tags.get(name=name)
                if tag:
                    tag.delete()
            for name in site_names:
                site = nb.dcim.sites.get(name=name)
                if site:
                    site.delete()

    def test_l2vpn_with_inline_targets_and_terminations(self, nfclient: Any) -> None:
        """Create and repeat an L2VPN with inline targets and VLAN attachments."""
        nb = pynetbox.api(url=NB_URL, token=NB_API_TOKEN)
        vpn_name = "NORFAB DESIGN L2VPN"
        other_vpn_name = "NORFAB DESIGN OTHER L2VPN"
        group_name = "NORFAB DESIGN L2VPN VLANS"
        target_name = "64512:99124"
        added_target_name = "64512:99125"
        if (
            nb.vpn.l2vpns.get(name=vpn_name)
            or nb.vpn.l2vpns.get(name=other_vpn_name)
            or nb.ipam.vlan_groups.get(name=group_name)
            or nb.ipam.route_targets.get(name=target_name)
            or nb.ipam.route_targets.get(name=added_target_name)
        ):
            pytest.skip("L2VPN test objects already exist")
        design = {
            "vlan_groups": [{"name": group_name}],
            "vlans": [
                {"name": "NORFAB L2VPN A", "group": group_name, "vid": 301},
                {"name": "NORFAB L2VPN B", "group": group_name, "vid": 302},
            ],
            "l2vpns": [
                {
                    "name": vpn_name,
                    "type": "vxlan",
                    "identifier": 99124,
                    "import_route_targets": [{"name": target_name}],
                    "export_route_targets": [{"name": target_name}],
                    "terminations": [{"group": group_name, "vid": 301}],
                }
            ],
            "l2vpn_terminations": [
                {"l2vpn": vpn_name, "group": group_name, "vid": 302}
            ],
        }
        try:
            preview = nfclient.run_job(
                "netbox",
                "design_deploy",
                workers="any",
                kwargs={"design": design, "dry_run": True},
            )
            for result in preview.values():
                assert not result["failed"], result
                assert result["result"]["l2vpns"]["created"] == [vpn_name]
                assert len(result["result"]["l2vpn_terminations"]["created"]) == 2
            assert nb.vpn.l2vpns.get(name=vpn_name) is None
            for action in ("created", "updated"):
                if action == "updated":
                    design["l2vpns"][0]["description"] = "updated L2VPN"
                    design["route_targets"] = [
                        {"name": target_name},
                        {"name": added_target_name},
                    ]
                    design["l2vpns"][0]["import_route_targets"] = [
                        {"query": {"name": [target_name, added_target_name]}},
                        {"query": {"name": target_name}},
                    ]
                    design["l2vpns"][0]["export_route_targets"] = [
                        {"query": {"name": target_name}}
                    ]
                response = nfclient.run_job(
                    "netbox", "design_deploy", workers="any", kwargs={"design": design}
                )
                for result in response.values():
                    assert not result["failed"], result
                    assert result["result"]["l2vpns"][action] == [vpn_name]
                    assert len(result["result"]["l2vpn_terminations"][action]) == 2
                    assert target_name in result["result"]["route_targets"][action]
            vpn = nb.vpn.l2vpns.get(name=vpn_name)
            assert vpn.description == "updated L2VPN"
            assert [target.name for target in vpn.import_targets] == [
                target_name,
                added_target_name,
            ]
            assert [target.name for target in vpn.export_targets] == [target_name]
            group = nb.ipam.vlan_groups.get(name=group_name)
            vlans = list(nb.ipam.vlans.filter(group_id=group.id))
            terminations = list(nb.vpn.l2vpn_terminations.filter(l2vpn_id=vpn.id))
            assert {
                (item.assigned_object_type, item.assigned_object_id)
                for item in terminations
            } == {("ipam.vlan", vlan.id) for vlan in vlans}
            conflict = nfclient.run_job(
                "netbox",
                "design_deploy",
                workers="any",
                kwargs={
                    "design": {
                        "l2vpns": [{"name": other_vpn_name, "type": "vxlan"}],
                        "l2vpn_terminations": [
                            {"l2vpn": other_vpn_name, "group": group_name, "vid": 301}
                        ],
                    }
                },
            )
            for result in conflict.values():
                assert result["failed"], result
                assert "already attached" in str(result["errors"])
        finally:
            other_vpn = nb.vpn.l2vpns.get(name=other_vpn_name)
            if other_vpn:
                other_vpn.delete()
            vpn = nb.vpn.l2vpns.get(name=vpn_name)
            if vpn:
                for termination in nb.vpn.l2vpn_terminations.filter(l2vpn_id=vpn.id):
                    termination.delete()
                vpn.delete()
            group = nb.ipam.vlan_groups.get(name=group_name)
            if group:
                for vlan in nb.ipam.vlans.filter(group_id=group.id):
                    vlan.delete()
                group.delete()
            for name in (target_name, added_target_name):
                target = nb.ipam.route_targets.get(name=name)
                if target:
                    target.delete()

    def test_custom_fields(self, nfclient: Any) -> None:
        """Create, PATCH, preserve and clear custom fields through design deployment."""
        nb = pynetbox.api(url=NB_URL, token=NB_API_TOKEN)
        if nb.extras.custom_fields.get(
            name="norfab_design_cf"
        ) or nb.extras.custom_fields.get(name="norfab_design_keep"):
            pytest.skip("Custom-field test definitions already exist")
        if list(nb.ipam.prefixes.filter(within_include="198.19.247.0/24")) or list(
            nb.ipam.ip_addresses.filter(parent="198.19.247.0/24")
        ):
            pytest.skip("Custom-field test pool already exists")
        definitions = []
        try:
            invalid = nfclient.run_job(
                "netbox",
                "design_deploy",
                workers="any",
                kwargs={
                    "design": {
                        "prefixes": [
                            {"prefix": "198.19.247.0/24", "custom_fields": ["invalid"]}
                        ]
                    }
                },
            )
            for result in invalid.values():
                assert result["failed"], result
                assert "custom_fields must be a dictionary" in str(result["errors"])
            assert not nb.ipam.prefixes.get(prefix="198.19.247.0/24")
            for name in ("norfab_design_cf", "norfab_design_keep"):
                definitions.append(
                    nb.extras.custom_fields.create(
                        {
                            "name": name,
                            "type": "text",
                            "object_types": ["ipam.prefix", "ipam.ipaddress"],
                        }
                    )
                )
            for fields in (
                {"norfab_design_cf": "first", "norfab_design_keep": "keep"},
                {"norfab_design_cf": "second"},
                {"norfab_design_cf": None},
            ):
                reply = nfclient.run_job(
                    "netbox",
                    "design_deploy",
                    workers="any",
                    kwargs={
                        "design": {
                            "prefixes": [
                                {"prefix": "198.19.247.0/24", "custom_fields": fields},
                                {
                                    "create_prefix": {
                                        "parent": "198.19.247.0/24",
                                        "prefixlen": 28,
                                        "description": "NORFAB CF CHILD",
                                        "custom_fields": fields,
                                    }
                                },
                            ],
                            "ip_addresses": [
                                {
                                    "address": "198.19.247.250/24",
                                    "custom_fields": fields,
                                },
                                {
                                    "create_ip": {
                                        "prefix": {"description": "NORFAB CF CHILD"},
                                        "description": "NORFAB CF IP",
                                        "custom_fields": fields,
                                    }
                                },
                            ],
                        }
                    },
                )
                for result in reply.values():
                    assert not result["failed"], result
                objects = list(
                    nb.ipam.prefixes.filter(within_include="198.19.247.0/24")
                ) + list(nb.ipam.ip_addresses.filter(parent="198.19.247.0/24"))
                assert len(objects) == 4
                for obj in objects:
                    assert (
                        obj.custom_fields["norfab_design_cf"]
                        == fields["norfab_design_cf"]
                    )
                    assert obj.custom_fields["norfab_design_keep"] == "keep"
            for value, expected in [("preview", ["norfab_design_cf"]), (None, [])]:
                reply = nfclient.run_job(
                    "netbox",
                    "create_prefix",
                    workers="any",
                    kwargs={
                        "parent": "198.19.247.0/24",
                        "prefixlen": 28,
                        "description": "NORFAB CF CHILD",
                        "custom_fields": {
                            "norfab_design_cf": value,
                            "norfab_design_keep": "keep",
                        },
                        "dry_run": True,
                    },
                )
                for result in reply.values():
                    assert not result["failed"], result
                    assert result["diff"].get("custom_fields", []) == expected
                assert (
                    nb.ipam.prefixes.get(description="NORFAB CF CHILD").custom_fields[
                        "norfab_design_cf"
                    ]
                    is None
                )
        finally:
            for obj in nb.ipam.ip_addresses.filter(parent="198.19.247.0/24"):
                obj.delete()
            for obj in nb.ipam.prefixes.filter(within="198.19.247.0/24"):
                obj.delete()
            parent = nb.ipam.prefixes.get(prefix="198.19.247.0/24")
            if parent:
                parent.delete()
            for definition in reversed(definitions):
                definition.delete()

    def test_community_description_matching(self, nfclient: Any) -> None:
        """Match a community by value alone or by value and description."""
        nb = pynetbox.api(url=NB_URL, token=NB_API_TOKEN)
        if list(nb.plugins.bgp.community.filter(value="65199:61999")):
            pytest.skip("Community test value already exists")
        try:
            for records, count in (
                ([{"value": "65199:61999", "description": "NORFAB FIRST"}], 1),
                ([{"value": "65199:61999"}], 1),
                ([{"value": "65199:61999", "description": "NORFAB SECOND"}], 2),
                ([{"value": "65199:61999", "description": "NORFAB SECOND"}], 2),
            ):
                response = nfclient.run_job(
                    "netbox",
                    "design_deploy",
                    workers="any",
                    kwargs={"design": {"bgp_communities": records}},
                )
                for result in response.values():
                    assert not result["failed"], result
                assert (
                    len(list(nb.plugins.bgp.community.filter(value="65199:61999")))
                    == count
                )
            response = nfclient.run_job(
                "netbox",
                "design_deploy",
                workers="any",
                kwargs={"design": {"bgp_communities": [{"value": "65199:61999"}]}},
            )
            for result in response.values():
                assert result["failed"], result
                assert "ambiguous BGP community" in str(result["errors"])
        finally:
            for item in nb.plugins.bgp.community.filter(value="65199:61999"):
                item.delete()

    def test_vlan_group_scopes(self, nfclient: Any) -> None:
        """Create and update VLAN groups across all supported Netbox scopes."""
        nb = pynetbox.api(url=NB_URL, token=NB_API_TOKEN)
        name = "NORFAB DESIGN SCOPE"
        scope_names = {
            "region": f"{name} REGION",
            "site_group": f"{name} SITE GROUP",
            "site": f"{name} SITE",
            "location": f"{name} LOCATION",
            "rack": f"{name} RACK",
            "cluster_group": f"{name} CLUSTER GROUP",
            "cluster_type": f"{name} CLUSTER TYPE",
            "cluster": f"{name} CLUSTER",
        }
        endpoints = {
            "region": nb.dcim.regions,
            "site_group": nb.dcim.site_groups,
            "site": nb.dcim.sites,
            "location": nb.dcim.locations,
            "rack": nb.dcim.racks,
            "cluster_group": nb.virtualization.cluster_groups,
            "cluster_type": nb.virtualization.cluster_types,
            "cluster": nb.virtualization.clusters,
        }
        group_names = {
            scope: f"{name} {scope.upper()} VLAN GROUP"
            for scope in scope_names
            if scope != "cluster_type"
        }
        if any(
            endpoint.get(name=scope_names[scope])
            for scope, endpoint in endpoints.items()
        ) or any(
            nb.ipam.vlan_groups.get(name=group_name)
            for group_name in group_names.values()
        ):
            pytest.skip("VLAN group scope test objects already exist in Netbox")

        created = []
        try:
            region = nb.dcim.regions.create(
                {"name": scope_names["region"], "slug": "norfab-design-scope-region"}
            )
            created.append(region)
            site_group = nb.dcim.site_groups.create(
                {
                    "name": scope_names["site_group"],
                    "slug": "norfab-design-scope-site-group",
                }
            )
            created.append(site_group)
            site = nb.dcim.sites.create(
                {
                    "name": scope_names["site"],
                    "slug": "norfab-design-scope-site",
                    "region": region.id,
                    "group": site_group.id,
                    "status": "active",
                }
            )
            created.append(site)
            location = nb.dcim.locations.create(
                {
                    "name": scope_names["location"],
                    "slug": "norfab-design-scope-location",
                    "site": site.id,
                }
            )
            created.append(location)
            rack = nb.dcim.racks.create(
                {
                    "name": scope_names["rack"],
                    "site": site.id,
                    "location": location.id,
                    "status": "active",
                }
            )
            created.append(rack)
            cluster_group = nb.virtualization.cluster_groups.create(
                {
                    "name": scope_names["cluster_group"],
                    "slug": "norfab-design-scope-cluster-group",
                }
            )
            created.append(cluster_group)
            cluster_type = nb.virtualization.cluster_types.create(
                {
                    "name": scope_names["cluster_type"],
                    "slug": "norfab-design-scope-cluster-type",
                }
            )
            created.append(cluster_type)
            cluster = nb.virtualization.clusters.create(
                {
                    "name": scope_names["cluster"],
                    "type": cluster_type.id,
                    "group": cluster_group.id,
                }
            )
            created.append(cluster)

            scopes = {
                "region": region,
                "site_group": site_group,
                "site": site,
                "location": location,
                "rack": rack,
                "cluster_group": cluster_group,
                "cluster": cluster,
            }
            design = {
                "vlan_groups": [
                    {
                        "name": group_names[scope],
                        scope: scope_names[scope],
                        **(
                            {"site": scope_names["site"]}
                            if scope in ("location", "rack")
                            else {}
                        ),
                    }
                    for scope in scopes
                ]
            }
            for action in ("created", "updated"):
                response = nfclient.run_job(
                    "netbox", "design_deploy", workers="any", kwargs={"design": design}
                )
                for result in response.values():
                    assert result["failed"] is False, result
                    assert result["result"]["vlan_groups"][action] == list(
                        group_names.values()
                    )
                for scope, obj in scopes.items():
                    group = nb.ipam.vlan_groups.get(name=group_names[scope])
                    assert group.scope_id == obj.id
                    assert group.scope_type == (
                        f"virtualization.{scope.replace('_', '')}"
                        if scope.startswith("cluster")
                        else f"dcim.{scope.replace('_', '')}"
                    )
        finally:
            for group_name in group_names.values():
                group = nb.ipam.vlan_groups.get(name=group_name)
                if group:
                    group.delete()
            for obj in reversed(created):
                obj.delete()

    def test_config_context(self, nfclient: Any) -> None:
        """Create a scoped context and compute local data after interfaces exist."""
        nb = pynetbox.api(url=NB_URL, token=NB_API_TOKEN)
        site_name = "NORFAB DESIGN CONTEXT SITE"
        added_site_name = "NORFAB DESIGN CONTEXT OTHER SITE"
        manufacturer_name = "NORFAB DESIGN CONTEXT MANUFACTURER"
        type_name = "NORFAB DESIGN CONTEXT TYPE"
        role_name = "NORFAB DESIGN CONTEXT ROLE"
        device_names = ["norfab-context-static", "norfab-context-computed"]
        context_name = "NORFAB DESIGN CONTEXT BASELINE"
        objects = [
            (nb.extras.config_contexts, {"name": context_name}),
            (nb.dcim.interfaces, {"device": device_names}),
            (nb.dcim.devices, {"name": device_names}),
            (nb.ipam.vrfs, {"name": "NORFAB DESIGN CONTEXT VRF"}),
            (nb.dcim.sites, {"name": [site_name, added_site_name]}),
            (nb.dcim.device_types, {"model": type_name}),
            (nb.dcim.device_roles, {"name": role_name}),
            (nb.dcim.manufacturers, {"name": manufacturer_name}),
            (nb.extras.custom_fields, {"name": "norfab_design_device_context"}),
            (nb.extras.custom_fields, {"name": "norfab_design_device_keep"}),
        ]
        for endpoint, filters in objects:
            if endpoint.name == "interfaces":
                continue
            if list(endpoint.filter(**filters)):
                pytest.skip("context test objects already exist")
        design = {
            "custom_functions": {
                "calculate_acme_device_context": "nf://netbox/designs/calculate_acme_device_context.py"
            },
            "manufacturers": [{"name": manufacturer_name}],
            "device_types": [{"model": type_name, "manufacturer": manufacturer_name}],
            "device_roles": [{"name": role_name}],
            "sites": [{"name": site_name}, {"name": added_site_name}],
            "vrfs": [{"name": "NORFAB DESIGN CONTEXT VRF"}],
            "devices": [
                {
                    "name": device_names[0],
                    "site": site_name,
                    "role": role_name,
                    "device_type": {
                        "manufacturer": manufacturer_name,
                        "model": type_name,
                    },
                    "local_context_data": {"acme": {"profile": "static"}},
                    "custom_fields": {
                        "norfab_design_device_context": "ACME first",
                        "norfab_design_device_keep": 42,
                        "norfab_design_device_ip": "198.19.243.10/32",
                        "norfab_design_device_ips": ["198.19.243.10/32"],
                    },
                },
                {
                    "name": device_names[1],
                    "site": site_name,
                    "role": role_name,
                    "device_type": {
                        "manufacturer": manufacturer_name,
                        "model": type_name,
                    },
                    "interfaces": {
                        "Loopback0": {
                            "type": "virtual",
                            "vrf": "NORFAB DESIGN CONTEXT VRF",
                        }
                    },
                },
            ],
            "local_context_data": [
                {
                    "device": device_names[1],
                    "site": site_name,
                    "local_context_data": {
                        "custom_function": "calculate_acme_device_context",
                        "profile": "test",
                    },
                }
            ],
            "config_context": [
                {
                    "name": context_name,
                    "sites": [site_name],
                    "data": {"acme": {"managed": True}},
                }
            ],
        }
        try:
            nb.extras.custom_fields.create(
                {
                    "name": "norfab_design_device_context",
                    "type": "text",
                    "object_types": ["dcim.device"],
                }
            )
            nb.extras.custom_fields.create(
                {
                    "name": "norfab_design_device_keep",
                    "type": "integer",
                    "object_types": ["dcim.device"],
                }
            )
            for run in (1, 2):
                if run == 2:
                    design["config_context"][0]["sites"] = [added_site_name]
                    design["devices"][0]["custom_fields"].update(
                        {
                            "norfab_design_device_ip": "198.19.243.11/32",
                            "norfab_design_device_ips": ["198.19.243.11/32"],
                        }
                    )
                reply = nfclient.run_job(
                    "netbox",
                    "design_deploy",
                    workers="any",
                    kwargs={"design": design, "context": {"profile": "test"}},
                )
                for result in reply.values():
                    assert not result["failed"], result
                    assert not result["errors"], result
                device = nb.dcim.devices.get(name=device_names[0])
                reference_ips = [
                    nb.ipam.ip_addresses.get(address=address)
                    for address in ("198.19.243.10/32", "198.19.243.11/32")
                ]
                assert (
                    device.custom_fields["norfab_design_device_ip"]["id"]
                    == reference_ips[run - 1].id
                )
                assert {
                    item["id"]
                    for item in device.custom_fields["norfab_design_device_ips"]
                } == {item.id for item in reference_ips[:run]}
                context = nb.extras.config_contexts.get(name=context_name)
                assert (
                    nb.dcim.interfaces.get(
                        device=device_names[1], name="Loopback0"
                    ).vrf.name
                    == "NORFAB DESIGN CONTEXT VRF"
                )
                assert context.data == {"acme": {"managed": True}}
                assert (
                    nb.dcim.devices.get(name=device_names[0]).custom_fields[
                        "norfab_design_device_context"
                    ]
                    == design["devices"][0]["custom_fields"][
                        "norfab_design_device_context"
                    ]
                )
                design["devices"][0]["custom_fields"][
                    "norfab_design_device_context"
                ] = "ACME updated"
                design["devices"][0]["custom_fields"].pop(
                    "norfab_design_device_keep", None
                )
                assert (
                    nb.dcim.devices.get(name=device_names[0]).custom_fields[
                        "norfab_design_device_keep"
                    ]
                    == 42
                )
                assert {site.name for site in context.sites} == (
                    {site_name} if run == 1 else {site_name, added_site_name}
                )
                assert nb.dcim.devices.get(name=device_names[0]).local_context_data == {
                    "acme": {"profile": "static"}
                }
                assert nb.dcim.devices.get(name=device_names[1]).local_context_data == {
                    "acme": {
                        "profile": "test",
                        "site": site_name,
                        "role": role_name,
                        "interface_count": 1,
                        "primary_ip": None,
                    }
                }
            device_id = nb.dcim.devices.get(name=device_names[0]).id
            # Omitted fields remain intact, dry runs do not write, and null clears.
            for fields, dry_run, expected in [
                ({}, False, "ACME updated"),
                ({"custom_fields": {}}, False, "ACME updated"),
                (
                    {"custom_fields": {"norfab_design_device_context": "dry run"}},
                    True,
                    "ACME updated",
                ),
                (
                    {"custom_fields": {"norfab_design_device_context": None}},
                    False,
                    None,
                ),
                (
                    {"custom_fields": {"norfab_design_device_context": None}},
                    False,
                    None,
                ),
            ]:
                reply = nfclient.run_job(
                    "netbox",
                    "design_deploy",
                    workers="any",
                    kwargs={
                        "design": {
                            "devices": [
                                {"name": device_names[0], "site": site_name, **fields}
                            ]
                        },
                        "dry_run": dry_run,
                    },
                )
                for result in reply.values():
                    assert not result["failed"], result
                    assert not result["errors"], result
                devices = list(nb.dcim.devices.filter(name=device_names[0]))
                assert len(devices) == 1
                assert devices[0].id == device_id
                assert (
                    devices[0].custom_fields["norfab_design_device_context"] == expected
                )
                assert devices[0].custom_fields["norfab_design_device_keep"] == 42
                assert devices[0].local_context_data == {"acme": {"profile": "static"}}
        finally:
            for endpoint, filters in objects:
                if endpoint.name == "interfaces":
                    for device_name in device_names:
                        for interface in nb.dcim.interfaces.filter(device=device_name):
                            interface.delete()
                    continue
                for record in endpoint.filter(**filters):
                    record.delete()

    def test_existing_vlan_references(self, nfclient: Any) -> None:
        """Use one deployment lookup for an existing VLAN referenced twice."""
        nb = pynetbox.api(url=NB_URL, token=NB_API_TOKEN)
        device = nb.dcim.devices.get(name="ceos1")
        if not device:
            pytest.skip("ceos1 fixture required")
        group_name = "NORFAB DESIGN CACHE VLANS"
        interface_name = "NORFAB-CACHE-INTERFACE"
        prefix_value = "198.19.244.0/24"
        if (
            nb.ipam.vlan_groups.get(name=group_name)
            or nb.dcim.interfaces.get(device_id=device.id, name=interface_name)
            or nb.ipam.prefixes.get(prefix=prefix_value)
        ):
            pytest.skip("VLAN reference test objects already exist")
        try:
            group = nb.ipam.vlan_groups.create(
                {"name": group_name, "slug": "norfab-design-cache-vlans"}
            )
            vlan = nb.ipam.vlans.create(
                {"group": group.id, "vid": 2999, "name": "NORFAB CACHE VLAN"}
            )
            design = {
                "prefixes": [
                    {"prefix": prefix_value, "vlan": {"group": group_name, "vid": 2999}}
                ],
                "interfaces": [
                    {
                        "device": device.name,
                        "name": interface_name,
                        "type": "virtual",
                        "mode": "access",
                        "untagged_vlan": {"group": group_name, "vid": 2999},
                    }
                ],
            }
            for _ in (1, 2):
                reply = nfclient.run_job(
                    "netbox", "design_deploy", workers="any", kwargs={"design": design}
                )
                for result in reply.values():
                    assert not result["failed"], result
                assert nb.ipam.prefixes.get(prefix=prefix_value).vlan.id == vlan.id
                assert (
                    nb.dcim.interfaces.get(
                        device_id=device.id, name=interface_name
                    ).untagged_vlan.id
                    == vlan.id
                )
        finally:
            interface = nb.dcim.interfaces.get(device_id=device.id, name=interface_name)
            if interface:
                interface.delete()
            prefix = nb.ipam.prefixes.get(prefix=prefix_value)
            if prefix:
                prefix.delete()
            group = nb.ipam.vlan_groups.get(name=group_name)
            if group:
                for vlan in nb.ipam.vlans.filter(group_id=group.id):
                    vlan.delete()
                group.delete()

    def test_prefix_scope_precedence(self, nfclient: Any) -> None:
        """Resolve prefix scopes from location through region in priority order."""
        nb = pynetbox.api(url=NB_URL, token=NB_API_TOKEN)
        prefixes = [
            "198.19.245.10/32",
            "198.19.245.11/32",
            "198.19.245.12/32",
            "198.19.245.13/32",
        ]
        if list(nb.ipam.prefixes.filter(prefix=prefixes)):
            pytest.skip("prefix scope test addresses already exist")
        if any(
            (
                nb.dcim.regions.get(name="NORFAB DESIGN SCOPE REGION"),
                nb.dcim.site_groups.get(name="NORFAB DESIGN SCOPE GROUP"),
                nb.dcim.sites.get(name="NORFAB DESIGN SCOPE SITE"),
                nb.dcim.locations.get(name="NORFAB DESIGN SCOPE LOCATION"),
            )
        ):
            pytest.skip("prefix scope test prerequisites already exist")
        try:
            region = nb.dcim.regions.create(
                {
                    "name": "NORFAB DESIGN SCOPE REGION",
                    "slug": "norfab-design-scope-region",
                }
            )
            site_group = nb.dcim.site_groups.create(
                {
                    "name": "NORFAB DESIGN SCOPE GROUP",
                    "slug": "norfab-design-scope-group",
                }
            )
            site = nb.dcim.sites.create(
                {
                    "name": "NORFAB DESIGN SCOPE SITE",
                    "slug": "norfab-design-scope-site",
                    "region": region.id,
                    "group": site_group.id,
                }
            )
            location = nb.dcim.locations.create(
                {
                    "name": "NORFAB DESIGN SCOPE LOCATION",
                    "slug": "norfab-design-scope-location",
                    "site": site.id,
                }
            )
            design = {
                "prefixes": [
                    {
                        "prefix": prefixes[0],
                        "location": location.name,
                        "site": site.name,
                        "site_group": site_group.name,
                        "region": region.name,
                    },
                    {
                        "prefix": prefixes[1],
                        "site": site.name,
                        "site_group": site_group.name,
                        "region": region.name,
                    },
                    {
                        "prefix": prefixes[2],
                        "site_group": site_group.name,
                        "region": region.name,
                    },
                    {"prefix": prefixes[3], "region": region.name},
                ]
            }
            for _ in (1, 2):
                reply = nfclient.run_job(
                    "netbox", "design_deploy", workers="any", kwargs={"design": design}
                )
                for result in reply.values():
                    assert not result["failed"], result
                for prefix, scope_type, scope_id in zip(
                    prefixes,
                    ("dcim.location", "dcim.site", "dcim.sitegroup", "dcim.region"),
                    (location.id, site.id, site_group.id, region.id),
                ):
                    record = nb.ipam.prefixes.get(prefix=prefix)
                    assert (record.scope_type, record.scope_id) == (
                        scope_type,
                        scope_id,
                    )
        finally:
            for prefix in prefixes:
                record = nb.ipam.prefixes.get(prefix=prefix)
                if record:
                    record.delete()
            for endpoint, name in (
                (nb.dcim.locations, "NORFAB DESIGN SCOPE LOCATION"),
                (nb.dcim.sites, "NORFAB DESIGN SCOPE SITE"),
                (nb.dcim.site_groups, "NORFAB DESIGN SCOPE GROUP"),
                (nb.dcim.regions, "NORFAB DESIGN SCOPE REGION"),
            ):
                record = endpoint.get(name=name)
                if record:
                    record.delete()

    def test_asn_updates_add_sites_tags_and_custom_field_values(
        self, nfclient: Any
    ) -> None:
        """Add ASN array members on design updates without removing existing ones."""
        nb = pynetbox.api(url=NB_URL, token=NB_API_TOKEN)
        asn_number = 4200999602
        new_asn_number = 4200999603
        rir_name = "NORFAB DESIGN ARRAY ASN RIR"
        site_names = [
            "NORFAB DESIGN ARRAY ASN SITE A",
            "NORFAB DESIGN ARRAY ASN SITE B",
        ]
        tag_names = ["norfab-design-asn-a", "norfab-design-asn-b"]
        field_name = "norfab_design_asn_sites"
        if (
            nb.ipam.asns.get(asn=asn_number)
            or nb.ipam.asns.get(asn=new_asn_number)
            or nb.ipam.rirs.get(name=rir_name)
            or nb.extras.custom_fields.get(name=field_name)
            or any(nb.dcim.sites.get(name=name) for name in site_names)
            or any(nb.extras.tags.get(name=name) for name in tag_names)
        ):
            pytest.skip("design ASN array test objects already exist")

        try:
            rir = nb.ipam.rirs.create(
                {"name": rir_name, "slug": "norfab-design-array-asn-rir"}
            )
            sites = nb.dcim.sites.create(
                [
                    {"name": site_names[0], "slug": "norfab-design-array-asn-site-a"},
                    {"name": site_names[1], "slug": "norfab-design-array-asn-site-b"},
                ]
            )
            nb.extras.tags.create(
                [
                    {"name": tag_names[0], "slug": tag_names[0]},
                    {"name": tag_names[1], "slug": tag_names[1]},
                ]
            )
            nb.extras.custom_fields.create(
                {
                    "name": field_name,
                    "type": "multiobject",
                    "object_types": ["ipam.asn"],
                    "related_object_type": "dcim.site",
                }
            )
            nb.ipam.asns.create(
                {
                    "asn": asn_number,
                    "rir": rir.id,
                    "sites": [sites[0].id],
                    "tags": [{"name": tag_names[0]}],
                    "custom_fields": {field_name: [sites[0].id]},
                }
            )
            for requested_sites, requested_tags, requested_refs in (
                ([site_names[1]], [tag_names[1]], [site_names[1]]),
                ([], [], []),
                (None, [], []),
            ):
                response = nfclient.run_job(
                    "netbox",
                    "design_deploy",
                    workers="any",
                    kwargs={
                        "design": {
                            "asns": [
                                {
                                    "asn": asn_number,
                                    "sites": requested_sites,
                                    "tags": requested_tags,
                                    "custom_fields": {field_name: requested_refs},
                                }
                            ]
                        }
                    },
                )
                for result in response.values():
                    assert not result["failed"], result
                asn = nb.ipam.asns.get(asn=asn_number)
                assert {site.name for site in asn.sites} == set(site_names)
                assert {tag.name for tag in asn.tags} == set(tag_names)
                assert {site["id"] for site in asn.custom_fields[field_name]} == {
                    site.id for site in sites
                }
            response = nfclient.run_job(
                "netbox",
                "design_deploy",
                workers="any",
                kwargs={
                    "design": {
                        "asns": [
                            {"asn": asn_number, "custom_fields": {field_name: None}}
                        ]
                    }
                },
            )
            for result in response.values():
                assert not result["failed"], result
            assert nb.ipam.asns.get(asn=asn_number).custom_fields[field_name] is None
            response = nfclient.run_job(
                "netbox",
                "design_deploy",
                workers="any",
                kwargs={
                    "design": {
                        "asns": [
                            {
                                "asn": new_asn_number,
                                "rir": rir_name,
                                "custom_fields": {field_name: [site_names[0]]},
                            }
                        ]
                    }
                },
            )
            for result in response.values():
                assert not result["failed"], result
            created = nb.ipam.asns.get(asn=new_asn_number)
            assert [site["id"] for site in created.custom_fields[field_name]] == [
                sites[0].id
            ]
        finally:
            for number in (asn_number, new_asn_number):
                asn = nb.ipam.asns.get(asn=number)
                if asn:
                    asn.delete()
            field = nb.extras.custom_fields.get(name=field_name)
            if field:
                field.delete()
            for name in tag_names:
                tag = nb.extras.tags.get(name=name)
                if tag:
                    tag.delete()
            for name in site_names:
                site = nb.dcim.sites.get(name=name)
                if site:
                    site.delete()
            rir = nb.ipam.rirs.get(name=rir_name)
            if rir:
                rir.delete()

    def test_allocated_asn_sites_and_role(self, nfclient: Any) -> None:
        """Allocate an ASN, attach its site and role, then reuse it."""
        nb = pynetbox.api(url=NB_URL, token=NB_API_TOKEN)
        objects = [
            (nb.ipam.asns, {"asn": [4200999600, 4200999601]}),
            (nb.ipam.asn_ranges, {"name": "NORFAB DESIGN ASN RANGE"}),
            (nb.ipam.roles, {"name": "NORFAB DESIGN ASN ROLE"}),
            (nb.ipam.rirs, {"name": "NORFAB DESIGN ASN RIR"}),
            (nb.dcim.sites, {"name": "NORFAB DESIGN ASN SITE"}),
        ]
        for endpoint, filters in objects:
            if list(endpoint.filter(**filters)):
                pytest.skip(f"ASN test object already exists: {filters}")
        design = {
            "sites": [{"name": "NORFAB DESIGN ASN SITE"}],
            "roles": [{"name": "NORFAB DESIGN ASN ROLE"}],
            "rirs": [{"name": "NORFAB DESIGN ASN RIR"}],
            "asn_ranges": [
                {
                    "name": "NORFAB DESIGN ASN RANGE",
                    "rir": "NORFAB DESIGN ASN RIR",
                    "start": 4200999600,
                    "end": 4200999601,
                }
            ],
            "asns": [
                {
                    "create_asn": {
                        "asn_range": "NORFAB DESIGN ASN RANGE",
                        "description": "NORFAB DESIGN ALLOCATED ASN",
                        "sites": ["NORFAB DESIGN ASN SITE"],
                        "role": "NORFAB DESIGN ASN ROLE",
                    }
                }
            ],
        }
        try:
            for _ in (1, 2):
                reply = nfclient.run_job(
                    "netbox", "design_deploy", workers="any", kwargs={"design": design}
                )
                for result in reply.values():
                    assert not result["failed"], result
                asn = nb.ipam.asns.get(asn=4200999600)
                assert asn.role.name == "NORFAB DESIGN ASN ROLE"
                assert [site.name for site in asn.sites] == ["NORFAB DESIGN ASN SITE"]
        finally:
            for endpoint, filters in objects:
                for record in endpoint.filter(**filters):
                    record.delete()

    def test_devices_with_same_name_at_different_sites(self, nfclient: Any) -> None:
        """Match devices by site and tenant on repeated deployment."""
        nb = pynetbox.api(url=NB_URL, token=NB_API_TOKEN)
        objects = [
            (nb.dcim.devices, {"name": "norfab-design-identity-device"}),
            (
                nb.dcim.sites,
                {"name": ["NORFAB DESIGN ID SITE A", "NORFAB DESIGN ID SITE B"]},
            ),
            (nb.dcim.device_types, {"model": "NORFAB DESIGN ID TYPE"}),
            (nb.dcim.device_roles, {"name": "NORFAB DESIGN ID ROLE"}),
            (nb.dcim.manufacturers, {"name": "NORFAB DESIGN ID MANUFACTURER"}),
            (nb.tenancy.tenants, {"name": "NORFAB DESIGN ID TENANT"}),
        ]
        for endpoint, filters in objects:
            if list(endpoint.filter(**filters)):
                pytest.skip(f"identity test object already exists: {filters}")
        design = {
            "tenants": [{"name": "NORFAB DESIGN ID TENANT"}],
            "manufacturers": [{"name": "NORFAB DESIGN ID MANUFACTURER"}],
            "device_types": [
                {
                    "model": "NORFAB DESIGN ID TYPE",
                    "manufacturer": "NORFAB DESIGN ID MANUFACTURER",
                }
            ],
            "device_roles": [{"name": "NORFAB DESIGN ID ROLE"}],
            "sites": [
                {"name": "NORFAB DESIGN ID SITE A"},
                {"name": "NORFAB DESIGN ID SITE B"},
            ],
            "devices": [
                {
                    "name": "norfab-design-identity-device",
                    "site": "NORFAB DESIGN ID SITE A",
                    "tenant": "NORFAB DESIGN ID TENANT",
                    "role": "NORFAB DESIGN ID ROLE",
                    "device_type": {
                        "manufacturer": "NORFAB DESIGN ID MANUFACTURER",
                        "model": "NORFAB DESIGN ID TYPE",
                    },
                },
                {
                    "name": "norfab-design-identity-device",
                    "site": "NORFAB DESIGN ID SITE B",
                    "tenant": "NORFAB DESIGN ID TENANT",
                    "role": "NORFAB DESIGN ID ROLE",
                    "device_type": {
                        "manufacturer": "NORFAB DESIGN ID MANUFACTURER",
                        "model": "NORFAB DESIGN ID TYPE",
                    },
                },
            ],
        }
        try:
            for run in (1, 2):
                reply = nfclient.run_job(
                    "netbox", "design_deploy", workers="any", kwargs={"design": design}
                )
                for result in reply.values():
                    assert not result["failed"], result
                    if run == 2:
                        assert not result["result"]["devices"]["created"]
                devices = list(
                    nb.dcim.devices.filter(name="norfab-design-identity-device")
                )
                assert len(devices) == 2
                assert {device.site.name for device in devices} == {
                    "NORFAB DESIGN ID SITE A",
                    "NORFAB DESIGN ID SITE B",
                }
        finally:
            for endpoint, filters in objects:
                for record in endpoint.filter(**filters):
                    record.delete()

    def test_connections(self, nfclient: Any) -> None:
        """Create and update a cable between test interfaces without duplicating it."""
        nb = pynetbox.api(url=NB_URL, token=NB_API_TOKEN)
        device = nb.dcim.devices.get(name="ceos1")
        if not device:
            pytest.skip("ceos1 fixture required")
        names = ["NORFAB-CABLE-A", "NORFAB-CABLE-B"]
        if list(nb.dcim.interfaces.filter(device="ceos1", name=names)):
            pytest.skip("cable fixtures already exist")
        design = {
            "interfaces": [
                {
                    "name": "NORFAB-CABLE-A",
                    "device": "ceos1",
                    "type": "1000base-t",
                    "connection": {
                        "device": "ceos1",
                        "interface": "NORFAB-CABLE-B",
                        "label": "NORFAB DESIGN CABLE",
                        "type": "cat6",
                    },
                },
                {"name": "NORFAB-CABLE-B", "device": "ceos1", "type": "1000base-t"},
            ],
        }
        cable_id = None
        try:
            for run in (1, 2):
                reply = nfclient.run_job(
                    "netbox", "design_deploy", workers="any", kwargs={"design": design}
                )
                assert reply
                for result in reply.values():
                    assert not result["failed"], result
                interface = nb.dcim.interfaces.get(device="ceos1", name=names[0])
                assert interface.cable
                if cable_id:
                    assert interface.cable.id == cable_id
                cable_id = interface.cable.id
                assert (
                    nb.dcim.interfaces.get(device="ceos1", name=names[1]).cable.id
                    == cable_id
                )
        finally:
            for interface in nb.dcim.interfaces.filter(device="ceos1", name=names):
                if interface.cable:
                    cable = nb.dcim.cables.get(interface.cable.id)
                    if cable:
                        cable.delete()
                interface.delete()

    def test_console_and_power_connections(self, nfclient: Any) -> None:
        """Deploy nested and top-level ports, then cable both port families."""
        nb = pynetbox.api(url=NB_URL, token=NB_API_TOKEN)
        site_name = "NORFAB DESIGN PORT SITE"
        device_names = ["norfab-design-port-a", "norfab-design-port-b"]
        if (
            nb.dcim.sites.get(name=site_name)
            or list(nb.dcim.devices.filter(name=device_names))
            or nb.dcim.device_roles.get(name="NORFAB DESIGN PORT ROLE")
            or nb.dcim.device_types.get(model="NORFAB DESIGN PORT TYPE")
            or nb.dcim.manufacturers.get(name="NORFAB DESIGN PORT MANUFACTURER")
        ):
            pytest.skip("design port test objects already exist")
        design = {
            "manufacturers": [{"name": "NORFAB DESIGN PORT MANUFACTURER"}],
            "device_types": [
                {
                    "model": "NORFAB DESIGN PORT TYPE",
                    "manufacturer": "NORFAB DESIGN PORT MANUFACTURER",
                }
            ],
            "device_roles": [{"name": "NORFAB DESIGN PORT ROLE"}],
            "sites": [{"name": site_name}],
            "devices": [
                {
                    "name": device_names[0],
                    "site": site_name,
                    "role": "NORFAB DESIGN PORT ROLE",
                    "device_type": {
                        "manufacturer": "NORFAB DESIGN PORT MANUFACTURER",
                        "model": "NORFAB DESIGN PORT TYPE",
                    },
                    "console_ports": {"Console": {"type": "rj-45"}},
                    "power_ports": {
                        "PSU1": {
                            "type": "iec-60320-c14",
                            "connection": {
                                "device": device_names[1],
                                "power_outlet": "Outlet 1",
                                "label": "NORFAB DESIGN POWER CABLE",
                            },
                        }
                    },
                },
                {
                    "name": device_names[1],
                    "site": site_name,
                    "role": "NORFAB DESIGN PORT ROLE",
                    "device_type": {
                        "manufacturer": "NORFAB DESIGN PORT MANUFACTURER",
                        "model": "NORFAB DESIGN PORT TYPE",
                    },
                },
            ],
            "console_server_ports": [
                {"device": device_names[1], "name": "Line 1", "type": "rj-45"}
            ],
            "power_outlets": [
                {
                    "device": device_names[1],
                    "name": "Outlet 1",
                    "type": "iec-60320-c13",
                }
            ],
            "connections": [
                {
                    "label": "NORFAB DESIGN CONSOLE CABLE",
                    "a_terminations": [
                        {"device": device_names[0], "console_port": "Console"}
                    ],
                    "b_terminations": [
                        {"device": device_names[1], "console_server_port": "Line 1"}
                    ],
                }
            ],
        }
        try:
            for run in (1, 2):
                reply = nfclient.run_job(
                    "netbox", "design_deploy", workers="any", kwargs={"design": design}
                )
                for result in reply.values():
                    assert not result["failed"], result
                    if run == 2:
                        assert not result["result"]["connections"]["created"]
                console = nb.dcim.console_ports.get(
                    device=device_names[0], name="Console"
                )
                server = nb.dcim.console_server_ports.get(
                    device=device_names[1], name="Line 1"
                )
                power = nb.dcim.power_ports.get(device=device_names[0], name="PSU1")
                outlet = nb.dcim.power_outlets.get(
                    device=device_names[1], name="Outlet 1"
                )
                assert console.cable and console.cable.id == server.cable.id
                assert power.cable and power.cable.id == outlet.cable.id
        finally:
            for device_name in device_names:
                for endpoint in (
                    nb.dcim.console_ports,
                    nb.dcim.console_server_ports,
                    nb.dcim.power_ports,
                    nb.dcim.power_outlets,
                ):
                    for port in endpoint.filter(device=device_name):
                        if port.cable:
                            cable = nb.dcim.cables.get(port.cable.id)
                            if cable:
                                cable.delete()
                        port.delete()
                device = nb.dcim.devices.get(name=device_name)
                if device:
                    device.delete()
            device_type = nb.dcim.device_types.get(model="NORFAB DESIGN PORT TYPE")
            if device_type:
                device_type.delete()
            for endpoint, name in (
                (nb.dcim.sites, site_name),
                (nb.dcim.device_roles, "NORFAB DESIGN PORT ROLE"),
                (nb.dcim.manufacturers, "NORFAB DESIGN PORT MANUFACTURER"),
            ):
                record = endpoint.get(name=name)
                if record:
                    record.delete()

    @pytest.mark.parametrize("deployments", [1, 3], ids=["clean", "repeat"])
    def test_acme_design(self, nfclient: Any, deployments: int) -> None:
        """Deploy the complete ACME example from scratch and clean all owned data."""
        nb = pynetbox.api(url=NB_URL, token=NB_API_TOKEN)
        context = {"site": "NORFAB ACME TEST", "parent_prefix": "198.19.224.0/20"}
        # Independent expectations, with dependent interfaces first for cleanup.
        expected_interfaces = {
            "acme-branch-rtr-1": [
                "Ethernet2.100",
                "Loopback100",
                "Ethernet1",
                "Ethernet2",
                "Ethernet3",
                "Loopback0",
                "Ethernet4",
            ],
            "acme-branch-rtr-2": [
                "Loopback100",
                "Ethernet1",
                "Ethernet2",
                "Ethernet3",
                "Loopback0",
            ],
            "acme-branch-agg-1": [
                "Ethernet6",
                "Ethernet7",
                "Loopback100",
                "Loopback0",
                "Ethernet1",
                "Ethernet2",
                "Ethernet3",
                "Ethernet4",
                "Ethernet5",
                "Port-Channel1",
                "Vlan100",
            ],
            "acme-branch-agg-2": [
                "Ethernet6",
                "Ethernet7",
                "Loopback100",
                "Loopback0",
                "Ethernet1",
                "Ethernet2",
                "Ethernet3",
                "Ethernet4",
                "Ethernet5",
                "Port-Channel1",
                "Vlan100",
            ],
            "acme-branch-access-1": [
                "Loopback100",
                "Ethernet1",
                "Ethernet2",
                "Ethernet3",
            ],
            "acme-branch-access-2": [
                "Loopback100",
                "Ethernet1",
                "Ethernet2",
                "Ethernet3",
            ],
            "acme-branch-access-3": [
                "Loopback100",
                "Ethernet1",
                "Ethernet2",
                "Ethernet3",
            ],
            "acme-branch-terminal-server": [],
            "acme-branch-pdu": [],
        }
        device_names = list(expected_interfaces)
        expected_vlans = {
            100: "ACME USERS",
            101: "ACME GUEST",
            110: "ACME VOICE",
            120: "ACME MANAGEMENT",
        }
        expected_prefixes = [
            "198.19.224.0/20",
            "198.19.224.0/24",
            "198.19.225.0/24",
            "198.19.230.0/24",
            "192.0.2.0/24",
            "198.51.100.0/30",
            "198.51.100.4/31",
        ]
        expected_addresses = [
            "198.19.230.1/24",
            "198.51.100.1/30",
            "198.51.100.2/30",
            "198.51.100.4/31",
            "198.51.100.5/31",
            "192.0.2.20/32",
            "192.0.2.101/32",
            "192.0.2.102/32",
            "192.0.2.103/32",
            "192.0.2.104/32",
            "192.0.2.105/32",
            "192.0.2.106/32",
            "192.0.2.107/32",
            "192.0.2.10/32",
            "192.0.2.11/32",
            "192.0.2.21/24",
            "192.0.2.22/24",
            "192.0.2.1/24",
        ]
        # Allocated addresses are identified by their explicit purpose, not guessed values.
        allocated_addresses = [
            "ACME allocated management VIP",
            "acme-branch-rtr-1 Ethernet1",
            "acme-branch-rtr-2 Ethernet1",
            "acme-branch-rtr-1 Loopback0",
            "acme-branch-rtr-2 Loopback0",
        ]
        console_power_connections = [
            ("acme-branch-rtr-1", "Line 1", "Outlet 1"),
            ("acme-branch-rtr-2", "Line 2", "Outlet 2"),
            ("acme-branch-agg-1", "Line 3", "Outlet 3"),
            ("acme-branch-agg-2", "Line 4", "Outlet 4"),
            ("acme-branch-access-1", "Line 5", "Outlet 5"),
            ("acme-branch-access-2", "Line 6", "Outlet 6"),
            ("acme-branch-access-3", "Line 7", "Outlet 7"),
        ]
        expected_peerings = [
            "acme-branch-rtr-1-upstream",
            "acme-branch-rtr-1_default_192.0.2.102",
            "acme-branch-rtr-1-to-acme-branch-agg-1",
            "acme-branch-rtr-1-to-acme-branch-agg-2",
            "acme-branch-rtr-2-to-acme-branch-rtr-1",
            "acme-branch-rtr-2-to-acme-branch-agg-1",
            "acme-branch-rtr-2-to-acme-branch-agg-2",
            "acme-branch-agg-1-to-acme-branch-rtr-1",
            "acme-branch-agg-1-to-acme-branch-rtr-2",
            "acme-branch-agg-1_default_198.51.100.5",
            "acme-branch-agg-1-to-acme-branch-access-1",
            "acme-branch-agg-1-to-acme-branch-access-2",
            "acme-branch-agg-1-to-acme-branch-access-3",
            "acme-branch-agg-2-to-acme-branch-rtr-1",
            "acme-branch-agg-2-to-acme-branch-rtr-2",
            "acme-branch-agg-2-to-acme-branch-agg-1",
            "acme-branch-agg-2-to-acme-branch-access-1",
            "acme-branch-agg-2-to-acme-branch-access-2",
            "acme-branch-agg-2-to-acme-branch-access-3",
            "acme-branch-access-1-to-acme-branch-agg-1",
            "acme-branch-access-1-to-acme-branch-agg-2",
            "acme-branch-access-2-to-acme-branch-agg-1",
            "acme-branch-access-2-to-acme-branch-agg-2",
            "acme-branch-access-3-to-acme-branch-agg-1",
            "acme-branch-access-3-to-acme-branch-agg-2",
        ]
        objects = [
            (
                nb.plugins.bgp.session,
                {"name": expected_peerings},
            ),
            (nb.vpn.l2vpns, {"name": "ACME BRANCH EVPN"}),
            (nb.ipam.ip_addresses, {"parent": "198.19.224.0/20"}),
            (nb.ipam.ip_addresses, {"parent": "192.0.2.0/24"}),
            (nb.ipam.ip_addresses, {"parent": "198.51.100.0/30"}),
            (nb.ipam.ip_addresses, {"parent": "198.51.100.4/31"}),
            (nb.dcim.interfaces, {"device": device_names}),
            (nb.dcim.devices, {"name": device_names}),
            (nb.ipam.prefixes, {"within_include": "198.19.224.0/20"}),
            (
                nb.ipam.prefixes,
                {
                    "prefix": [
                        "192.0.2.0/24",
                        "198.51.100.0/30",
                        "198.51.100.4/31",
                    ]
                },
            ),
            (nb.ipam.vlan_groups, {"name": "NORFAB ACME TEST VLANS"}),
            (nb.ipam.vrfs, {"name": "ACME BRANCH", "rd": "4200650001:100"}),
            (
                nb.ipam.route_targets,
                {"name": ["4200650001:100", "4200650001:200", "4200650001:300"]},
            ),
            (nb.plugins.bgp.routing_policy, {"name": ["ACME IMPORT", "ACME EXPORT"]}),
            (
                nb.plugins.bgp.peer_group,
                {"name": ["ACME UPSTREAM PEERS", "ACME LOOPBACK PEERS"]},
            ),
            (nb.plugins.bgp.community, {"value": "4200650001:100"}),
            (nb.ipam.asns, {"asn": [4200650000, 4200650001, 4200650002, 4200650003]}),
            (
                nb.ipam.asns,
                {
                    "description": [
                        "ACME allocated branch ASN",
                        "ACME allocated aggregation ASN",
                    ]
                },
            ),
            (nb.ipam.asn_ranges, {"name": "ACME BRANCH ALLOCATED ASNS"}),
            (nb.ipam.rirs, {"name": "ACME PRIVATE"}),
            (
                nb.ipam.roles,
                {
                    "name": [
                        "ACME-BRANCH-LAN",
                        "ACME-BRANCH-LOOPBACK",
                        "ACME UPSTREAM ASN",
                    ]
                },
            ),
            (
                nb.dcim.device_types,
                {
                    "model": [
                        "ACME BRANCH ROUTER",
                        "ACME AGG SWITCH",
                        "ACME ACCESS SWITCH",
                        "ACME TERMINAL SERVER",
                        "ACME PDU",
                    ]
                },
            ),
            (
                nb.dcim.device_roles,
                {
                    "name": [
                        "ACME ROUTER",
                        "ACME AGGREGATION SWITCH",
                        "ACME ACCESS SWITCH",
                        "ACME TERMINAL SERVER",
                        "ACME PDU",
                    ]
                },
            ),
            (nb.dcim.platforms, {"name": "ACME OS"}),
            (nb.dcim.manufacturers, {"name": "ACME NETWORKS"}),
            (nb.extras.config_contexts, {"name": "ACME BRANCH BASELINE"}),
            (nb.dcim.sites, {"name": "NORFAB ACME TEST"}),
            (nb.dcim.regions, {"name": "ACME REGION"}),
            (nb.tenancy.tenants, {"name": "ACME"}),
        ]
        for endpoint, filters in objects:
            if endpoint.name == "interfaces":
                continue  # Device names are checked below.
            if list(endpoint.filter(**filters)):
                pytest.skip(
                    f"ACME objects already exist; refusing to change them: {filters}"
                )
        if list(nb.ipam.fhrp_groups.filter(group_id=[10, 20])):
            pytest.skip("VRRP group IDs 10 or 20 already exist")
        try:
            previous_ids = None
            previous_allocated_asns = None
            for run in range(deployments):
                reply = nfclient.run_job(
                    "netbox",
                    "design_deploy",
                    workers="any",
                    kwargs={
                        "design": "nf://netbox/designs/acme_branch_network_design_v1.yaml",
                        "context": context,
                    },
                )
                assert reply
                for result in reply.values():
                    assert not result["failed"], result
                    assert not result["errors"], result
                    assert (
                        100
                        in result["result"]["vlans"][
                            "created" if run == 0 else "updated"
                        ]
                    )
                    assert all(
                        "unchanged" not in changes
                        for changes in result["result"].values()
                    )
                    assert result["result"]["route_targets"]["custom"] == [
                        {
                            "function": "allocate_bgp_route_target",
                            "result": {"name": "4200650001:300"},
                        }
                    ]
                    if run:
                        for collection, changes in result["result"].items():
                            assert not changes["created"], (collection, changes)
                group = nb.ipam.vlan_groups.get(name="NORFAB ACME TEST VLANS")
                device = nb.dcim.devices.get(name="acme-branch-rtr-1")
                reference_ips = [
                    nb.ipam.ip_addresses.get(address=address)
                    for address in ("198.19.243.10/32", "198.19.243.11/32")
                ]
                assert (
                    device.custom_fields["norfab_design_device_ip"]["id"]
                    == reference_ips[0].id
                )
                assert {
                    item["id"]
                    for item in device.custom_fields["norfab_design_device_ips"]
                } == {item.id for item in reference_ips}
                allocated_target = nb.ipam.route_targets.get(name="4200650001:300")
                assert allocated_target.description == "ACME allocated route target"
                assert allocated_target.tenant.name == "ACME"
                assert group.scope_type == "dcim.site"
                assert group.scope_id == nb.dcim.sites.get(name=context["site"]).id
                prefix = nb.ipam.prefixes.get(prefix="192.0.2.0/24")
                site_id = nb.dcim.sites.get(name=context["site"]).id
                for item in (
                    nb.ipam.asns.get(asn=4200650001),
                    nb.ipam.vlans.get(group_id=group.id, vid=100),
                    prefix,
                ):
                    assert item.custom_fields["norfab_acme_site"]["id"] == site_id
                    assert [
                        site["id"] for site in item.custom_fields["norfab_acme_sites"]
                    ] == [site_id]
                allocated_asns = {
                    description: nb.ipam.asns.get(description=description)
                    for description in (
                        "ACME allocated branch ASN",
                        "ACME allocated aggregation ASN",
                    )
                }
                assert all(allocated_asns.values())
                assert len({asn.asn for asn in allocated_asns.values()}) == 2
                for asn in allocated_asns.values():
                    assert 4200650100 <= asn.asn <= 4200650109
                    assert asn.rir.name == "ACME PRIVATE"
                    assert [site.id for site in asn.sites] == [site_id]
                allocated_numbers = {
                    description: asn.asn for description, asn in allocated_asns.items()
                }
                if previous_allocated_asns is not None:
                    assert allocated_numbers == previous_allocated_asns
                previous_allocated_asns = allocated_numbers
                allocated_peering = nb.plugins.bgp.session.get(
                    name="acme-branch-rtr-1-to-acme-branch-agg-1"
                )
                assert (
                    allocated_peering.local_as.asn
                    == allocated_numbers["ACME allocated branch ASN"]
                )
                assert (
                    allocated_peering.remote_as.asn
                    == allocated_numbers["ACME allocated aggregation ASN"]
                )
                termination_vlan = nb.ipam.vlans.get(group_id=group.id, vid=100)
                assert termination_vlan.name == "ACME USERS"
                assert termination_vlan.description == "ACME branch user access"
                assert termination_vlan.tenant.name == "ACME"
                assert termination_vlan.role.name == "ACME-BRANCH-LAN"
                assert (
                    termination_vlan.custom_fields["norfab_acme_site"]
                    == context["site"]
                )
                vpn = nb.vpn.l2vpns.get(name="ACME BRANCH EVPN")
                assert vpn.type.value == "vxlan"
                assert vpn.identifier == 10100
                assert [target.name for target in vpn.import_targets] == [
                    "4200650001:100"
                ]
                assert [target.name for target in vpn.export_targets] == [
                    "4200650001:100"
                ]
                assert {
                    (item.assigned_object_type, item.assigned_object_id)
                    for item in nb.vpn.l2vpn_terminations.filter(l2vpn_id=vpn.id)
                } == {
                    ("ipam.vlan", nb.ipam.vlans.get(group_id=group.id, vid=100).id),
                    (
                        "dcim.interface",
                        nb.dcim.interfaces.get(
                            device="acme-branch-rtr-1", name="Ethernet2.100"
                        ).id,
                    ),
                }
                assert prefix.scope_type == "dcim.site"
                assert prefix.scope_id == nb.dcim.sites.get(name=context["site"]).id
                assert prefix.vlan.vid == 100
                allocated_prefix = nb.ipam.prefixes.get(
                    description=f"ACME {context['site']} user prefix"
                )
                assert (
                    allocated_prefix.vlan.id
                    == nb.ipam.vlans.get(group_id=group.id, vid=100).id
                )
                assert (
                    nb.ipam.prefixes.get(prefix="198.19.230.0/24").vrf.name
                    == "ACME BRANCH"
                )
                assert (
                    nb.ipam.ip_addresses.get(address="198.19.230.1/24").vrf.name
                    == "ACME BRANCH"
                )
                assert (
                    nb.dcim.interfaces.get(
                        device="acme-branch-rtr-1", name="Ethernet2.100"
                    ).parent.name
                    == "Ethernet2"
                )
                assert (
                    nb.dcim.interfaces.get(
                        device="acme-branch-agg-1", name="Ethernet6"
                    ).lag.name
                    == "Port-Channel1"
                )
                asn = nb.ipam.asns.get(asn=4200650002)
                assert asn.role.name == "ACME-BRANCH-LAN"
                assert [site.name for site in asn.sites] == [context["site"]]
                assert (
                    len(
                        {
                            interface.cable.id
                            for device_name in device_names
                            for interface in nb.dcim.interfaces.filter(
                                device=device_name
                            )
                            if interface.cable
                        }
                    )
                    == 12
                )
                for device_name, line_name, outlet_name in console_power_connections:
                    console = nb.dcim.console_ports.get(
                        device=device_name, name="Console"
                    )
                    server = nb.dcim.console_server_ports.get(
                        device="acme-branch-terminal-server", name=line_name
                    )
                    power = nb.dcim.power_ports.get(device=device_name, name="PSU1")
                    outlet = nb.dcim.power_outlets.get(
                        device="acme-branch-pdu", name=outlet_name
                    )
                    assert console.cable and console.cable.id == server.cable.id
                    assert power.cable and power.cable.id == outlet.cable.id
                current_ids = [
                    sorted(record.id for record in endpoint.filter(**filters))
                    for endpoint, filters in objects
                ]
                assert all(current_ids), current_ids
                assert len(current_ids[0]) == 25
                loopback_peering = nb.plugins.bgp.session.get(
                    name="acme-branch-rtr-1_default_192.0.2.102"
                )
                assert loopback_peering.device.name == "acme-branch-rtr-1"
                assert loopback_peering.local_address.address == "192.0.2.101/32"
                assert loopback_peering.remote_address.address == "192.0.2.102/32"
                assert (
                    loopback_peering.local_as.asn
                    == allocated_numbers["ACME allocated branch ASN"]
                )
                assert (
                    loopback_peering.remote_as.asn
                    == allocated_numbers["ACME allocated branch ASN"]
                )
                upstream = nb.plugins.bgp.session.get(name="acme-branch-rtr-1-upstream")
                assert upstream.local_address.address == "198.51.100.1/30"
                assert upstream.remote_address.address == "198.51.100.2/30"
                assert upstream.remote_as.asn == 4200650000
                assert upstream.peer_group.name == "ACME UPSTREAM PEERS"
                assert loopback_peering.peer_group.name == "ACME LOOPBACK PEERS"
                assert nb.ipam.asns.get(asn=4200650000).role.name == "ACME UPSTREAM ASN"
                interconnect = nb.plugins.bgp.session.get(
                    name="acme-branch-agg-1_default_198.51.100.5"
                )
                assert interconnect.local_address.address == "198.51.100.4/31"
                assert interconnect.remote_address.address == "198.51.100.5/31"
                assert (
                    interconnect.local_as.asn
                    == allocated_numbers["ACME allocated aggregation ASN"]
                )
                assert (
                    interconnect.remote_as.asn
                    == allocated_numbers["ACME allocated aggregation ASN"]
                )
                for device_name, names in expected_interfaces.items():
                    assert sorted(
                        item.name
                        for item in nb.dcim.interfaces.filter(device=device_name)
                    ) == sorted(names), device_name
                assert len(current_ids[7]) == 9
                assert len(list(nb.ipam.vlans.filter(group_id=group.id))) == 4
                assert {
                    vlan.vid: vlan.name
                    for vlan in nb.ipam.vlans.filter(group_id=group.id)
                } == expected_vlans
                for value in expected_prefixes:
                    assert nb.ipam.prefixes.get(prefix=value), value
                for value in expected_addresses:
                    assert nb.ipam.ip_addresses.get(address=value), value
                shared_vips = list(nb.ipam.ip_addresses.filter(address="192.0.2.23/24"))
                assert len(shared_vips) == 2
                assert {ip.role.value for ip in shared_vips} == {"vip"}
                assert {
                    (ip.assigned_object.device.name, ip.assigned_object.name)
                    for ip in shared_vips
                } == {
                    ("acme-branch-agg-1", "Vlan100"),
                    ("acme-branch-agg-2", "Vlan100"),
                }
                for description in allocated_addresses:
                    assert nb.ipam.ip_addresses.get(
                        description=description
                    ), description
                assert len(list(nb.ipam.fhrp_groups.filter(group_id=[10, 20]))) == 2
                fhrp_groups = list(nb.ipam.fhrp_groups.filter(group_id=[10, 20]))
                assert (
                    sum(
                        len(
                            list(
                                nb.ipam.fhrp_group_assignments.filter(group_id=item.id)
                            )
                        )
                        for item in fhrp_groups
                    )
                    == 4
                )
                vip = nb.ipam.ip_addresses.get(address="192.0.2.1/24")
                assert vip.assigned_object.group_id == 10
                allocated_vip = nb.ipam.ip_addresses.get(
                    description="ACME allocated management VIP"
                )
                management_group = nb.ipam.fhrp_groups.get(
                    name="ACME MANAGEMENT GATEWAY"
                )
                assert allocated_vip.assigned_object_type == "ipam.fhrpgroup"
                assert allocated_vip.assigned_object_id == management_group.id
                assert allocated_vip.role.value == "vrrp"
                assert allocated_vip.address.endswith("/24")
                assert (
                    len(
                        list(
                            nb.ipam.ip_addresses.filter(
                                assigned_object_type="ipam.fhrpgroup",
                                assigned_object_id=management_group.id,
                            )
                        )
                    )
                    == 1
                )
                assert (
                    nb.dcim.devices.get(name="acme-branch-agg-1").primary_ip4.address
                    == "192.0.2.10/32"
                )
                context_record = nb.extras.config_contexts.get(
                    name="ACME BRANCH BASELINE"
                )
                assert context_record.data == {"acme": {"managed": True}}
                assert [site.name for site in context_record.sites] == [context["site"]]
                assert nb.dcim.devices.get(
                    name="acme-branch-rtr-1"
                ).local_context_data == {
                    "acme": {"profile": "core-router", "managed": True}
                }
                aggregation = nb.dcim.devices.get(name="acme-branch-agg-1")
                assert aggregation.local_context_data == {
                    "acme": {
                        "profile": "aggregation",
                        "site": context["site"],
                        "role": "ACME AGGREGATION SWITCH",
                        "interface_count": 11,
                        "primary_ip": "192.0.2.10/32",
                    }
                }
                if previous_ids is not None:
                    assert current_ids == previous_ids
                previous_ids = current_ids
        finally:
            cleanup_errors = []
            vpn = nb.vpn.l2vpns.get(name="ACME BRANCH EVPN")
            if vpn:
                for termination in nb.vpn.l2vpn_terminations.filter(l2vpn_id=vpn.id):
                    termination.delete()
            cable_ids = set()
            for device_name in device_names:
                device = nb.dcim.devices.get(name=device_name)
                if device:
                    for endpoint in (
                        nb.dcim.interfaces,
                        nb.dcim.power_ports,
                        nb.dcim.console_ports,
                        nb.dcim.power_outlets,
                        nb.dcim.console_server_ports,
                    ):
                        for port in endpoint.filter(device_id=device.id):
                            if port.cable:
                                cable_ids.add(port.cable.id)
            for cable_id in cable_ids:
                try:
                    cable = nb.dcim.cables.get(cable_id)
                    if cable:
                        cable.delete()
                except Exception as exc:
                    cleanup_errors.append(f"cable {cable_id}: {exc}")
            for device_name in ("acme-branch-agg-1", "acme-branch-agg-2"):
                device = nb.dcim.devices.get(name=device_name)
                if device and device.primary_ip4:
                    device.primary_ip4 = None
                    device.save()
            for group in nb.ipam.fhrp_groups.filter(group_id=[10, 20]):
                for assignment in nb.ipam.fhrp_group_assignments.filter(
                    group_id=group.id
                ):
                    assignment.delete()
            for endpoint, filters in objects:
                try:
                    if endpoint.name == "interfaces":
                        for group in nb.ipam.fhrp_groups.filter(group_id=[10, 20]):
                            group.delete()
                        for device_name in device_names:
                            device = nb.dcim.devices.get(name=device_name)
                            if device:
                                for name in expected_interfaces[device_name]:
                                    interface = nb.dcim.interfaces.get(
                                        device_id=device.id, name=name
                                    )
                                    if interface:
                                        interface.delete()
                                for port_endpoint in (
                                    nb.dcim.power_ports,
                                    nb.dcim.console_ports,
                                    nb.dcim.power_outlets,
                                    nb.dcim.console_server_ports,
                                ):
                                    for port in port_endpoint.filter(
                                        device_id=device.id
                                    ):
                                        port.delete()
                        continue
                    if endpoint.name == "vlan-groups":
                        group = nb.ipam.vlan_groups.get(name="NORFAB ACME TEST VLANS")
                        if group:
                            for vlan in nb.ipam.vlans.filter(group_id=group.id):
                                vlan.delete()
                    for record in endpoint.filter(**filters):
                        record.delete()
                except Exception as exc:
                    cleanup_errors.append(f"{filters}: {exc}")
            assert not cleanup_errors, cleanup_errors
            for endpoint, filters in objects:
                if endpoint.name == "interfaces":
                    continue
                assert not list(endpoint.filter(**filters)), filters

    def test_bgp_peering_policies(self, nfclient: Any) -> None:
        """Derive a session name and leave its existing fields unchanged."""
        nb = pynetbox.api(url=NB_URL, token=NB_API_TOKEN)
        if not nb.dcim.devices.get(name="ceos1"):
            pytest.skip("ceos1 fixture is required")
        session_name = "ceos1_default_198.19.246.2"
        objects = [
            (nb.plugins.bgp.session, {"name": session_name}),
            (nb.plugins.bgp.peer_group, {"name": "NORFAB DESIGN BGP PEERS"}),
            (
                nb.plugins.bgp.routing_policy,
                {
                    "name": [
                        "NORFAB DESIGN BGP IMPORT",
                        "NORFAB DESIGN BGP EXTRA",
                        "NORFAB DESIGN BGP EXPORT",
                    ]
                },
            ),
            (nb.ipam.ip_addresses, {"address": ["198.19.246.1/30", "198.19.246.2/30"]}),
            (nb.ipam.asns, {"asn": 4200999246}),
            (nb.ipam.rirs, {"name": "NORFAB DESIGN BGP RIR"}),
            (
                nb.extras.tags,
                {"name": ["NORFAB DESIGN BGP TAG A", "NORFAB DESIGN BGP TAG B"]},
            ),
            (nb.extras.custom_fields, {"name": "norfab_design_bgp_device"}),
        ]
        for endpoint, filters in objects:
            if list(endpoint.filter(**filters)):
                pytest.skip(f"BGP design fixture already exists: {filters}")
        design = {
            "rirs": [{"name": "NORFAB DESIGN BGP RIR", "is_private": True}],
            "asns": [{"asn": 4200999246, "rir": "NORFAB DESIGN BGP RIR"}],
            "ip_addresses": [
                {"address": "198.19.246.1/30"},
                {"address": "198.19.246.2/30"},
            ],
            "bgp_peerings": [
                {
                    "device": "ceos1",
                    "local_address": "198.19.246.1",
                    "remote_address": "198.19.246.2",
                    "local_as": 4200999246,
                    "remote_as": 4200999246,
                    "peer_group": {
                        "name": "NORFAB DESIGN BGP PEERS",
                        "description": "Design peer group",
                    },
                    "tags": ["NORFAB DESIGN BGP TAG A"],
                    "custom_fields": {"norfab_design_bgp_device": "ceos1"},
                    "import_policies": [
                        {
                            "name": "NORFAB DESIGN BGP IMPORT",
                            "description": "inline policy",
                        }
                    ],
                    "export_policies": ["NORFAB DESIGN BGP EXPORT"],
                }
            ],
        }
        try:
            nb.extras.custom_fields.create(
                name="norfab_design_bgp_device",
                type="object",
                object_types=["netbox_bgp.bgpsession"],
                related_object_type="dcim.device",
            )
            for name in ("NORFAB DESIGN BGP TAG A", "NORFAB DESIGN BGP TAG B"):
                nb.extras.tags.create(name=name, slug=name.lower().replace(" ", "-"))
            for run, description in enumerate(("initial", "updated", "updated")):
                design["bgp_peerings"][0]["description"] = description
                if run == 1:
                    design["bgp_peerings"][0]["peer_group"] = "NORFAB DESIGN BGP PEERS"
                if description == "updated":
                    design["bgp_peerings"][0]["import_policies"] = [
                        {"name": "NORFAB DESIGN BGP EXTRA"}
                    ]
                    design["bgp_peerings"][0]["tags"] = ["NORFAB DESIGN BGP TAG B"]
                reply = nfclient.run_job(
                    "netbox", "design_deploy", workers="any", kwargs={"design": design}
                )
                assert reply
                for result in reply.values():
                    assert not result["failed"], result
                    assert not result["errors"], result
                    assert result["result"]["bgp_peerings"]["created"] == (
                        [session_name] if run == 0 else []
                    )
                    assert result["result"]["bgp_peerings"]["updated"] == []
                    assert result["result"]["peer_groups"] == {
                        "created": ["NORFAB DESIGN BGP PEERS"] if run == 0 else [],
                        "updated": [] if run == 0 else ["NORFAB DESIGN BGP PEERS"],
                    }
                session = nb.plugins.bgp.session.get(name=session_name)
                assert session.description == "initial"
                assert session.peer_group.name == "NORFAB DESIGN BGP PEERS"
                assert session.custom_fields["norfab_design_bgp_device"]["id"] == (
                    nb.dcim.devices.get(name="ceos1").id
                )
                assert {policy.name for policy in session.import_policies} == {
                    "NORFAB DESIGN BGP IMPORT"
                }
                assert {policy.name for policy in session.export_policies} == {
                    "NORFAB DESIGN BGP EXPORT"
                }
                assert {tag.name for tag in session.tags} == {"NORFAB DESIGN BGP TAG A"}
        finally:
            for endpoint, filters in objects:
                for record in endpoint.filter(**filters):
                    record.delete()

    def test_custom_function(self, nfclient: Any) -> None:
        """Load a custom creator from nf:// and execute after explicit records."""
        nb = pynetbox.api(url=NB_URL, token=NB_API_TOKEN)
        names = ["NORFAB CUSTOM BASE", "NORFAB CUSTOM TENANT"]
        if list(nb.tenancy.tenants.filter(name=names)):
            pytest.skip("custom design fixtures already exist")
        design = """custom_functions:
  custom_create_tenant: nf://netbox/designs/custom_create_tenant.py
tenants:
  - custom_function: custom_create_tenant
    name: NORFAB CUSTOM TENANT
    slug: norfab-custom-tenant
    prerequisite: NORFAB CUSTOM BASE
  - name: NORFAB CUSTOM BASE
"""
        try:
            nb.tenancy.tenants.create({"name": names[0], "slug": "norfab-custom-base"})
            for dry_run in (True, False, False):
                reply = nfclient.run_job(
                    "netbox",
                    "design_deploy",
                    workers="any",
                    kwargs={
                        "design": design,
                        "context": {"tenant_name": names[1]},
                        "dry_run": dry_run,
                    },
                )
                assert reply
                for result in reply.values():
                    assert not result["failed"], result
                    assert not result["errors"], result
                    assert result["result"]["tenants"]["custom"][0]["result"] == {
                        "name": names[1],
                        "dry_run": dry_run,
                        "context_tenant": names[1],
                    }
                assert bool(nb.tenancy.tenants.get(name=names[1])) is not dry_run
        finally:
            for tenant in nb.tenancy.tenants.filter(name=names):
                tenant.delete()

    def test_task_wrappers(self, nfclient: Any) -> None:
        """Deploy task-name wrappers and repeat without allocating duplicates."""
        nb = pynetbox.api(url=NB_URL, token=NB_API_TOKEN)
        objects = [
            (nb.ipam.ip_addresses, {"parent": "198.19.247.0/24"}),
            (nb.ipam.prefixes, {"within_include": "198.19.247.0/24"}),
            (nb.ipam.asns, {"asn": 4200999251}),
            (nb.ipam.asns, {"asn": 4200999252}),
            (nb.ipam.asn_ranges, {"name": "NORFAB DESIGN WRAPPER RANGE"}),
            (nb.ipam.vlans, {"name": "NORFAB DESIGN WRAPPER VLAN"}),
            (nb.ipam.vlans, {"name": "NORFAB DESIGN EXPLICIT VLAN"}),
            (nb.ipam.vlan_groups, {"name": "NORFAB DESIGN WRAPPER GROUP"}),
            (nb.ipam.rirs, {"name": "NORFAB DESIGN WRAPPER RIR"}),
        ]
        for endpoint, filters in objects:
            if list(endpoint.filter(**filters)):
                pytest.skip(f"design fixture already exists: {filters}")
        design = {
            "rirs": [
                {
                    "name": "NORFAB DESIGN WRAPPER RIR",
                    "slug": "norfab-design-wrapper-rir",
                    "is_private": True,
                }
            ],
            "vlan_groups": [
                {
                    "name": "NORFAB DESIGN WRAPPER GROUP",
                    "slug": "norfab-design-wrapper-group",
                    "vid_ranges": [[251, 259]],
                }
            ],
            "asn_ranges": [
                {
                    "name": "NORFAB DESIGN WRAPPER RANGE",
                    "slug": "norfab-design-wrapper-range",
                    "start": 4200999251,
                    "end": 4200999252,
                    "rir": "NORFAB DESIGN WRAPPER RIR",
                }
            ],
            "asns": [
                {
                    "create_asn": {
                        "asn_range": "NORFAB DESIGN WRAPPER RANGE",
                        "description": "NORFAB DESIGN ALLOCATED ASN",
                    }
                },
                {"asn": 4200999252, "rir": "NORFAB DESIGN WRAPPER RIR"},
            ],
            "vlans": [
                {
                    "vid": 259,
                    "name": "NORFAB DESIGN EXPLICIT VLAN",
                    "group": "NORFAB DESIGN WRAPPER GROUP",
                },
                {
                    "create_vlan": {
                        "vlan_group": "NORFAB DESIGN WRAPPER GROUP",
                        "name": "NORFAB DESIGN WRAPPER VLAN",
                    }
                },
            ],
            "prefixes": [
                {"prefix": "198.19.247.0/24"},
                {
                    "create_prefix": {
                        "parent": "198.19.247.0/24",
                        "prefixlen": 28,
                        "description": "NORFAB DESIGN WRAPPER PREFIX",
                    }
                },
            ],
            "ip_addresses": [
                {
                    "create_ip": {
                        "prefix": "198.19.247.0/28",
                        "description": "NORFAB DESIGN WRAPPER IP",
                        "create_peer_ip": False,
                    }
                }
            ],
        }
        try:
            for dry_run in (False, False, True):
                reply = nfclient.run_job(
                    "netbox",
                    "design_deploy",
                    workers="any",
                    kwargs={"design": design, "dry_run": dry_run},
                )
                assert reply
                for result in reply.values():
                    assert not result["failed"], result
                    assert not result["errors"], result
                assert nb.ipam.asns.get(asn=4200999251)
                assert nb.ipam.asns.get(asn=4200999252)
                assert nb.ipam.vlans.get(name="NORFAB DESIGN WRAPPER VLAN").vid == 251
                assert nb.ipam.prefixes.get(prefix="198.19.247.0/28")
                assert (
                    len(list(nb.ipam.ip_addresses.filter(parent="198.19.247.0/28")))
                    == 1
                )
        finally:
            for endpoint, filters in objects:
                for record in endpoint.filter(**filters):
                    record.delete()

    def test_simple_collections(self, nfclient: Any) -> None:
        """Create and update dependent DCIM and IPAM objects in order."""
        nb = pynetbox.api(url=NB_URL, token=NB_API_TOKEN)
        design = {
            "regions": [
                {
                    "name": "NORFAB DESIGN REGION",
                    "description": "old",
                }
            ],
            "manufacturers": [{"name": "NORFAB DESIGN MFR"}],
            "platforms": [
                {
                    "name": "NORFAB DESIGN OS",
                    "manufacturer": "NORFAB DESIGN MFR",
                }
            ],
            "device_types": [
                {
                    "model": "NORFAB DESIGN DEVICE",
                    "manufacturer": "NORFAB DESIGN MFR",
                    "default_platform": "NORFAB DESIGN OS",
                }
            ],
            "device_roles": [
                {
                    "name": "NORFAB DESIGN ROLE",
                    "color": "ff0000",
                }
            ],
            "sites": [
                {
                    "name": "NORFAB DESIGN SITE",
                    "region": "NORFAB DESIGN REGION",
                    "status": "active",
                }
            ],
            "roles": [{"name": "NORFAB DESIGN IPAM ROLE"}],
            "rirs": [
                {
                    "name": "NORFAB DESIGN RIR",
                    "is_private": True,
                }
            ],
        }
        design["rack_roles"] = [{"name": "NORFAB DESIGN RACK ROLE"}]
        design["racks"] = [
            {
                "name": "NORFAB DESIGN RACK",
                "site": "NORFAB DESIGN SITE",
                "role": "NORFAB DESIGN RACK ROLE",
                "status": "active",
            }
        ]
        design["asn_ranges"] = [
            {
                "name": "NORFAB DESIGN ASN RANGE",
                "rir": "NORFAB DESIGN RIR",
                "start": 64512,
                "end": 64520,
            }
        ]
        design["vlan_groups"] = [
            {
                "name": "NORFAB DESIGN VLAN GROUP",
                "vid_ranges": [[100, 199]],
            }
        ]
        design["vrfs"] = [
            {
                "name": "NORFAB DESIGN VRF",
                "rd": "64512:123",
                "import_route_targets": [
                    {"name": "64512:99123", "description": "design target"}
                ],
                "export_route_targets": [{"query": {"name": "64512:99123"}}],
            }
        ]
        design["bgp_communities"] = [
            {"value": "64512:987", "description": "design community"}
        ]
        design["routing_policies"] = [{"name": "NORFAB DESIGN EXPORT"}]
        objects = [
            (nb.plugins.bgp.community, {"value": "64512:987"}),
            (nb.plugins.bgp.routing_policy, {"name": "NORFAB DESIGN EXPORT"}),
            (nb.dcim.racks, {"name": "NORFAB DESIGN RACK"}),
            (nb.dcim.rack_roles, {"name": "NORFAB DESIGN RACK ROLE"}),
            (nb.ipam.asn_ranges, {"name": "NORFAB DESIGN ASN RANGE"}),
            (nb.ipam.vlan_groups, {"name": "NORFAB DESIGN VLAN GROUP"}),
            (nb.ipam.vrfs, {"name": "NORFAB DESIGN VRF"}),
            (nb.ipam.route_targets, {"name": "64512:99123"}),
            (nb.dcim.sites, {"name": "NORFAB DESIGN SITE"}),
            (nb.dcim.device_types, {"model": "NORFAB DESIGN DEVICE"}),
            (nb.dcim.device_roles, {"name": "NORFAB DESIGN ROLE"}),
            (nb.dcim.platforms, {"name": "NORFAB DESIGN OS"}),
            (nb.dcim.manufacturers, {"name": "NORFAB DESIGN MFR"}),
            (nb.dcim.regions, {"name": "NORFAB DESIGN REGION"}),
            (nb.ipam.roles, {"name": "NORFAB DESIGN IPAM ROLE"}),
            (nb.ipam.rirs, {"name": "NORFAB DESIGN RIR"}),
        ]
        if any(endpoint.get(**filters) for endpoint, filters in objects):
            pytest.skip("Design test objects already exist in NetBox")
        try:
            for action in ("created", "updated"):
                if action == "updated":
                    design["regions"][0]["description"] = "updated"
                response = nfclient.run_job(
                    "netbox", "design_deploy", workers="any", kwargs={"design": design}
                )
                for worker, result in response.items():
                    assert result["failed"] is False, f"{worker} failed: {result}"
                    for collection, records in design.items():
                        identity = (
                            "model"
                            if collection == "device_types"
                            else "value" if collection == "bgp_communities" else "name"
                        )
                        assert result["result"][collection][action] == [
                            records[0][identity]
                        ]
            vrf = nb.ipam.vrfs.get(name="NORFAB DESIGN VRF")
            assert [target.name for target in vrf.import_targets] == ["64512:99123"]
            assert [target.name for target in vrf.export_targets] == ["64512:99123"]
            assert (
                nb.ipam.route_targets.get(name="64512:99123").description
                == "design target"
            )
            assert (
                nb.dcim.regions.get(name="NORFAB DESIGN REGION").description
                == "updated"
            )
        finally:
            for endpoint, filters in objects:
                item = endpoint.get(**filters)
                if item:
                    item.delete()

    def test_single_document_metadata_and_tenants(self, nfclient: Any) -> None:
        """Metadata and rendered tenant records share one YAML document."""
        nb = pynetbox.api(url=NB_URL, token=NB_API_TOKEN)
        name = "norfab-design-single-document"
        if nb.tenancy.tenants.get(name=name):
            pytest.skip("Design test tenant already exists in NetBox")
        design = """design_input_schema:
  type: object
  additionalProperties: false
  properties:
    tenant_name:
      type: string
  required:
    - tenant_name
jinja_functions: {}
tenants:
  - name: "{{ context.tenant_name }}"
    slug: "{{ context.tenant_name }}"
"""
        try:
            response = nfclient.run_job(
                "netbox",
                "design_deploy",
                workers="any",
                kwargs={"design": design, "context": {"tenant_name": name}},
            )
            for worker, result in response.items():
                assert result["failed"] is False, f"{worker} failed: {result}"
                assert result["result"]["tenants"]["created"] == [name]
            assert nb.tenancy.tenants.get(name=name)
        finally:
            tenant = nb.tenancy.tenants.get(name=name)
            if tenant:
                tenant.delete()

    @pytest.mark.parametrize(
        "design",
        [
            {"unknown": []},
            {"tenants": {"name": "tenant-1"}},
            {"tenants": ["tenant-1"]},
            {"vrfs": [{"name": "invalid", "import_route_targets": ["64512:100"]}]},
            {"vrfs": [{"name": "invalid", "import_route_targets": [{"query": {}}]}]},
            {
                "l2vpns": [
                    {
                        "name": "invalid",
                        "type": "vxlan",
                        "export_route_targets": [
                            {"query": {"name": "64512:999999999"}}
                        ],
                    }
                ]
            },
            {"route_targets": ["64512:100"]},
            {"bgp_communities": ["64512:100"]},
            {"routing_policies": ["ACME EXPORT"]},
            {"bgp_peerings": [{"name": "invalid", "import_policies": [42]}]},
            {"bgp_peerings": [{"name": "invalid", "export_policies": [42]}]},
            {"bgp_peerings": [{"name": "invalid", "peer_group": {}}]},
            {"l2vpns": [{"name": "invalid", "import_route_targets": ["64512:100"]}]},
            {"l2vpn_terminations": [{"l2vpn": "invalid", "device": "ceos1"}]},
            {"l2vpn_terminations": [{"l2vpn": "invalid", "group": "test"}]},
            {
                "l2vpn_terminations": [
                    {
                        "l2vpn": "invalid",
                        "device": "ceos1",
                        "interface": "Ethernet1",
                        "group": "test",
                        "vid": 100,
                    }
                ]
            },
            {"platforms": [{"name": "invalid", "manufacturer": {"name": "ACME"}}]},
            {"vlans": [{"name": "invalid", "vid": 321}]},
            {
                "vlans": [
                    {"name": "invalid", "vid": 321, "group": "test", "site": "test"}
                ]
            },
            {
                "vlans": [
                    {
                        "create_vlan": {
                            "vlan_group": "test",
                            "name": "invalid",
                            "site": "test",
                        }
                    }
                ]
            },
        ],
    )
    def test_invalid_design(self, nfclient: Any, design: dict) -> None:
        """The worker rejects unsupported collections and invalid list shapes."""
        response = nfclient.run_job(
            "netbox", "design_deploy", workers="any", kwargs={"design": design}
        )
        for result in response.values():
            assert result["failed"] is True

    def test_tenant_write_error(self, nfclient: Any) -> None:
        """A NetBox write error is returned with the failing collection."""
        nb = pynetbox.api(url=NB_URL, token=NB_API_TOKEN)
        name = "norfab-design-invalid-tenant"
        if nb.tenancy.tenants.get(name=name):
            pytest.skip("Design test tenant already exists in NetBox")
        try:
            response = nfclient.run_job(
                "netbox",
                "design_deploy",
                workers="any",
                kwargs={
                    "design": {
                        "tenants": [
                            {
                                "name": name,
                                "slug": name,
                                "group": "NORFAB MISSING TENANT GROUP",
                            }
                        ]
                    }
                },
            )
            for result in response.values():
                assert result["failed"] is True
                assert result["errors"]
                assert "failed to deploy tenants" in result["errors"][0]
        finally:
            tenant = nb.tenancy.tenants.get(name=name)
            if tenant:
                tenant.delete()

    def test_five_tenants(self, nfclient: Any) -> None:
        """A design dictionary creates five tenants and patches them on rerun."""
        nb = pynetbox.api(url=NB_URL, token=NB_API_TOKEN)
        design = {
            "tenants": [
                {"name": "norfab-design-create-1", "slug": "norfab-design-create-1"},
                {"name": "norfab-design-create-2", "slug": "norfab-design-create-2"},
                {"name": "norfab-design-create-3", "slug": "norfab-design-create-3"},
                {"name": "norfab-design-create-4", "slug": "norfab-design-create-4"},
                {"name": "norfab-design-create-5", "slug": "norfab-design-create-5"},
            ]
        }
        names = [tenant["name"] for tenant in design["tenants"]]
        if any(nb.tenancy.tenants.get(name=name) for name in names):
            pytest.skip("Design test tenants already exist in NetBox")
        try:
            for expected_action in ("created", "updated"):
                response = nfclient.run_job(
                    "netbox", "design_deploy", workers="any", kwargs={"design": design}
                )
                for worker, result in response.items():
                    assert result["failed"] is False, f"{worker} failed: {result}"
                    assert result["result"]["tenants"][expected_action] == names
            assert all(nb.tenancy.tenants.get(name=name) for name in names)
        finally:
            for name in names:
                tenant = nb.tenancy.tenants.get(name=name)
                if tenant:
                    tenant.delete()

    def test_mixed_tenant_create_and_update(self, nfclient: Any) -> None:
        """One deployment separates existing tenants from missing tenants."""
        nb = pynetbox.api(url=NB_URL, token=NB_API_TOKEN)
        design = {
            "tenants": [
                {
                    "name": "norfab-design-mixed-1",
                    "slug": "norfab-design-mixed-1",
                    "description": "new",
                },
                {
                    "name": "norfab-design-mixed-2",
                    "slug": "norfab-design-mixed-2",
                    "description": "new",
                },
                {
                    "name": "norfab-design-mixed-3",
                    "slug": "norfab-design-mixed-3",
                    "description": "new",
                },
                {
                    "name": "norfab-design-mixed-4",
                    "slug": "norfab-design-mixed-4",
                    "description": "new",
                },
                {
                    "name": "norfab-design-mixed-5",
                    "slug": "norfab-design-mixed-5",
                    "description": "new",
                },
            ]
        }
        names = [tenant["name"] for tenant in design["tenants"]]
        if any(nb.tenancy.tenants.get(name=name) for name in names):
            pytest.skip("Design test tenants already exist in NetBox")
        try:
            nb.tenancy.tenants.create(
                {"name": names[0], "slug": names[0], "description": "old"}
            )
            response = nfclient.run_job(
                "netbox", "design_deploy", workers="any", kwargs={"design": design}
            )
            for worker, result in response.items():
                assert result["failed"] is False, f"{worker} failed: {result}"
                assert result["result"]["tenants"] == {
                    "created": names[1:],
                    "updated": [names[0]],
                }
            assert all(
                nb.tenancy.tenants.get(name=name).description == "new" for name in names
            )
        finally:
            for name in names:
                tenant = nb.tenancy.tenants.get(name=name)
                if tenant:
                    tenant.delete()
