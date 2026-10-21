from collections.abc import Mapping
from os import PathLike
from pathlib import Path

import jinja2
from modflow_devtools.dfns.schema import (
    Array,
    Block,
    Component,
    Double,
    InputField,
    Keyword,
    List,
    Record,
    Union,
)

from flopy4.mf6.codec.reader.grammar import filters
from flopy4.mf6.codec.reader.grammar.names import rule_name, to_rule_name


def _get_env():
    loader = jinja2.PackageLoader("flopy4", "mf6/codec/reader/grammar/templates/")
    env = jinja2.Environment(
        loader=loader,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters["field_type"] = filters.field_type
    env.tests["dynamically_named_array"] = filters.is_dynamically_named_array
    env.filters["keyword_literal"] = filters.keyword_literal
    env.filters["record_child_type"] = filters.record_child_type
    env.filters["scalar_type"] = filters.scalar_type
    env.filters["to_rule_name"] = to_rule_name
    env.globals["rule"] = lambda *path, tags=(): rule_name(*path, tags=tuple(tags))
    env.globals["part_tag"] = filters.part_tag
    return env


def _field_tag(field: InputField) -> str:
    """The kind tag of a block field's rule (see grammar.names)."""
    if filters.is_dynamically_named_array(field):
        return "val"
    if isinstance(field, Record) and field.children is not None:
        return "rec"
    if isinstance(field, Union) and field.children is not None:
        return "union"
    if isinstance(field, Keyword):
        return "kw"
    return "val"


def _to_context(
    blocks: dict[str, Block], names: Mapping[tuple[str, str], str] | None = None
) -> tuple[list[dict], dict[str, object]]:
    """Build block and field context. A block's field's rule is named by
    its class attribute in `names` (see `make.attr_names`), as ``__init__``
    takes it (without a leading underscore), else by its DFN name."""
    names = names or {}
    all_blocks = []
    all_fields = {}

    for block_name, block in blocks.items():

        def attr(field_name: str) -> str:
            return names.get((block_name, field_name), field_name).lstrip("_")

        header = block.header.field if block.header is not None else None
        has_index = header is not None and not isinstance(header, Record)
        if isinstance(header, Record):
            all_fields[header.name] = header
        recarrays = []
        standalone_fields = []
        # each field's rule's name path (see names.py)
        paths: dict[str, tuple[str, ...]] = {}
        # a list's element lines, each read into the list (see names.py)
        elements = set()
        # tagged `valid` scalars, whose name precedes their value. The union
        # valid_as_union makes of one is tagged by its keyword arms, so it
        # can't say whether the scalar was.
        tagged_valid = set()

        for field_name, field in block.fields.items():
            # as codegen skips them: a line of one is a block's unknown line
            if field.removed or field.developmode:
                continue
            if field.tagged and getattr(field, "valid", None):
                tagged_valid.add(field_name)
            field = filters.valid_as_union(field)
            if isinstance(field, List):
                if isinstance(field.item, Union):
                    for arm_name, arm in field.item.arms.items():
                        if arm.removed:
                            continue
                        all_fields[arm_name] = arm
                        standalone_fields.append(arm_name)
                        paths[arm_name] = (attr(field_name), arm_name)
                        elements.add(arm_name)
                elif field.tagged:
                    all_fields[field_name] = field.item
                    standalone_fields.append(field_name)
                    paths[field_name] = (attr(field_name),)
                    elements.add(field_name)
                else:
                    recarrays.append({"name": rule_name(attr(field_name), tags=("rows",))})
                    all_fields[field_name] = field
                continue
            all_fields[field_name] = field
            standalone_fields.append(field_name)
            paths[field_name] = (attr(field_name),)

        bare_array = any(
            isinstance(all_fields[n], Array) and not all_fields[n].tagged for n in standalone_fields
        )
        named_array = any(
            filters.is_dynamically_named_array(all_fields[n]) for n in standalone_fields
        )
        rules = {
            name: rule_name(
                *paths[name],
                tags=(_field_tag(all_fields[name]), *(("elem",) if name in elements else ())),
            )
            for name in standalone_fields
        }
        all_blocks.append(
            {
                "name": block_name,
                "has_index": has_index,
                # utl-tas's TIME block is indexed by a time, not a number
                "index_rule": "double_index" if isinstance(header, Double) else "block_index",
                "header": header.name if isinstance(header, Record) else None,
                "standalone_fields": standalone_fields,
                "rules": rules,
                "tagged_valid": tagged_valid,
                "recarrays": recarrays,
                "redirect": not bare_array,
                # a line no field takes, which a block with no list rows and
                # no untagged or auxiliary arrays, whose lines a word could
                # begin, can tell from its fields' (see typed.lark's
                # unknown_line)
                "unknown_lines": not (recarrays or bare_array or named_array),
            }
        )

    return all_blocks, all_fields


def make_grammar(
    component: Component,
    outdir: PathLike,
    names: Mapping[tuple[str, str], str] | None = None,
):
    """Generate a Lark grammar file for a single component, its block
    fields' rules named by their class attributes in `names`, by (block,
    field name), else by their DFN names."""
    outdir = Path(outdir).expanduser().resolve().absolute()
    env = _get_env()
    template = env.get_template("component.lark.jinja")
    target_path = outdir / f"{component.name}.lark"
    blocks, fields = _to_context(component.blocks or {}, names)
    text = template.render(name=component.name, blocks=blocks, fields=fields)
    # one trailing newline, however the template's last rule ends
    target_path.write_text(text.rstrip("\n") + "\n")


def make_grammars(dfns: dict[str, Component], outdir: PathLike):
    """Generate grammars for all components, their block fields' rules
    named by the class attributes codegen makes of them."""
    from flopy4.mf6.utils.codegen.make import attr_names

    outdir = Path(outdir).expanduser().resolve().absolute()
    outdir.mkdir(parents=True, exist_ok=True)
    for component in dfns.values():
        make_grammar(component, outdir, attr_names(component, dfns))
