from os import linesep

from lark import Lark

ATTRIBUTES = [
    "block",
    "name",
    "type",
    "reader",
    "optional",
    "true",
    "mf6internal",
    "longname",
    "description",
    "layered",
    "shape",
    "valid",
    "tagged",
    "in_record",
    "preserve_case",
    "default_value",
    "numeric_index",
    "deprecated",
    "removed",
    "repeating",
    "time_series",
    "other_names",
    "support_negative_index",
    "jagged_array",
    "just_data",
    "block_variable"
]

DFN_GRAMMAR = r"""
// dfn
dfn: _NL* parameter* _NL*

// parameter
parameter.+1: _head (_NL attribute)* _NL*
_head: block _NL name
block: "block" WS_INLINE CNAME
name: "name" WS_INLINE CNAME

// attribute
attribute.-1: key [value]
key: ATTRIBUTE
value: _string

// string (anything but newline)
_string: /[^\n]+/

// newline
_NL: /(\r?\n[\t ]*)+/

%import common.CNAME
%import common.SH_COMMENT
%import common.WORD
%import common.WS_INLINE

%ignore SH_COMMENT
%ignore WS_INLINE
"""
"""
EBNF description for the MODFLOW 6 definition language.
"""


def make_parser():
    """
    Create a parser for the MODFLOW 6 definition language.
    """

    attributes = "|".join(['"' + n + '"i' for n in ATTRIBUTES])
    grammar = linesep.join([DFN_GRAMMAR, f"ATTRIBUTE: ({attributes})"])
    return Lark(grammar, start="dfn")
