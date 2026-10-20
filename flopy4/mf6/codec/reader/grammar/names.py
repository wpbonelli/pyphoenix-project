"""Rule names in the generated typed grammars.

A generated rule's name says how to read it, so the typed transformer
needs nothing but the parse tree. The name is a path of names, then one or
more kind tags, all joined by ``__``:

- ``val``: a value, or values (``optional_value__val``)
- ``kw``: a keyword, True when given (``print_input__kw``)
- ``arr``: a record part holding a list of values
- ``rec``: a record, read into a dict of its parts
- ``union``: a union, read as its arm's value, or a keyword arm's name
- ``elem``: one element of a list, which collects them
- ``rows``: a list's rows, which the block's untagged rows are
- ``hdr``: a block's record header (OBS's ``CONTINUOUS FILEOUT <file>``)
- ``block``, ``fields``: a block, and its contents

A block's field is named by the class attribute holding it, as the class's
``__init__`` takes it (``head_file`` for OC's ``head_filerecord``, see
`flopy4.mf6.spec.attr_names`); a record part, union arm, or block by its
DFN name. A value is read under its path's last segment, except a list's
element, read into the list its path's first segment names, and, if the
list's items are a union, keyed by its arm (``stress_period_data__saverecord
__rec__elem`` is a ``{"saverecord": ...}`` in OC's ``stress_period_data``).
Neither kind of name contains ``__`` or begins with ``_``, so splitting at
each ``__`` not followed by ``_`` is unambiguous, even after a name ending
with one (``continue___kw``, for IMS's ``continue_``).
"""

import re

SEP = "__"
_SPLIT = re.compile(r"__(?!_)")
TAGS = frozenset({"val", "kw", "arr", "rec", "union", "elem", "rows", "hdr", "block", "fields"})


def to_rule_name(name: str) -> str:
    """Convert a DFN name to a valid Lark rule name (no hyphens)."""
    return name.replace("-", "_")


def rule_name(*path: str, tags: tuple[str, ...] = ()) -> str:
    """A rule's name from its name path and kind tags."""
    for p in path:
        if SEP in p or p.startswith("_"):
            raise ValueError(f"name {p!r} contains {SEP!r} or begins with '_'")
    if unknown := set(tags) - TAGS:
        raise ValueError(f"unknown rule tags: {sorted(unknown)}")
    return SEP.join([*(to_rule_name(p) for p in path), *tags])


def parse_rule_path(rule: str) -> tuple[tuple[str, ...], frozenset[str]]:
    """A rule's name path and kind tags, or its own name and no tags for a
    rule that isn't tagged (one of typed.lark's)."""
    parts = _SPLIT.split(rule)
    tags = set()
    while len(parts) > 1 and parts[-1] in TAGS:
        tags.add(parts.pop())
    return tuple(parts), frozenset(tags)


def parse_rule_name(rule: str) -> tuple[str, frozenset[str]]:
    """A rule's name, its path's last segment, and kind tags (see
    `parse_rule_path`)."""
    path, tags = parse_rule_path(rule)
    return path[-1], tags
