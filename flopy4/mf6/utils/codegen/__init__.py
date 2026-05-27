from os import PathLike
from pathlib import Path

import jinja2
from modflow_devtools.dfns import Component, Dfns

from flopy4.mf6.utils.codegen import filters


def _get_env() -> jinja2.Environment:
    loader = jinja2.PackageLoader("flopy4", "mf6/utils/codegen/templates")
    env = jinja2.Environment(
        loader=loader,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        undefined=jinja2.StrictUndefined,
    )
    env.filters["unhyphenate"] = ...
    return env


def make_component(dfn: Component, outdir: str | PathLike, developmode: bool = False):
    """Generate a Python source file for a single component."""
    outdir = Path(outdir).expanduser().resolve().absolute()
    env = _get_env()
    template = env.get_template("component.py.jinja")
    target_path = outdir / filters.rel_path(dfn.name)
    with open(target_path, "w") as f:
        f.write(template.render(dfn=dfn, developmode=developmode))


def make_components(dfns: Dfns, outdir: PathLike, developmode: bool = False):
    """Generate Python source files for all components."""
    outdir = Path(outdir).expanduser().resolve().absolute()
    outdir.mkdir(parents=True, exist_ok=True)
    for dfn in dfns.values():
        make_component(dfn, outdir, developmode)


__all__ = ["make_component", "make_components"]
