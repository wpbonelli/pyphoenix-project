from modflow_devtools.dfns import Block, Field


def unhyphenate(name: str) -> str:
    """Lark rule names must not contain hyphens, replace them with underscores."""
    return name.replace("-", "_")


def tagged_fields(block: Block) -> dict[str, Field]:
    """Return the block's tagged fields."""
    return {name: field for name, field in block.fields.items() if field.tagged}


def list_field(block: Block) -> Field | None:
    """Return the block's solitary list field, if it has one."""
    return next(iter([field for field in block.fields.values() if field.type == "list"]), None)
