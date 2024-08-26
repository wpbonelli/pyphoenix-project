from functools import singledispatch
from itertools import repeat
from os import PathLike, linesep
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from flopy4.array import is_constant
from flopy4.mf6.io.constants import ArrayHow
from flopy4.param import Scalar
from flopy4.utils import depth

Param = Scalar | np.ndarray | pd.DataFrame


def _indent(n=2):
    return "".join(repeat(" "), n)


@singledispatch
def dumps_scalar(
    value: Scalar,
    name: Optional[str],
    indent: int = 2,
    separator: str = "\t",
    **kwargs,
) -> str:
    return (
        _indent(indent),
        name.upper(),
        separator,
        str(value),
    )


@dumps_scalar.register
def dumps_bool(
    value: bool, name: str, indent: int = 2, separator: str = "\t", **kwargs
) -> str:
    if value:
        return (_indent(indent), name.upper)


@dumps_scalar.register
def dumps_int(
    value: int,
    name: Optional[str],
    indent: int = 2,
    separator: str = "\t",
    **kwargs,
) -> str:
    return dumps_scalar(value, name, indent, separator)


@dumps_scalar.register
def dumps_float(
    value: float,
    name: Optional[str],
    indent: int = 2,
    separator: str = "\t",
    **kwargs,
) -> str:
    return dumps_scalar(value, name, indent, separator)


@dumps_scalar.register
def dumps_str(
    value: str,
    name: Optional[str],
    indent: int = 2,
    separator: str = "\t",
    **kwargs,
) -> str:
    return dumps_scalar(value, name, indent, separator)


@dumps_scalar.register
def dumps_path(
    value: Path,
    name: Optional[str],
    indent: int = 2,
    separator: str = "\t",
    **kwargs,
) -> str:
    inout = kwargs.pop("inout", None)
    name_section = f"{name.upper()} + {separator}"
    inout_section = "" if inout is None else f"{inout}{separator}"
    return (_indent(indent), name_section, inout_section, value)


def _dumps_factor(
    separator: str = "\t", factor: Optional[float] = None
) -> str:
    ret = ""
    if factor is not None:
        ret += f"{separator}FACTOR{separator}{factor}"
    return ret


def dumps_array_internal(
    value: np.ndarray,
    indent: int = 2,
    separator: str = "\t",
) -> str:
    def _dumps_control() -> str:
        how = ArrayHow.internal.value.upper()
        control = f"{_indent(indent * 2)}{how}"
        return control

    def _dumps_array() -> str:
        dims = len(value.shape)
        if dims == 1:
            return "".join(
                _indent(indent * 3),
                separator.join([str(x) for x in value]),
            )
        elif dims == 2:
            v = f"{linesep}{_indent(indent * 3)}"
            v = v.join(" ".join(str(x) for x in y) for y in value)
            return v
        elif dims == 3:
            v = _indent(indent * 3)
            for i in range(len(value)):
                v += separator.join(
                    f"{linesep}{_indent(indent * 3)}"
                    + separator.join(str(x) for x in y)
                    for y in value[i]
                )
            return v
        else:
            raise ValueError(
                "Too many dimensions," f"expected <= 3: {value.shape}"
            )

    return linesep.join(_dumps_control(), _dumps_array())


def dumps_array_external(
    path: PathLike,
    indent: int = 2,
    separator: str = "\t",
) -> str:
    how = ArrayHow.external.value.upper()
    path = Path(path).expanduser()
    return f"{_indent(indent * 2)}{how}{separator}{str(path)}"


def dumps_array_constant(
    value: np.ndarray, indent: int = 2, separator: str = "\t"
) -> str:
    if not is_constant(value):
        raise ValueError("Array isn't constant!")
    v = value.item(0)
    how = ArrayHow.constant.value.upper()
    f"{_indent(indent * 2)}{how}{separator}{str(v)}"


def dumps_array(
    value: np.ndarray,
    name: str,
    indent: int = 2,
    separator: str = "\t",
    constant: bool = False,
    layered: bool = False,
    factor: float = 1.0,
    path: Optional[PathLike] = None,
    **kwargs,
) -> str:
    def _lines(a) -> str:
        lines = []
        if constant:
            lines.append(
                dumps_array_constant(
                    a * factor,
                    indent,
                    separator,
                )
            )
        elif path:
            lines.append(dumps_array_external(path, indent, separator))
        else:
            lines.append(dumps_array_internal(a * factor, indent, separator))
        return lines

    lines = []
    if layered:
        lines.append(
            "".join(
                _indent(indent),
                name.upper(),
                separator,
                "LAYERED",
            )
        )
        for v in value:
            lines.extend(_lines(v))
    else:
        lines.extend(_lines(value))
    return linesep.join(lines)


def dumps_table(
    value: pd.DataFrame,
    name: str,
    indent: int = 2,
    separator: str = "\t",
    **kwargs,
) -> str:
    # TODO: implement after implementing tables
    pass


def dumps_record(
    value: dict, indent: int = 2, separator: str = "\t", **kwargs
) -> str:
    """Convert a record parameter to an MF6 input string."""
    ret = ""
    for name, param in value.items():
        # only keywords are tagged
        ret += dumps_param(
            param,
            name=None if isinstance(param, bool) else name,
            indent=indent,
            separator=separator,
            **kwargs,
        )
    return ret


def dumps_choice(
    value: dict, indent: int = 2, separator: str = "\t", **kwargs
) -> str:
    """Convert a choice parameter to an MF6 input string."""
    # TODO
    pass


def dumps_param(
    value: Param, name: str, indent: int = 2, separator: str = "\t", **kwargs
) -> str:
    if isinstance(value, np.ndarray):
        if not name:
            raise ValueError("Can't serialize anonymous array, provide a name")
        return dumps_array(value, name, indent, separator, **kwargs)
    elif isinstance(value, pd.DataFrame):
        if not name:
            raise ValueError("Can't serialize anonymous table, provide a name")
        return dumps_table(value, name, indent, separator, **kwargs)
    return dumps_scalar(value, name, **kwargs)


def dumps_block(
    value: dict, name: str, indent: int = 2, separator: str = "\t", **kwargs
) -> str:
    """Convert a block to an MF6 input string."""
    ret = ""
    index = kwargs.get("index", "")
    ret += f"BEGIN {name.upper()} {index}\n"
    for name, param in value.items():
        ret += dumps_param(param, name, indent, separator, **kwargs)
    ret += f"END {name.upper()}\n"
    return ret


def dumps_list(l: list, indent=2, separator="\t", **kwargs) -> str:
    retval = ""
    for item in l:
        if isinstance(item, dict):
            clsname = item["_type"]
            if clsname.endswith("Block"):
                retval += dumps_block(item, indent, separator, **kwargs)
            elif clsname.endswith("Record"):
                retval += dumps_record(item, indent, separator, **kwargs)
            elif clsname.endswith("Setting"):
                retval += dumps_choice(item, indent, separator, **kwargs)
            else:
                raise ValueError(f"List of {clsname} is not supported")
        else:
            raise ValueError(f"List of {type(item)} is not supported")

    return retval


def dumps_dict(
    d: dict, indent: int = 2, separator: str = "\t", **kwargs
) -> str:
    if depth(d) > 5:
        # is this sanity check needed?? max depth as:
        # simulation -> model -> package -> block -> param
        raise ValueError("Expected nesting depth <= 5")
    retval = ""
    for name, item in d.items():
        if isinstance(item, dict):
            retval += dumps_dict(item, indent, separator, **kwargs)
        elif isinstance(item, list):
            retval += dumps_list(item, indent, separator, **kwargs)
        else:
            retval += dumps_param(item, name, indent, separator, **kwargs)
        retval += linesep
    return retval


class MF6Encoder:
    """
    MF6 input format encoder. Encodes Python built-in primitives and
    containers, as well as NumPy arrays and Pandas data frames, into
    MF6 input file format.

    Notes
    -----

    Performs the following translations:

    +---------------+-------------------------------------------------------+
    | Python        | MF6 Input                                             |
    +===============+=======================================================+
    | bool          | keyword                                               |
    +---------------+-------------------------------------------------------|
    | int           | integer                                               |
    +---------------+-------------------------------------------------------|
    | float         | double precision                                      |
    +---------------+-------------------------------------------------------|
    | str           | string                                                |
    +---------------+-------------------------------------------------------|
    | Path          | filename                                              |
    +---------------+-------------------------------------------------------|
    | dict          | record, keystring, block, package, model, or exchange |
    +---------------+-------------------------------------------------------|
    | list          | list                                                  |
    +---------------+-------------------------------------------------------|
    | pd.DataFrame  | list                                                  |
    +---------------+-------------------------------------------------------|
    | np.ndarray    | array                                                 |
    +---------------+-------------------------------------------------------|

    To determine how to translate a dictionary, the encoder looks for an item
    "_type", whose value is a type within the MF6 input component hierarchy.

    This is according to the "tagged union" strategy described in the `cattrs`
    docs: https://catt.rs/en/stable/strategies.html#tagged-unions-strategy.

    This is used to dispatch the proper encoding function, which may construct
    a string manually or TODO: invoke a template generator.

    """

    def __init__(self, indent=2, separator="\t", tag_key="_type") -> None:
        self.indent = indent
        self.separator = separator
        self.tag_key = tag_key

    def encode(self, o: Any, **kwargs) -> str:
        """
        Return an MF6 input format representation of a Python data structure.
        """

        if isinstance(o, dict):
            return dumps_dict(o, self.indent, self.separator, **kwargs)
        if isinstance(o, list):
            return dumps_list(o, self.indent, self.separator, **kwargs)
        elif isinstance(o, Param):
            name = kwargs.pop("name", None)
            if not name:
                raise ValueError(
                    "Can't serialize parameter "
                    "without keyword argument 'name'"
                )
            return dumps_param(o, name, self.indent, self.separator, **kwargs)


def dump(o, f, *, indent=2, separator="\t", **kwargs):
    if not f.write:
        raise TypeError("File must be writeable")
    f.write(dumps(o, indent, separator, **kwargs))


def dumps(o, *, indent=2, separator="\t", **kwargs):
    encoder = MF6Encoder(indent, separator, **kwargs)
    return encoder.encode(o)
