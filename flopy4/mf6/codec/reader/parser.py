from pathlib import Path

from lark import Lark


def make_component_parser(name: str) -> Lark:
    grammar_path = Path(__file__).parent / "grammar" / "generated" / f"{name}.lark"
    if not grammar_path.exists():
        raise FileNotFoundError(f"Component-specific grammar file not found: {grammar_path}")
    with open(grammar_path, "r") as f:
        grammar = f.read()
    return Lark(grammar, parser="lalr", debug=True)


def make_generic_parser() -> Lark:
    grammar_path = Path(__file__).parent / "grammar" / "mf6.lark"
    with open(grammar_path, "r") as f:
        grammar = f.read()
    return Lark(grammar, parser="lalr", debug=True)
