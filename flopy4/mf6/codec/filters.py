"""Filters shared by both reader and writer."""

from typing import Any

import numpy as np
import pandas as pd
import xarray as xr
from modflow_devtools.dfns import FieldBase, FieldType

from flopy4.utils import is_union


def field_type(value: Any) -> FieldType:
    """Get a field or field value's type according to the MF6 specification."""

    if isinstance(value, FieldBase):
        return value.type
    if isinstance(value, bool):
        return "keyword"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "double"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (dict, tuple)):
        return "record"
    if is_union(value):
        return "union"
    if isinstance(value, np.typing.NDArray, xr.DataArray):
        if value.dtype == "object":
            return "list"
        return "array"
    if isinstance(value, (list, np.recarray, pd.DataFrame, xr.Dataset)):
        return "list"
    raise ValueError(f"Unsupported field type: {type(value)}")
