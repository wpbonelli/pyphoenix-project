import struct
import warnings
from abc import ABC
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast, get_args, get_origin

import attrs
import numpy as np
import numpy.typing as npt
from modflow_devtools.dfns import dim_value

from flopy4.dimensions import DimensionProvider
from flopy4.mf6._types import TimeArraySeriesRef
from flopy4.mf6.block import block_list_type
from flopy4.mf6.codec.reader.transformer.rows import BlockRows, NumberRows, parts, row_values
from flopy4.mf6.component import Component, get_ftype
from flopy4.mf6.item import (
    Item,
    RowContext,
    conditional_fields,
    dim_lookup,
    item_list_type,
    item_list_words,
    ncelldim_from_dims,
    parse_union_items,
    sized_by,
)
from flopy4.mf6.item_table import ItemTable, read_rows
from flopy4.mf6.load_context import LoadContext
from flopy4.mf6.package import Package
from flopy4.mf6.period_arrays import is_grid_package
from flopy4.mf6.record import Record
from flopy4.mf6.spec import (
    BlockKeys,
    attr_names,
    binding_fields,
    block_keys,
    dfn,
    following_tags,
    to_field_type,
)
from flopy4.mf6.write_context import ArrayIO, WriteContext, array_hash
from flopy4.spec import is_array, resolve
from flopy4.utils import unwrap_optional


def _inner_class_type(field_type) -> type[Record] | None:
    """If field_type is Optional[C] where C is an attrs inner-record class, return C."""
    args = get_args(field_type)
    if not args:
        return None
    for arg in args:
        if arg is type(None):
            continue
        if isinstance(arg, type) and issubclass(arg, Record) and "_keyword" in vars(arg):
            return arg
    return None


def _tagged_value(f: Any, row: list) -> Any:
    """The value of the tagged field `f` from its row, which begins with
    its key: a record's, from all its tokens; a keyword's, True; an
    inline array's (AUXILIARY's names), the rest of the row; a scalar's,
    the token after the key. MF6 ignores anything after what the field
    takes (often an inline comment, or a second value like IMS's
    `UNDER_RELAXATION NONE DBD`)."""
    # A Record-typed field must go through from_tokens(), even when the
    # matched token is the field's own name rather than the record's
    # trigger keyword.
    if (inner_cls := _inner_class_type(f.type)) is not None:
        return inner_cls.from_tokens(row)
    t = unwrap_optional(f.type)
    if t is bool:
        return True
    if get_origin(t) in (list, np.ndarray, npt.NDArray):
        # even with one element; numpy >= 2.5's NDArray[X] has origin
        # NDArray, not ndarray
        return list(row[1:])
    if t is str:
        # a numeric-looking string (e.g. a bare year for START_DATE_TIME)
        # tokenizes as a number
        return str(row[1])
    return row[1]


def _parse_rows(
    rows: list,
    item_cls: "type[Item] | tuple[type[Item], ...]",
    *,
    context: LoadContext,
    sizes: "dict[str, int] | None" = None,
    enabled: frozenset[str] = frozenset(),
    union_arm: str = "cellid",
    union_forms: Callable[[Mapping[str, Any]], Any] | None = None,
    load_child: Callable[[Any, str], Any] | None = None,
    words: tuple[str, ...] = (),
) -> "list | ItemTable | None":
    """Parse rows of tokens into Items (or, for a list of unions, its
    ``words``); a block of only numbers into an `ItemTable` if it's
    tabular."""
    if not rows:
        return None
    classes = item_cls if isinstance(item_cls, tuple) else (item_cls,)
    ncelldim = context.ncelldim(classes[0]) if len(classes) == 1 else None
    if ncelldim is None:
        ncelldim = ncelldim_from_dims(dict(context.dims))
    row_context = RowContext(ncelldim=ncelldim, sizes=sizes or {}, enabled=enabled)
    if isinstance(item_cls, tuple):
        return parse_union_items(
            rows, item_cls, words=words, context=row_context, load_child=load_child
        )
    # a block of only numeric lines, read by column if its rows allow (and,
    # if tabular, kept so: see ItemTable)
    if isinstance(rows, NumberRows):
        if (read := read_rows(item_cls, rows.text, row_context)) is not None:
            return read or None
    result = item_cls.from_rows(
        [row for row in rows if row],
        row_context,
        union_arm=union_arm,
        union_forms=union_forms,
        load_child=load_child,
    )
    return result or None


# One MF6 binary-array record: KSTP, KPER (int4 each), PERTIM, TOTIM
# (float8 each), TEXT (16-byte label), NCOL, NROW, ILAY (int4 each) -- 52
# bytes total. Same layout flopy4's own binary head-output reader
# (`utils/heads_reader.py::read_hds_timestep`, "f.seek(52, 1)  # skip
# kstp, kper, pertime") already decodes; MF6 has used one binary
# 2D-array record format for both real and integer arrays since
# MODFLOW-2005 (u2drel/u2dint), for output and OPEN/CLOSE (BINARY) input
# alike -- the data portion follows immediately, real arrays
# double-precision (matching MF6's own double-precision solver and
# head-output convention) and integer arrays 4-byte. MF6 only logs the
# header's NCOL/NROW/ILAY (`ArrayReaders.f90::read_binary_header`): it
# reads as many values as the array holds, so a non-LAYERED 3-D array's
# file holds every layer after one header.
_BINARY_ARRAY_HEADER = struct.Struct("<iidd16siii")


def _read_binary_array_values(path: Path, dtype) -> np.ndarray:
    """Read an MF6 binary-array record (a header, then every value after
    it, as MF6 does) from an OPEN/CLOSE (BINARY)-referenced file. See
    `_BINARY_ARRAY_HEADER`.
    """
    with path.open("rb") as fh:
        header = fh.read(_BINARY_ARRAY_HEADER.size)
        if len(header) < _BINARY_ARRAY_HEADER.size:
            raise ValueError(f"{path}: too short for an MF6 binary-array header")
        file_dtype = np.dtype("<i4" if dtype == np.int64 else "<f8")
        values = np.fromfile(fh, dtype=file_dtype)
    return values.astype(dtype)


def _strip_quotes(fname: str) -> str:
    """MF6 (and flopy3's own writer, confirmed against its
    `test_gwf_utl01_binaryinput.py`: writes ``OPEN/CLOSE 'top.bin' ...``)
    allows an OPEN/CLOSE filename to be single- or double-quoted; `word`'s
    tokenizer keeps the quote characters as part of the token since they're
    valid filename characters on their own. Strip one matching pair from
    the ends, if present."""
    if len(fname) >= 2 and fname[0] == fname[-1] and fname[0] in ("'", '"'):
        return fname[1:-1]
    return fname


def _read_open_close_values(vrow: list, context: LoadContext, dtype) -> np.ndarray:
    """Read an ``OPEN/CLOSE <fname> [(BINARY)] [FACTOR <f>] [IPRN <i>]``
    griddata control record's referenced file.

    Not seen in the corpus (0/242 models use OPEN/CLOSE ... (BINARY) for
    an input array) so this path is unverified against a real fixture --
    based on the binary-array record format flopy4's own head-output
    reader already relies on, per `_BINARY_ARRAY_HEADER`. Otherwise the
    referenced file is a plain numeric array, whitespace- or (seen in one
    fixture family) comma-separated with no spaces at all. FACTOR is
    applied by the caller, `_read_control_record`.
    """
    tokens = [str(t) for t in vrow[1:]]
    if not tokens:
        raise ValueError("OPEN/CLOSE control record missing a filename")
    path = context.resolve(_strip_quotes(tokens[0]))
    binary = any(t.upper() in ("BINARY", "(BINARY)") for t in tokens[1:])
    return read_array_file(path, binary, dtype)


def read_array_file(path: Path, binary: bool, dtype) -> np.ndarray:
    """The values in an OPEN/CLOSE array file: an MF6 binary-array record,
    or numbers separated by whitespace or commas."""
    if binary:
        return _read_binary_array_values(path, dtype)
    text = path.read_text().replace(",", " ")
    return np.array(text.split(), dtype=dtype)


def _resolve_open_close_rows(rows: list, context: LoadContext) -> list:
    """A block's row data can itself be OPEN/CLOSE-redirected
    to an external file instead of written inline -- MF6 syntax:
    ``BEGIN PERIOD 1 / OPEN/CLOSE <fname> / END PERIOD 1``. Same keyword as
    griddata's OPEN/CLOSE control record, but a different mechanism: the
    referenced file holds list rows, not a flat numeric array, so it's
    parsed the same way an inline block's own content would be (wrapped in
    a synthetic block and passed back through the block/token grammar) rather
    than through `_read_open_close_values`.

    Detects that shape -- a block whose *only* content is one OPEN/CLOSE
    row -- and returns the referenced file's rows in its place; otherwise
    returns `rows` unchanged.
    """
    if isinstance(rows, (NumberRows, BlockRows)):
        return rows  # has numbers (and counting them would read them)
    if len(rows) != 1 or not rows[0] or str(rows[0][0]).upper() != "OPEN/CLOSE":
        return rows
    row = rows[0]
    if len(row) < 2:
        raise ValueError("OPEN/CLOSE control record missing a filename")
    path = context.resolve(_strip_quotes(str(row[1])))

    from flopy4.mf6.codec.reader import loads as _codec_loads

    text = path.read_text()
    wrapped = _codec_loads(f"BEGIN DATA\n{text}\nEND DATA\n")
    return wrapped.get("DATA", [])


_CONTROL_KINDS = frozenset({"CONSTANT", "INTERNAL", "OPEN/CLOSE"})


def _leading_word(part) -> str:
    """The part's first token in upper case (a control record's kind, or a
    field's name), or empty for numbers only."""
    if isinstance(part, NumberRows) or not part:
        return ""
    return str(part[0]).upper()


def _numeric_prefix(row: list) -> list:
    """Tokens from the start of `row` up to (not including) the first
    non-numeric one. Real INTERNAL/bare-data-row array data is purely
    numeric; a trailing inline annotation -- e.g. a "row 1" remark seen
    on some fixtures, one per data line, as many lines as the array has
    -- always starts with a non-numeric word, so stopping there drops
    the annotation without needing to know each line's real data width
    up front (unlike a single trailing annotation on the array's last
    line only, `_read_control_record`'s final `values[:length]` slice
    already handles that case)."""
    out = []
    for tok in row:
        if not isinstance(tok, (int, float)):
            try:
                float(tok)
            except (TypeError, ValueError):
                break
        out.append(tok)
    return out


def _factor(vrow: list, dtype) -> "int | float | None":
    """The INTERNAL/OPEN-CLOSE control record's ``FACTOR <f>`` option, if
    `vrow` has one. MF6 reads an integer array's FACTOR as an integer, so
    it's truncated to one here too."""
    tokens = [str(t) for t in vrow[1:]]
    for j, tok in enumerate(tokens):
        if tok.upper() == "FACTOR" and j + 1 < len(tokens):
            factor = float(tokens[j + 1])
            return int(factor) if dtype == np.int64 else factor
    return None


def _control_io(vrow: list, values: np.ndarray) -> ArrayIO:
    """How a control record wrote its array, to write it back the same
    way: its kind, as an `ArrayFormat`, and ``IPRN <n>``; an OPEN/CLOSE
    record's file, as written (relative to the simulation directory), and
    the hash of the `values` read from it, scaled by its FACTOR. The
    FACTOR itself isn't kept: see `ArrayIO`."""
    kind = _leading_word(vrow)
    if kind == "CONSTANT":
        return ArrayIO(format="constant")
    if kind not in ("INTERNAL", "OPEN/CLOSE"):
        return ArrayIO()
    tokens = [str(t) for t in vrow[1:]]
    iprn = None
    for j, tok in enumerate(tokens):
        if tok.upper() == "IPRN" and j + 1 < len(tokens):
            iprn = int(float(tokens[j + 1]))
            break
    if kind == "INTERNAL":
        return ArrayIO(iprn=iprn, format="internal")
    if not tokens:
        return ArrayIO(iprn=iprn)
    binary = any(t.upper() in ("BINARY", "(BINARY)") for t in tokens[1:])
    return ArrayIO(
        iprn=iprn,
        path=Path(_strip_quotes(tokens[0])),
        format="binary" if binary else "open/close",
        hash=array_hash(values),
    )


def _record_array_io(
    arrays: "dict | None", key: tuple, ios: "list[ArrayIO]", layered: bool = False
) -> None:
    """Record how an array's control records wrote it in `arrays`, by
    `ArrayKey`: whether it's LAYERED, and a single record's settings for
    the whole array; for a LAYERED one's, IPRN for the whole array if
    every layer has the same, and each layer's other settings."""
    if arrays is None or not ios:
        return
    whole = key[0] if len(key) == 1 else key
    if not layered:
        arrays[whole] = attrs.evolve(ios[0], layered=False)
        return
    iprns = {io.iprn for io in ios}
    iprn = ios[0].iprn if len(iprns) == 1 else None
    arrays[whole] = ArrayIO(iprn=iprn, layered=True)
    if iprn is not None:
        ios = [attrs.evolve(io, iprn=None) for io in ios]
    for layer, io in enumerate(ios):
        if io != ArrayIO():
            arrays[(*key, layer)] = io


def _read_control_record(
    rows: list, i: int, context: LoadContext, dtype, length: int
) -> "tuple[np.ndarray, ArrayIO, int]":
    """Read one CONSTANT/INTERNAL/OPEN-CLOSE array control record starting
    at ``rows[i]`` (a block's `parts`), for `_read_array`.

    Returns a full ``length``-element ``ndarray`` (CONSTANT broadcasts
    here rather than leaving that to the caller), scaled by its FACTOR;
    how the record wrote it (see `_control_io`); and the next row index to
    resume from. INTERNAL's (and a bare, keyword-less data row's) values
    commonly wrap across multiple physical lines for a large array -- each
    is one row here -- so both keep consuming rows until ``length`` values
    are collected, rather than assuming exactly one row.
    """
    vrow = rows[i]
    kind = _leading_word(vrow)
    if kind == "CONSTANT":
        v = int(vrow[1]) if dtype == np.int64 else float(vrow[1])
        return np.full(length, v, dtype=dtype), ArrayIO(format="constant"), i + 1
    factor = _factor(vrow, dtype)
    if kind == "OPEN/CLOSE":
        # read only the values the array needs; a file may hold more
        array = _read_open_close_values(vrow, context, dtype)[:length]
        j = i + 1
    else:
        j = i + 1 if kind == "INTERNAL" else i
        chunks: list[np.ndarray] = []
        count = 0
        while count < length and j < len(rows):
            part = rows[j]
            if isinstance(part, NumberRows):
                chunk = row_values(part, dtype)
            else:
                chunk = np.array(_numeric_prefix(part), dtype=dtype)
            chunks.append(chunk)
            count += len(chunk)
            j += 1
        array = np.concatenate(chunks)[:length] if chunks else np.array([], dtype=dtype)
    if factor is not None:
        array = array * factor
    return array, _control_io(vrow, array), j


def _from_file_index(value: np.ndarray) -> np.ndarray:
    """1-based file values to 0-based. A negative value is allowed (DISU's
    ja marks each cell's own entry that way) and means the same as positive."""
    return np.abs(value) - 1


@attrs.frozen
class _Grid:
    """The grid sizes an array's shape resolves against: the dims, with
    ``nodes`` and ``ncpl`` filled in from each other and ``nlay``."""

    dims: dict
    nlay: int
    ncpl: int

    @classmethod
    def of(cls, dims: Mapping[str, int]) -> "_Grid | None":
        """The grid of `dims`, or None if they give no cells."""
        nlay = dims.get("nlay", 1)
        # a component with cells but no layers of its own has only ncpl (NCF)
        nodes = dims.get("nodes") or nlay * dims.get("ncpl", 0)
        if not nodes:
            return None
        ncpl = nodes // nlay if nlay else nodes
        return cls({"nodes": nodes, "ncpl": ncpl, **dims}, nlay or 1, ncpl)

    def size(self, f: Any) -> int:
        """How many values the array field `f` holds: its DFN shape (one
        dimension, e.g. DIS's `delr` is ``(ncol,)``, `botm` ``(nodes,)``)
        resolved against the dims, else every node. An unknown field's
        array is a layer's (a G/A package's)."""
        if f is None:
            return self.ncpl
        shape = f.metadata.get("shape") or ()
        name = shape[-1] if isinstance(shape, (tuple, list)) and shape else shape
        return self.dims.get(name) or self.dims["nodes"]


def _read_array(
    rows: list,
    i: int,
    f: Any,
    grid: _Grid,
    context: LoadContext,
    layered: bool,
) -> "tuple[np.ndarray | None, list[ArrayIO], int]":
    """Read the array field `f`'s control record(s) from ``rows[i]`` (a
    block's `parts`) on: one, or with `layered` (its name row said
    LAYERED), one per layer. Returns the array, flat and as long as the
    field's shape says (see `_Grid.size`), or None if there's no record;
    how each record wrote it; and the next row index. `f` is None for an
    unknown field, whose records are read only to skip them."""
    dtype = np.int64 if f is not None and to_field_type(f.type) == "integer" else np.float64
    size = grid.size(f)
    ios: list[ArrayIO] = []
    if layered:
        # Read as many per-layer control records as are actually there,
        # rather than assuming exactly `nlay` -- some real-world files
        # (mf5to15-converted ones observed so far) tag a field LAYERED
        # with fewer rows than nlay (e.g. a single-row TOP); trusting
        # nlay blindly would consume the next field's name row as if
        # it were layer data. Stops at the first row that isn't a
        # recognized control record -- i.e. the next field's row.
        #
        # A record is a layer's (ncpl values), or the whole field's if
        # it's smaller (delr/delc/top tagged LAYERED despite not truly
        # being layered): reading ncpl there would consume however many
        # subsequent lines (including the next field's own name row) it
        # takes to reach ncpl values.
        record = min(grid.ncpl, size)
        layers = []
        while i < len(rows) and _leading_word(rows[i]) in _CONTROL_KINDS:
            value, io, i = _read_control_record(rows, i, context, dtype, record)
            layers.append(value)
            ios.append(io)
        if not layers:
            return None, ios, i
        # fewer records than layers repeat, to fill the field
        values = np.concatenate(layers).astype(dtype)
        if values.size and values.size < size:
            values = np.resize(values, size)
    else:
        if i >= len(rows):
            return None, ios, i
        values, io, i = _read_control_record(rows, i, context, dtype, size)
        ios.append(io)
    if f is not None and f.metadata.get("index"):
        values = _from_file_index(values)
    return values, ios, i


def _is_layered(row: list) -> bool:
    """Whether an array's name row says LAYERED."""
    return any(str(t).upper() == "LAYERED" for t in row[1:])


def _self_dims_from_kwargs(kwargs: dict) -> dict:
    """Derive grid dimensions from a component's own just-parsed DIMENSIONS
    block (already in `kwargs` from Pass 1) -- needed when structuring a
    `DimensionProvider` itself (Dis/Disv/...): its GRIDDATA block has to be
    parsed before an instance -- and thus `get_dims()` -- exists, and
    before it's registered as a sibling dims source for anyone else. A
    no-op ({}) for any other class, which simply has none of these fields.
    """
    keys = ("nlay", "nrow", "ncol", "ncpl", "nvert", "nodes", "nja")
    local = {k: kwargs[k] for k in keys if isinstance(kwargs.get(k), int)}
    if "ncpl" not in local and "nrow" in local and "ncol" in local:
        local["ncpl"] = local["nrow"] * local["ncol"]
    if "nodes" not in local and "nlay" in local and "ncpl" in local:
        local["nodes"] = local["nlay"] * local["ncpl"]
    return local


def _names(value: Any) -> list[str]:
    """A string-array field's entries (AUXILIARY's names), or none."""
    return [] if value is None else [str(v) for v in np.atleast_1d(value)]


def _apply_binding_terms(child: Any, terms: list, models: list) -> None:
    """Set the child's reference fields from the rest of its row, in
    order: a single one takes a term, a list the rest."""
    # the models loaded so far, so a loaded exchange or solution holds
    # them as a built one does; unknown names stay
    found = resolve([str(t) for t in terms], models)
    for f in child._reference_fields():
        if not found:
            break
        if f.metadata["many"]:
            value, found = found, []
        else:
            value, found = found[0], found[1:]
        setattr(child, f.name, value)


def _disambiguate_ga_variant(candidates: "list[type[Component]]", path: Path) -> "type[Component]":
    """
    Pick between a base package class and its G/A-variant sibling
    when both share one namefile ftype, by peeking at the package file's
    options (READASARRAYS or READARRAYGRID), which come before any other
    block; the rest of the file isn't read.
    """
    is_variant = False
    with path.open() as f:
        for line in f:
            text = line.upper()
            words = text.split()
            if words[:2] == ["END", "OPTIONS"] or (
                words[:1] == ["BEGIN"] and words[1:2] != ["OPTIONS"]
            ):
                break
            if "READASARRAYS" in text or "READARRAYGRID" in text:
                is_variant = True
                break
    for c in candidates:
        suffixed = len(c.__name__) == 4 and c.__name__[-1] in ("g", "a")
        if suffixed == is_variant:
            return c
    return candidates[0]


def _exchange_models(model_names: list, models: list) -> tuple[Any, Any] | None:
    """The models an exchange row names, looked up case-insensitively
    (as MF6 does) among those loaded so far, or None if either isn't."""
    by_name = {str(model.name).lower(): model for model in models}
    found = [by_name.get(str(name).lower()) for name in model_names[:2]]
    if len(found) < 2 or None in found:
        return None
    return found[0], found[1]


def _resolve_bindings(cls: type, rows_by_block: dict, context: LoadContext) -> dict[str, Any]:
    """Resolve the rows naming children (a model's packages, the
    simulation's models, exchanges and solutions), by block, into loaded
    child component instances, keyed by field name -- merged
    into `structure_component`'s kwargs so children are attached the same
    way manual construction already attaches them (`Gwf(dis=Dis(...))`).

    The child fields are `binding_fields`', by block, since several
    fields can share one (every `Gwf` package field shares
    `"packages"`); egress's `_Unstructure.bindings` is the inverse. Within a block,
    `DimensionProvider` targets (`dis`/`disv`/`disu`) are resolved first so
    their dims can be threaded into the context of that block's other
    children -- `dimensions.py`'s object-graph walk only helps once a child
    is already attached, not while its siblings are still loading. An
    exchange's context gets the models it connects, from the models block,
    loaded before the exchanges block (field order).
    """
    from flopy4.mf6.converter.binding import component_ftype
    from flopy4.mf6.exchange import Exchange
    from flopy4.mf6.model import Model
    from flopy4.mf6.solution import Solution

    # Model scope to prefer when resolving this class's own binding rows'
    # ftype tokens via get_ftype() below -- e.g. structuring a Gwf's
    # "packages" block should resolve "DIS6" to gwf's own Dis, not gwt's/
    # gwe's/prt's.
    # A Model class's __module__ is "flopy4.mf6.<model>" (defined directly
    # in that subpackage's __init__.py), not "...<model>.<name>" like its
    # child packages, so this can't reuse component.py's _model_prefix --
    # a Model's own class name *is* its model prefix by convention.
    model_prefix = cls.__name__.lower() if issubclass(cls, Model) else None

    kwargs: dict[str, Any] = {}
    for block_name, field_specs in binding_fields(cls).items():
        rows = rows_by_block.get(block_name)
        if not rows:
            continue

        # Resolve each row's target class + owning field up front, so rows
        # can be reordered (dims providers first) without re-parsing.
        resolved = []
        for row in rows:
            if not row:
                continue
            token = str(row[0]).lower()
            for child_field, kind, accepted in field_specs:
                # Concrete candidates first: compare each accepted class's
                # own ftype directly to the row's token. G/A-variant pairs
                # (Chd/Chdg, Rch/Rcha, ...) share one namefile ftype (real
                # MF6 has no separate 'CHDG6' case, only 'CHD6' -- see
                # component_ftype()'s docstring), so more than one concrete
                # candidate can match; disambiguate from the file content.
                concrete = [c for c in accepted if ABC not in c.__bases__]
                matches = [c for c in concrete if component_ftype(c).lower() == token]
                if len(matches) > 1:
                    target_cls = _disambiguate_ga_variant(matches, context.resolve(str(row[1])))
                elif matches:
                    target_cls = matches[0]
                else:
                    # Fall back to the ftype registry for abstract-typed
                    # fields (Model/Exchange/Solution), where the
                    # field's declared type can't be compared to a token
                    # directly.
                    resolved_cls = get_ftype(token, prefix=model_prefix)
                    if resolved_cls is None or not any(
                        issubclass(resolved_cls, t) for t in accepted
                    ):
                        continue
                    target_cls = resolved_cls

                resolved.append((row, target_cls, child_field.name, kind))
                break
            else:
                # a package flopy4 has no class for yet, say
                warnings.warn(
                    f"{cls.__name__}: no field takes {block_name} entry "
                    f"{str(row[0]).upper()} ({row[1] if len(row) > 1 else ''}), skipped",
                    UserWarning,
                    stacklevel=2,
                )

        resolved.sort(key=lambda r: 0 if issubclass(r[1], DimensionProvider) else 1)

        dims: dict = {}
        collectors: dict[str, Any] = {}
        for row, target_cls, child_name, kind in resolved:
            fname = str(row[1])
            # A row's third+ terms mean different things by target kind (see
            # _apply_binding_terms): for a plain Model/Package they're the
            # pname, passed through as name= and preserved directly on the
            # loaded child's own .name attribute; for Exchange/Solution
            # they're real semantic data (coupled model names / applicable
            # models), not a name to assign the loaded child itself.
            # an empty pname is none
            pname = (
                str(row[2]) or None
                if len(row) > 2 and not issubclass(target_cls, (Exchange, Solution))
                else None
            )
            child_context = attrs.evolve(
                context,
                dims=dims,
                parent=None,
                exchange=(
                    _exchange_models(row[2:], kwargs.get("models", []))
                    if issubclass(target_cls, Exchange)
                    else None
                ),
            )
            child = target_cls.load(context.resolve(fname), name=pname, context=child_context)
            child.filename = Path(fname)
            _apply_binding_terms(child, row[2:], kwargs.get("models", []))
            if isinstance(child, DimensionProvider):
                dims = {**dims, **child.get_dims()}

            if kind == "only":
                collectors[child_name] = child
            elif kind == "list":
                collectors.setdefault(child_name, []).append(child)

        kwargs.update(collectors)

    return kwargs


def _union_forms(parent: "type | None") -> Callable[[Mapping[str, Any]], Any] | None:
    """The forms a child's untagged union columns take (OBS's ids), by the
    row's observation type, from the parent's table (see _read_unions)."""
    table = getattr(parent, "observations", None)
    if not table:
        return None
    return lambda row: table.get(str(row.get("obstype", "")).lower())


def _union_arm(parent: "type | None") -> str:
    """The arm a child's untagged union columns prefer for numbers (OBS's
    ids) when their forms are unknown (see _union_forms): an index under an
    exchange or a package keyed by one (LAK's lake number, a pk column),
    else a cellid."""
    from flopy4.mf6.exchange import Exchange

    if parent is None:
        return "cellid"
    if issubclass(parent, Exchange):
        return "index"
    for f in attrs.fields(cast(type[attrs.AttrsInstance], parent)):
        item = item_list_type(f.type)
        for c in item if isinstance(item, tuple) else (item,) if item else ():
            if any(g.metadata.get("pk") for g in c.fields()):
                return "index"
    return "cellid"


def _load_file_child(field: Any, path: Path, context: LoadContext) -> Any:
    """Load the child a file record or row names (DIS's ``NCF6 FILEIN
    <path>``, LAK's ``ifno TAB6 FILEIN <path>``), picking SPC or SPCA by
    the file's content. Like MF6, the path resolves against the
    simulation directory (the context's workspace), not the directory of
    the file naming it. `context` is the child's: its parent is the class
    whose file names it."""
    from flopy4.attrs_xarray import child_field_candidates

    spec = child_field_candidates(field)
    assert spec is not None
    file = context.resolve(path)
    candidates = list(spec[1])
    child_cls = _disambiguate_ga_variant(candidates, file) if len(candidates) > 1 else candidates[0]
    assert issubclass(child_cls, Package)
    child = child_cls.load(file, context=context)
    child.filename = path
    return child


def read_component(
    path: Path, cls: "type[Component]", *, context: LoadContext, name: str | None = None
) -> Any:
    """Read the MF6 input file ``path`` into a ``cls``, with the context's
    loader (see ``LoadContext.loader``)."""
    from flopy4.mf6.codec.reader import load, loads_typed
    from flopy4.mf6.converter.ingress import typed

    with open(path) as fp:
        if context.loader == "typed":
            parsed = loads_typed(fp.read(), cls.dfn_name)
            return typed.structure_typed(parsed, cls, context=context, name=name)
        raw = load(fp)
    return structure_component(raw, cls, context=context, name=name)


def _init_key(f: attrs.Attribute) -> str:
    """The `__init__` argument setting the field `f`: its alias (a private
    field's name without the underscore, as ``stress_period_data``), else
    its name."""
    return f.alias or f.name


def _is_grid_array(f: Any) -> bool:
    """Whether `f` holds a numeric array read with control records
    (griddata, a G/A period's, a TAS time's), not inline (AUXILIARY's)."""
    return is_array(f) and to_field_type(f.type) in ("integer", "double")


def _per_header(f: attrs.Attribute) -> bool:
    """Whether the field `f`, of a repeating block, holds a value per
    header (a period's, a time's, an OBS output file's), not one."""
    return get_origin(unwrap_optional(f.type)) is dict or block_list_type(f.type) is not None


def _header(block: Any, tokens: list[str]) -> Any:
    """A repeating block's header, from the words after its name: IPER as
    a 0-based period, another number as one, a record (OBS's ``FILEOUT
    <name>``) as its words, case kept. Raises ValueError if there are
    none, or the number doesn't parse."""
    if not tokens:
        raise ValueError("no header")
    field = block.header.field
    if field.type == "integer":
        value = int(tokens[0])
        return value - 1 if field.name == "iper" else value
    if field.type == "double":
        return float(tokens[0])
    return tuple(tokens)


def _occurrences(raw: dict, cls: type) -> dict[str, dict[Any, list]]:
    """The file's blocks by DFN block name, each as ``{None: rows}``, or for
    a repeating block ``{header: rows}`` (see `_header`) in file order. MF6
    ignores a block it doesn't read (an old IMS file's XMD), so one that
    isn't in the DFN warns and is skipped; so, silently, is a repeating
    one whose header doesn't parse."""
    blocks = dfn(cls).blocks or {}
    found: dict[str, dict[Any, list]] = {}
    for raw_name, rows in raw.items():
        name, *tokens = raw_name.lower().split()
        if (block := blocks.get(name)) is None:
            if rows:
                warnings.warn(f"{cls.__name__}: ignoring unknown block {raw_name.upper()}")
            continue
        header = None
        if block.header is not None:
            try:
                header = _header(block, raw_name.split()[1:])
            except ValueError:
                continue
        found.setdefault(name, {})[header] = rows
    return found


def _period_array(
    value: np.ndarray, ios: "list[ArrayIO]", f: Any, grid: _Grid, layered: bool
) -> np.ndarray:
    """A G/A period's array as the field holds it (see
    flopy4.mf6.period_arrays): a LAYERED one by layer, a CONSTANT one as
    its value (0-d, as a scalar given at construction is), a nodes-shaped
    one by layer, else flat."""
    if layered:
        return value.reshape(-1, grid.ncpl)  # (nlay, ncpl)
    if ios[0].format == "constant":
        return np.asarray(value[0])
    if (f.metadata.get("shape") or ("",))[-1] == "nodes" and grid.nlay > 1:
        return value.reshape(grid.nlay, grid.ncpl)
    return value


class ComponentLoad:
    """What any loader's read of one component's file builds: its
    `__init__` arguments, so far; how the file wrote each array; and the
    rows naming children, for `_resolve_bindings`. Its fields are read a
    block at a time in file-schema order, options and dimensions first, so
    a block can read by those before it (the auxiliary names, the sizes
    and switches of a list's columns, a dims provider's own dims)."""

    def __init__(self, cls: type, context: LoadContext) -> None:
        self.cls = cls
        self.context = context
        self.kwargs: dict[str, Any] = {}
        # how the file wrote each array, by `ArrayKey`, for the instance's
        # write_context
        self.array_ios: dict = {}
        self.bindings: dict[str, list] = {}
        self._children: dict[Path, Any] = {}
        self._union_arm = _union_arm(context.parent)
        self._union_forms = _union_forms(context.parent)
        # the child fields named by each block's rows
        self.binding_blocks = binding_fields(cls)

    @property
    def dims(self) -> dict:
        """The grid's dims: the context's, or for a dims provider, which
        has none yet, its own (see `_self_dims_from_kwargs`)."""
        return dict(self.context.dims) or _self_dims_from_kwargs(self.kwargs)

    def finish(self, name: str | None = None) -> Any:
        """The component, from the arguments read, with its children
        loaded from the rows naming them and its arrays written back the
        way the file wrote them."""
        kwargs = self.kwargs
        if self.context.workspace and self.bindings:
            kwargs.update(_resolve_bindings(self.cls, self.bindings, self.context))
        if name is not None:
            kwargs["name"] = name
        if self.array_ios:
            kwargs["write_context"] = WriteContext(arrays=self.array_ios)
        return self.cls(**kwargs)

    def read_blocks(
        self,
        name: str,
        fields: list,
        found: dict[Any, Any],
        *,
        numbered: bool,
        fill_forward: bool,
    ) -> None:
        """Read the occurrences of the block `name`, ``{header: contents}``
        (``{None: contents}`` for a block that doesn't repeat), into the
        arguments: its `fields`' values, or a repeating block's by header,
        in order if `numbered`. An empty occurrence of a `fill_forward`
        block (a period) clears its lists and, for a grid package, its
        arrays. `body` reads each occurrence's contents."""
        if None in found:
            for f, value in self.body(name, found[None], None).items():
                self.kwargs[_init_key(f)] = value
            return
        if len(found) > 1 and not any(_per_header(f) for f in fields):
            # several solution groups, each with its own MXITER, would be
            # merged into one, which MF6 runs differently
            names = ", ".join(f"{name.upper()} {h}" for h in found)
            raise ValueError(
                f"{self.cls.__name__}: more than one {name} block ({names}); only one is supported"
            )
        values: dict[attrs.Attribute, dict] = {}
        for header in sorted(found) if numbered else found:
            if contents := found[header]:
                body = self.body(name, contents, header)
            elif fill_forward:
                body = self.cleared(fields)
            else:
                body = {}
            for f, value in body.items():
                values.setdefault(f, {})[header] = value
        for f in fields:
            if (blocks := block_list_type(f.type)) is not None:
                header_cls, list_name, _ = blocks.parts()
                self.kwargs[_init_key(f)] = [
                    blocks(
                        **{
                            blocks._header: header_cls.from_tokens(list(header)),
                            list_name: values.get(f, {}).get(header) or [],
                        }
                    )
                    for header in found
                ]
            elif f in values:
                by_header = values[f]
                self.kwargs[_init_key(f)] = (
                    by_header if _per_header(f) else next(iter(by_header.values()))
                )

    def body(self, name: str, contents: Any, header: Any) -> dict:
        """The values of one occurrence of the block `name`, by field."""
        raise NotImplementedError

    def cleared(self, fields: list) -> dict:
        """An empty period's values: no rows for each list, and for a grid
        package, no array."""
        lists: dict[Any, Any] = {f: [] for f in fields if item_list_type(f.type) is not None}
        if not is_grid_package(self.cls):
            return lists
        return lists | {f: None for f in fields if _is_grid_array(f) and not f.metadata.get("fk")}

    def parse_list(self, rows: list, item_cls: Any, words: tuple[str, ...] = ()) -> Any:
        """A list field's value from its rows, with the sizes (aux by
        auxiliary, GNC's alphasj by numalphaj) and switches (boundnames)
        of its columns read so far."""
        sizes = {}
        for shape in sized_by(item_cls):
            n = dim_value(shape, lookup=lambda name: dim_lookup(self.kwargs, name))
            if n is not None:
                sizes[shape] = n
        enabled = frozenset(o for o in conditional_fields(item_cls).values() if self.kwargs.get(o))
        return _parse_rows(
            rows,
            item_cls,
            sizes=sizes,
            enabled=enabled,
            # the grid's dims give the cellids' width (see LoadContext.ncelldim)
            context=attrs.evolve(self.context, dims=self.dims),
            union_arm=self._union_arm,
            union_forms=self._union_forms,
            load_child=self.load_child,
            words=words,
        )

    def load_child(self, f: Any, token: str) -> Any:
        """A row's child column (LAK's TAB6 file), loaded from its file,
        once per file (SFR's periods may name one table again)."""
        path = Path(_strip_quotes(token))
        if path not in self._children:
            context = attrs.evolve(self.context, dims=self.dims, parent=self.cls)
            self._children[path] = _load_file_child(f, path, context)
        return self._children[path]


class _Load(ComponentLoad):
    """The basic loader's read of one component's file, a block at a time
    in DFN order (see `ComponentLoad`)."""

    def __init__(self, cls: type, context: LoadContext) -> None:
        super().__init__(cls, context)
        self._fields = attrs.fields_dict(cls)
        self._names = attr_names(cls)

    def attribute(self, block: str, f: Any) -> "attrs.Attribute | None":
        """The class's field holding the DFN field `f` of `block`, if it
        has one: not a computed one (a list package's MAXBOUND) or one
        codegen leaves out."""
        a = self._fields.get(self._names.get((block, f.name), ""))
        return a if a is not None and a.init is not False else None

    def value_at(self, path: str) -> Any:
        """The value read so far for the DFN field at `path` (``block.field``)."""
        block, name = path.split(".", 1)
        a = self._fields.get(self._names.get((block, name), ""))
        return None if a is None else self.kwargs.get(_init_key(a))

    def read(self, name: str, block: Any, found: dict[Any, list]) -> None:
        """Read the occurrences of the DFN block `block` into the
        arguments (see `ComponentLoad.read_blocks`)."""
        fields = [a for f in block.fields.values() if (a := self.attribute(name, f)) is not None]
        header = block.header
        self.read_blocks(
            name,
            fields,
            found,
            numbered=header is not None and header.field.type in ("integer", "double"),
            fill_forward=header is not None and bool(header.fill_forward),
        )

    def body(self, name: str, rows: list, header: Any) -> dict:
        """The values of one occurrence of the block `name`, by field. A
        row whose first word is a tagged field's key is that field's; the
        rest are the block's untagged field's, or name children (see
        `_resolve_bindings`). A tagged list collects its rows. An unknown
        word warns, and the rows after it that aren't another field's (its
        array's control records, say) are skipped."""
        keys = block_keys(self.cls, name)
        rows = _resolve_open_close_rows(rows, self.context)
        binds = name in self.binding_blocks
        untagged = self.attribute(name, keys.untagged) if keys.untagged else None
        if not keys.tagged and not keys.dynamic:
            if binds:
                self.bindings.setdefault(name, []).extend(rows)
                return {}
            value = None if untagged is None else self.untagged(untagged, rows)
            return {} if value is None else {untagged: value}

        values: dict[attrs.Attribute, Any] = {}
        lists: dict[attrs.Attribute, list] = {}
        rest: list = []
        rows = parts(rows)
        i = 0
        while i < len(rows):
            row = rows[i]
            found = self.field_of(keys, row) if row else None
            if found is None:
                if not row:
                    pass
                elif binds or keys.untagged is not None:
                    rest.extend(row if isinstance(row, NumberRows) else [row])
                elif _leading_word(row) not in _CONTROL_KINDS and not isinstance(
                    row[0], (int, float)
                ):
                    self.unknown(name, row)
                i += 1
                continue
            f, aux_name = found
            a = self.attribute(name, f)
            if a is None or (
                a.metadata.get("direction")
                and str(row[1] if len(row) > 1 else "").upper() not in ("FILEIN", "FILEOUT")
            ):
                # a file record has its direction token, so OC's "HEAD
                # PRINT_FORMAT ..." isn't the "HEAD FILEOUT <path>" record
                self.unknown(name, row)
                i += 1
            elif _is_grid_array(a):
                i = self.array(a, aux_name, rows, i, header, values)
            elif item_list_type(a.type) is not None:
                lists.setdefault(a, []).append(row)
                i += 1
            elif a.metadata.get("_keyword"):
                self.file(a, row, values)
                i += 1
            else:
                values[a] = _tagged_value(a, row)
                i += 1
        for a, list_rows in lists.items():
            item_cls = item_list_type(a.type)
            value = self.parse_list(list_rows, item_cls, item_list_words(a.type))
            if value is not None:
                values[a] = value
        if binds:
            self.bindings.setdefault(name, []).extend(rest)
        elif untagged is not None and rest:
            if (value := self.untagged(untagged, rest)) is not None:
                values[untagged] = value
        return values

    def field_of(self, keys: BlockKeys, row: Any) -> "tuple[Any, str | None] | None":
        """The DFN field whose row `row` is, by its first word, with the
        name a dynamic key gives (an auxiliary variable's); None for a row
        of numbers, or a word no field's. A dynamic key wins: an auxiliary
        name that matches a field's (Q) is the aux array, as in MF6. Where
        a word begins several fields' rows (OC's HEAD), the next one tells
        them apart."""
        word = _leading_word(row).lower()
        if not word:
            return None
        for path, f in keys.dynamic.items():
            for n in _names(self.value_at(path)):
                if n.lower() == word:
                    return f, n
        candidates = keys.tagged.get(word, ())
        if len(candidates) > 1:
            following = str(row[1]).lower() if len(row) > 1 else ""
            candidates = tuple(f for f in candidates if following in following_tags(f)) or tuple(
                f for f in candidates if not following_tags(f)
            )
        return (candidates[0], None) if candidates else None

    def unknown(self, name: str, row: list) -> None:
        """Warn of a row no field of the block `name` takes. MF6 rejects a
        keyword it doesn't know, so this is likely one flopy4 doesn't
        support yet. A computed one (a list package's MAXBOUND) is
        derived, not read."""
        key = str(row[0])
        if not isinstance(getattr(self.cls, key.lower(), None), property):
            warnings.warn(
                f"{self.cls.__name__}: no field takes {name.upper()} entry {key.upper()}, skipped",
                UserWarning,
                stacklevel=4,
            )

    def array(
        self, f: Any, aux_name: "str | None", rows: list, i: int, header: Any, values: dict
    ) -> int:
        """Read the grid array `f` named on ``rows[i]`` into `values`, and
        how the file wrote it, by `ArrayKey`, into `array_ios`; an
        auxiliary variable's (`aux_name`) into `f`'s value by that name.
        Returns the next row's index. A field can come from a time-array
        series, by name -- ``RECHARGE TIMEARRAYSERIES <name>`` -- instead
        of a control record on the next row; its value keeps the name
        (see flopy4.mf6.period_arrays)."""
        row = rows[i]
        if (grid := _Grid.of(self.dims)) is None:
            return i + 1
        tokens = [str(t) for t in row[1:]]
        tas = next(
            (j for j, t in enumerate(tokens) if t.upper() in ("TIMEARRAYSERIES", "TAS6")), None
        )
        value: Any
        if tas is not None:
            if not f.metadata.get("time_series") or tas + 1 >= len(tokens):
                return i + 1
            value, i = TimeArraySeriesRef(tokens[tas + 1]), i + 1
        else:
            # An array is layered only when given with LAYERED (the dfn's
            # `layered` flag just allows it); otherwise it covers the
            # field's whole shape, all nodes for a grid package.
            layered = _is_layered(row)
            value, ios, i = _read_array(rows, i + 1, f, grid, self.context, layered)
            if aux_name is None:
                key = (f.name,) if header is None else (f.name, header)
                _record_array_io(self.array_ios, key, ios, layered=layered)
            if value is None:
                return i
            if header is not None:
                value = _period_array(value, ios, f, grid, layered)
        if aux_name is None:
            values[f] = value
        else:
            values.setdefault(f, {})[aux_name] = value
        return i

    def file(self, f: Any, row: list, values: dict) -> None:
        """A file record's value (``KEYWORD [FILEIN|FILEOUT] <path>``) into
        `values`: its path, or the child loaded from it. A list of them (a
        DFN tagged list of file records) gets one element per row."""
        has_direction = len(row) > 1 and str(row[1]).upper() in ("FILEIN", "FILEOUT")
        tokens = row[2:] if has_direction else row[1:]
        if not tokens:
            return
        path = Path(_strip_quotes(str(tokens[0])))
        value = (
            _load_file_child(f, path, attrs.evolve(self.context, parent=self.cls))
            if f.metadata.get("child")
            else path
        )
        if get_origin(unwrap_optional(f.type)) is list:
            values.setdefault(f, []).append(value)
        else:
            values[f] = value

    def untagged(self, f: Any, rows: list) -> Any:
        """The value of a block's untagged field from its rows: a list's
        elements (an OBS output file's, for a list of blocks), or a TAS
        time's array, a control record with no name row."""
        if (item_cls := item_list_type(f.type)) is not None:
            return self.parse_list(rows, item_cls, item_list_words(f.type))
        if (blocks := block_list_type(f.type)) is not None:
            return self.parse_list(rows, blocks.parts()[2])
        if _is_grid_array(f) and (grid := _Grid.of(self.dims)) is not None:
            value, _, _ = _read_array(parts(rows), 0, f, grid, self.context, layered=False)
            return value
        return None


def structure_component(
    raw: dict,
    cls: type,
    *,
    context: LoadContext | None = None,
    name: str | None = None,
) -> Any:
    """Reconstruct a component instance from a raw parsed MF6 input dict.

    The file's blocks are read in the order of ``cls``'s DFN, whose
    options and dimensions blocks come first (see `_Load`). Each row goes
    to the field of its block whose key it begins with, else to the
    block's untagged field; a repeating block's values are kept by header
    (see `_occurrences`). The rows naming children are resolved last (see
    `_resolve_bindings`).

    Parameters
    ----------
    raw : dict
        Output of ``loads()`` — {BLOCK_NAME_UPPER: list_of_token_rows}.
    cls : type
        The component class to instantiate.
    context : LoadContext, optional
        Where the file sits in the simulation: the workspace relative
        paths resolve against, the grid dims (e.g. {"nlay": 3, "nodes":
        675}) array shapes and cellid widths come from, the class of the
        component whose file named this one (see `_union_arm`), and the
        models an exchange connects. Its children's contexts derive from
        it. Without one, there are no dims and no workspace, so a file
        that names others (a namefile, OPEN/CLOSE) can't be read.
    name : str, optional
        Explicit component name (e.g. a namefile binding row's pname),
        overriding the component's default auto-assigned name. Not
        derivable from the file's own content -- passed down by a
        parent's `_resolve_bindings` call when loading this component
        as a child.

    Returns
    -------
    Component instance.
    """
    context = context or LoadContext()
    load = _Load(cls, context)
    found = _occurrences(raw, cls)
    for block_name, block in (dfn(cls).blocks or {}).items():
        if block_name in found:
            load.read(block_name, block, found[block_name])

    return load.finish(name)
