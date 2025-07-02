from collections.abc import Hashable, Mapping
from io import StringIO

import numpy as np
import xarray as xr
from jinja2 import pass_context
from modflow_devtools.dfn import Dfn, Field
from numpy.typing import NDArray

from flopy4.mf6.constants import FILL_DNODATA
from flopy4.adapters import get_cellid
import sparse

from flopy4.mf6.spec import get_blocks, is_list_block, is_list_field


def dict_blocks(dfn: Dfn) -> dict:
    """
    Get dictionary blocks from an MF6 input definition. A
    dictionary block is a standard block which can contain
    one or more fields, as opposed to a list block, which
    may only contain one recarray field, using list input.
    """
    return {
        block_name: block
        for block_name, block in get_blocks(dfn).items()
        if not is_list_block(block)
    }


def list_blocks(dfn: Dfn) -> dict:
    return {
        block_name: block for block_name, block in get_blocks(dfn).items() if is_list_block(block)
    }


def field_type(field: Field) -> str:
    """
    Get a field's type as defined by the MODFLOW 6 input definition language:
    https://modflow6.readthedocs.io/en/stable/_dev/dfn.html#variable-types
    """
    return field["type"]


@pass_context
def field_value(ctx, field: Field):
    """Get a field's value via the template context."""
    return ctx["data"][field["name"]]


def array_how(value: xr.DataArray) -> str:
    return "internal"


def array_chunks(value: xr.DataArray, chunks: Mapping[Hashable, int] | None = None):
    """
    Yield chunks from an array of up to 3 dimensions. If the
    array is not already chunked, split it into chunks of the
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
    """

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


def array2string(value: NDArray) -> str:
    """
    Convert an array to a string. The array can be 1D or 2D.
    If the array is 1D, it is converted to a 1-line string,
    with elements separated by whitespace. If the array is
    2D, each row becomes a line in the string.
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


@pass_context
def to_sparse_dict(ctx, field: Field):
    """Lazily convert a field's DataArray to sparse dict format for MF6 list input."""
    component = ctx.get('component')  # We'll need to pass this in the context
    if not component:
        return None
        
    field_name = field["name"]
    original_array = getattr(component, field_name, None)
    if original_array is None:
        return None
    
    return _unstructure_array_lazy(original_array)


@pass_context 
def to_period_records(ctx, block_tuple):
    """Lazily convert period data to records for MF6 list input."""
    component = ctx.get('component')
    if not component:
        return {}
    
    # Unpack the tuple from the template
    block_name, block = block_tuple
        
    component_type = type(component).__name__.lower()
    
    if component_type == "tdis" and block_name == "perioddata":
        return _prepare_tdis_lazy(component, block)
    elif component_type == "chd" and block_name == "period":
        return _prepare_chd_lazy(component, block)
    elif component_type == "oc" and block_name == "period":
        return _prepare_oc_lazy(component, block)
    else:
        return _prepare_generic_lazy(component, block_name, block)


def _unstructure_array_lazy(value: xr.DataArray) -> dict:
    """Lazy version of unstructure_array - only converts when actually accessed."""
    if (time_dim := "nper") not in value.dims:
        raise ValueError(f"Array must have dimension '{time_dim}'")
    
    if isinstance(value.data, sparse.COO):
        # For sparse arrays, use the coordinates directly
        coords = value.coords
        data = value.data
    else:
        # For dense arrays, find non-fill values
        # Handle both FILL_DNODATA and NaN values
        valid_mask = (value.data != FILL_DNODATA) & ~np.isnan(value.data)
        coords = np.array(np.where(valid_mask)).T
        if coords.size == 0:
            return {}
        data = value.data[tuple(coords.T)]
    
    if coords.size == 0:
        return {}
    
    result = {}
    match value.ndim:
        case 1:
            # Only kper dimension
            for kper, v in zip(coords[:, 0], data):
                result[int(kper)] = v
        case _:
            # kper + spatial dimensions
            for row, v in zip(coords, data):
                kper = int(row[0])
                spatial = tuple(int(x) for x in row[1:])
                if kper not in result:
                    result[kper] = {}
                # flatten spatial index if only one spatial dim
                key = spatial[0] if len(spatial) == 1 else spatial
                result[kper][key] = v
    
    return result


def _prepare_tdis_lazy(component, block):
    """Lazy TDIS preparation."""
    arrs_d = {}
    periods = set()
    
    for field_name in block.keys():
        original_array = getattr(component, field_name, None)
        if original_array is not None:
            arr_d = _unstructure_array_lazy(original_array)
            arrs_d[field_name] = arr_d
            periods.update(arr_d.keys())
    
    periods = sorted(periods)
    perioddata = {}
    for kper in periods:
        line = []
        for arr_d in arrs_d.values():
            if val := arr_d.get(kper, None):
                line.append(val)
        perioddata[kper] = tuple(line)
    
    return perioddata


def _prepare_chd_lazy(component, block):
    """Lazy CHD preparation."""
    if (parent := getattr(component, 'parent', None)) is None:
        raise ValueError("CHD cannot be prepared without a parent model and grid.")
    
    grid = parent.grid
    arrs_d = {}
    periods = set()
    
    for field_name in block.keys():
        original_array = getattr(component, field_name, None)
        if original_array is not None:
            arr_d = _unstructure_array_lazy(original_array)
            if arr_d:  # Only add if the dict is not empty
                arrs_d[field_name] = arr_d
                periods.update(arr_d.keys())
    
    if not periods:
        return {}
    
    periods = sorted(periods)
    perioddata = {}
    for kper in periods:
        lines = []
        for arr_d in arrs_d.values():
            if val := arr_d.get(kper, None):
                for nn, v in val.items():
                    # Convert node index to grid coordinates manually
                    # For structured grid: node = layer * nrow * ncol + row * ncol + col
                    nlay, nrow, ncol = grid.nlay, grid.nrow, grid.ncol
                    layer = nn // (nrow * ncol)
                    remaining = nn % (nrow * ncol)
                    row = remaining // ncol
                    col = remaining % ncol
                    
                    # Convert to 1-based indexing for MODFLOW 6
                    cellid = (layer + 1, row + 1, col + 1)
                    lines.append((*cellid, v))
        if lines:  # Only add period if it has data
            perioddata[kper] = lines
    
    return perioddata


def _prepare_oc_lazy(component, block):
    """Lazy OC preparation."""
    fields = []
    for field_name, field in block.items():
        action, rtype = field_name.split("_")
        fields.append((action, rtype, field_name))
    
    arrs_d = {}
    periods = set()
    for action, rtype, field_name in fields:
        original_array = getattr(component, field_name, None)
        if original_array is not None:
            arr_d = _unstructure_array_lazy(original_array)
            arrs_d[(action, rtype)] = arr_d
            periods.update(arr_d.keys())
    
    periods = sorted(periods)
    perioddata = {}
    for kper in periods:
        if kper not in perioddata:
            perioddata[kper] = []
        for (action, rtype), arr_d in arrs_d.items():
            if arr := arr_d.get(kper, None):
                perioddata[kper].append((action, rtype, arr))
    
    return perioddata


def _prepare_generic_lazy(component, block_name, block):
    """Generic lazy preparation."""
    result = {}
    
    # For generic components, we need to process all arrays in the block
    for field_name, field in block.items():
        if is_list_field(field):
            original_array = getattr(component, field_name, None)
            if original_array is not None:
                arr_d = _unstructure_array_lazy(original_array)
                if arr_d:  # Only add if not empty
                    result[field_name] = arr_d
    
    # If this is a period block but not CHD/OC, we need to combine the arrays
    if block_name == "period" and result:
        periods = set()
        for arr_d in result.values():
            periods.update(arr_d.keys())
        
        periods = sorted(periods)
        perioddata = {}
        for kper in periods:
            lines = []
            for field_name, arr_d in result.items():
                if val := arr_d.get(kper, None):
                    for spatial_key, v in val.items():
                        lines.append((spatial_key, v))
            if lines:
                perioddata[kper] = lines
        return perioddata
    
    return result
