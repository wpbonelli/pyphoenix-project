"""
DFN type to grammar type rule mapping for type-aware parsing.

This module maps MF6 DFN types to the type-specific rules in the enhanced base grammar.
"""

from typing import Dict

from modflow_devtools.dfn import Dfn

# DFN type to grammar rule mapping
DFN_TYPE_TO_GRAMMAR_RULE: Dict[str, str] = {
    # Scalar types
    "integer": "scalar_integer",
    "double precision": "scalar_double",
    "string": "scalar_string",
    "keyword": "keyword",  # Boolean options
    # Structured types
    "record": "record_type",
    "recarray": "recarray_type",
    # Keystring (irregular recarray)
    "keystring": "keystring_type",
}


def get_dfn_type(field_spec: dict) -> str:
    """
    Extract the DFN type from a field specification.

    Parameters
    ----------
    field_spec : dict
        DFN field specification dictionary

    Returns
    -------
    str
        The DFN type string
    """
    return field_spec.get("type", "string")


def is_array_field(field_spec: dict) -> bool:
    """
    Check if a field is an array based on having a shape property.

    Parameters
    ----------
    field_spec : dict
        DFN field specification

    Returns
    -------
    bool
        True if field has shape property (is an array)
    """
    return isinstance(field_spec, dict) and "shape" in field_spec


def get_grammar_rule(field_spec: dict) -> str:
    """
    Map a DFN field specification to its corresponding grammar rule.

    Parameters
    ----------
    field_spec : dict
        DFN field specification dictionary

    Returns
    -------
    str
        Grammar rule name (e.g., "scalar_integer", "array_section")
    """
    if is_array_field(field_spec):
        return "array_section"

    dfn_type = get_dfn_type(field_spec)
    return DFN_TYPE_TO_GRAMMAR_RULE.get(dfn_type, "scalar_string")


def is_recarray_block(block_spec: dict) -> bool:
    """
    Check if a block contains recarray data.

    Parameters
    ----------
    block_spec : dict
        DFN block specification

    Returns
    -------
    bool
        True if block contains recarray fields
    """
    for field_name, field_spec in block_spec.items():
        if isinstance(field_spec, dict) and get_dfn_type(field_spec) == "recarray":
            return True
    return False


def is_keystring_block(block_spec: dict) -> bool:
    """
    Check if a block contains keystring (irregular recarray) data.

    Parameters
    ----------
    block_spec : dict
        DFN block specification

    Returns
    -------
    bool
        True if block contains keystring fields
    """
    for field_name, field_spec in block_spec.items():
        if isinstance(field_spec, dict) and get_dfn_type(field_spec) == "keystring":
            return True
    return False


def get_block_type(block_spec: dict) -> str:
    """
    Determine the primary type of a block based on its fields.

    Parameters
    ----------
    block_spec : dict
        DFN block specification

    Returns
    -------
    str
        Block type: "recarray", "keystring", "options", or "scalar"
    """
    if is_keystring_block(block_spec):
        return "keystring"
    elif is_recarray_block(block_spec):
        return "recarray"
    elif any("options" in name.lower() for name in block_spec.keys()):
        return "options"
    else:
        return "scalar"


def get_field_types(dfn: Dfn) -> Dict[str, Dict[str, str]]:
    """
    Extract field type information from a DFN.

    Parameters
    ----------
    dfn : Dfn
        Component DFN specification

    Returns
    -------
    Dict[str, Dict[str, str]]
        Nested dict: {block_name: {field_name: grammar_rule}}
    """
    field_types = {}

    for block_name, block_spec in dfn.items():
        if block_name in {"name", "advanced", "multi", "ref", "sln"}:
            continue

        if isinstance(block_spec, dict):
            field_types[block_name] = {}
            for field_name, field_spec in block_spec.items():
                if isinstance(field_spec, dict) and "type" in field_spec:
                    grammar_rule = get_grammar_rule(field_spec)
                    field_types[block_name][field_name] = grammar_rule

    return field_types
