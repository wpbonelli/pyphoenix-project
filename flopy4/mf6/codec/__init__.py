import sys
from os import PathLike
from typing import Any

import numpy as np
import xattree
from cattrs import Converter
from jinja2 import Environment, PackageLoader

from flopy4.mf6 import filters
from flopy4.mf6.codec.converter import unstructure_component

_JINJA_ENV = Environment(
    loader=PackageLoader("flopy4.mf6"),
    trim_blocks=True,
    lstrip_blocks=True,
)
_JINJA_ENV.filters["dict_blocks"] = filters.dict_blocks
_JINJA_ENV.filters["list_blocks"] = filters.list_blocks
_JINJA_ENV.filters["field_type"] = filters.field_type
_JINJA_ENV.filters["field_value"] = filters.field_value
_JINJA_ENV.filters["array_how"] = filters.array_how
_JINJA_ENV.filters["array_chunks"] = filters.array_chunks
_JINJA_ENV.filters["array2string"] = filters.array2string
_JINJA_ENV.filters["to_sparse_dict"] = filters.to_sparse_dict
_JINJA_ENV.filters["to_period_records"] = filters.to_period_records

_JINJA_TEMPLATE_NAME = "blocks.jinja"

_PRINT_OPTIONS = {
    "precision": 4,
    "linewidth": sys.maxsize,
    "threshold": sys.maxsize,
}


def _make_converter() -> Converter:
    """Create a simple converter that just handles structure conversion."""
    from flopy4.mf6.component import Component

    converter = Converter()
    converter.register_unstructure_hook_factory(xattree.has, lambda _: xattree.asdict)
    converter.register_unstructure_hook(Component, unstructure_component)
    return converter


_CONVERTER = _make_converter()


def loads(data: str) -> Any:
    # TODO
    pass


def load(path: str | PathLike) -> Any:
    # TODO
    pass


def dumps(data) -> str:
    template = _JINJA_ENV.get_template(_JINJA_TEMPLATE_NAME)
    unstructured_data = _CONVERTER.unstructure(data)
    with np.printoptions(**_PRINT_OPTIONS):  # type: ignore
        return template.render(dfn=type(data).dfn, data=unstructured_data, component=data)


def dump(data, path: str | PathLike) -> None:
    template = _JINJA_ENV.get_template(_JINJA_TEMPLATE_NAME)
    unstructured_data = _CONVERTER.unstructure(data)
    iterator = template.generate(dfn=type(data).dfn, data=unstructured_data, component=data)
    with np.printoptions(**_PRINT_OPTIONS), open(path, "w") as f:  # type: ignore
        f.writelines(iterator)


__all__ = [
    "loads",
    "load",
    "dumps",
    "dump",
]
