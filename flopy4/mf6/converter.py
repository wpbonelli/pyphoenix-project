from datetime import datetime
from pathlib import Path
from typing import Any

import attrs
import xattree
from cattrs import Converter

from flopy4.mf6.component import Component
from flopy4.mf6.context import Context
from flopy4.mf6.spec import get_blocks


def _with6(component) -> str:
    class_name = component.__class__.__name__
    return f"{class_name.upper()}6"


@attrs.define
class ComponentBinding:
    ftype: str
    fname: str
    mname: str | None = None

    def to_tuple(self):
        return (self.ftype, self.fname, self.mname) if self.mname else (self.ftype, self.fname)

    @classmethod
    def from_component(cls, name: str | None, component) -> "ComponentBinding":
        ftype = component.mf6_type if hasattr(component, "mf6_type") else _with6(component)
        fname = component.filename or component.default_filename()
        return cls(ftype=ftype, fname=fname, mname=name)


def _to_bindings(field_name: str, components):
    if not components:
        return []

    needs_name = field_name in ["models", "solutions"]
    if isinstance(components, dict):
        return [
            ComponentBinding.from_component(name if needs_name else None, comp).to_tuple()
            for name, comp in components.items()
        ]
    elif isinstance(components, list):
        return [ComponentBinding.from_component(None, comp).to_tuple() for comp in components]
    else:
        return [ComponentBinding.from_component(None, components).to_tuple()]


def _path_to_record(field_name: str, path_value: Path) -> tuple:
    if field_name.endswith("_file"):
        base_name = field_name.replace("_file", "").upper()
        return (base_name, "FILEOUT", str(path_value))
    return (field_name.upper(), "FILEOUT", str(path_value))


def unstructure_component(value: Component) -> dict[str, Any]:
    data = xattree.asdict(value)
    blockspec = get_blocks(value.dfn)
    blocks: dict[str, dict[str, Any]] = {}
    for block_name, block in blockspec.items():
        blocks[block_name] = {}
        for field_name in block.keys():
            field_value = data[field_name]

            # transform child components to bindings
            if isinstance(value, Context):
                if field_value is not None and hasattr(field_value, "__class__"):
                    if (
                        hasattr(field_value, "filename")
                        or isinstance(field_value, (dict, list))
                        and field_value
                    ):
                        field_value = _to_bindings(field_name, field_value)

            # transform paths to records
            elif isinstance(field_value, Path) and field_value is not None:
                field_value = _path_to_record(field_name, field_value)

            # transform datetimes to strings
            elif isinstance(field_value, datetime) and field_value is not None:
                field_value = field_value.isoformat()

            # transform auxiliary variables to tuple
            elif (
                field_name == "auxiliary"
                and hasattr(field_value, "values")
                and field_value is not None
            ):
                field_value = tuple(field_value.values.tolist())

            blocks[block_name][field_name] = field_value
    return blocks


def _make_converter() -> Converter:
    converter = Converter()
    converter.register_unstructure_hook_factory(xattree.has, lambda _: xattree.asdict)
    converter.register_unstructure_hook(Component, unstructure_component)
    return converter


COMPONENT_CONVERTER = _make_converter()
