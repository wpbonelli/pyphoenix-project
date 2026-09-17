"""Base class for generated MF6 inner-class record types.

Item (item.py) subclasses Record and adds what a table row needs beyond
this: index/pk/fk renumbering, cellid packing, aux/boundname, and external
parse context. Record itself has none of that -- just a keyword-tagged or
positional compound value.

A Record can also compose another Record (a DFN record nested inside
another) rather than flattening the nested one's fields into itself --
see _nested_class, inferred from the field's own type annotation rather
than a declared flag, and make.py's _build_record_class_specs.

Generated Record/Item subclasses are `pydantic.dataclasses.dataclass`, not
`attrs.define` -- `record_fields()`/`_nested_class()` below read
`__pydantic_fields__`/`FieldInfo.json_schema_extra` accordingly. A nested/
composed field's annotation (e.g. `Headprint.formatrecord: "Oc.Format"`) is
a forward-reference string naming a SIBLING class inside the same enclosing
package class -- unresolvable via any module-global lookup at class-body-
execution time (Python class bodies can't see sibling names in an enclosing
class's scope). Unlike attrs (which leaves this unresolved forever, forcing
a qualname-walking string resolver), pydantic resolves it lazily and
self-heals on first construction -- `record_fields()`'s guarded
`rebuild_dataclass()` call handles the one case that doesn't self-heal on
its own: something (like `from_tokens()`) inspecting a class's fields
before any instance of it has ever been built.
"""

from __future__ import annotations

import types
from pathlib import Path
from typing import Any, Union, get_args, get_origin

from pydantic import ConfigDict
from pydantic.dataclasses import rebuild_dataclass

CFG = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True, extra="forbid")


def keyword_of(cls: type) -> str:
    return vars(cls).get("_keyword", "")


def record_fields(cls: type) -> dict[str, Any]:
    """Non-private fields of a Record (or Item) class, in declaration
    order, keyed by name -- each value a pydantic `FieldInfo`.

    Guards with a `rebuild_dataclass()` call so a nested/composed field's
    annotation is the real class, not a stale `ForwardRef`, even when
    called before any instance of `cls` has ever been constructed (exactly
    what `from_tokens()` does).
    """
    if not cls.__pydantic_complete__:  # type: ignore[attr-defined]
        rebuild_dataclass(cls, force=True, _parent_namespace_depth=4)  # type: ignore[arg-type]
    return {n: f for n, f in cls.__pydantic_fields__.items() if not n.startswith("_")}  # type: ignore[attr-defined]


def _nested_class(cls: type, annotation: Any) -> "type[Record] | None":
    """If a field's (already-resolved) annotation is -- or wraps, via
    `Optional[...]` -- a Record subclass, return it; else None.
    Resolvability against a real Record subclass is itself the signal, no
    declared "is this nested" flag needed.

    Replaces the attrs original's qualname-walking string resolver
    entirely: by the time `record_fields()` above has run, `annotation`
    (a pydantic `FieldInfo.annotation`) IS the real class object already,
    not a string -- no `sys.modules`/qualname lookup needed.
    """
    args = get_args(annotation)
    candidate = next((a for a in args if a is not type(None)), annotation)
    return candidate if isinstance(candidate, type) and issubclass(candidate, Record) else None


def _is_bool_field(finfo: Any) -> bool:
    t = finfo.annotation
    origin = get_origin(t)
    if origin is types.UnionType or origin is Union:
        t = next((a for a in get_args(t) if a is not type(None)), t)
    return t is bool


def _coerce(token: Any, finfo: Any) -> Any:
    """Cast a raw token to a field's declared type (time_series falls back
    to the raw string if it isn't a float). Only Optional[X] (a single
    non-None union arm) is unwrapped -- a genuine multi-type union like
    Union[float, str] is deliberately ambiguous and left as the raw token."""
    meta = finfo.json_schema_extra or {}
    if isinstance(meta, dict) and meta.get("time_series"):
        try:
            return float(token)
        except (ValueError, TypeError):
            return str(token)
    t = finfo.annotation
    origin = get_origin(t)
    if origin is types.UnionType or origin is Union:
        args = [a for a in get_args(t) if a is not type(None)]
        if len(args) != 1:
            return token
        t = args[0]
    if t is int:
        return int(float(str(token)))
    if t is float:
        return float(token)
    if t is Path:
        return Path(token)
    return token


def _is_tagged(finfo: Any) -> bool:
    meta = finfo.json_schema_extra or {}
    return bool(isinstance(meta, dict) and meta.get("tagged"))


def _tagged_tokens(name: str, v: Any) -> list:
    """Bare ``NAME`` for a true bool flag, ``NAME value`` otherwise."""
    if isinstance(v, bool):
        return [name.upper()] if v else []
    return [name.upper(), v]


def _consume_tagged(tokens: list, i: int, name: str, finfo: Any) -> "tuple[Any, int] | None":
    """Match field `name`'s tagged keyword at tokens[i]; a bool field needs
    no value token, anything else does. None if unmatched or value
    missing."""
    if str(tokens[i]).upper() != name.upper():
        return None
    if _is_bool_field(finfo):
        return True, 1
    if i + 1 >= len(tokens):
        return None
    return _coerce(tokens[i + 1], finfo), 2


class Record:
    """Mixin for generated inner-class record types.

    Provides symmetric :meth:`to_tokens`/:meth:`from_tokens`.
    """

    def to_tokens(self) -> tuple:
        inner_cls = type(self)
        keyword = keyword_of(inner_cls)
        tokens: list = [keyword.upper()] if keyword else []
        for tok in vars(inner_cls).get("_extra_tokens", ()):
            tokens.append(tok)
        all_fields = record_fields(inner_cls)
        tagged = [(n, f) for n, f in all_fields.items() if _is_tagged(f)]
        untagged = [(n, f) for n, f in all_fields.items() if not _is_tagged(f)]
        for name, finfo in tagged + untagged:
            v = getattr(self, name)
            if v is None:
                continue
            if isinstance(v, Record):
                tokens.extend(v.to_tokens())
            elif _is_tagged(finfo):
                tokens.extend(_tagged_tokens(name, v))
            elif isinstance(v, bool):
                if v:
                    tokens.append(name.upper())
            else:
                tokens.append(v)
        return tuple(tokens)

    @classmethod
    def from_tokens(cls, tokens: "str | list[str]") -> "Record":
        """Parse a token string/list back into an instance.

        Tagged fields are matched by keyword wherever it appears; whatever's
        left fills required tagged fields (not keyword-matched) then plain
        fields, in declaration order. E.g. for ``Oc.Headprint``, these are
        all equivalent: ``"HEAD PRINT_FORMAT COLUMNS 10 WIDTH 12 DIGITS 6
        exponential"``, ``"COLUMNS 10 WIDTH 12 DIGITS 6 exponential"``,
        ``"exponential"``.
        """
        if isinstance(tokens, str):
            tokens = tokens.split()

        skip: list[str] = []
        if kw := keyword_of(cls):
            skip.append(kw.upper())
        skip.extend(t.upper() for t in vars(cls).get("_extra_tokens", ()))
        if [t.upper() for t in tokens[: len(skip)]] == skip:
            tokens = tokens[len(skip) :]

        all_fields = record_fields(cls)

        nested_fields = [
            (n, f) for n, f in all_fields.items() if _nested_class(cls, f.annotation) is not None
        ]
        if nested_fields:
            # A record composed of nested record(s) has, in the current
            # corpus, no other fields of its own once _keyword/_extra_tokens
            # are stripped -- delegate the rest of the tokens wholesale.
            assert len(nested_fields) == 1 and len(nested_fields) == len(all_fields), (
                f"{cls.__name__}: exactly one nested record field, with no plain "
                "fields of its own, is the only shape supported so far"
            )
            nf_name, nf_finfo = nested_fields[0]
            nested_cls = _nested_class(cls, nf_finfo.annotation)
            assert nested_cls is not None
            return cls(**{nf_name: nested_cls.from_tokens(tokens)})

        tagged = {n.upper(): (n, f) for n, f in all_fields.items() if _is_tagged(f)}
        untagged = [(n, f) for n, f in all_fields.items() if not _is_tagged(f)]

        kwargs: dict = {}
        consumed: set[int] = set()

        i = 0
        while i < len(tokens):
            entry = tagged.get(tokens[i].upper())
            result = None if entry is None else _consume_tagged(tokens, i, entry[0], entry[1])
            if entry is None or result is None:
                i += 1
                continue
            val, width = result
            kwargs[entry[0]] = val
            for j in range(width):
                consumed.add(i + j)
            i += width

        required_tagged = [
            (n, f)
            for n, f in all_fields.items()
            if _is_tagged(f) and f.is_required() and n not in kwargs
        ]
        positional_queue = required_tagged + untagged
        remaining = [t for j, t in enumerate(tokens) if j not in consumed]
        for (name, finfo), tok in zip(positional_queue, remaining):
            kwargs[name] = _coerce(tok, finfo)

        return cls(**kwargs)
