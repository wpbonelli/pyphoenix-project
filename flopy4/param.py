from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd
from attrs import field
from numpy.typing import ArrayLike

from flopy4.map import MapAttrs

Scalar = bool | int | float
"""A scalar input parameter."""


class Record(MapAttrs[Scalar | str | Path | List[Scalar | str | Path]]):
    """
    An ordered collection (product type) of scalar parameters.

    See https://en.wikipedia.org/wiki/Record_(computer_science).
    """

    # TODO: some mechanism to enforce order? Are we guaranteed
    # that `__attrs_attrs__` preserves the order in which they
    # are defined in the class body?

    # TODO: only the last element can be a list, enforce this
    pass



Param = Scalar | str | Path | Record | ArrayLike | pd.DataFrame | Union[Scalar | str | Path | Record]
"""An input parameter."""


def param(
    description: Optional[str] = None,
    deprecated: bool = False,
    default: Optional[Any] = None,
    metadata: Optional[Dict] = None,
    **kwargs,
):
    """
    Define a program input parameter. Wraps `attrs.field()`
    with a few extra metadata properties.
    """
    metadata = metadata or {}
    metadata["description"] = description
    metadata["deprecated"] = deprecated
    return field(**kwargs, default=default, metadata=metadata)
