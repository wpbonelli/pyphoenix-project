"""Attribute hooks for attrs on_setattr callbacks."""

import numpy as np

from flopy4.mf6.spec import fields


def update_maxbound(instance, attr, value):
    """
    Generalized function to update maxbound when period block arrays change.
    Calculates maxbound based on the maximum number of values in the arrays.
    """

    array_names = []
    for field in fields(type(instance)):
        if field.metadata and field.metadata.get("block") == "period" and "dims" in field.metadata:
            array_names.append(field.name)

    bounds = []
    for array_name in array_names:
        if attr and attr.name == array_name:
            val = value
        else:
            val = getattr(instance, array_name, None)
        if val is None:
            continue
        arr = (
            val if val.data.shape == val.shape else val.todense()
        )
        if arr.dtype.kind in ["U", "S"]:  # String arrays
            bound = len(np.where(arr != "")[0])
        else:  # Numeric arrays
            bound = np.count_nonzero(~np.isnan(arr))
        bounds.append(bound)
    if any(bounds):
        instance.maxbound = max(bounds)
