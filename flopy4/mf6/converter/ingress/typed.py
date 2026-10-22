"""The typed loader: a component from its typed parse (its own grammar's,
see ``flopy4.mf6.codec.reader.loads_typed``), without the basic loader's
converter or the DFNs. Kept beside the basic loader to compare the two
(see docs/dev/converter-simplification-plan.md, Track B).

The typed parse has already sent each line to its field, by the class
attribute holding it, and read headers, keywords, records and unions. What's
left reads the class's own fields: shaping arrays to the grid, making items
and records, fill-forward, and the children a file names, which load as the
basic loader's do (see `ComponentLoad`)."""

import warnings
from pathlib import Path
from typing import Any, get_origin

import attrs
import numpy as np
import numpy.typing as npt

from flopy4.mf6._types import TimeArraySeriesRef
from flopy4.mf6.block import block_list_type
from flopy4.mf6.codec.reader.transformer.typed import UnknownBlock
from flopy4.mf6.converter.ingress.structure import (
    ComponentLoad,
    _from_file_index,
    _Grid,
    _header,
    _init_key,
    _is_grid_array,
    _load_file_child,
    _period_array,
    _record_array_io,
    read_array_file,
)
from flopy4.mf6.item import Item, is_cellid, item_list_type, item_list_words
from flopy4.mf6.load_context import LoadContext
from flopy4.mf6.record import Record, _coerce, _elem_coerce, _nested_class, record_type
from flopy4.mf6.spec import to_field_type
from flopy4.mf6.write_context import ArrayIO, array_hash
from flopy4.utils import unwrap_optional


def _occurrences(parsed: dict, cls: type) -> dict[str, dict[Any, Any]]:
    """The parse's blocks by name, each as ``{None: contents}``, or for a
    repeating block ``{header: contents}`` (see `structure._header`) in
    file order. A TAS time's block is keyed by its time. Unknown blocks
    are left out (see `structure_typed`)."""
    found: dict[str, dict[Any, Any]] = {}
    for key, contents in parsed.items():
        name, *words = key.split()
        if isinstance(contents, UnknownBlock):
            continue
        if (
            not words
            and isinstance(contents, dict)
            and contents
            and all(isinstance(k, float) for k in contents)
        ):
            found.setdefault(name, {}).update(contents)
            continue
        found.setdefault(name, {})[_header(cls, name, words) if words else None] = contents
    return found


def _arm_word(arm: str) -> str:
    """A union arm's name without its DFN ``record`` suffix, as codegen
    names its class's keyword (``saverecord`` is OC's ``save``)."""
    words = arm.lower().split("_")
    if words[-1] == "record":
        words = words[:-1]
    elif words[-1].endswith("record"):
        words[-1] = words[-1][: -len("record")]
    return "_".join(w for w in words if w)


def _arm_class(classes: tuple, arm: str) -> "type[Item] | None":
    """The class of a list's union arm, by its keyword or name."""
    word = _arm_word(arm)
    for c in classes:
        if c.keyword().lower() == word or c.__name__.lower() == word.replace("_", ""):
            return c
    return None


def _field_value(cls: Any, f: Any, value: Any) -> Any:
    """A record's or item's field `f`'s value from its typed parse: a
    nested record's from its parts, an array's as a tuple, a scalar as
    its type, an index or cellid 0-based; a union's as is (its converter
    takes a word or ``(arm, value)``)."""
    if f.metadata.get("type") == "union":
        return value
    if isinstance(f.type, str) and (nested := _nested_class(cls, f.type)) is not None:
        return _record(nested, value)
    if f.metadata.get("type") == "array":
        values = value if isinstance(value, (list, tuple)) else [value]
        return tuple(_elem_coerce(v, f) for v in values)
    value = _coerce(value, f)
    if is_cellid(f) and isinstance(value, (list, tuple)):
        return tuple(int(v) - 1 for v in value)
    if f.metadata.get("index") and isinstance(value, int):
        return value - 1
    return value


def _record(cls: Any, parts: Any) -> Any:
    """A record or item from its typed parse's parts, by name (a field
    named for a Python keyword is the part without its trailing
    underscore: Format's ``format_``)."""
    if not isinstance(parts, dict):
        return cls.convert(parts) if issubclass(cls, Record) else cls(parts)
    kwargs = {}
    for f in cls.fields():
        key = f.name if f.name in parts else f.name.rstrip("_")
        if key in parts and parts[key] is not None:
            kwargs[f.name] = _field_value(cls, f, parts[key])
    return cls(**kwargs)


def _typed_record(record: dict, length: int, dtype, context: LoadContext) -> tuple:
    """One array control record's values, ``length`` of them, scaled by
    its FACTOR, and how it wrote them (see `ArrayIO`)."""
    control = record["control"]
    kind = control["type"]
    if kind == "constant":
        value = control["value"]
        value = int(value) if dtype == np.int64 else float(value)
        return np.full(length, value, dtype=dtype), ArrayIO(format="constant")
    if kind == "external":
        path = Path(control["value"])
        values = read_array_file(context.resolve(path), bool(control.get("binary")), dtype)
    else:
        values = np.asarray(record["data"], dtype=float).ravel().astype(dtype)
    values = values[:length]
    if (factor := control.get("factor")) is not None:
        values = values * (int(factor) if dtype == np.int64 else factor)
    iprn = control.get("iprn")
    if kind == "external":
        return values, ArrayIO(
            iprn=iprn,
            path=path,
            format="binary" if control.get("binary") else "open/close",
            hash=array_hash(values),
        )
    return values, ArrayIO(iprn=iprn, format="internal")


def _typed_array(
    array: dict, f: Any, grid: _Grid, context: LoadContext
) -> "tuple[np.ndarray, list[ArrayIO], bool]":
    """A grid array's values, flat and as long as the field's shape says
    (see `_Grid.size`), from its typed parse; how each control record
    wrote it; and whether it was LAYERED. A LAYERED array's records are
    a layer's each, or the whole field's if it's smaller (DIS's top), and
    fewer than the layers repeat to fill the field, as MF6 reads them."""
    dtype = np.int64 if to_field_type(f.type) == "integer" else np.float64
    size = grid.size(f)
    layered = isinstance(array["control"], list)
    values: np.ndarray
    ios: list[ArrayIO] = []
    if layered:
        records = [{"control": c, "data": d} for c, d in zip(array["control"], array["layers"])]
        layers = []
        for r in records:
            layer, io = _typed_record(r, min(grid.ncpl, size), dtype, context)
            layers.append(layer)
            ios.append(io)
        values = np.concatenate(layers).astype(dtype)
        if values.size and values.size < size:
            values = np.resize(values, size)
    else:
        values, io = _typed_record(array, size, dtype, context)
        ios.append(io)
    if f.metadata.get("index"):
        values = _from_file_index(values)
    return values, ios, layered


def _block_order(cls: type, found: dict) -> list[str]:
    """The blocks in `found`, options and dimensions first, then in the
    order of the class's fields, which is the file's (the grid's dims
    before its arrays, the auxiliary names before the lists that use
    them)."""
    order = ["options", "dimensions"]
    for f in attrs.fields(cls):  # type: ignore[arg-type]
        if (block := f.metadata.get("block")) is not None and block not in order:
            order.append(block)
    return sorted(found, key=lambda b: order.index(b) if b in order else len(order))


class _TypedLoad(ComponentLoad):
    """The typed loader's read of one component's file (see
    `ComponentLoad`), by the class's own fields: no DFN."""

    def __init__(self, cls: type, context: LoadContext) -> None:
        super().__init__(cls, context)
        # each block's fields, by their `__init__` names, which the typed
        # parse keys them by
        self.fields: dict[str, dict[str, attrs.Attribute]] = {}
        for f in attrs.fields(cls):  # type: ignore[arg-type]
            if (block := f.metadata.get("block")) is not None and f.init:
                self.fields.setdefault(block, {})[_init_key(f)] = f

    def read(self, name: str, found: dict[Any, Any]) -> None:
        """Read the occurrences of the block `name` into the arguments
        (see `ComponentLoad.read_blocks`)."""
        fields = list(self.fields.get(name, {}).values())
        self.read_blocks(
            name,
            fields,
            found,
            numbered=all(isinstance(h, (int, float)) for h in found),
            fill_forward=any(f.metadata.get("fill_forward") for f in fields),
        )

    def body(self, name: str, contents: Any, header: Any) -> dict:
        """The values of one occurrence of the block `name`, by field, from
        its typed parse; the rows naming children are kept for
        `_resolve_bindings`."""
        contents = self.redirected(name, contents, header)
        fields = self.fields.get(name, {})
        values: dict[attrs.Attribute, Any] = {}
        for key, value in contents.items():
            f = fields.get(key)
            if name in self.binding_blocks and (
                f is None or any(f is b for b, *_ in self.binding_blocks[name])
            ):
                self.bindings.setdefault(name, []).extend(value)
                continue
            if f is None:
                self.unknown(name, key)
                continue
            if (value := self.value(f, value, header)) is not None:
                values[f] = value
        return values

    def redirected(self, name: str, contents: dict, header: Any) -> dict:
        """A block's contents, with those of the file an ``OPEN/CLOSE``
        line names (``BEGIN PERIOD 1 / OPEN/CLOSE <file> / END PERIOD 1``)
        in its place, parsed as the block's."""
        if (path := contents.get("open/close")) is None:
            return contents
        from flopy4.mf6.codec.reader import loads_typed

        text = self.context.resolve(path).read_text()
        # the block's header, as its grammar takes one (any number will do
        # for a period's)
        words = list(header) if isinstance(header, tuple) else [] if header is None else [header]
        begin = " ".join(str(w) for w in [name, *words])
        parsed = loads_typed(f"BEGIN {begin}\n{text}\nEND {name}\n", getattr(self.cls, "dfn_name"))
        rest = {k: v for k, v in contents.items() if k != "open/close"}
        return rest | next(iter(parsed.values()), {})

    def unknown(self, name: str, key: str) -> None:
        """Warn of a value no field of the block `name` takes, unless it's
        a computed one (a list package's MAXBOUND)."""
        if not isinstance(getattr(self.cls, key, None), property):
            warnings.warn(
                f"{self.cls.__name__}: no field takes {name.upper()} entry {key.upper()}, skipped",
                UserWarning,
                stacklevel=4,
            )

    def value(self, f: attrs.Attribute, value: Any, header: Any) -> Any:
        """The field `f`'s value from its typed parse."""
        if _is_grid_array(f):
            return self.array(f, value, header)
        if (item_cls := item_list_type(f.type)) is not None:
            return self.items(f, item_cls, value)
        if (blocks := block_list_type(f.type)) is not None:
            return self.parse_list(value, blocks.parts()[2])
        if f.metadata.get("_keyword"):
            return self.file(f, value)
        if (rec := record_type(f.type)) is not None:
            return _record(rec, value)
        t = unwrap_optional(f.type)
        if t is bool:
            return True
        if get_origin(t) in (list, np.ndarray, npt.NDArray):
            return [str(v) for v in value] if isinstance(value, list) else [str(value)]
        if t is str:
            return str(value)
        return value

    def items(self, f: attrs.Attribute, item_cls: Any, value: Any) -> Any:
        """A list's items: its rows', or its union elements' (OC's
        ``{"saverecord": {...}}``), or a word's (PRP's ALL)."""
        rows = value if isinstance(value, list) or hasattr(value, "rows") else [value]
        if not isinstance(item_cls, tuple) or not any(isinstance(r, dict) for r in rows):
            rows = [[r] if isinstance(r, str) else r for r in rows]
            return self.parse_list(rows, item_cls, item_list_words(f.type))
        items = []
        for element in rows:
            if isinstance(element, str):
                items.append(element.upper())
                continue
            ((arm, parts),) = element.items()
            if (arm_cls := _arm_class(item_cls, arm)) is None:
                warnings.warn(f"{self.cls.__name__}: no item of {f.name} is {arm}, skipped")
                continue
            items.append(_record(arm_cls, parts))
        return items or None

    def file(self, f: attrs.Attribute, value: Any) -> Any:
        """A file record's value: its path, or the child loaded from it; a
        list of them (TAS6's) one per record."""
        if isinstance(value, list):
            return [self.file(f, v) for v in value]
        path = Path(next(iter(value.values())) if isinstance(value, dict) else value)
        if f.metadata.get("child"):
            return _load_file_child(f, path, attrs.evolve(self.context, parent=self.cls))
        return path

    def array(self, f: attrs.Attribute, value: Any, header: Any) -> Any:
        """A grid array's value, and how the file wrote it, into
        `array_ios`, by `ArrayKey`; an auxiliary variable's arrays, a list
        of ``[name, array]``, by name. An array can come from a time-array
        series, by name (``RECHARGE TIMEARRAYSERIES <name>``); its value
        keeps the name (see flopy4.mf6.period_arrays)."""
        if (grid := _Grid.of(self.dims)) is None:
            return None
        if f.metadata.get("fk"):
            names = {n.lower(): n for n in self.kwargs.get(f.metadata["fk"].split(".")[-1]) or []}
            arrays = {}
            for aux_name, array in value:
                if (known := names.get(str(aux_name).lower())) is None:
                    self.unknown(f.metadata["block"], str(aux_name))
                elif (v := self.one_array(f, array, header, grid, record=False)) is not None:
                    arrays[known] = v
            return arrays or None
        return self.one_array(f, value, header, grid)

    def one_array(
        self, f: attrs.Attribute, array: dict, header: Any, grid: _Grid, record: bool = True
    ) -> Any:
        """One array's value, a period's shaped as the field holds it (see
        `_period_array`), and with `record`, how the file wrote it. A TAS
        time's array, a block's untagged one, is kept flat, its records
        unrecorded, as the basic loader reads it."""
        control = array["control"]
        if isinstance(control, dict) and control["type"] == "timearrayseries":
            if not f.metadata.get("time_series"):
                return None
            return TimeArraySeriesRef(str(control["value"]))
        value, ios, layered = _typed_array(array, f, grid, self.context)
        if not f.metadata.get("fill_forward") and header is not None:
            return value
        if record:
            key = (f.name,) if header is None else (f.name, header)
            _record_array_io(self.array_ios, key, ios, layered=layered)
        if header is not None:
            value = _period_array(value, ios, f, grid, layered)
        return value


def structure_typed(
    parsed: dict, cls: type, *, context: LoadContext, name: str | None = None
) -> Any:
    """A ``cls`` from its file's typed parse: its blocks read in the
    class's field order (see `_block_order`), a repeating block's values
    kept by header (see `_occurrences`), and the rows naming children
    resolved last, as the basic loader's are."""
    load = _TypedLoad(cls, context)
    for key, contents in parsed.items():
        # MF6 ignores a block it doesn't read (an old IMS file's XMD)
        if isinstance(contents, UnknownBlock) and contents:
            warnings.warn(f"{cls.__name__}: ignoring unknown block {key.upper()}")
    found = _occurrences(parsed, cls)
    for block in _block_order(cls, found):
        load.read(block, found[block])
    return load.finish(name)
