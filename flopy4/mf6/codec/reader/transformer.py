from typing import Any

from lark import Token, Transformer

from flopy4.mf6.codec.reader.grammar.type_mapping import get_field_types
from flopy4.mf6.component import COMPONENTS


class BaseTransformer(Transformer):
    def start(self, items: list[Any]) -> dict[str, Any]:
        blocks = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            block_name = next(iter(item.keys()))
            blocks[block_name] = next(iter(item.values()))
        return blocks

    def block(self, items: list[Any]) -> dict[str, Any]:
        return {items[0]: items[1 : (len(items) - 1)]}

    def block_name(self, items: list[Any]) -> str:
        return " ".join([str(item) for item in items if item is not None])


class GenericTransformer(BaseTransformer):
    """
    Generic transformer for MF6 input files. Works only with the generic
    grammar. Returns structures of blocks consisting of lines of tokens.
    """

    def line(self, items: list[Any]) -> list[Any]:
        return items[1:]

    def item(self, items: list[Any]) -> str | float | int:
        return items[0]

    def word(self, items: list[Token]) -> str:
        return str(items[0])

    def NUMBER(self, token: Token) -> int | float:
        value = str(token)
        try:
            if "." in value or "e" in value.lower():
                return float(value)
            else:
                return int(value)
        except ValueError:
            return float(value)

    def CNAME(self, token: Token) -> str:
        return str(token)

    def INT(self, token: Token) -> int:
        return int(token)


class ComponentTransformer(BaseTransformer):
    """
    Component-type-aware transformer for MF6 input files. Compatible only
    with component-specific grammars.

    This transformer uses type information from the class specification to
    handle scalars, records, arrays, keystrings and lists/recarrays.
    """

    def __init__(self, component_name: str):
        super().__init__()
        self._cls = COMPONENTS[component_name]
        self._dfn = self._cls.get_dfn()
        self._field_types = get_field_types(self._dfn)

    def record(self, items: list[Any]) -> list[Any]:
        return items

    def integer(self, items: list[Token]) -> int:
        return int(items[0])

    def double(self, items: list[Token]) -> float:
        return float(items[0])

    def string(self, items: list[Token]) -> str:
        return str(items[0])

    def keyword(self, items: list[Token]) -> str:
        return str(items[0])

    def array(self, items: list[Any]) -> dict[str, Any]:
        # TODO
        pass

    list = list

    def array_control(self, items: list[Any]) -> dict[str, Any]:
        result = {"name": items[0] if items else None}
        if len(items) > 1:
            result["multiplier"] = items[1]
        if len(items) > 2:
            result["format"] = items[2]
        return result

    def array_data(self, items: list[Any]) -> list[Any]:
        return items

    def word(self, items: list[Token]) -> str:
        return str(items[0])

    def NUMBER(self, token: Token) -> int | float:
        value = str(token)
        try:
            if "." in value or "e" in value.lower():
                return float(value)
            else:
                return int(value)
        except ValueError:
            return float(value)

    def FLOAT(self, token: Token) -> float:
        return float(token)

    def INT(self, token: Token) -> int:
        return int(token)

    def CNAME(self, token: Token) -> str:
        return str(token)
