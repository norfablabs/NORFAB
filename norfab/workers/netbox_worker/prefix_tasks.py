import ipaddress
import logging

from typing import Union
from norfab.core.worker import Task, Job
from norfab.models import Result
from norfab.models.netbox import CreatePrefixInput, NetboxFastApiArgs
from .netbox_exceptions import NetboxAllocationError

log = logging.getLogger(__name__)


class NetboxPrefixTasks:

    @Task(
        input=CreatePrefixInput,
        fastapi={"methods": ["POST"], "schema": NetboxFastApiArgs.model_json_schema()},
    )
    def create_prefix(
        self,
        job: Job,
        parent: Union[str, dict],
        description: str = None,
        prefixlen: int = 30,
        vrf: str = None,
        tags: Union[None, list] = None,
        tenant: str = None,
        comments: str = None,
        role: str = None,
        site: str = None,
        status: str = None,
        instance: Union[None, str] = None,
        dry_run: bool = False,
        branch: str = None,
    ) -> Result:
        """
        Creates a new IP prefix in NetBox or updates an existing one.

        Args:
            parent (Union[str, dict]): Parent prefix to allocate new prefix from, could be:

                - IPv4 prefix string e.g. 10.0.0.0/24
                - IPv6 prefix string e.g. 2001::/64
                - Prefix description string to filter by
                - Dictionary with prefix filters for `pynetbox` prefixes.get method
                    e.g. `{"prefix": "10.0.0.0/24", "site__name": "foo"}`

            description (str): Description for the new prefix, prefix description used for
                deduplication to source existing prefixes.
            prefixlen (int, optional): The prefix length of the new prefix to create, by default
                allocates next available /30 point-to-point prefix.
            vrf (str, optional): Name of the VRF to associate with the prefix.
            tags (Union[None, list], optional): List of tags to assign to the prefix.
            tenant (str, optional): Name of the tenant to associate with the prefix.
            comments (str, optional): Comments for the prefix.
            role (str, optional): Role to assign to the prefix.
            site (str, optional): Name of the site to associate with the prefix.
            status (str, optional): Status of the prefix.
            instance (Union[None, str], optional): NetBox instance identifier.
            dry_run (bool, optional): If True, simulates the creation without making changes.
            branch (str, optional): Branch name to use, need to have branching plugin installed,
                automatically creates branch if it does not exist in Netbox.

        Returns:
            Result: An object containing the outcome, including status, details of the prefix, and resources used.
        """
        instance = instance or self.default_instance
        changed = {}
        ret = Result(
            task=f"{self.name}:create_prefix",
            result={},
            resources=[instance],
            diff=changed,
        )
        tags = tags or []
        nb_prefix = None
        nb = self._get_pynetbox(instance, branch=branch)

        job.event(
            f"Processing prefix create request within '{parent}' for '/{prefixlen}' subnet"
        )

        # source parent prefix from Netbox
        if isinstance(parent, str):
            # check if parent prefix is IP network or description
            try:
                _ = ipaddress.ip_network(parent)
                is_network = True
            except Exception:
                is_network = False
            if is_network is True and vrf:
                parent_filters = {"prefix": parent, "vrf__name": vrf}
            elif is_network is True:
                parent_filters = {"prefix": parent}
            elif is_network is False and vrf:
                parent_filters = {"description": parent, "vrf__name": vrf}
            elif is_network is False:
                parent_filters = {"description": parent}
        nb_parent_prefix = nb.ipam.prefixes.get(**parent_filters)
        if not nb_parent_prefix:
            raise NetboxAllocationError(
                f"Unable to source parent prefix from Netbox - {parent}"
            )

        # check that parent vrf and new prefix vrf are same
        if vrf and str(nb_parent_prefix.vrf) != vrf:
            raise NetboxAllocationError(
                f"Parent prefix vrf '{nb_parent_prefix.vrf}' not same as requested child prefix vrf '{vrf}'"
            )

        # try to source existing prefix from netbox
        prefix_filters = {}
        if vrf:
            prefix_filters["vrf__name"] = vrf
        if site:
            prefix_filters["site__name"] = site
        if description:
            prefix_filters["description"] = description
        try:
            if prefix_filters:
                nb_prefix = nb.ipam.prefixes.get(
                    within=nb_parent_prefix.prefix, **prefix_filters
                )
        except Exception as e:
            raise NetboxAllocationError(
                f"Failed to source existing prefix from Netbox using filters '{prefix_filters}', error: {e}"
            )

        # create new prefix
        if not nb_prefix:
            job.event(f"Creating new '/{prefixlen}' prefix within '{parent}' prefix")
            # execute dry run on new prefix
            if dry_run is True:
                nb_prefixes = nb_parent_prefix.available_prefixes.list()
                if not nb_prefixes:
                    raise NetboxAllocationError(
                        f"Parent prefix '{parent}' has no child prefixes available"
                    )
                for pfx in nb_prefixes:
                    # parent prefix empty, can use first subnet as a child prefix
                    if pfx.prefix == nb_parent_prefix.prefix:
                        nb_prefix = (
                            nb_parent_prefix.prefix.split("/")[0] + f"/{prefixlen}"
                        )
                        break
                    # find child prefix by prefixlenght
                    elif str(pfx).endswith(f"/{prefixlen}"):
                        nb_prefix = str(pfx)
                        break
                else:
                    raise NetboxAllocationError(
                        f"Parent prefix '{parent}' has no child prefixes available with '/{prefixlen}' prefix length"
                    )
                ret.status = "unchanged"
                ret.dry_run = True
                ret.result = {
                    "prefix": nb_prefix,
                    "description": description,
                    "parent": nb_parent_prefix.prefix,
                    "vrf": vrf,
                    "site": site,
                }
                # add branch to results
                if branch is not None:
                    ret.result["branch"] = branch
                return ret
            # create new prefix
            else:
                try:
                    nb_prefix = nb_parent_prefix.available_prefixes.create(
                        {"prefix_length": prefixlen}
                    )
                except Exception as e:
                    raise NetboxAllocationError(
                        f"Failed creating child prefix of '/{prefixlen}' prefix length "
                        f"within parent prefix '{str(nb_parent_prefix)}', error: {e}"
                    )
            job.event(f"Created new '{nb_prefix}' prefix within '{parent}' prefix")
            ret.status = "created"
        else:
            # check existing prefix length matching requested length
            if not nb_prefix.prefix.endswith(f"/{prefixlen}"):
                raise NetboxAllocationError(
                    f"Found existing child prefix '{nb_prefix.prefix}' with mismatch "
                    f"requested prefix length '/{prefixlen}'"
                )
            job.event(f"Using existing prefix {nb_prefix}")

        # update prefix parameters
        if description and description != nb_prefix.description:
            changed["description"] = {"-": str(nb_prefix.description), "+": description}
            nb_prefix.description = description
        if vrf and vrf != str(nb_prefix.vrf):
            changed["vrf"] = {"-": str(nb_prefix.vrf), "+": vrf}
            nb_prefix.vrf = {"name": vrf}
        if tenant and tenant != str(nb_prefix.tenant):
            changed["tenant"] = {
                "-": str(nb_prefix.tenant) if nb_prefix.tenant else None,
                "+": tenant,
            }
            nb_prefix.tenant = {"name": tenant}
        if site and str(nb_prefix.scope) != site:
            nb_site = nb.dcim.sites.get(name=site)
            if not nb_site:
                raise NetboxAllocationError(f"Failed to get '{site}' site from Netbox")
            changed["site"] = {
                "-": str(nb_prefix.scope) if nb_prefix.scope else None,
                "+": nb_site.name,
            }
            nb_prefix.scope_type = "dcim.site"
            nb_prefix.scope_id = nb_site.id
        if status and status.lower() != nb_prefix.status:
            changed["status"] = {"-": str(nb_prefix.status), "+": status.title()}
            nb_prefix.status = status.lower()
        if comments and comments != nb_prefix.comments:
            changed["comments"] = {"-": str(nb_prefix.comments), "+": comments}
            nb_prefix.comments = comments
        if role and role != nb_prefix.role:
            changed["role"] = {"-": str(nb_prefix.role), "+": role}
            nb_prefix.role = {"name": role}
        existing_tags = [str(t) for t in nb_prefix.tags]
        if tags and not any(t in existing_tags for t in tags):
            changed["tags"] = {
                "-": existing_tags,
                "+": [t for t in tags if t not in existing_tags] + existing_tags,
            }
            for t in tags:
                if t not in existing_tags:
                    nb_prefix.tags.append({"name": t})

        # save prefix into Netbox
        if dry_run:
            ret.status = "unchanged"
            ret.dry_run = True
            ret.diff = changed
        elif changed:
            ret.diff = changed
            nb_prefix.save()
            if ret.status != "created":
                ret.status = "updated"
        else:
            ret.status = "unchanged"

        # source vrf name
        vrf_name = None
        if nb_prefix.vrf:
            if isinstance(nb_prefix.vrf, dict):
                vrf_name = nb_prefix.vrf["name"]
            else:
                vrf_name = nb_prefix.vrf.name

        # form and return results
        ret.result = {
            "prefix": nb_prefix.prefix,
            "description": nb_prefix.description,
            "vrf": vrf_name,
            "site": str(nb_prefix.scope) if nb_prefix.scope else site,
            "parent": nb_parent_prefix.prefix,
        }
        # add branch to results
        if branch is not None:
            ret.result["branch"] = branch

        return ret
