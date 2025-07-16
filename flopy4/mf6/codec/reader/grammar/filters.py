from boltons.iterutils import default_enter, remap
from modflow_devtools.dfn import Dfn


def _get_vars(d: dict) -> dict[str, dict]:
    """Extract all variables from a DFN as a flat dict."""
    vars_ = dict()

    def visit(p, k, v):
        if isinstance(v, dict) and "type" in v:
            vars_[k] = v
        return True

    def enter(p, k, v):
        if isinstance(v, dict) and "type" in v:
            return (v, False)
        return default_enter(p, k, v)

    dd = d.copy()
    remap(dd, enter=enter, visit=visit)
    return vars_


def get_blocks(dfn: Dfn) -> dict[str, dict]:
    """Get blocks from DFN, filtering out metadata."""
    blocks = {}
    for name, value in dfn.items():
        if isinstance(value, dict) and any(
            isinstance(v, dict) and "type" in v for v in value.values()
        ):
            blocks[name] = value
    return blocks


def get_variables(dfn: Dfn) -> dict[str, dict]:
    """Get all variables from DFN as a flat dict."""
    return _get_vars(dfn)


def is_recarray_block(block: dict) -> bool:
    """Check if a block contains recarray fields."""
    return any(
        isinstance(field, dict) and field.get("type", "").startswith("recarray")
        for field in block.values()
    )


def get_block_variables(block: dict) -> list[str]:
    """Get list of variable names in a block."""
    return [name for name, field in block.items() if isinstance(field, dict) and "type" in field]


def lark_type(field_type: str) -> str:
    """Convert DFN field type to Lark grammar type."""
    if field_type in ["integer", "double precision"]:
        return "NUMBER"
    if "recarray" in field_type:
        return "recarray"
    return "word"
