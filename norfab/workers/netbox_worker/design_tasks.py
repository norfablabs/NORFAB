import re
import yaml

from typing import Any, Union, List, Optional, Dict, Type, Literal
from norfab.core.worker import Task
from norfab.models import Result
from norfab.models.netbox import NetboxFastApiArgs
from pydantic import BaseModel, Field, create_model, ConfigDict, ValidationError

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

DEFAULT_REF_FIELD = "name"

RESERVED_PYDANTIC_NAMES = {
    "model_config",
    "model_fields",
    "model_computed_fields",
    "model_extra",
    "model_fields_set",
    "model_construct",
    "model_copy",
    "model_dump",
    "model_dump_json",
    "model_json_schema",
    "model_parametrized_name",
    "model_post_init",
    "model_rebuild",
    "model_validate",
    "model_validate_json",
    "model_validate_strings",
}

TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


class NetboxDesignTasks:

    def get_schema_name(
        self, app: str, object_type: str, schema: dict
    ) -> Optional[str]:
        """Extract schema name from OpenAPI spec for given endpoint."""
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

    def resolve_type(
        self, field_schema: dict, definitions: dict, cache: dict, hint: str = None
    ) -> type:
        """Convert OpenAPI field schema to Python type."""
        # Handle $ref
        if "$ref" in field_schema:
            ref_name = field_schema["$ref"].split("/")[-1]
            if ref_schema := definitions.get(ref_name):
                return self.build_model(ref_name, ref_schema, definitions, cache)
            return Any

        # Merge allOf schemas
        if "allOf" in field_schema:
            merged, ref_hint = {}, hint
            for sub in field_schema["allOf"]:
                if "$ref" in sub:
                    ref_hint = sub["$ref"].split("/")[-1]
                    sub = definitions.get(ref_hint, {})
                merged.update(sub)
            field_schema, hint = merged, ref_hint or hint

        # Handle anyOf/oneOf as Union
        if options := field_schema.get("anyOf") or field_schema.get("oneOf"):
            types = list(
                {self.resolve_type(o, definitions, cache, hint) for o in options}
            )
            return (
                types[0] if len(types) == 1 else Union[tuple(types)] if types else Any
            )

        nullable = field_schema.get("nullable", False)
        schema_type = field_schema.get("type")

        # Handle enum with Literal
        if enum_vals := field_schema.get("enum"):
            py_type = (
                Literal[tuple(enum_vals)]
                if len(enum_vals) <= 10
                else (str if all(isinstance(v, str) for v in enum_vals) else Any)
            )
            return Optional[py_type] if nullable else py_type

        py_type = TYPE_MAP.get(schema_type, Any)

        # Handle array items
        if schema_type == "array" and "items" in field_schema:
            py_type = List[
                self.resolve_type(
                    field_schema["items"],
                    definitions,
                    cache,
                    f"{hint}Item" if hint else None,
                )
            ]

        # Handle nested object
        if schema_type == "object" and "properties" in field_schema:
            py_type = self.build_model(
                hint or f"Inline_{id(field_schema)}", field_schema, definitions, cache
            )

        return Optional[py_type] if nullable else py_type

    def build_model(
        self, name: str, schema_def: dict, definitions: dict, cache: dict = None
    ) -> Type[BaseModel]:
        """Build Pydantic model from OpenAPI schema definition."""
        cache = cache if cache is not None else {}
        if name in cache and cache[name]:
            return cache[name]
        cache[name] = None  # Placeholder for recursion

        required = set(schema_def.get("required", []))
        fields = {}

        for fname, fschema in schema_def.get("properties", {}).items():
            py_type = self.resolve_type(
                fschema, definitions, cache, f"{name}_{fname.capitalize()}"
            )
            # is_required = fname in required and not fschema.get("nullable", False)

            # Build field kwargs
            kwargs = {}
            if fname in RESERVED_PYDANTIC_NAMES:
                kwargs["alias"] = fname
                fname = f"{fname}_"

            # Add constraints
            if fschema.get("type") == "string":
                for k, v in [
                    ("minLength", "min_length"),
                    ("maxLength", "max_length"),
                    ("pattern", "pattern"),
                ]:
                    if k in fschema:
                        kwargs[v] = fschema[k]
            elif fschema.get("type") in ("integer", "number"):
                for k, v in [("minimum", "ge"), ("maximum", "le")]:
                    if k in fschema:
                        kwargs[v] = fschema[k]

            # default = ... if is_required else None
            default = None
            fields[fname] = (
                (py_type, Field(default=default, **kwargs))
                if kwargs
                else (py_type, default)
            )

        model = create_model(
            name, __config__=ConfigDict(extra="allow", populate_by_name=True), **fields
        )
        cache[name] = model
        return model

    def build_design_model(self, design_data: dict, schema: dict) -> Type[BaseModel]:
        """Build complete nested Pydantic model for design data structure."""
        definitions = schema.get("components", {}).get("schemas", {})
        cache = {}
        app_fields = {}

        for app_name, app_data in design_data.items():
            if not isinstance(app_data, dict):
                continue

            obj_fields = {}
            for obj_type, objects in app_data.items():
                if not isinstance(objects, list):
                    continue

                schema_name = self.get_schema_name(
                    app_name, obj_type.replace("_", "-"), schema
                )
                if schema_name and schema_name in definitions:
                    entity_model = self.build_model(
                        schema_name, definitions[schema_name], definitions, cache
                    )
                    obj_fields[obj_type] = (
                        Optional[List[entity_model]],
                        Field(default_factory=list),
                    )
                else:
                    obj_fields[obj_type] = (
                        Optional[List[Dict[str, Any]]],
                        Field(default_factory=list),
                    )

            if obj_fields:
                app_fields[app_name] = (
                    Optional[
                        create_model(f"{app_name.capitalize()}Model", **obj_fields)
                    ],
                    None,
                )

        if "create_order" in design_data:
            app_fields["create_order"] = (Optional[List[str]], None)

        return create_model("DesignModel", **app_fields)

    def get_model_by_name(
        self, model: Type[BaseModel], model_name: str
    ) -> Optional[Type[BaseModel]]:
        """
        Recursively search for a Pydantic model by name within a nested model structure.
        """
        if model.__name__ == model_name:
            return model

        for field_name, field_info in model.model_fields.items():
            field_type = field_info.annotation

            # Unwrap Optional, List, Union types
            origin = getattr(field_type, "__origin__", None)
            args = getattr(field_type, "__args__", ())

            types_to_check = []
            if origin is Union:
                types_to_check.extend(args)
            elif origin is list:
                types_to_check.extend(args)
            else:
                types_to_check.append(field_type)

            for t in types_to_check:
                if t is type(None):
                    continue
                # Check if it's a Pydantic model
                if isinstance(t, type) and issubclass(t, BaseModel):
                    if t.__name__ == model_name:
                        return t
                    # Recurse into nested models
                    found = self.get_model_by_name(t, model_name)
                    if found:
                        return found
                # Handle nested generics (e.g., List[SomeModel])
                nested_origin = getattr(t, "__origin__", None)
                nested_args = getattr(t, "__args__", ())
                if nested_origin is list:
                    for nested_t in nested_args:
                        if isinstance(nested_t, type) and issubclass(
                            nested_t, BaseModel
                        ):
                            if nested_t.__name__ == model_name:
                                return nested_t
                            found = self.get_model_by_name(nested_t, model_name)
                            if found:
                                return found
        return None

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

    def slugify(self, value: str) -> str:
        """Convert a string to a slug format (lowercase, hyphens instead of spaces/underscores)."""
        # Convert to lowercase
        slug = value.lower().strip()
        # Replace spaces and underscores with hyphens
        slug = re.sub(r"[\s_]+", "-", slug)
        # Remove any characters that aren't alphanumeric or hyphens
        slug = re.sub(r"[^a-z0-9\-]", "", slug)
        # Remove consecutive hyphens
        slug = re.sub(r"-+", "-", slug)
        # Strip leading/trailing hyphens
        slug = slug.strip("-")
        return slug

    def mutate_input_data(
        self, error: dict, design_data: dict, netbox_api_model: Type[BaseModel]
    ) -> bool:
        """
        Mutate input data to conform to the Pydantic model based on validation error.

        Args:
            error: Pydantic validation error dict with 'type', 'loc', 'msg', 'input', 'ctx'
            design_data: The original design data dictionary to mutate
            netbox_api_model: The root Pydantic model for validation

        Returns:
            True if mutation was successful, False otherwise

        Raises:
            ValueError: If the model expects an integer but input is a string without DEFAULT_REF_FIELD
        """
        error_type = error.get("type")
        loc = error.get("loc", ())
        input_value = error.get("input")
        ctx = error.get("ctx", {})

        # Only handle model_type errors (where a dict/model is expected but got a simple value)
        if error_type != "model_type":
            return False

        class_name = ctx.get("class_name")
        if not class_name:
            return False

        # Get the target Pydantic model from the netbox_api_model
        target_model = self.get_model_by_name(netbox_api_model, class_name)
        if not target_model:
            raise ValueError(f"Could not find model '{class_name}' in netbox_api_model")

        # Check if the model has the DEFAULT_REF_FIELD
        if DEFAULT_REF_FIELD in model.model_fields:
            ref_field = DEFAULT_REF_FIELD
            transform_value = lambda v: v  # no transformation needed for name
        elif self.model_has_slug_field(target_model):
            ref_field = "slug"
            transform_value = self.slugify
        elif self.model_has_model_field(target_model):
            ref_field = "model"
            transform_value = lambda v: v  # no transformation needed for model
        else:
            ref_field = None
            transform_value = None

        if ref_field is not None:
            # The loc path includes the model name at the end, we need the parent
            path_without_model = loc[:-1]
            # Navigate to the parent container and the key to mutate
            parent, key, current_value = self.get_data_item_by_path(
                design_data, path_without_model
            )
            if parent is not None and key is not None:
                # Transform simple value to dict with ref_field
                if isinstance(current_value, str):
                    parent[key] = {ref_field: transform_value(current_value)}
                    return True
        else:
            raise ValueError(
                f"Cannot transform input for model '{class_name}': "
                f"model does not have '{DEFAULT_REF_FIELD}', 'slug', or 'model' field and input '{input_value}' cannot be converted."
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
        try:
            netbox_api_model.model_validate(design_data)
        except ValidationError as e:
            # attempt to mutate input data based on errors to be in compliance with Netbox API
            for error in e.errors():
                self.mutate_input_data(error, design_data, netbox_api_model)
            netbox_api_model.model_validate(design_data)

        # push data to Netbox
        for entity in design_data.get("create_order", DEFAULT_CREATE_ORDER):
            app, obj_type = entity.split(".")

            if data := design_data.get(app, {}).get(obj_type, []):
                # deduplicate objects
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
