import yaml
import logging

from typing import Any, Union, List, Optional, Dict, Type
from datamodel_code_generator import (
    generate_dynamic_models,
    GenerateConfig,
    Formatter,
    DataModelType,
)
from norfab.core.worker import Task
from norfab.models import Result
from norfab.utils.text import slugify
from norfab.models.netbox import NetboxFastApiArgs
from pydantic import BaseModel, Field, create_model, ConfigDict, ValidationError

log = logging.getLogger(__name__)

DEFAULT_CREATE_ORDER = [
    "tenancy.tenants",
    "dcim.regions",
    "dcim.site_groups",
    "dcim.manufacturers",
    "dcim.platforms",
    "dcim.device_roles",
    "dcim.device_types",
    "dcim.rack_roles",
    "ipam.rirs",
    "ipam.roles",
    "ipam.vlan_groups",
    "ipam.vrfs",
    "circuits.providers",
    "circuits.circuit_types",
    "virtualization.cluster_types",
    "virtualization.cluster_groups",
    "dcim.locations",
    "dcim.sites",
    "ipam.asns",
    "circuits.provider_networks",
    "ipam.prefixes",
    "ipam.vlans",
    "circuits.circuits",
    "virtualization.clusters",
    "dcim.racks",
    "dcim.rack_reservations",
    "dcim.power_panels",
    "dcim.power_feeds",
    "dcim.devices",
    "virtualization.virtual_machines",
    "circuits.circuit_terminations",
    "dcim.interfaces",
    "dcim.front_ports",
    "dcim.rear_ports",
    "dcim.console_ports",
    "dcim.console_server_ports",
    "dcim.power_ports",
    "dcim.power_outlets",
    "dcim.device_bays",
    "dcim.module_bays",
    "dcim.inventory_items",
    "virtualization.vminterfaces",
    "ipam.ip_addresses",
    "dcim.cables",
    "dcim.virtual_chassis",
    "ipam.services",
    "ipam.fhrp_groups",
    "ipam.fhrp_group_assignments",
]

_DMCG_CONFIG = GenerateConfig(
    formatters=[Formatter.RUFF_FORMAT, Formatter.RUFF_CHECK],
    output_model_type=DataModelType.PydanticV2BaseModel,
    input_file_type="openapi",
    force_optional_for_required_fields=True,
    allow_extra_fields=False,
)


def _collect_schema_refs(
    fragment: Any, all_definitions: Dict[str, Any], collected: Dict[str, Any]
) -> None:
    """
    Recursively walk *fragment* and collect every $ref target that exists in
    all_definitions into *collected*, including their own transitive deps.
    """
    if isinstance(fragment, dict):
        if "$ref" in fragment:
            ref_name = fragment["$ref"].split("/")[-1]
            if ref_name not in collected and ref_name in all_definitions:
                collected[ref_name] = all_definitions[ref_name]
                _collect_schema_refs(
                    all_definitions[ref_name], all_definitions, collected
                )
        for value in fragment.values():
            _collect_schema_refs(value, all_definitions, collected)
    elif isinstance(fragment, list):
        for item in fragment:
            _collect_schema_refs(item, all_definitions, collected)


class NetboxDesignTasks:

    def get_schema_name(
        self, app: str, object_type: str, schema: dict
    ) -> Optional[str]:
        """Extract the write-model schema name from the OpenAPI spec for a given endpoint."""
        path_spec = schema.get("paths", {}).get(f"/api/{app}/{object_type}/", {})
        schema_ref = (
            path_spec.get("post", {})
            .get("requestBody", {})
            .get("content", {})
            .get("application/json", {})
            .get("schema", {})
        )

        for source in [schema_ref] + schema_ref.get("oneOf", []):
            if "$ref" in source:
                return source["$ref"].split("/")[-1]
            if source.get("type") == "array" and "$ref" in source.get("items", {}):
                return source["items"]["$ref"].split("/")[-1]
        return None

    def _build_entity_model(
        self,
        schema_name: str,
        all_definitions: Dict[str, Any],
        cache: Dict[str, Optional[Type[BaseModel]]],
    ) -> Optional[Type[BaseModel]]:
        """
        Generate a Pydantic model for a single Netbox entity from its OpenAPI
        component schema definition.

        Builds a minimal OpenAPI envelope that contains only the target schema
        plus its transitive $ref dependencies, then passes it to
        generate_dynamic_models so that only the models needed for this one
        entity type are generated.

        Results are stored in *cache* so repeated calls for the same schema
        name are free (generate_dynamic_models also has its own internal LRU
        cache keyed on the schema+config hash).
        """
        if schema_name in cache:
            return cache[schema_name]

        if schema_name not in all_definitions:
            cache[schema_name] = None
            return None

        # Collect the target schema definition and all schemas it references
        # (directly or transitively) so that $ref links resolve correctly.
        deps: Dict[str, Any] = {}
        _collect_schema_refs(all_definitions[schema_name], all_definitions, deps)

        # Minimal OpenAPI envelope: target schema + its deps in components.schemas
        minimal_openapi: Dict[str, Any] = {
            "openapi": "3.0.0",
            "info": {"title": "Netbox", "version": "1.0"},
            "components": {
                "schemas": {
                    schema_name: all_definitions[schema_name],
                    **deps,
                }
            },
        }

        models = generate_dynamic_models(minimal_openapi, config=_DMCG_CONFIG)

        model = models.get(schema_name)
        cache[schema_name] = model
        return model

    def build_design_model(
        self, design_data: dict, openapi_schema: dict
    ) -> Type[BaseModel]:
        """
        Build a nested Pydantic DesignModel that mirrors the design data structure.

        For each entity type present in *design_data* (e.g. ``dcim.manufacturers``)
        a dedicated Pydantic model is generated from its individual OpenAPI component
        schema via ``_build_entity_model``.  Those per-entity models are then
        composed into app-level models and finally into a single ``DesignModel``
        using ``pydantic.create_model``.
        """
        all_definitions: Dict[str, Any] = openapi_schema.get("components", {}).get(
            "schemas", {}
        )
        # per-call cache: avoids re-generating models for schemas that appear
        # in multiple entity types within the same design file
        entity_model_cache: Dict[str, Optional[Type[BaseModel]]] = {}
        app_fields: Dict[str, Any] = {}

        for app_name, app_data in design_data.items():
            if not isinstance(app_data, dict):
                continue

            obj_fields: Dict[str, Any] = {}
            for obj_type, objects in app_data.items():
                if not isinstance(objects, list):
                    continue

                schema_name = self.get_schema_name(
                    app_name, obj_type.replace("_", "-"), openapi_schema
                )
                entity_model = (
                    self._build_entity_model(
                        schema_name, all_definitions, entity_model_cache
                    )
                    if schema_name
                    else None
                )

                if entity_model is not None:
                    obj_fields[obj_type] = (
                        Optional[List[entity_model]],
                        Field(default_factory=list),
                    )
                else:
                    log.debug(
                        f"No OpenAPI schema found for {app_name}.{obj_type} "
                        f"(looked up '{schema_name}') — using untyped dict list"
                    )
                    obj_fields[obj_type] = (
                        Optional[List[Dict[str, Any]]],
                        Field(default_factory=list),
                    )

            if obj_fields:
                app_model = create_model(
                    f"{app_name.capitalize()}Model",
                    __config__=ConfigDict(extra="allow", populate_by_name=True),
                    **obj_fields,
                )
                app_fields[app_name] = (Optional[app_model], None)

        if "create_order" in design_data:
            app_fields["create_order"] = (Optional[List[str]], None)

        return create_model(
            "DesignModel",
            __config__=ConfigDict(extra="allow", populate_by_name=True),
            **app_fields,
        )

    def get_model_by_path(
        self, model: Type[BaseModel], path: tuple
    ) -> Optional[Type[BaseModel]]:
        """
        Navigate a nested Pydantic model structure by a sequence of field names,
        unwrapping Optional/List/Union at each step.
        """
        current = model
        for segment in path:
            if not (isinstance(current, type) and issubclass(current, BaseModel)):
                return None

            field_info = current.model_fields.get(segment)
            if field_info is None:
                return None

            # Unwrap Optional / Union / List layers to find the inner BaseModel
            found = None
            queue = [field_info.annotation]
            while queue:
                t = queue.pop()
                if t is type(None):
                    continue
                origin = getattr(t, "__origin__", None)
                args = getattr(t, "__args__", ())
                if origin is Union or origin is list:
                    queue.extend(args)
                elif isinstance(t, type) and issubclass(t, BaseModel):
                    found = t
                    break

            if found is None:
                return None
            current = found

        return current

    def get_data_item_by_path(self, data: dict, path: tuple) -> tuple:
        """
        Navigate to the data item using the error location path.
        Returns (parent_container, key, current_value).
        """
        current = data
        parent = None
        key = None

        for i, segment in enumerate(path):
            parent = current
            key = segment

            if isinstance(current, dict) and segment in current:
                current = current[segment]
            elif (
                isinstance(current, list)
                and isinstance(segment, int)
                and segment < len(current)
            ):
                current = current[segment]
            else:
                # Can't navigate further, return what we have
                break

        return parent, key, current

    def model_has_slug_field(self, model: Type[BaseModel]) -> bool:
        """Check if the Pydantic model has a 'slug' field."""
        return "slug" in model.model_fields

    def model_has_model_field(self, model: Type[BaseModel]) -> bool:
        """Check if the Pydantic model has a 'model' field."""
        return "model" in model.model_fields

    def _preprocess_design_data(
        self, design_data: dict, design_model: Type[BaseModel]
    ) -> None:
        """
        Walk every entity object in *design_data* and, for any object whose
        Pydantic model declares a ``slug`` field, auto-generate the slug from
        the object's ``name`` value when ``slug`` is absent.

        This runs before the first Pydantic validation pass so that the
        ``missing`` error for required slug fields never needs to be caught.
        """
        for app_name, app_data in design_data.items():
            if not isinstance(app_data, dict):
                continue
            for obj_type, objects in app_data.items():
                if not isinstance(objects, list):
                    continue
                entity_model = self.get_model_by_path(
                    design_model, (app_name, obj_type)
                )
                if entity_model is None or not self.model_has_slug_field(entity_model):
                    continue
                for obj in objects:
                    if "slug" not in obj:
                        if "name" in obj:
                            obj["slug"] = slugify(obj["name"])
                        elif "model" in obj:
                            obj["slug"] = slugify(obj["model"])
                        else:
                            log.error(
                                f"Failed to autogenerate slug for {app_name}.{obj_type}"
                            )

    def mutate_input_data(
        self, error: dict, design_data: dict, netbox_api_model: Type[BaseModel]
    ) -> bool:
        """
        Mutate input data to conform to the Pydantic model based on a validation error.

        Handles ``model_type`` errors where a plain string is supplied for a field
        that expects a nested object — the string is transformed into
        ``{ref_field: value}`` using the best available reference field
        (``name`` → ``slug`` → ``model``, in that priority order).

        Args:
            error: Pydantic validation error dict with 'type', 'loc', 'msg', 'input', 'ctx'
            design_data: The original design data dictionary to mutate in-place
            netbox_api_model: The root Pydantic model for navigation

        Returns:
            True if the data was mutated, False otherwise
        """
        error_type = error.get("type")
        loc = error.get("loc", ())
        input_value = error.get("input")

        if error_type == "model_type":
            # Resolve the Pydantic model for the field that caused the error
            # transform path from ('dcim', 'devices', 9, 'device_type') to ('dcim', 'device_type')
            model_path = (loc[0], loc[3])
            target_model = self.get_model_by_path(netbox_api_model, model_path)
            if not target_model:
                log.warning(
                    f"Could not find model for path {model_path} in netbox_api_model — skipping mutation"
                )
                return False
            # Determine the best reference field and any value transformation
            if self.model_has_model_field(target_model):
                ref_field = "model"
                transform_value = lambda v: v  # noqa
            elif self.model_has_slug_field(target_model):
                ref_field = "slug"
                transform_value = slugify
            elif "name" in target_model.model_fields:
                ref_field = "name"
                transform_value = lambda v: v  # noqa
            else:
                raise ValueError(
                    f"Cannot transform input for model '{target_model}': "
                    f"model does not have 'name', 'slug', or "
                    f"'model' field and input reference '{input_value}' cannot be converted."
                )

            # loc ends with the model class name — strip it to reach the actual value
            path_to_value = loc[:-1]
            parent, key, current_value = self.get_data_item_by_path(
                design_data, path_to_value
            )
            if (
                parent is not None
                and key is not None
                and isinstance(current_value, str)
            ):
                parent[key] = {ref_field: transform_value(current_value)}
                return True

        # handle missing required fields other than slug (slug is pre-filled by _preprocess_design_data)
        if error_type == "missing":
            target_model = self.get_model_by_path(netbox_api_model, loc[:2])
            if not target_model:
                log.warning(
                    f"Could not find model for path {loc[:2]} in netbox_api_model — skipping mutation"
                )
                return False
            path_to_parent = loc[:-1]
            parent, key, current_value = self.get_data_item_by_path(
                design_data, path_to_parent
            )
            missing_field = loc[-1]
            if isinstance(current_value, dict):
                if missing_field == "slug" and "name" in current_value:
                    current_value["slug"] = slugify(current_value["name"])
                    return True
                else:
                    log.error(
                        f"Missing required field '{missing_field}' has no auto-fill rule, path: {loc}"
                    )
            else:
                log.error(
                    f"Input must contain 'name' field, got - {current_value}, path: {loc}"
                )

        return False

    @Task(
        fastapi={"methods": ["POST"], "schema": NetboxFastApiArgs.model_json_schema()}
    )
    def create_design(
        self,
        job,
        design_data: Union[str, dict],
        context: Union[str, dict] = {},
        instance: str = None,
        dry_run: bool = False,
        branch: str = None,
    ) -> Result:
        ret = Result(task=f"{self.name}:design_create", result={})
        nb = self._get_pynetbox(instance or self.default_instance, branch=branch)

        if self.is_url(context):
            context = self.fetch_file(context)
            if context is None:
                raise FileNotFoundError(f"Context file download failed: {context}")
        if isinstance(context, str):
            context = yaml.safe_load(context)

        if self.is_url(design_data):
            design_data = self.jinja2_render_templates(
                templates=[design_data],
                context={"norfab": self.client, "context": context, "netbox": nb},
            )
        if isinstance(design_data, str):
            design_data = yaml.safe_load(design_data)

        if not design_data:
            raise ValueError("No design data provided")

        # build pydantic model out of Netbox OpenAPI schema and validate input data
        netbox_api_model = self.build_design_model(design_data, nb.openapi())

        # Pre-process: auto-fill slug fields derived from name before validation
        self._preprocess_design_data(design_data, netbox_api_model)

        try:
            netbox_api_model.model_validate(design_data)
        except ValidationError as e:
            for error in e.errors():
                self.mutate_input_data(error, design_data, netbox_api_model)

        # push data to Netbox
        import pprint

        pprint.pprint(design_data)
        for entity in design_data.get("create_order", DEFAULT_CREATE_ORDER):
            app, obj_type = entity.split(".")

            if data := design_data.get(app, {}).get(obj_type, []):
                job.event(f"creating {app}.{obj_type}")
                print(f"creating {app}.{obj_type}")
                # identify existing objects to not create them
                new_objects = []
                while data:
                    object_data = data.pop(0)
                    object_filter_data = {
                        k: object_data[k]
                        for k in ["slug", "name", "model"]
                        if k in object_data
                    }
                    nb_object = getattr(getattr(nb, app), obj_type).filter(
                        **object_filter_data
                    )
                    if not nb_object:
                        new_objects.append(object_data)

                # create new objects
                if new_objects:
                    result = getattr(getattr(nb, app), obj_type).create(new_objects)
                    ret.result.setdefault(app, {})[obj_type] = [str(i) for i in result]

        return ret
