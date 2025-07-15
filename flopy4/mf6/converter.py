from datetime import datetime
from pathlib import Path
from typing import Any

import attrs
import numpy as np
import xarray as xr
import xattree
from attrs import define
from cattrs import Converter

from flopy4.mf6.component import Component
from flopy4.mf6.context import Context
from flopy4.mf6.exchange import Exchange
from flopy4.mf6.model import Model
from flopy4.mf6.package import Package
from flopy4.mf6.spec import get_blocks


@define
class _Binding:
    """
    An MF6 component binding: a record representation of the
    component for writing to a parent component's name file.
    """

    type: str
    fname: str
    terms: tuple[str, ...] | None = None

    def to_tuple(self):
        return (
            (self.type, self.fname, self.terms)
            if (self.terms and any(self.terms))
            else (self.type, self.fname)
        )

    @classmethod
    def from_component(cls, component: Component) -> "_Binding":
        def _get_binding_type(component: Component) -> str:
            cls_name = component.__class__.__name__
            if isinstance(component, Exchange):
                return f"{'-'.join([cls_name[:2], cls_name[3:]]).upper()}6"
            else:
                return f"{cls_name.upper()}6"

        def _get_binding_terms(component: Component) -> tuple[str, ...] | None:
            if isinstance(component, Exchange):
                return (component.exgmnamea, component.exgmnameb)
            elif isinstance(component, (Model, Package)):
                return (component.name,)  # type: ignore
            # TODO solutions
            return None

        return cls(
            type=_get_binding_type(component),
            fname=component.filename,
            terms=_get_binding_terms(component),
        )


def _path_to_record(field_name: str, path_value: Path) -> tuple:
    if field_name.endswith("_file"):
        base_name = field_name.replace("_file", "").upper()
        return (base_name, "FILEOUT", str(path_value))
    return (field_name.upper(), "FILEOUT", str(path_value))


def unstructure_component(value: Component) -> dict[str, Any]:
    data = xattree.asdict(value)
    blockspec = get_blocks(value.dfn)
    blocks: dict[str, dict[str, Any]] = {}
    xatspec = xattree.get_xatspec(type(value))

    for block_name, block in blockspec.items():
        is_period_block = "period" in block_name.lower()
        if not is_period_block:
            blocks[block_name] = {}
        period_data = {}
        period_blocks = {}

        for field_name in block.keys():
            field_value = data[field_name]

            # children to bindings
            if isinstance(value, Context):
                if field_name not in xatspec.children:
                    continue
                if isinstance(field_value, Component):
                    components = [_Binding.from_component(field_value).to_tuple()]
                elif isinstance(field_value, dict):
                    components = [
                        _Binding.from_component(comp).to_tuple() for comp in field_value.values()
                    ]
                elif isinstance(field_value, (list, tuple)):
                    components = [_Binding.from_component(comp).to_tuple() for comp in field_value]
                blocks[block_name][field_name] = components

            # paths to records
            elif isinstance(field_value, Path) and field_value is not None:
                blocks[block_name][field_name] = _path_to_record(field_name, field_value)

            # datetimes to strings
            elif isinstance(field_value, datetime) and field_value is not None:
                blocks[block_name][field_name] = field_value.isoformat()

            # aux vars to a tuple
            elif (
                field_name == "auxiliary"
                and hasattr(field_value, "values")
                and field_value is not None
            ):
                blocks[block_name][field_name] = tuple(field_value.values.tolist())

            # pre-slice period block arrays
            elif (
                isinstance(field_value, xr.DataArray)
                and "nper" in field_value.dims
            ):
                period_data[field_name] = {
                    kper: field_value.isel(nper=kper) for kper in range(field_value.sizes["nper"])
                }
            
            else:
                if field_value is not None:
                    blocks[block_name][field_name] = field_value

        # make period blocks
        for arr_name, period_data in period_data.items():
            for kper, arr in period_data.items():
                if kper not in period_blocks:
                    period_blocks[kper] = {}
                period_blocks[kper][arr_name] = arr
        # attach period blocks as datasets
        for kper, block in period_blocks.items():
            blocks[f"{block_name} {kper + 1}"] = {block_name: xr.Dataset(block)}

    return blocks


def make_converter() -> Converter:
    converter = Converter()
    # converter.register_unstructure_hook_factory(attrs.has, attrs.astuple),
    converter.register_unstructure_hook_factory(xattree.has, lambda _: xattree.asdict)
    # TODO: make `unstructure_component` pluggable as a public API, so it
    # can be used to inject custom preserialization logic for components,
    # like what we are doing above for component parent/child bindings...
    converter.register_unstructure_hook(Component, unstructure_component)
    return converter


COMPONENT_CONVERTER = make_converter()
