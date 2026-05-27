from pathlib import Path

from lark import Lark
from modflow_devtools.dfns import Component

_LALR = "lalr"
_GRAMMAR_MODULE = Path(__file__).parent / "grammar"


def get_basic_parser() -> Lark:
    grammar_path = _GRAMMAR_MODULE / "basic.lark"
    with open(grammar_path, "r") as f:
        return Lark(f.read(), parser=_LALR, debug=True)


def get_typed_parser(dfn: Component) -> Lark:
    grammar_path = _GRAMMAR_MODULE / "generated" / f"{dfn.name}.lark"
    if not grammar_path.exists():
        raise FileNotFoundError(f"Grammar file not found: {grammar_path}")
    with open(grammar_path, "r") as f:
        return Lark(
            f.read(),
            parser=_LALR,
            debug=True,
            import_paths=[str(_GRAMMAR_MODULE)],
        )
