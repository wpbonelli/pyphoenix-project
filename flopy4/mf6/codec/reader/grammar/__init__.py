from os import PathLike
from pathlib import Path

import jinja2
from modflow_devtools.dfns import Component, Dfns

from flopy4.mf6.codec.reader.grammar import filters


def _get_env():
    loader = jinja2.PackageLoader("flopy4", "mf6/codec/reader/grammar/templates/")
    env = jinja2.Environment(
        loader=loader,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters["unhyphenate"] = filters.unhyphenate
    env.filters["tagged_fields"] = filters.tagged_fields
    env.filters["list_field"] = filters.list_field
    return env


def make_grammar(dfn: Component, outdir: str | PathLike):
    """Generate a Lark grammar file for a single component."""
    outdir = Path(outdir).expanduser().resolve().absolute()
    env = _get_env()
    template = env.get_template("component.lark.jinja")
    target_path = outdir / f"{dfn.name}.lark"
    with open(target_path, "w") as f:
        name = dfn.name
        f.write(template.render(name=name, blocks=dfn.blocks, fields=dfn.fields))


<<<<<<< HEAD
def make_grammars(dfns: dict[str, Dfn], outdir: PathLike):
=======
def make_grammars(dfns: Dfns, outdir: str | PathLike):
>>>>>>> 4221103 (adapt wip)
    """Generate grammars for all components."""
    outdir = Path(outdir).expanduser().resolve().absolute()
    outdir.mkdir(parents=True, exist_ok=True)
    for dfn in dfns.components.values():
        make_grammar(dfn, outdir)
