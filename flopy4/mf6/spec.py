"""
Wrap `xattree` and `attrs` specification utilities for MF6.
These include field decorators and introspection functions.
"""

import builtins
import types
from datetime import datetime
from functools import singledispatch
from pathlib import Path
from typing import Literal, Union, get_args, get_origin

import numpy as np
from attrs import NOTHING, Attribute
from modflow_devtools.dfns import FieldType

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
    longname: str | None = None,
):
    """Define a field."""
    if block or longname:
        metadata = metadata or {}
        if block:
            metadata["block"] = block
        if longname:
            metadata["longname"] = longname
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


FileInOut = Literal[None, "filein", "fileout"]


def path(
    default=NOTHING,
    validator=None,
    converter=None,
    repr=True,
    eq=True,
    init=True,
    metadata=None,
    on_setattr=None,
    block: str | None = None,
    inout: FileInOut | None = None,
    longname: str | None = None,
):
    """Define a file path field."""
    if block or inout or longname:
        metadata = metadata or {}
        if block:
            metadata["block"] = block
        if inout:
            metadata["inout"] = inout
        if longname:
            metadata["longname"] = longname
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
    block: str | None = None,
    longname: str | None = None,
):
    """Define a dimension field."""
    if block or longname:
        metadata = metadata or {}
        if block:
            metadata["block"] = block
        if longname:
            metadata["longname"] = longname
    return flopy_dim(
        scope=scope,
        coord=coord,
        default=default,
        repr=repr,
        eq=eq,
        init=init,
        metadata=metadata,
    )


def coord(
    scope=None,
    default=NOTHING,
    repr=True,
    eq=True,
    metadata=None,
    block: str | None = None,
    longname: str | None = None,
):
    """Define a coordinate field."""
    if block or longname:
        metadata = metadata or {}
        if block:
            metadata["block"] = block
        if longname:
            metadata["longname"] = longname
    return flopy_coord(
        scope=scope,
        default=default,
        repr=repr,
        eq=eq,
        metadata=metadata,
    )


def array(
    dtype: np.dtype | str | type | None = None,
    dims=None,
    default=NOTHING,
    validator=None,
    converter=None,
    repr=True,
    eq=None,
    metadata=None,
    on_setattr=None,
    block: str | None = None,
    netcdf: bool | None = None,
    longname: str | None = None,
    prefix: tuple[str, ...] | None = None,
    row_keyword: bool | str = False,
    cellid: bool = False,
):
    """Define an array field."""
    if block or netcdf or longname or prefix or row_keyword or cellid:
        metadata = metadata or {}
        if block:
            metadata["block"] = block
        if netcdf:
            metadata["netcdf"] = netcdf
        if longname:
            metadata["longname"] = longname
        if prefix:
            metadata["prefix"] = tuple(prefix)
        if row_keyword:
            metadata["row_keyword"] = row_keyword
        if cellid:
            metadata["cellid"] = True
    return flopy_array(
        dtype=dtype,
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


def _block_sort_key(item) -> int:
    k, _ = item
    if k == "options":
        return 0
    elif k == "dimensions":
        return 1
    elif k == "griddata":
        return 2
    elif "period" in k:
        return 4
    else:
        return 3


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
    return dict(sorted(blocks.items(), key=_block_sort_key))


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


@singledispatch
def get_field_type(obj) -> FieldType:
    raise ValueError(f"Cannot infer field type from object of type {type(obj)}")


@get_field_type.register(type)
def _(t: type) -> FieldType:
    match t:
        case builtins.str | np.str_:
            return "string"
        case builtins.bool | np.bool:
            return "keyword"
        case builtins.int | np.integer:
            return "integer"  # type: ignore
        case builtins.float | np.floating:
            return "double"  # type: ignore
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
                        return "double"
                    case tt if tt is Path or tt is datetime:
                        return "string"
                    case _:
                        return "record"
            return "list"
        # TODO handle arrays
        case _:
            return "record"


@get_field_type.register(Attribute)
def _(attribute: Attribute) -> FieldType:
    """
    Get a `xattree` field's type as defined by the MODFLOW 6 input
    definition language:
    https://modflow6.readthedocs.io/en/stable/_dev/dfn.html#variable-types

    The type of the field is determined from `xattree` metadata.
    """
    if (xatmeta := attribute.metadata.get("xattree", None)) is None:
        raise ValueError(f"Attribute {attribute.name} in {attribute.name} has no xattree metadata.")
    match xatmeta["kind"]:
        case "child":
            return "list"  # Child components become tabular bindings
        case "array":
            return "array"
        case "coord":
            return "array"
        case "dim":
            return "integer"
        case "attr":
            if (t := attribute.type) is None:
                raise ValueError(f"Attribute {attribute.name} in {attribute.name} has no type.")
            return get_field_type(t)
    raise ValueError(f"Could not map {attribute.name} to a valid MF6 type.")
