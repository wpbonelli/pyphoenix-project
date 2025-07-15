"""
Wrap `xattree` and `attrs` specification utilities for MF6,
including field decorators, converters,  and introspection.
"""

import builtins
import types
from datetime import datetime
from pathlib import Path
from typing import Any, Union, get_args, get_origin

import numpy as np
from attrs import NOTHING, Attribute
from modflow_devtools.dfn import Dfn, Field, FieldType, Reader
from numpy.typing import NDArray
import sparse
from xattree import get_xatspec

from flopy4.adapters import get_nn
from flopy4.mf6.config import SPARSE_THRESHOLD
from flopy4.spec import array as flopy_array
from flopy4.spec import coord as flopy_coord
from flopy4.spec import dim as flopy_dim
from flopy4.spec import field as flopy_field
from flopy4.spec import fields_dict as flopy_fields_dict


def field(
    default=NOTHING,
    validator=None,
    converter=None,
    repr=True,
    eq=True,
    init=True,
    metadata=None,
    on_setattr=None,
    block: str | None = None,
):
    """Define a field."""
    if block:
        metadata = metadata or {}
        metadata["block"] = block
        metadata["reader"] = "urword"
    return flopy_field(
        default=default,
        validator=validator,
        converter=converter,
        repr=repr,
        eq=eq,
        init=init,
        on_setattr=on_setattr,
        metadata=metadata,
    )


def dim(
    scope=None,
    coord: bool | str = True,
    default=NOTHING,
    repr=True,
    eq=True,
    init=True,
    metadata=None,
    group=None,
    block: str | None = None,
):
    """Define a dimension field."""
    if block:
        metadata = metadata or {}
        metadata["block"] = block
        metadata["reader"] = "urword"
    return flopy_dim(
        scope=scope,
        coord=coord,
        default=default,
        repr=repr,
        eq=eq,
        init=init,
        metadata=metadata,
        group=group,
    )


def coord(
    scope=None,
    default=NOTHING,
    repr=True,
    eq=True,
    metadata=None,
    block: str | None = None,
):
    """Define a coordinate field."""
    if block:
        metadata = metadata or {}
        metadata["block"] = block
        metadata["reader"] = "readarray"
    return flopy_coord(
        scope=scope,
        default=default,
        repr=repr,
        eq=eq,
        metadata=metadata,
    )


def array(
    cls=None,
    dims=None,
    default=NOTHING,
    validator=None,
    converter=None,
    repr=True,
    eq=None,
    metadata=None,
    on_setattr=None,
    block: str | None = None,
    reader: Reader = "readarray",
):
    """Define an array field."""
    if block:
        metadata = metadata or {}
        metadata["block"] = block
        metadata["reader"] = reader
    return flopy_array(
        cls=cls,
        dims=dims,
        default=default,
        validator=validator,
        converter=converter,
        repr=repr,
        eq=eq,
        on_setattr=on_setattr,
        metadata=metadata,
    )


Block = dict[str, Attribute]


def block_sort_key(item: tuple[str, dict]) -> int:
    k, _ = item
    if k == "options":
        return 0
    elif k == "dimensions":
        return 1
    elif k == "griddata":
        return 2
    elif k == "packagedata":
        return 3
    elif "period" in k:
        # some packages have block "period", some have "perioddata"
        return 4
    else:
        return 5


def blocks(cls) -> list[list[Attribute]]:
    """Return an ordered list of blocks for a component class."""
    return [list(v.values()) for v in blocks_dict(cls).values()]


def blocks_dict(cls) -> dict[str, Block]:
    """
    Return an ordered dictionary of blocks for a component class,
    whose keys are block names. Each block is a map from variable
    (field) name to `attrs.Attribute`.
    """
    fields = fields_dict(cls)
    blocks: dict[str, Block] = {}
    for k, v in fields.items():
        block = v.metadata["block"]
        if block not in blocks:
            blocks[block] = {}
        blocks[block][k] = v
    return dict(sorted(blocks.items(), key=block_sort_key))


def fields(cls) -> list[Attribute]:
    """Return an ordered list of fields for a component class."""
    return list(fields_dict(cls).values())


def fields_dict(cls) -> dict[str, Attribute]:
    """
    Return an ordered dictionary of fields for a component class,
    whose keys are field names. Each field is an `attrs.Attribute`.
    """
    fields = flopy_fields_dict(cls)
    return {k: v for k, v in fields.items() if "block" in v.metadata}


def to_dfn_field_type(t: type) -> FieldType:
    match t:
        case builtins.str | np.str_:
            return "string"
        case builtins.bool | np.bool:
            return "keyword"
        case builtins.int | np.integer:
            return "integer"  # type: ignore
        case builtins.float | np.floating:
            return "double precision"  # type: ignore
        case t if t is Path or t is datetime:
            return "string"
        case t if get_origin(t) in (Union, types.UnionType):
            args = get_args(t)
            if args[-1] is types.NoneType:
                match args[0]:
                    case builtins.str | np.str_:
                        return "string"
                    case builtins.bool | np.bool:
                        return "keyword"
                    case builtins.int | np.integer:
                        return "integer"
                    case builtins.float | np.floating:
                        return "double precision"
                    case tt if tt is Path or tt is datetime:
                        return "string"
                    case _:
                        return "record"
            return "keystring"
        case _:
            return "record"


def get_dfn_field_type(attribute: Attribute) -> FieldType:
    """
    Get a `xattree` field's type as defined by the MODFLOW 6 input
    definition language:
    https://modflow6.readthedocs.io/en/stable/_dev/dfn.html#variable-types

    The type of the field is determined from `xattree` metadata.
    """
    if (xatmeta := attribute.metadata.get("xattree", None)) is None:
        raise ValueError(f"Attribute {attribute.name} in {attribute.name} has no xattree metadata.")
    kind = xatmeta["kind"]
    match kind:
        case "child":
            raise ValueError(f"Top-level field should not be a child: {attribute.name}")
        case "array":
            return "recarray"
        case "coord":
            return "recarray"
        case "dim":
            return "integer"
        case "attr":
            if (t := attribute.type) is None:
                raise ValueError(f"Attribute {attribute.name} in {attribute.name} has no type.")
            return to_dfn_field_type(t)
    raise ValueError(f"Could not map {attribute.name} to a valid MF6 type.")


def to_dfn_field(attribute: Attribute) -> Field:
    """
    Convert a `xattree` field specification to a field as defined by the
    MODFLOW 6 input definition language:
    https://modflow6.readthedocs.io/en/stable/_dev/dfn.html#variable-types.
    """
    if (xatmeta := attribute.metadata.get("xattree", None)) is None:
        raise ValueError(f"Attribute {attribute.name} in {attribute.name} has no xattree metadata.")
    return Field(
        name=attribute.name,
        type=get_dfn_field_type(attribute),
        shape=xatmeta.get("dims", None),
        block=attribute.metadata.get("block", None),
        default=attribute.default,
        children={k: to_dfn_field(v) for k, v in fields_dict(attribute.type)}  # type: ignore
        if attribute.metadata.get("kind", None) == "child"  # type: ignore
        else None,  # type: ignore
        reader=attribute.metadata.get("reader", "urword"),
    )


def get_blocks(dfn: Dfn) -> dict[str, Block]:
    """
    Get blocks from an MF6 input definition. Anything not an
    explicitly defined key in the `Dfn` typed dict is a block.
    """
    return dict(
        sorted(
            {k: v for k, v in dfn.items() if k not in Dfn.__annotations__}.items(),
            key=block_sort_key,
        )
    )


def is_list_field(field: Field) -> bool:
    """
    Check if a field is a list field, which is a recarray
    field that uses list input. This is determined by the
    reader being "readarray" and the type being "recarray".
    """
    return field["type"] == "recarray" and field["reader"] != "readarray"


def is_list_block(block: Block) -> bool:
    return (
        len(block) == 1
        and (field := next(iter(block.values()))).metadata.get("type") == "recarray"
        and field.metadata.get("reader") != "readarray"
    ) or (
        all(
            f.metadata.get("type") == "recarray" and f.metadata.get("reader") != "readarray"
            for f in block.values()
        )
    )


def dict_to_array(value, self_, field) -> NDArray:
    """
    Convert a sparse dictionary representation of an array to a
    dense numpy array or a sparse COO array.

    # TODO: this should move to transformation step in reader?
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
                fill_value=field.default or np.nan,
            )
    else:
        a = np.full(shape, np.nan, dtype=field.dtype)  # type: ignore

        def set_(arr, val, *ind):
            arr[ind] = val

        def final(arr):
            arr[np.isnan(arr)] = field.default or np.nan
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
