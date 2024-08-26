from typing import Any, Type, TypeVar

from cattrs import BaseConverter, Converter
from cattrs.strategies import include_subclasses

from flopy4.context import Context
from flopy4.mf6.io.decoder import loads
from flopy4.mf6.io.encoder import dumps

T = TypeVar("T")


class MF6Converter(Converter):
    def dumps(
        self, obj: Any, unstructure_as: Any = None, **kwargs: Any
    ) -> str:
        return dumps(
            self.unstructure(obj, unstructure_as=unstructure_as), **kwargs
        )

    def loads(self, data: bytes | str, cl: Type[T], **kwargs: Any) -> T:
        return self.structure(loads(data, **kwargs), cl)


def configure_converter(converter: BaseConverter):
    include_subclasses(Context, converter)
    # TODO: register converter hooks, what do we need?
    pass


def make_converter(*args, **kwargs) -> MF6Converter:
    converter = MF6Converter(*args, **kwargs)
    configure_converter(converter)
    return converter
