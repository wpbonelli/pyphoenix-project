from typing import Any

import numpy as np
import sparse
import xarray as xr

from flopy4.adapters import get_cellid
from flopy4.mf6.constants import FILL_DNODATA
from flopy4.mf6.spec import get_blocks, is_list_field


def unstructure_array(value: xr.DataArray) -> dict:
    """
    Convert a dense numpy array or a sparse COO array to a sparse
    dictionary representation suitable for serialization into the
    MF6 list-based input format.

    The input array must have a time dimension named 'nper', i.e.
    it must be stress period data for some MODFLOW 6 component.

    Returns:
        dict: {kper: {spatial indices: value, ...}, ...}
    """
    if (time_dim := "nper") not in value.dims:
        raise ValueError(f"Array must have dimension '{time_dim}'")
    if isinstance(value.data, sparse.COO):
        coords = value.coords
        data = value.data
    else:
        coords = np.array(np.where(value.data != FILL_DNODATA)).T  # type: ignore
        data = value.data[tuple(coords.T)]  # type: ignore
    if not coords.size:  # type: ignore
        return {}
    result = {}
    match value.ndim:
        case 1:
            # Only kper, no spatial dims
            for kper, v in zip(coords[:, 0], data):
                result[int(kper)] = v
        case _:
            # kper + spatial dims
            for row, v in zip(coords, data):
                kper = int(row[0])  # type: ignore
                spatial = tuple(int(x) for x in row[1:])  # type: ignore
                if kper not in result:
                    result[kper] = {}
                # flatten spatial index if only one spatial dim
                key = spatial[0] if len(spatial) == 1 else spatial
                result[kper][key] = v
    return result


def prepare_for_template(component: Any, data: dict[str, Any]) -> dict[str, Any]:
    """Prepare component data for Jinja template rendering by converting to MF6 list format."""
    # Start with a copy of the data
    prepared_data = data.copy()
    
    # Get component type to determine how to handle period data
    component_type = type(component).__name__.lower()
    
    if component_type == "tdis":
        prepared_data = _prepare_tdis_data(component, prepared_data)
    elif component_type == "chd":
        prepared_data = _prepare_chd_data(component, prepared_data)
    elif component_type == "oc":
        prepared_data = _prepare_oc_data(component, prepared_data)
    else:
        # Generic preparation for other components
        prepared_data = _prepare_generic_data(component, prepared_data)
    
    return prepared_data


def _prepare_generic_data(component: Any, data: dict[str, Any]) -> dict[str, Any]:
    """Generic preparation: convert list fields to sparse dict format."""
    blocks = get_blocks(component.dfn)
    for block in blocks.values():
        for field_name, field in block.items():
            if is_list_field(field) and field_name in data:
                # Get the original array from the component
                original_array = getattr(component, field_name, None)
                if original_array is not None:
                    data[field_name] = unstructure_array(original_array)
    return data


def _prepare_tdis_data(component: Any, data: dict[str, Any]) -> dict[str, Any]:
    """Prepare TDIS perioddata as tuples for each period."""
    blocks = get_blocks(component.dfn)
    for block_name, block in blocks.items():
        if block_name == "perioddata":
            arrs_d = {}
            periods = set()
            for field_name in block.keys():
                original_array = getattr(component, field_name, None)
                if original_array is not None:
                    arr_d = unstructure_array(original_array)
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
            data["perioddata"] = perioddata
    return data


def _prepare_chd_data(component: Any, data: dict[str, Any]) -> dict[str, Any]:
    """Prepare CHD period data with cell IDs."""
    if (parent := getattr(component, 'parent', None)) is None:
        raise ValueError(
            "CHD cannot be prepared without a parent "
            "model and corresponding grid discretization."
        )
    
    grid = parent.grid
    blocks = get_blocks(component.dfn)
    
    for block_name, block in blocks.items():
        if block_name == "period":
            arrs_d = {}
            periods = set()
            for field_name in block.keys():
                original_array = getattr(component, field_name, None)
                if original_array is not None:
                    arr_d = unstructure_array(original_array)
                    arrs_d[field_name] = arr_d
                    periods.update(arr_d.keys())
            
            periods = sorted(periods)
            perioddata = {}
            for kper in periods:
                lines = []
                for arr_d in arrs_d.values():
                    if val := arr_d.get(kper, None):
                        for nn, v in val.items():
                            cellid = get_cellid(nn, grid)
                            lines.append((*cellid, v))
                perioddata[kper] = lines
            data["period"] = perioddata
    return data


def _prepare_oc_data(component: Any, data: dict[str, Any]) -> dict[str, Any]:
    """Prepare OC period data with action/record type structure."""
    blocks = get_blocks(component.dfn)
    
    for block_name, block in blocks.items():
        if block_name == "period":
            fields = []
            for field_name, field in block.items():
                action, rtype = field_name.split("_")
                fields.append((action, rtype, field_name))
            
            arrs_d = {}
            periods = set()
            for action, rtype, field_name in fields:
                original_array = getattr(component, field_name, None)
                if original_array is not None:
                    arr_d = unstructure_array(original_array)
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
            data["period"] = perioddata
        else:
            for field_name, field in block.items():
                if is_list_field(field) and field_name in data:
                    original_array = getattr(component, field_name, None)
                    if original_array is not None:
                        data[field_name] = unstructure_array(original_array)
    return data
