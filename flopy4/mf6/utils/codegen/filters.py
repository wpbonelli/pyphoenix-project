import builtins
from functools import singledispatch
import keyword
from pathlib import Path
from typing import Any

from jinja2 import pass_context

from modflow_devtools.dfns import Component, Field


def class_name(dfn: Component) -> str:
    if dfn.type == "simulation":
        return "Sim"
    elif dfn.type == "model":
        return dfn.name.split("-")[0].capitalize()
    elif dfn.type == "package":
        return dfn.name.split("-")[2].capitalize()


def module_name(dfn: Component) -> str:
    return class_name(dfn).lower()


def rel_path(dfn: Component) -> Path:
    module = module_name(dfn)
    if dfn.type in ["simulation", "model"]:
        return f"{module}.py"
    return dfn.parent / f"{module}.py"


def has_period_block(dfn: Component) -> bool:
    return "period" in (dfn.blocks or {})


def has_dimensions_block(dfn: Component) -> bool:
    return "dimensions" in (dfn.blocks or {})


def uses_maxbound(dfn: Component) -> bool:
    return has_dimensions_block(dfn) and "maxbound" in (dfn.blocks or {}).get("dimensions", {})


def is_scalar(f: Field) -> bool:
    return f.type in ["keyword", "integer", "double", "string"]


@pass_context
def is_inline_array(ctx, f: Field) -> bool:
    dfn = ctx.get("dfn") 
    # TODO add/use Dfns.get_block(f: Field) method
    return f.type == "array" and len(f.shape) <= 1


def is_self_sizing_array(f: Field) -> bool:
    return f.type == "array" and not f.shape


@pass_context
def is_dimension(ctx, f: Field) -> bool:
    dfn = ctx.get("dfn")
    return f.name in dfn.dims


<<<<<<< HEAD
def is_file_record(f: Field) -> bool:
    """True for record fields whose children include filein or fileout."""
    return f.type.startswith("record") and _has_file_child(f)


def is_aux_list_field(f: Field) -> bool:
    """True for auxiliary variable name lists (options block, shape naux).

    These are generated as ``Optional[list[str]]`` with no dims and no
    structure_array converter, matching the hand-written pattern.
    """
    return f.type == "string" and f.block == "options" and bool(f.shape) and "naux" in f.shape


def is_period_array(f: Field) -> bool:
    """True for array fields in the period block."""
    return f.block == "period" and (is_array(f) or is_keyword_array(f))


def is_dimensions_scalar(f: Field) -> bool:
    """True for scalar fields in the dimensions block (computed, init=False)."""
    return f.block == "dimensions" and is_scalar(f)


def is_boundname_field(f: Field) -> bool:
    """True for the boundname string array in the period block."""
    return f.block == "period" and f.name == "boundname"


# Per-package OC record types.  Each entry maps a DFN name to the list of
# rtype strings that are valid for its SAVE/PRINT period records.
_OC_RTYPES: dict[str, list[str]] = {
    "gwf-oc": ["head", "budget"],
    "gwt-oc": ["concentration", "budget"],
    "gwe-oc": ["temperature", "budget"],
    "prt-oc": ["budget"],
}


def is_oc_record(f: Field, dfn_name: str) -> bool:
    """True for saverecord/printrecord in OC-style period blocks.

    These records take the form ``SAVE|PRINT RTYPE OCSETTING`` and are
    expanded by codegen into per-rtype NDArray[np.str_] fields rather than
    being emitted as inner classes or TODO comments.
    """
    return (
        f.block == "period"
        and f.type.startswith("record")
        and f.name in ("saverecord", "printrecord")
        and dfn_name in _OC_RTYPES
    )


def is_list_field(f: Field) -> bool:
    """True for list-type sub-table fields (packagedata, perioddata, etc.)."""
    return f.type == "list"


def list_columns(f: Field) -> list[dict]:
    """Return the leaf column dicts of a list-type sub-table.

    Children in the v2 TOML schema are stored as plain dicts, not Field
    objects.  The list field has a single record child dict; the column
    entries are that record's ``children`` mapping.
    """
    if not f.children:
        return []
    record_child = next(iter(f.children.values()))
    if not isinstance(record_child, dict):
        return []
    return list(record_child.get("children", {}).values())


def list_col_dim(f: Field, dfn: Dfn) -> str | None:
    """Return the dimension name for list column arrays.

    Uses the last token from the list field's explicit shape when present,
    preferring the actual dimensions-block field name when the shape token
    differs (e.g. shape uses 'npackages' but field is 'maxpackages').
    Falls back to the single entry in the DFN's dimensions block.
    Returns None when the dimension cannot be determined unambiguously.
    """
    dim_block = (dfn.blocks or {}).get("dimensions", {})
    if f.shape:
        inner = f.shape.strip().strip("()")
        parts = [p.strip() for p in inner.split(",") if p.strip()]
        if parts:
            shape_dim = _DIM_ALIASES.get(parts[-1], parts[-1])
            if shape_dim in dim_block:
                return shape_dim
            # Shape dim may use a different prefix than the actual field name
            # (e.g., shape "npackages" vs dimensions field "maxpackages").
            # Try suffix matching: strip leading "n" and find a field that ends
            # with the remainder.
            suffix = shape_dim.lstrip("n")
            if suffix:
                for fname in dim_block:
                    if fname.endswith(suffix):
                        return fname
    if len(dim_block) == 1:
        name = next(iter(dim_block))
        return _DIM_ALIASES.get(name, name)
    return None


def is_generatable(f: Field) -> bool:
    """True if this field can be handled in the current generation pass."""
    if _has_complex_shape(f):
        return False
    return (
        is_scalar(f)
        or is_array(f)
        or is_keyword_array(f)
        or is_file_record(f)
        or is_aux_list_field(f)
    )


def _is_expandable_child(child: dict) -> bool:
    """True if a record child dict can be generated as a standalone field.

    Only keyword-type children are expandable: they're self-naming tokens that
    map cleanly to individual bool fields.  Scalar data fields (even tagged ones)
    are positional components of a compound construct and must stay grouped.
    """
    return child["type"] == "keyword"


_RECORD_CLASS_SCALAR_TYPES = frozenset({"integer", "double precision", "double", "string"})


def can_generate_record_class(f: Field) -> bool:
    """True when a compound record should be rendered as an inner attrs class.

    All non-file records whose children are entirely scalars and/or keywords
    become inner attrs classes.  The first keyword child (if any) is the
    trigger token (``_keyword``); remaining keyword children become
    ``Optional[bool]`` fields so related options stay grouped.

    All-keyword records with only one child (a lone flag keyword) are left to
    :func:`can_expand_record` — a bare bool field is cleaner there than an
    empty inner class.  Records with unsupported child types (recarray, union,
    complex shapes) fall back to TODO comments.
    """
    if is_file_record(f) or not f.children:
        return False
    children = list(f.children.values())
    _supported = _RECORD_CLASS_SCALAR_TYPES | {"keyword"}
    all_supported = all(c.get("type") in _supported for c in children)
    if not all_supported:
        return False
    has_scalar = any(c.get("type") in _RECORD_CLASS_SCALAR_TYPES for c in children)
    # All-keyword records need at least 2 children (trigger + modifier) to
    # justify a class; a single lone keyword expands more cleanly to a bool.
    if not has_scalar:
        return len(children) >= 2
    return True


def can_expand_record(f: Field) -> bool:
    """True if a non-file compound record can be at least partially expanded.

    A record can be expanded when all its required (non-optional) children are
    individually generatable as standalone fields.  Optional children that
    can't be generated standalone are noted in a TODO comment but don't
    block expansion.
    """
    if is_file_record(f) or not f.children:
        return False
    for child in f.children.values():
        if not child.get("optional", False) and not _is_expandable_child(child):
            return False
    return True


def skip_reason(f: Field) -> str | None:
    """Return a human-readable reason why a field is skipped, or None."""
    if is_generatable(f):
        return None
    if is_list_field(f):
        return None  # handled by _expand_list_field in make.py
    if can_expand_record(f):
        return None  # handled by _expand_record_field in make.py
    if _has_complex_shape(f):
        return f"complex shape '{f.shape}' not yet supported"
    if f.type in ("record", "recarray", "keystring"):
        return f"complex type '{f.type}' not yet supported"
    return f"type '{f.type}' not yet supported"


# Field iteration


def flat_fields(dfn: Dfn, *, developmode: bool = False) -> list[Field]:
    """Return an ordered flat list of all fields from all blocks.

    Parameters
    ----------
    dfn :
        The component definition.
    developmode :
        If False (default), fields marked developmode are excluded.
    """
    # Collect subfield names from file records so they can be suppressed.
    subfield_names: set[str] = set()
    for block in (dfn.blocks or {}).values():
        for f in block.values():
            if is_file_record(f):
                subfield_names.update(_file_record_subfield_names(f))

    result = []
    for block in (dfn.blocks or {}).values():
        for f in block.values():
            f = apply_override(dfn.name, f)
            if f.developmode and not developmode:
                continue
            if f.name in subfield_names:
                continue
            result.append(f)
    return result


# Python type annotations

_SCALAR_PY_TYPES: dict[str, str] = {
=======
_SCALAR_PRIMITIVES: dict[str, str] = {
>>>>>>> 4221103 (adapt wip)
    "keyword": "bool",
    "integer": "int",
    "double": "float",
    "string": "str",
}

_ARRAY_DTYPES: dict[str, str] = {
    "double": "np.float64",
    "integer": "np.int64",
    "string": "np.object_",
    "keyword": "np.bool_",
}


def py_type(f: Field) -> str:
    """Return the Python type annotation string for a field."""
    
    if is_scalar(f):
        # Keywords are always bool (not Optional[bool]) regardless of optional flag.
        if f.type == "keyword":
            return "bool"
        base = _SCALAR_PRIMITIVES.get(f.type, "Any")
    elif f.type == "file":
        base = "Path"
    elif is_inline_array(f):
        base = f"[list[{scalar_type(f.dtype)}]]"
    elif f.type == "array":
        dtype = _ARRAY_DTYPES.get(f.type, "np.object_")
        base = f"NDArray[{dtype}]"
    elif f.type == "record":
        pass # TODO
    elif f.type == "union":
        pass # TODO
    elif f.type == "list":
        pass # TODO
    else:
        base = "Any"
    
    return f"Optional[{base}]" if f.optional else base


def safe_name(name: str) -> str:
    """Return a safe Python identifier for a DFN field name."""
    name = name.replace("-", "_")
    if keyword.iskeyword(name) or name in dir(builtins):
        return f"{name}_"
    return name


def dims_tuple(shape: str) -> str:
    """Convert a DFN shape string to a Python dims tuple literal.

    Applies _ALT_DIM_TOKENS, then _DIM_ALIASES to normalise dimension names.

    Examples
    --------
    "(ncol)"                    -> '("ncol",)'
    "(nper, nnodes)"            -> '("nper", "nodes")'
    "(nper, ncol*nrow; ncpl)"   -> '("nper", "ncpl")'
    """
    return str(
        tuple(
            [
                p.strip() for p in shape.strip().strip("()").split(",")
                if p.strip()
            ]
        )
    )


def try_repr(longname: str | None) -> str | None:
    if not longname:
        return None
    return repr(longname)


def default_repr(f: Field) -> str:
    """Return the Python repr of a field's default value."""
    if f.default is None and f.type == "keyword":
        return "False"
    return repr(f.default)


def as_bool(val: Any) -> bool:
    """Normalize a v1 DFN attribute that may be bool or string 'true'/'false'."""
    if isinstance(val, bool):
        return val
    return str(val).lower() == "true"


def base_class(dfn: Component) -> str | None:
    """Determine the Python base class for a component."""
    if dfn.type == "simulation":
        return None
    if dfn.type == "model":
        return "Model"
    if dfn.subtype == "solution":
        return "Solution"
    if dfn.subtype == "exchange":
        return "Exchange"
    return "Package"


@singledispatch
def scalar_type(obj: Any) -> str | None:
    raise ValueError(f"Cannot infer scalar type from {type(obj)}")


@scalar_type.register(Field)
def _(field: Field) -> str | None:
    return scalar_type(field.type)


@scalar_type.register(str)
def _(s: str) -> str | None:
    return {
        "keyword": "bool",
        "integer": "int",
        "double precision": "float",
        "double": "float",
        "string": "str",
    }.get(s, None)


def slntype(dfn: Component) -> str | None:
    """Return the slntype string for solution DFNs, or None."""
    if dfn.subtype == "solution":
        return dfn.name.split("-")[1]
    return None
