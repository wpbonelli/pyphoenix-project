from collections.abc import Hashable, Mapping
from io import StringIO
from typing import Any

import attrs
import numpy as np
import pandas as pd
import xarray as xr
from numpy.typing import NDArray


def is_dataset(value: Any) -> bool:
    return isinstance(value, xr.Dataset)


def field_format(value: Any) -> str:
    """
    Get a field's formatting type as defined by the MF6 definition language:
    https://modflow6.readthedocs.io/en/stable/_dev/dfn.html#variable-types
    """
    if isinstance(value, bool):
        return "keyword"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "double precision"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (dict, tuple)):
        return "record"
    if isinstance(value, xr.DataArray):
        if value.dtype == "object":
            return "list"
        return "array"
    if isinstance(value, (xr.Dataset, list)):
        return "list"
    return "keystring"


def has_time_dim(value: Any) -> bool:
    return isinstance(value, xr.DataArray) and "nper" in value.dims


def array_how(value: xr.DataArray) -> str:
    # TODO
    # - detect constant arrays?
    # - above certain size, use external?
    return "internal"


def array_chunks(value: xr.DataArray, chunks: Mapping[Hashable, int] | None = None):
    """
    Yield chunks from a dask-backed array of up to 3 dimensions.
    If it's not already chunked, split it into chunks of the
    specified sizes, given as a dictionary mapping dimension
    names to chunk sizes.

    If chunk sizes are not specified, chunk the array with at
    most 2 dimensions per chunk, where:

    - If the array is 3D, assume the first dimension is the
    vertical (i.e. layers) and the others horizontal (rows and
    columns, in that order), and yield a chunk per layer, such
    that an array with indices (k, i, j) becomes k chunks, each
    of shape (i, j).

    - If the array is 1D or 2D, yield it as a single chunk.

    If the array is not a dask array, yield it as a single chunk.
    """

    if hasattr(value.data, "blocks"):
        if value.chunks is None:
            if chunks is None:
                match value.ndim:
                    case 1:
                        # 1D array, single chunk
                        chunks = {value.dims[0]: value.shape[0]}
                    case 2:
                        # 2D array, single chunk
                        chunks = {value.dims[0]: value.shape[0], value.dims[1]: value.shape[1]}
                    case 3:
                        # 3D array, chunk for each layer
                        chunks = {
                            value.dims[0]: 1,
                            value.dims[1]: value.shape[1],
                            value.dims[2]: value.shape[2],
                        }
            value = value.chunk(chunks)
        for chunk in value.data.blocks:
            yield np.squeeze(chunk.compute())
    else:
        # regular array, single chunk
        yield np.squeeze(value.values)


def array2string(value: NDArray) -> str:
    """
    Convert an array to a string. The array can be 1D or 2D.
    If the array is 1D, it is converted to a 1-line string,
    with elements separated by whitespace. If the array is
    2D, each row becomes a line in the string.

    Used for writing array-based input to MF6 input files.
    """
    buffer = StringIO()
    value = np.asarray(value)
    if value.ndim > 2:
        raise ValueError("Only 1D and 2D arrays are supported.")
    if value.ndim == 1:
        # add an axis to 1d arrays so np.savetxt writes elements on 1 line
        value = value[None]
    value = np.atleast_1d(value)
    format = (
        "%d"
        if np.issubdtype(value.dtype, np.integer)
        else "%f"
        if np.issubdtype(value.dtype, np.floating)
        else "%s"
    )
    np.savetxt(buffer, value, fmt=format, delimiter=" ")
    return buffer.getvalue().strip()


def nonempty(arr: NDArray) -> NDArray:
    if arr.dtype == "object":
        mask = arr != None
    else:
        mask = ~np.ma.masked_invalid(arr).mask
    return mask


def data2list(value: list | xr.DataArray | xr.Dataset):
    """
    Yield record tuples suitable for MF6 list-based input from a single `DataArray` or `Dataset`.

    Yields
    ------
    tuple
        Tuples of (*cellid, *values) or (*values) depending on spatial dimensions
    """

    if isinstance(value, list):
        for item in value:
            yield item
        return

    if isinstance(value, xr.Dataset):
        yield from dataset2list(value)
        return

    spatial_dims = [d for d in value.dims if d in ("nlay", "nrow", "ncol", "nnodes")]
    has_spatial_dims = len(spatial_dims) > 0
    mask = nonempty(value)
    indices = np.where(mask)
    values = value.values[mask]
    for i, val in enumerate(values):
        if attrs.has(val):
            val = attrs.astuple(val)
        if has_spatial_dims:
            cellid = tuple(idx[i] + 1 for idx in indices)
            result = cellid + (val if isinstance(val, tuple) else (val,))
        else:
            result = val if isinstance(val, tuple) else (val,)
        
        yield result


def dataset2list(value: xr.Dataset):
    """
    Combine multiple arrays and yield record tuples suitable for MF6 list-based input.

    Yields
    ------
    tuple
        Tuples of (*cellid, *values) or (*values) depending on spatial dimensions
    """
    if value is None or not any(value.data_vars):
        return
    
    combined_mask: Any = None
    for field_name, arr in value.data_vars.items():
        mask = nonempty(arr)
        combined_mask = mask if combined_mask is None else combined_mask | mask
    if combined_mask is None or not np.any(combined_mask):
        return

    spatial_dims = [d for d in next(iter(value.data_vars.values())).dims if d in ("nlay", "nrow", "ncol", "nnodes")]
    has_spatial_dims = len(spatial_dims) > 0
    indices = np.where(combined_mask)
    for i in range(len(indices[0])):
        field_vals = []
        for field_name in value.data_vars.keys():
            field_val = value[field_name][tuple(idx[i] for idx in indices)]
            if attrs.has(field_val):
                field_val = attrs.astuple(field_val)
            field_vals.append(field_val)

        flattened = []
        for fv in field_vals:
            if isinstance(fv, tuple):
                flattened.extend(fv)
            else:
                flattened.append(fv)

        if has_spatial_dims:
            cellid = tuple(idx[i] + 1 for idx in indices)
            yield cellid + tuple(flattened)
        else:
            yield tuple(flattened)
