import fnmatch
import ipaddress
import logging
from typing import Any, Union

from norfab.core.worker import Job
from norfab.models import Result

log = logging.getLogger(__name__)

SYNC_DIFF_ACTIONS = ("create", "update", "delete")


def merge_array_values(
    existing: list | None, additions: list | None, attribute: str | None = None
) -> list:
    """Append new array values in order without removing existing values.

    Args:
        existing: Current values.
        additions: Requested values. ``None`` and an empty list leave the
            current values intact.
        attribute: Optional attribute to read from NetBox records. ``id``
            returns IDs; other attributes return dictionaries keyed by that
            attribute.

    Returns:
        list: Existing values followed by requested values not already present,
            formatted for the target NetBox field.
    """

    def field_value(value: Any) -> Any:
        if not attribute:
            return value
        return (
            value.get(attribute, value)
            if isinstance(value, dict)
            else getattr(value, attribute, value)
        )

    merged = [field_value(value) for value in existing or []]
    for value in additions or []:
        value = field_value(value)
        if value not in merged:
            merged.append(value)
    return (
        [{attribute: value} for value in merged]
        if attribute and attribute != "id"
        else merged
    )


def merge_resolved_custom_fields(
    worker: Any,
    nb: Any,
    nb_object: Any,
    additions: dict,
    object_fields: list,
    multiobject_fields: list,
) -> tuple[dict, dict]:
    """Resolve custom-field object names and merge supplied array values.

    Args:
        worker: NetBox worker used to fetch named related objects in batches.
        nb: Pynetbox API for the selected instance and branch.
        nb_object: Existing NetBox object, or ``None`` when creating one.
        additions: Custom-field values supplied to the task.
        object_fields: Object custom-field definitions for this object type.
        multiobject_fields: Multiobject custom-field definitions for this type.

    Returns:
        tuple[dict, dict]: Normalized current fields and merged write payload.

    Raises:
        ValueError: If a related object type has no endpoint or a supplied name
            does not identify exactly one related object.
    """
    object_types = {field.name: field.related_object_type for field in object_fields}
    multiobject_types = {
        field.name: field.related_object_type for field in multiobject_fields
    }

    def reference_id(value: Any) -> Any:
        return value["id"] if isinstance(value, dict) and "id" in value else value

    current = {}
    current_fields = nb_object.custom_fields if nb_object else None
    for name, value in (current_fields or {}).items():
        if name in object_types:
            current[name] = reference_id(value)
        elif name in multiobject_types and isinstance(value, list):
            current[name] = [reference_id(item) for item in value]
        else:
            current[name] = value

    def resolve_references(object_type: str, values: list) -> list:
        """Replace names with IDs while retaining supplied IDs and their order."""
        names = {item for item in values if isinstance(item, str)}
        resolved = {}
        if names:
            # NetBox maps dcim.device to /api/dcim/devices/ and plugin models
            # to /api/plugins/...; use that path to find the Pynetbox endpoint.
            app_label, model = object_type.split(".", 1)
            definition = nb.core.object_types.get(app_label=app_label, model=model)
            path = (
                definition.rest_api_endpoint.strip("/").split("/")
                if definition and definition.rest_api_endpoint
                else []
            )
            if len(path) < 3 or path[0] != "api":
                raise ValueError(
                    f"custom-field object type '{object_type}' has no REST endpoint"
                )
            endpoint = nb
            for segment in path[1:]:
                endpoint = getattr(endpoint, segment.replace("-", "_"))
            # A name can exist on multiple objects, so require exactly one ID.
            matches = {item: set() for item in names}
            for item in worker.bulk_filter(
                endpoint, name=sorted(names), fields="id,name"
            ):
                item_name = getattr(item, "name", None)
                if item_name in matches:
                    matches[item_name].add(item.id)
            for item_name, ids in matches.items():
                if len(ids) != 1:
                    raise ValueError(
                        f"custom-field {object_type} name '{item_name}' matched {len(ids)} objects"
                    )
                resolved[item_name] = next(iter(ids))
        # Existing IDs need no lookup; NetBox expects IDs in reference fields.
        return [
            resolved[item] if isinstance(item, str) else reference_id(item)
            for item in values
        ]

    merged = dict(current)
    for name, value in additions.items():
        if value is None:
            merged[name] = None
        elif name in object_types:
            merged[name] = resolve_references(object_types[name], [value])[0]
        elif name in multiobject_types:
            merged[name] = merge_array_values(
                current.get(name),
                resolve_references(multiobject_types[name], value),
            )
        elif isinstance(value, list) and isinstance(current.get(name), list):
            merged[name] = merge_array_values(current[name], value)
        else:
            merged[name] = value
    return current, merged


def sync_diff_has_changes(diff: dict, ignore_deletions: bool = False) -> bool:
    """Return whether a sync diff contains a relevant actionable change."""
    if any(action in diff for action in SYNC_DIFF_ACTIONS):
        actions = ("create", "update") if ignore_deletions else SYNC_DIFF_ACTIONS
        return any(bool(diff.get(action)) for action in actions)

    # Combined sync tasks group action dictionaries by device or resource type.
    return any(
        sync_diff_has_changes(value, ignore_deletions=ignore_deletions)
        for value in diff.values()
        if isinstance(value, dict)
    )


def map_interface_name(
    name: Union[None, str],
    rules: list[dict],
    device_name: str,
    device_type: str,
) -> Union[None, str]:
    """Apply the first matching interface-name mapping rule."""
    for rule in rules:
        if (
            name
            and fnmatch.fnmatchcase(device_name, rule["device_name"])
            and fnmatch.fnmatchcase(device_type, rule["device_type"])
            and rule["match"] in name
        ):
            return name.replace(rule["match"], rule["replace"])
    return name


def apply_description_policy(
    live_description: Union[None, str],
    netbox_description: Union[None, str],
    preserve_description: Union[None, bool] = None,
) -> str:
    """Return the description selected by a NetBox sync preservation policy."""
    live_description = str(live_description or "")
    netbox_description = str(netbox_description or "")

    # Explicit preservation always keeps the description already in NetBox.
    if preserve_description is True:
        return netbox_description

    # By default, empty live data must not erase an existing description.
    if preserve_description is None:
        if not live_description:
            return netbox_description

    # Use live data when preservation is disabled or the default has live text.
    return live_description


def review_sync_task_result(
    job: Job,
    task_name: str,
    preview: Any,
) -> bool:
    """Request review for a prepared sync dry-run result."""
    approved = job.request_input(
        question=f"Apply {task_name} dry-run changes to NetBox?",
        default=False,
        metadata={"preview": preview},
    )
    if not approved:
        job.event(f"{task_name} changes were not approved; returning dry-run result")
        return False

    job.event(f"{task_name} changes approved; applying changes")
    return True


def resolve_vrf(
    name: Union[None, str], nb: Any, job: Job, ret: Result, worker_name: str
) -> Union[int, None]:
    """Resolve or create a VRF, return its NetBox ID or None."""
    if not name:
        return None
    if name.lower() in ["global", "default"]:
        return None
    vrf_objects = list(nb.ipam.vrfs.filter(name=name))
    if vrf_objects:
        if len(vrf_objects) > 1:
            msg = f"Found multiple VRF in Netbox matching name '{name}', using VRF with ID {vrf_objects[0].id}"
            log.warning(msg)
            job.event(msg, severity="WARNING")
        return vrf_objects[0].id
    try:
        new_vrf = nb.ipam.vrfs.create(name=name)
        msg = f"created VRF '{name}' in NetBox"
        job.event(msg)
        log.info(f"{worker_name} - {msg}")
        return new_vrf.id
    except Exception as e:
        msg = f"failed to create VRF '{name}' in NetBox: {e}"
        job.event(msg, severity="ERROR")
        log.error(f"{worker_name} - {msg}")
        ret.errors.append(msg)
        return None


def resolve_ip(
    address: Union[None, str, int],
    nb: Any,
    job: Job,
    ret: Result,
    worker_name: str,
    lookup_cache: Union[None, dict] = None,
) -> Union[int, None]:
    """Resolve or create an IP address in IPAM, return its NetBox ID or None."""
    if not address:
        return None
    if type(address) is int:
        return address
    if lookup_cache is None:
        lookup_cache = {}
    cache_key = ("ip", address)
    if cache_key in lookup_cache:
        return lookup_cache[cache_key]
    existing = list(nb.ipam.ip_addresses.filter(q=f"{address}/"))
    if existing:
        ip_id = existing[0].id
        lookup_cache[cache_key] = ip_id
        return ip_id
    # Try to find a containing prefix for mask length
    mask: str = None
    prefixes = list(nb.ipam.prefixes.filter(contains=address))
    if prefixes:
        # pick up longest prefix length for the mask
        mask = str(max([int(p.prefix.split("/")[1]) for p in prefixes]))
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
        log.info(f"{worker_name} - {msg}")
        lookup_cache[cache_key] = new_ip.id
        return new_ip.id
    except Exception as e:
        msg = f"failed to create IP address '{address}/{mask}': {e}"
        job.event(msg, severity="ERROR")
        log.error(f"{worker_name} - {msg}")
        ret.errors.append(msg)
        lookup_cache[cache_key] = None
        return None
