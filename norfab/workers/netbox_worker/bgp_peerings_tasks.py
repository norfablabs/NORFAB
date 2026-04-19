import ipaddress
import logging
from enum import Enum
from typing import List, Union

import pynetbox
from pydantic import Field, StrictInt

from norfab.core.worker import Job, Task
from norfab.models import Result

from .netbox_models import NetboxCommonArgs, NetboxFastApiArgs

log = logging.getLogger(__name__)


class BgpSessionStatusEnum(str, Enum):
    active = "active"
    planned = "planned"
    maintenance = "maintenance"
    offline = "offline"
    decommissioned = "decommissioned"


class SyncBgpPeeringsInput(NetboxCommonArgs, use_enum_values=True):
    devices: Union[None, List] = Field(
        None,
        description="List of device names to create BGP peerings for",
    )
    status: BgpSessionStatusEnum = Field(
        "active",
        description="Status to set on created/updated BGP sessions",
    )
    process_deletions: bool = Field(
        False,
        description="Delete BGP sessions present in NetBox but not found on the device",
    )
    timeout: StrictInt = Field(
        60,
        description="Timeout in seconds for Nornir parse_ttp job",
    )
    batch_size: StrictInt = Field(
        10,
        description="Number of devices to process per Nornir batch",
    )
    rir: Union[None, str] = Field(
        None,
        description="RIR name to use when creating new ASNs in NetBox (e.g. 'RFC 1918', 'ARIN')",
    )
    message: Union[None, str] = Field(
        None,
        description="Changelog message to record in NetBox for all create, update, and delete operations",
    )
    name_template: str = Field(
        "{device}_{name}",
        description=(
            "Template string for BGP session names in NetBox. "
            "Available variables: device, name, "
            "description, local_address, local_as, remote_address, remote_as, "
            "vrf, state, peer_group, import_policies, export_policies, "
            "prefix_list_in, prefix_list_out."
        ),
    )


class NetboxBgpPeeringsTasks:

    @Task(fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()})
    def get_bgp_peerings(
        self,
        job: Job,
        instance: Union[None, str] = None,
        devices: Union[None, list] = None,
        cache: Union[None, bool, str] = None,
    ) -> Result:
        """
        Retrieve device BGP peerings from Netbox using REST API.

        Args:
            job: NorFab Job object containing relevant metadata
            instance (str, optional): Netbox instance name.
            devices (list, optional): List of devices to retrieve BGP peerings for.
            cache (Union[bool, str], optional): Cache usage options:

                - True: Use data stored in cache if it is up to date, refresh it otherwise.
                - False: Do not use cache and do not update cache.
                - refresh: Ignore data in cache and replace it with data fetched from Netbox.
                - force: Use data in cache without checking if it is up to date.

        Returns:
            dict: Dictionary keyed by device name with BGP peerings details.

        Example return data for single bgp peering - same data as returned by Netbox built-in REST
        API explorer:

        ```
        "fceos4-fceos5-eth105": {
            "comments": "",
            "created": "2026-04-08T10:29:13.404863Z",
            "custom_fields": {},
            "description": "BGP peering between fceos4 and fceos5 on eth105",
            "device": {
                "description": "",
                "display": "fceos4 (UUID-123451)",
                "id": 119,
                "name": "fceos4",
                "url": "http://netbox.lab:8000/api/dcim/devices/119/"
            },
            "display": "fceos4 (UUID-123451):fceos4-fceos5-eth105",
            "export_policies": [
                {
                    "description": "",
                    "display": "RPL1",
                    "id": 1,
                    "name": "RPL1",
                    "url": "http://netbox.lab:8000/api/plugins/bgp/routing-policy/1/"
                }
            ],
            "id": 7,
            "import_policies": [
                {
                    "description": "",
                    "display": "RPL1",
                    "id": 1,
                    "name": "RPL1",
                    "url": "http://netbox.lab:8000/api/plugins/bgp/routing-policy/1/"
                }
            ],
            "last_updated": "2026-04-18T21:39:38.947199Z",
            "local_address": {
                "address": "10.0.2.1/30",
                "description": "",
                "display": "10.0.2.1/30",
                "family": {
                    "label": "IPv4",
                    "value": 4
                },
                "id": 489,
                "url": "http://netbox.lab:8000/api/ipam/ip-addresses/489/"
            },
            "local_as": {
                "asn": 65100,
                "description": "BGP ASN for fceos4",
                "display": "AS65100",
                "id": 3,
                "url": "http://netbox.lab:8000/api/ipam/asns/3/"
            },
            "name": "fceos4-fceos5-eth105",
            "peer_group": {
                "description": "Test BGP peer group 1 for standard peerings",
                "display": "TEST_BGP_PEER_GROUP_1",
                "id": 3,
                "name": "TEST_BGP_PEER_GROUP_1",
                "url": "http://netbox.lab:8000/api/plugins/bgp/bgppeergroup/3/"
            },
            "prefix_list_in": {
                "description": "",
                "display": "PFL1",
                "id": 1,
                "name": "PFL1",
                "url": "http://netbox.lab:8000/api/plugins/bgp/prefix-list/1/"
            },
            "prefix_list_out": {
                "description": "",
                "display": "PFL1",
                "id": 1,
                "name": "PFL1",
                "url": "http://netbox.lab:8000/api/plugins/bgp/prefix-list/1/"
            },
            "remote_address": {
                "address": "10.0.2.2/30",
                "description": "",
                "display": "10.0.2.2/30",
                "family": {
                    "label": "IPv4",
                    "value": 4
                },
                "id": 490,
                "url": "http://netbox.lab:8000/api/ipam/ip-addresses/490/"
            },
            "remote_as": {
                "asn": 65101,
                "description": "BGP ASN for fceos5",
                "display": "AS65101",
                "id": 4,
                "url": "http://netbox.lab:8000/api/ipam/asns/4/"
            },
            "site": {
                "description": "",
                "display": "SALTNORNIR-LAB",
                "id": 13,
                "name": "SALTNORNIR-LAB",
                "slug": "saltnornir-lab",
                "url": "http://netbox.lab:8000/api/dcim/sites/13/"
            },
            "status": {
                "label": "Active",
                "value": "active"
            },
            "tags": [],
            "tenant": {
                "description": "",
                "display": "SALTNORNIR",
                "id": 10,
                "name": "SALTNORNIR",
                "slug": "saltnornir",
                "url": "http://netbox.lab:8000/api/tenancy/tenants/10/"
            },
            "url": "http://netbox.lab:8000/api/plugins/bgp/bgpsession/7/",
            "virtualmachine": null
        }
        ```
        """
        instance = instance or self.default_instance
        devices = devices or []
        log.info(
            f"{self.name} - Get BGP peerings: Fetching BGP peerings for {len(devices)} device(s) from '{instance}' Netbox"
        )
        cache = self.cache_use if cache is None else cache
        ret = Result(
            task=f"{self.name}:get_bgp_peerings",
            result={d: {} for d in devices},
            resources=[instance],
        )

        # Check if BGP plugin is installed
        if not self.has_plugin("netbox_bgp", instance, strict=True):
            ret.errors.append(f"{instance} Netbox instance has no BGP Plugin installed")
            ret.failed = True
            return ret

        self.cache.expire()

        # Get device details to collect device IDs
        devices_result = self.get_devices(
            job=job, devices=devices, instance=instance, cache=False
        )
        if devices_result.errors:
            ret.errors.append(
                f"Failed to retrieve device details: {devices_result.errors}"
            )
            return ret

        nb = self._get_pynetbox(instance)

        for device_name in devices:
            # Skip devices not found in Netbox
            if device_name not in devices_result.result:
                msg = f"Device '{device_name}' not found in Netbox"
                job.event(msg, resource=instance, severity="WARNING")
                log.warning(msg)
                continue

            device_id = devices_result.result[device_name]["id"]
            cache_key = f"get_bgp_peerings::{device_name}"
            cached_data = self.cache.get(cache_key)

            # Mode: force with cached data - use cache directly
            if cache == "force" and cached_data is not None:
                ret.result[device_name] = cached_data
                job.event(
                    f"using cached BGP peerings for '{device_name}' (forced)",
                    resource=instance,
                )
                continue

            # Mode: cache disabled - fetch without caching
            if cache is False:
                bgp_sessions = nb.plugins.bgp.session.filter(device_id=device_id)
                ret.result[device_name] = {s.name: dict(s) for s in bgp_sessions}
                job.event(
                    f"retrieved {len(ret.result[device_name])} BGP session(s) for '{device_name}'",
                    resource=instance,
                )
                continue

            # Mode: refresh or no cached data - fetch and cache
            if cache == "refresh" or cached_data is None:
                if cache == "refresh" and cached_data is not None:
                    self.cache.delete(cache_key, retry=True)
                bgp_sessions = nb.plugins.bgp.session.filter(device_id=device_id)
                ret.result[device_name] = {s.name: dict(s) for s in bgp_sessions}
                self.cache.set(
                    cache_key, ret.result[device_name], expire=self.cache_ttl
                )
                job.event(
                    f"fetched and cached {len(ret.result[device_name])} BGP session(s) for '{device_name}'",
                    resource=instance,
                )
                continue

            # Mode: cache=True with cached data - smart update (only fetch changed sessions)
            ret.result[device_name] = dict(cached_data)
            job.event(
                f"retrieved {len(cached_data)} BGP session(s) from cache for '{device_name}'",
                resource=instance,
            )

            # Fetch brief session info to compare timestamps
            brief_sessions = nb.plugins.bgp.session.filter(
                device_id=device_id, fields="id,last_updated,name"
            )
            netbox_sessions = {
                s.id: {"name": s.name, "last_updated": s.last_updated}
                for s in brief_sessions
            }

            # Build lookup maps
            cached_by_id = {s["id"]: name for name, s in cached_data.items()}
            session_ids_to_fetch = []
            sessions_to_remove = []

            # Find stale sessions (exist in both but timestamps differ) and deleted sessions
            for session_name, cached_session in cached_data.items():
                cached_id = cached_session["id"]
                if cached_id in netbox_sessions:
                    if (
                        cached_session["last_updated"]
                        != netbox_sessions[cached_id]["last_updated"]
                    ):
                        session_ids_to_fetch.append(cached_id)
                else:
                    sessions_to_remove.append(session_name)

            # Find new sessions in Netbox not in cache
            for nb_id in netbox_sessions:
                if nb_id not in cached_by_id:
                    session_ids_to_fetch.append(nb_id)

            # Remove deleted sessions
            for session_name in sessions_to_remove:
                ret.result[device_name].pop(session_name, None)
                job.event(
                    f"removed deleted session '{session_name}' from cache for '{device_name}'",
                    resource=instance,
                )

            # Fetch updated/new sessions
            if session_ids_to_fetch:
                job.event(
                    f"fetching {len(session_ids_to_fetch)} updated BGP session(s) for '{device_name}'",
                    resource=instance,
                )
                for session in nb.plugins.bgp.session.filter(id=session_ids_to_fetch):
                    ret.result[device_name][session.name] = dict(session)

            # Update cache if any changes occurred
            if session_ids_to_fetch or sessions_to_remove:
                self.cache.set(
                    cache_key, ret.result[device_name], expire=self.cache_ttl
                )
                job.event(f"updated cache for '{device_name}'", resource=instance)
            else:
                job.event(
                    f"using cache, it is up to date for '{device_name}'",
                    resource=instance,
                )

        return ret

    @Task(
        fastapi={"methods": ["POST"], "schema": NetboxFastApiArgs.model_json_schema()}
    )
    def sync_bgp_peerings(
        self,
        job: Job,
        instance: Union[None, str] = None,
        devices: Union[None, list] = None,
        status: str = "active",
        dry_run: bool = False,
        process_deletions: bool = False,
        timeout: int = 60,
        batch_size: int = 10,
        branch: str = None,
        rir: str = None,
        message: str = None,
        name_template: str = "{device}_{name}",
        **kwargs,
    ) -> Result:
        """
        Synchronize BGP sessions between live devices and NetBox.

        Collects BGP session data from devices via Nornir ``parse_ttp`` with
        ``get="bgp_neighbors"``, compares against existing NetBox BGP sessions and
        creates, updates, or (optionally) deletes sessions in NetBox accordingly.

        Args:
            job: NorFab Job object.
            instance (str, optional): NetBox instance name.
            devices (list, optional): List of device names to process.
            status (str): Status to assign to created/updated sessions when not ``established`` on device.
            dry_run (bool): If True, return diff report without writing to NetBox.
            process_deletions (bool): If True, delete NetBox sessions not found on device.
            timeout (int): Timeout in seconds for Nornir ``parse_ttp`` job.
            batch_size (int): Devices per Nornir batch (reserved for future use).
            branch (str, optional): NetBox branching plugin branch name.
            rir (str, optional): RIR name to use when creating new ASNs in NetBox (e.g. ``RFC 1918``, ``ARIN``).
            message (str, optional): Changelog message recorded in NetBox for all create, update, and delete operations.
            name_template (str): Template string for BGP session names written to NetBox. Formatted with the
                following keyword arguments from parsing results:

                - ``device`` — device name (e.g. ``ceos-leaf-1``)
                - ``name`` — parsed session name - ``{vrf}_{remote_address}`` by default
                - ``description`` — session description
                - ``local_address`` — local IP address string (e.g. ``10.0.0.1``)
                - ``local_as`` — local AS number string (e.g. ``65100``)
                - ``remote_address`` — remote IP address string
                - ``remote_as`` — remote AS number string
                - ``vrf`` — VRF name or ``None``
                - ``state`` — device-reported state (e.g. ``established``)
                - ``peer_group`` — peer group name or ``None``

                Default: ``"{device}_{name}"``.
            **kwargs: Nornir host filters (e.g. ``FC``, ``FL``, ``FB``).

        Returns:
            Normal run result keyed by device name::

                {
                    "<device>": {
                        "created": ["<session_name>", ...],
                        "updated": ["<session_name>", ...],
                        "deleted": ["<session_name>", ...],
                        "in_sync": ["<session_name>", ...],
                    }
                }

            Dry-run result keyed by device name::

                {
                    "<device>": {
                        "create": ["<session_name>", ...],
                        "delete": ["<session_name>", ...],
                        "update": {"<session_name>": {"<field>": {"old_value": ..., "new_value": ...}, ...}, ...},
                        "in_sync": ["<session_name>", ...],
                    }
                }
        """
        instance = instance or self.default_instance
        devices = devices or []
        ret = Result(
            task=f"{self.name}:sync_bgp_peerings",
            result={},
            resources=[instance],
        )

        # Normalised session dicts keyed by device name -> session name -> session field values
        normalised_nb = (
            {}
        )  # NetBox data: device name -> session name -> normalised field values
        normalised_live = (
            {}
        )  # Live data:   device name -> session name -> normalised field values
        # Diff results keyed by device name: device name -> diff result (create/source, update, in_sync)
        full_diff = {}
        # pynetbox API client, initialised after the dry-run guard
        nb = None
        # Device detail lookup: device name -> {"id": ..., "site_id": ...}
        devices_info = {}
        # RIR ID used when creating new ASNs in NetBox (resolved from rir param if provided)
        rir_id = None
        # Per-device result tracking: created/updated/deleted/in_sync session names
        device_results = {}

        # Validate BGP plugin
        if not self.has_plugin("netbox_bgp", instance, strict=True):
            ret.errors.append(
                f"'{instance}' NetBox instance has no BGP plugin installed"
            )
            ret.failed = True
            return ret

        # Source additional devices from Nornir filters
        if kwargs:
            nornir_hosts = self.get_nornir_hosts(kwargs, timeout)
            for host in nornir_hosts:
                if host not in devices:
                    devices.append(host)

        if not devices:
            ret.errors.append("no devices specified")
            ret.failed = True
            return ret

        log.info(
            f"{self.name} - Sync BGP peerings: processing {len(devices)} device(s) in '{instance}'"
        )

        # Fetch existing NetBox BGP sessions
        job.event(f"fetching BGP session data from Netbox for {len(devices)} device(s)")
        nb_sessions_result = self.get_bgp_peerings(
            job=job, instance=instance, devices=devices, cache=True
        )
        if nb_sessions_result.errors:
            ret.errors.extend(nb_sessions_result.errors)
            ret.failed = True
            return ret

        # Fetch live BGP data from devices via Nornir parse_ttp
        job.event(
            f"fetching BGP session data from {len(devices)} device(s) via Nornir parse_ttp"
        )
        parse_data = self.client.run_job(
            "nornir",
            "parse_ttp",
            kwargs={"get": "bgp_neighbors", "FL": devices},
            workers="all",
            timeout=timeout,
        )

        # Build normalised dicts per device
        for device_name in devices:
            # Normalise NetBox sessions for this device
            normalised_nb[device_name] = {}
            for sname, nb_session in nb_sessions_result.result.get(
                device_name, {}
            ).items():
                try:
                    normalised_nb[device_name][sname] = {
                        "name": nb_session["name"],
                        "description": nb_session.get("description") or "",
                        "local_address": nb_session["local_address"]["address"].split(
                            "/"
                        )[0],
                        "local_as": str(nb_session["local_as"]["asn"]),
                        "remote_address": nb_session["remote_address"]["address"].split(
                            "/"
                        )[0],
                        "remote_as": str(nb_session["remote_as"]["asn"]),
                        "vrf": (
                            nb_session["vrf"]["name"] if nb_session.get("vrf") else None
                        ),
                        "status": nb_session["status"]["value"],
                        "peer_group": (
                            nb_session["peer_group"]["name"]
                            if nb_session.get("peer_group")
                            else None
                        ),
                        "import_policies": "|".join(
                            sorted(
                                p["name"]
                                for p in nb_session.get("import_policies") or []
                            )
                        ),
                        "export_policies": "|".join(
                            sorted(
                                p["name"]
                                for p in nb_session.get("export_policies") or []
                            )
                        ),
                        "prefix_list_in": (
                            nb_session["prefix_list_in"]["name"]
                            if nb_session.get("prefix_list_in")
                            else None
                        ),
                        "prefix_list_out": (
                            nb_session["prefix_list_out"]["name"]
                            if nb_session.get("prefix_list_out")
                            else None
                        ),
                    }
                except Exception as e:
                    log.warning(
                        f"{self.name} - failed to normalise NetBox session '{sname}' for '{device_name}': {e}"
                    )

        # Normalize live parse data per device
        for wname, wdata in parse_data.items():
            if wdata.get("failed"):
                log.warning(f"{wname} - failed to parse devices")
                continue
            for device_name, host_sessions in wdata.get("result", {}).items():
                normalised_live.setdefault(device_name, {})
                for s in host_sessions:
                    try:
                        session_name = name_template.format(device=device_name, **s)
                    except (KeyError, IndexError) as e:
                        log.warning(
                            f"{self.name} - name_template '{name_template}' failed for session '{s.get('name')}' on '{device_name}': {e}, falling back to default"
                        )
                        session_name = f"{device_name}_{s['name']}"
                    normalised_live[device_name][session_name] = {
                        "name": session_name,
                        "description": s.get("description") or "",
                        "local_address": s.get("local_address"),
                        "local_as": str(s.get("local_as", "")),
                        "remote_address": s.get("remote_address"),
                        "remote_as": str(s.get("remote_as", "")),
                        "vrf": s.get("vrf"),
                        "status": (
                            "active" if s.get("state") == "established" else status
                        ),
                        "peer_group": s.get("peer_group"),
                        "import_policies": "|".join(
                            sorted(s.get("import_policies") or [])
                        ),
                        "export_policies": "|".join(
                            sorted(s.get("export_policies") or [])
                        ),
                        "prefix_list_in": s.get("prefix_list_in"),
                        "prefix_list_out": s.get("prefix_list_out"),
                    }

        # Single diff on the full normalised datasets
        full_diff = self.make_diff(normalised_live, normalised_nb)

        # Return dry-run results per device
        if dry_run:
            ret.result = full_diff
            return ret

        # Proceed with sessions updates
        nb = self._get_pynetbox(instance, branch=branch)

        # Set changelog message header for all NetBox write operations
        if message:
            nb.http_session.headers["X-Changelog-Message"] = message

        # Pre-fetch device IDs and site IDs once
        devices_info = {
            d.name: {"id": d.id, "site_id": d.site.id if d.site else None}
            for d in nb.dcim.devices.filter(name=devices, fields="name,id,site")
        }

        # Resolve RIR ID once if rir name provided
        if rir:
            rir_obj = nb.ipam.rirs.get(name=rir)
            if rir_obj:
                rir_id = rir_obj.id
            else:
                msg = (
                    f"RIR '{rir}' not found in NetBox, ASN creation will fail if needed"
                )
                job.event(msg, severity="WARNING")
                log.warning(f"{self.name} - {msg}")

        def _resolve_ip(address):
            """Resolve or create an IP address in IPAM, return its ID or None."""
            if not address:
                return None
            existing = list(nb.ipam.ip_addresses.filter(q=f"{address}/"))
            if existing:
                return existing[0].id
            # Try to find a containing prefix for mask length
            mask = None
            prefixes = list(nb.ipam.prefixes.filter(contains=address))
            if prefixes:
                mask = prefixes[0].prefix.split("/")[1]
            if not mask:
                try:
                    net = ipaddress.ip_network(address, strict=False)
                    mask = "128" if net.version == 6 else "32"
                except Exception:
                    mask = "32"
            try:
                new_ip = nb.ipam.ip_addresses.create(address=f"{address}/{mask}")
                msg = f"created IP address '{address}/{mask}' in NetBox IPAM"
                job.event(msg)
                log.info(f"{self.name} - {msg}")
                return new_ip.id
            except Exception as e:
                msg = f"failed to create IP address '{address}/{mask}': {e}"
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - {msg}")
                ret.errors.append(msg)
                return None

        def _resolve_asn(asn_str):
            """Resolve or create an ASN, return its ID or None."""
            if not asn_str:
                return None
            try:
                asn_int = int(asn_str)
            except (ValueError, TypeError):
                return None
            existing = list(nb.ipam.asns.filter(asn=asn_int))
            if existing:
                return existing[0].id
            if not rir_id:
                msg = f"cannot create ASN '{asn_str}': no RIR provided, use 'rir' parameter"
                job.event(msg, severity="WARNING")
                log.warning(f"{self.name} - {msg}")
                ret.errors.append(msg)
                return None
            try:
                new_asn = nb.ipam.asns.create(asn=asn_int, rir=rir_id)
                msg = f"created ASN '{asn_str}' in NetBox IPAM"
                job.event(msg)
                log.info(f"{self.name} - {msg}")
                return new_asn.id
            except Exception as e:
                msg = f"failed to create ASN '{asn_str}': {e}"
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - {msg}")
                ret.errors.append(msg)
                return None

        def _resolve_or_create(endpoint, name, obj_type="object", family=None):
            """Resolve or create a named object (peer_group / routing_policy / prefix_list)."""
            if not name:
                return None
            if family:
                existing = endpoint.get(name=name, family=family)
            else:
                existing = endpoint.get(name=name)
            if existing:
                return existing.id
            create_kwargs = {"name": name}
            if family is not None:
                create_kwargs["family"] = family
            try:
                new_obj = endpoint.create(**create_kwargs)
                msg = f"created {obj_type} '{name}' in NetBox"
                job.event(msg)
                log.info(f"{self.name} - {msg}")
                return new_obj.id
            except Exception as e:
                msg = f"failed to create {obj_type} '{name}' in NetBox: {e}"
                job.event(msg, severity="ERROR")
                log.error(f"{self.name} - {msg}")
                ret.errors.append(msg)
                return None

        def _get_addr_family(address):
            """Return 'ipv4' or 'ipv6' based on the IP address version."""
            try:
                return "ipv6" if ipaddress.ip_address(address).version == 6 else "ipv4"
            except Exception:
                return "ipv4"

        # Per-device result tracking
        device_results = {
            device_name: {
                "created": [],
                "updated": [],
                "deleted": [],
                "in_sync": actions["in_sync"],
            }
            for device_name, actions in full_diff.items()
        }

        for device_name, actions in full_diff.items():

            device_info = devices_info.get(device_name)
            if not device_info:
                msg = f"device '{device_name}' not found in NetBox, skipping"
                job.event(msg, severity="WARNING")
                ret.errors.append(msg)
                continue
            device_id = device_info["id"]

            # --- Create ---
            payloads = []
            for sname in actions["create"]:
                job.event(
                    f"preparing to create BGP session '{sname}' for '{device_name}'"
                )
                s = normalised_live[device_name][sname]
                local_ip_id = _resolve_ip(s["local_address"])
                remote_ip_id = _resolve_ip(s["remote_address"])
                local_as_id = _resolve_asn(s["local_as"])
                remote_as_id = _resolve_asn(s["remote_as"])

                resolution_errors = []
                if not local_ip_id:
                    resolution_errors.append(f"local IP '{s['local_address']}'")
                if not remote_ip_id:
                    resolution_errors.append(f"remote IP '{s['remote_address']}'")
                if not local_as_id:
                    resolution_errors.append(f"local ASN '{s['local_as']}'")
                if not remote_as_id:
                    resolution_errors.append(f"remote ASN '{s['remote_as']}'")
                if resolution_errors:
                    msg = f"skipping '{sname}': could not resolve {', '.join(resolution_errors)}"
                    job.event(msg, severity="WARNING")
                    log.warning(f"{self.name} - {msg}")
                    ret.errors.append(msg)
                    continue

                payload = {
                    "name": sname,
                    "description": s["description"],
                    "device": device_id,
                    "local_address": local_ip_id,
                    "local_as": local_as_id,
                    "remote_address": remote_ip_id,
                    "remote_as": remote_as_id,
                    "status": s["status"],
                    "site": device_info["site_id"],
                }

                if s.get("vrf"):
                    vrf = nb.ipam.vrfs.get(name=s["vrf"])
                    if vrf:
                        payload["vrf"] = vrf.id

                if s.get("peer_group"):
                    pg_id = _resolve_or_create(
                        nb.plugins.bgp.peer_group,
                        s["peer_group"],
                        obj_type="peer group",
                    )
                    if pg_id:
                        payload["peer_group"] = pg_id

                addr_family = _get_addr_family(s["local_address"])

                if s.get("import_policies"):
                    names = [p for p in s["import_policies"].split("|") if p]
                    ids = [
                        _resolve_or_create(
                            nb.plugins.bgp.routing_policy,
                            p,
                            obj_type="routing policy",
                            family=addr_family,
                        )
                        for p in names
                    ]
                    payload["import_policies"] = [i for i in ids if i]

                if s.get("export_policies"):
                    names = [p for p in s["export_policies"].split("|") if p]
                    ids = [
                        _resolve_or_create(
                            nb.plugins.bgp.routing_policy,
                            p,
                            obj_type="routing policy",
                            family=addr_family,
                        )
                        for p in names
                    ]
                    payload["export_policies"] = [i for i in ids if i]

                if s.get("prefix_list_in"):
                    pl_id = _resolve_or_create(
                        nb.plugins.bgp.prefix_list,
                        s["prefix_list_in"],
                        obj_type="prefix list",
                        family=addr_family,
                    )
                    if pl_id:
                        payload["prefix_list_in"] = pl_id

                if s.get("prefix_list_out"):
                    pl_id = _resolve_or_create(
                        nb.plugins.bgp.prefix_list,
                        s["prefix_list_out"],
                        obj_type="prefix list",
                        family=addr_family,
                    )
                    if pl_id:
                        payload["prefix_list_out"] = pl_id

                payloads.append(payload)

            if payloads:
                try:
                    nb.plugins.bgp.session.create(payloads)
                    msg = f"created {len(payloads)} BGP session(s) for '{device_name}'"
                    log.info(f"{self.name} - {msg}")
                    job.event(msg)
                    device_results[device_name]["created"].extend(
                        p["name"] for p in payloads
                    )
                except Exception as e:
                    msg = f"failed to create BGP sessions for '{device_name}': {e}"
                    ret.errors.append(msg)
                    log.error(f"{self.name} - {msg}")

            # --- Update ---
            for sname, field_changes in actions["update"].items():
                try:
                    session = nb.plugins.bgp.session.get(name=sname)
                    if not session:
                        msg = f"BGP session '{sname}' not found in NetBox, skipping update"
                        job.event(msg, severity="WARNING")
                        log.warning(f"{self.name} - {msg}")
                        ret.errors.append(msg)
                        continue

                    addr_family = _get_addr_family(
                        session.local_address.address.split("/")[0]
                    )
                    changed_payload = {}

                    for field, change in field_changes.items():
                        new_value = change["new_value"]
                        if field in ("local_address", "remote_address"):
                            ip_id = _resolve_ip(new_value)
                            if ip_id:
                                changed_payload[field] = ip_id
                        elif field in ("local_as", "remote_as"):
                            asn_id = _resolve_asn(new_value)
                            if asn_id:
                                changed_payload[field] = asn_id
                        elif field in ("description", "status"):
                            changed_payload[field] = new_value
                        elif field == "vrf":
                            if new_value:
                                vrf = nb.ipam.vrfs.get(name=new_value)
                                changed_payload["vrf"] = vrf.id if vrf else None
                            else:
                                changed_payload["vrf"] = None
                        elif field == "peer_group":
                            changed_payload["peer_group"] = (
                                _resolve_or_create(
                                    nb.plugins.bgp.peer_group,
                                    new_value,
                                    obj_type="peer group",
                                )
                                if new_value
                                else None
                            )
                        elif field in ("import_policies", "export_policies"):
                            names = (
                                [p for p in new_value.split("|") if p]
                                if new_value
                                else []
                            )
                            ids = [
                                _resolve_or_create(
                                    nb.plugins.bgp.routing_policy,
                                    p,
                                    obj_type="routing policy",
                                    family=addr_family,
                                )
                                for p in names
                            ]
                            changed_payload[field] = [i for i in ids if i]
                        elif field in ("prefix_list_in", "prefix_list_out"):
                            changed_payload[field] = (
                                _resolve_or_create(
                                    nb.plugins.bgp.prefix_list,
                                    new_value,
                                    obj_type="prefix list",
                                    family=addr_family,
                                )
                                if new_value
                                else None
                            )

                    if changed_payload:
                        session.update(changed_payload)
                        device_results[device_name]["updated"].append(sname)
                        msg = f"updated BGP session '{sname}' for '{device_name}'"
                        job.event(msg)
                        log.info(f"{self.name} - {msg}")
                except Exception as e:
                    msg = f"failed to update BGP session '{sname}' for '{device_name}': {e}"
                    ret.errors.append(msg)
                    log.error(f"{self.name} - {msg}")

            # --- Delete ---
            if process_deletions:
                for sname in actions["delete"]:
                    try:
                        session = nb.plugins.bgp.session.get(name=sname)
                        if session:
                            session.delete()
                            device_results[device_name]["deleted"].append(sname)
                            msg = f"deleted BGP session '{sname}' for '{device_name}'"
                            job.event(msg)
                            log.info(f"{self.name} - {msg}")
                    except Exception as e:
                        msg = f"failed to delete BGP session '{sname}' for '{device_name}': {e}"
                        ret.errors.append(msg)
                        log.error(f"{self.name} - {msg}")

        ret.result = device_results

        return ret
