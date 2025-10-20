from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import sparse
import xarray as xr
import xattree
from cattrs import Converter
from modflow_devtools.dfn import block_sort_key
from numpy.typing import NDArray
from xattree import get_xatspec

from flopy4.adapters import get_nn
from flopy4.mf6.binding import Binding
from flopy4.mf6.component import Component, _try_get_structured_grid_dims
from flopy4.mf6.config import SPARSE_THRESHOLD
from flopy4.mf6.constants import FILL_DNODATA, PERIOD
from flopy4.mf6.context import Context
from flopy4.mf6.spec import fields_dict


def path_to_tuple(name: str, value: Path) -> tuple[str, str, str]:
    if name.endswith("_file"):
        base_name = name.replace("_file", "").upper()
        return (base_name, "FILEOUT", str(value))
    return (name.upper(), "FILEOUT", str(value))


def get_binding_blocks(value: Component) -> dict[str, dict[str, list[tuple[str, ...]]]]:
    if not isinstance(value, Context):
        return {}

    blocks = {}  # type: ignore
    xatspec = xattree.get_xatspec(type(value))

    for child_name, child_spec in xatspec.children.items():
        if (child := getattr(value, child_name, None)) is None:
            continue
        if (block_name := child_spec.metadata["block"]) not in blocks:  # type: ignore
            blocks[block_name] = {}
        match child:
            case Component():
                blocks[block_name][child_name] = [Binding.from_component(child).to_tuple()]
            case Mapping():
                blocks[block_name][child_name] = [
                    Binding.from_component(comp).to_tuple()
                    for comp in child.values()
                    if comp is not None
                ]
            case Iterable():
                blocks[block_name][child_name] = [
                    Binding.from_component(comp).to_tuple() for comp in child if comp is not None
                ]
            case _:
                raise ValueError(f"Unexpected child type: {type(child)}")

    return blocks


def has_structured_grid_dims(value: xr.DataArray | xr.Dataset) -> bool:
    """
    Check if the DataArray has structured grid dimensions: 'nlay', 'nrow', and 'ncol'.
    """
    return all(dim in value.dims for dim in ["nlay", "nrow", "ncol"])


def has_grid_dims(value: xr.DataArray | xr.Dataset) -> bool:
    """
    Check if the DataArray has spatial dimensions: 'nodes' and/or 'nlay', 'nrow', and 'ncol'.
    """
    return "nodes" in value.dims or has_structured_grid_dims(value)


def has_tdis_dims(value: xr.DataArray | xr.Dataset) -> bool:
    """
    Check if the DataArray has a time dimensions 'nper'.
    """
    return "nper" in value.dims


def _hack_structured_grid_dims(value: xr.DataArray, structured_grid_dims: Mapping):
    """
    Temporary hack to convert flat nodes dimension to 3d structured dims.
    long term solution for this is to use a custom xarray index. filters
    should then have access to all dimensions needed.
    """

    if "nper" in (old_dims := set(value.dims).copy()):
        old_dims.remove("nper")
        shape: tuple[int, ...] = (
            value.sizes["nper"],
            structured_grid_dims["nlay"],
            structured_grid_dims["nrow"],
            structured_grid_dims["ncol"],
        )
        dims: tuple[str, ...] = ("nper", "nlay", "nrow", "ncol")
        coords = {
            "nper": value.coords["nper"],
            "nlay": range(structured_grid_dims["nlay"]),
            "nrow": range(structured_grid_dims["nrow"]),
            "ncol": range(structured_grid_dims["ncol"]),
        }
    else:
        shape = (
            structured_grid_dims["nlay"],
            structured_grid_dims["nrow"],
            structured_grid_dims["ncol"],
        )
        dims = ("nlay", "nrow", "ncol")
        coords = {
            "nlay": range(structured_grid_dims["nlay"]),
            "nrow": range(structured_grid_dims["nrow"]),
            "ncol": range(structured_grid_dims["ncol"]),
        }

    if old_dims == {"nodes"}:
        value = xr.DataArray(
            value.data.reshape(shape),
            dims=dims,
            coords=coords,
        )

    return value


def unstructure_field(
    name: str,
    value: Any,
    # TODO: temporary, remove not needed
    structured_grid_dims: Mapping | None,
) -> tuple[str, Any]:
    """
    Convert:

      - bools to keywords (since they should only be written if true)
      - paths to records with 'FILEIN/OUT' keywords etc
      - datetimes to ISO format
      - 'auxiliary' arrays to tuples since they are written inline
      - period block arrays to dictionaries of kper-sliced arrays

    All other values are left as is.

    Parameters
    ----------
    name : str
        The name of the field
    value : Any
        The value of the field

    Returns
    -------
        A tuple of (name, value) since the name might be
        modified (e.g. '_file' suffix removed for paths)
    """

    match value:
        case None:
            return name, None
        case bool():
            return name, (value if value else None)
        case Path():
            rec = path_to_tuple(name, value)
            name = rec[0]  # '_file' suffix may have been dropped
            return name, rec
        case datetime():
            return name, value.isoformat()
        case xr.DataArray():
            if name == "auxiliary":
                return name, tuple(value.values.tolist())
            if has_grid_dims(value):
                if structured_grid_dims is None:
                    raise ValueError("Need structured grid dimension sizes")
                value = _hack_structured_grid_dims(value, structured_grid_dims=structured_grid_dims)
            # if has_tdis_dims(value) and name not in ["perlen", "nstp", "tsmult"]:
            #     # slice by stress period
            #     value = {kper: value.isel(nper=kper) for kper in range(value.sizes["nper"])}
            return name, value
        case _:
            return name, value


def unstructure_block(
    block: dict[str, Any],
    # TODO: temporary, remove not needed
    structured_grid_dims: Mapping | None,
) -> dict[str, Any]:
    """Unstructure a block of data, converting fields to a suitable format."""
    fields = [
        unstructure_field(
            name=field_name,
            value=block.get(field_name, None),
            structured_grid_dims=structured_grid_dims,
        )
        for field_name in block.keys()
    ]
    return {k: v for k, v in fields if v is not None}


def try_combine_table_data(
    block: dict[str, xr.DataArray], cls: type[Component]
) -> dict[str, xr.Dataset | dict[str, xr.Dataset]]:
    field_spec = fields_dict(cls)
    table_names = [field_spec[n].get("table", None) for n in block.keys()]
    if not any(table_names):
        return block

    table_name = table_names[0]
    if not all(table_name == n for n in table_names):
        raise ValueError("All arrays in the same block must share the same table specification")

    ds = xr.Dataset(block)

    if has_tdis_dims(ds) and cls.__name__.lower() != "tdis":  # dirty hack, do better
        # slice by stress period
        return {table_name: {kper: ds.isel(nper=kper) for kper in range(ds.sizes["nper"])}}

    return {table_name: ds}


def unstructure_period_data(block: dict[str, xr.Dataset]) -> dict[str, dict[str, Any]]:
    """Partition period data by stress period"""
    arrays = {}  # type: ignore
    blocks = {}  # type: ignore
    period = PERIOD.upper()

    for arr_name, periods in block.items():
        for kper, arr in periods.items():
            if kper not in arrays:
                arrays[kper] = {}
            arrays[kper][arr_name] = arr

    for kper, data in periods.items():
        blocks[f"{period} {kper + 1}"] = data

    return blocks


def unstructure_component(value: Component) -> dict[str, Any]:
    """Unstructure a Component."""
    dfn = value.dfn
    cls = type(value)
    data = value.to_dict(blocks=True)
    blocks: dict[str, dict[str, Any]] = {}
    blocks.update(binding_blocks := get_binding_blocks(value))
    blocks.update(
        {
            block_name: unstructure_block(
                data[block_name], structured_grid_dims=_try_get_structured_grid_dims(value)
            )
            for block_name in dfn.blocks.keys()
            if block_name not in binding_blocks
        }
    )
    blocks = {k: try_combine_table_data(v, cls) for k, v in blocks.items()}
    if period_block := blocks.pop(PERIOD, None):
        blocks.update(unstructure_period_data(period_block))

    # total temporary hack! manually set solutiongroup 1.
    # TODO support multiple solution groups
    if "solutiongroup" in blocks:
        sg = blocks["solutiongroup"]
        blocks["solutiongroup 1"] = sg
        del blocks["solutiongroup"]

    return dict(sorted(blocks.items(), key=block_sort_key))


def make_component_converter() -> Converter:
    converter = Converter()
    converter.register_unstructure_hook_factory(xattree.has, lambda _: xattree.asdict)
    converter.register_unstructure_hook(Component, unstructure_component)
    return converter


COMPONENT_CONVERTER = make_component_converter()


def dict_to_array(value, self_, field) -> NDArray:
    """
    Convert a sparse dictionary representation of an array to a
    dense numpy array or a sparse COO array.

    TODO: generalize this not only to dictionaries but to any
    form that can be converted to an array (e.g. nested list)
    """

    if not isinstance(value, dict):
        # if not a dict, assume it's a numpy array
        # and let xarray deal with it if it isn't
        return value

    spec = get_xatspec(type(self_)).flat
    field = spec[field.name]
    if not field.dims:
        raise ValueError(f"Field {field} missing dims")

    # resolve dims
    explicit_dims = self_.__dict__.get("dims", {})
    inherited_dims = dict(self_.parent.data.dims) if self_.parent else {}
    dims = inherited_dims | explicit_dims
    shape = [dims.get(d, d) for d in field.dims]
    unresolved = [d for d in shape if isinstance(d, str)]
    if any(unresolved):
        raise ValueError(f"Couldn't resolve dims: {unresolved}")

    if np.prod(shape) > SPARSE_THRESHOLD:
        a: dict[tuple[Any, ...], Any] = dict()

        def set_(arr, val, *ind):
            arr[tuple(ind)] = val

        def final(arr):
            coords = np.array(list(map(list, zip(*arr.keys()))))
            return sparse.COO(
                coords,
                list(arr.values()),
                shape=shape,
                fill_value=field.default or FILL_DNODATA,
            )
    else:
        a = np.full(shape, FILL_DNODATA, dtype=field.dtype)  # type: ignore

        def set_(arr, val, *ind):
            arr[ind] = val

        def final(arr):
            arr[arr == FILL_DNODATA] = field.default or FILL_DNODATA
            return arr

    if "nper" in dims:
        for kper, period in value.items():
            if kper == "*":
                kper = 0
            match len(shape):
                case 1:
                    set_(a, period, kper)
                case _:
                    for cellid, v in period.items():
                        nn = get_nn(cellid, **dims)
                        set_(a, v, kper, nn)
            if kper == "*":
                break
    else:
        for cellid, v in value.items():
            nn = get_nn(cellid, **dims)
            set_(a, v, nn)

    return final(a)


def structure(data: dict[str, Any], path: Path) -> Component:
    component = COMPONENT_CONVERTER.structure(data, Component)
    if isinstance(component, Context):
        component.workspace = path.parent
    component.filename = path.name
    return component


def unstructure(component: Component) -> dict[str, Any]:
    return COMPONENT_CONVERTER.unstructure(component)
