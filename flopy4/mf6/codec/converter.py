from functools import partial
from typing import Any, Tuple

import numpy as np
import pandas as pd
import sparse
import xattree
from cattrs import structure, unstructure
from numpy.typing import NDArray
from xarray import DataArray
from xattree import get_xatspec

from flopy4.adapters import get_cellid, get_nn
from flopy4.mf6.component import Component
from flopy4.mf6.config import SPARSE_THRESHOLD
from flopy4.mf6.constants import FILL_DNODATA
from flopy4.mf6.spec import get_blocks, is_list_field


def _dataframe_to_array(value: pd.DataFrame, self_, field) -> NDArray:
    # get spec
    spec = get_xatspec(type(self_))
    field = spec[field.name]
    if not field.dims:
        raise ValueError(f"Field {field} missing dims")

    # resolve dims
    explicit_dims = self_.__dict__.get("dims", {})
    inherited_dims = dict(self_.parent.data.dims) if self_.parent else {}
    dims = inherited_dims | explicit_dims
    shape = [dims.get(d, d) for d in field.dims]
    unresolved = [d for d in shape if isinstance(d, str)]
    if any(unresolved):
        raise ValueError(f"Couldn't resolve dims: {unresolved}")

    convert = (
        (lambda val: structure(val, field.type)) if field.dtype is np.object_ else (lambda val: val)
    )

    if np.prod(shape) > SPARSE_THRESHOLD:
        a: dict[Tuple[Any, ...], Any] = dict()

        def set_(arr, val, *ind):
            arr[tuple(ind)] = convert(val)

        def final(arr):
            coords = np.array(list(map(list, zip(*arr.keys()))))
            return sparse.COO(
                coords,
                list(arr.values()),
                shape=shape,
                fill_value=field.default or FILL_DNODATA,
            )
    else:
        a = np.full(shape, FILL_DNODATA, dtype=field.dtype)  # type: ignore

        def set_(arr, val, *ind):
            arr[ind] = convert(val)

        def final(arr):
            arr[arr == FILL_DNODATA] = field.default or FILL_DNODATA
            return arr

    # Expect DataFrame with columns: 'kper', 'cellid', 'value'
    if "nper" in dims:
        for row in value.itertuples(index=False):
            set_(a, row.value, row.kper, get_nn(row.cellid, **dims))
    else:
        for row in value.itertuples(index=False):
            set_(a, row.value, get_nn(row.cellid, **dims))

    return final(a)


def structure_array(value, self_, field) -> NDArray:
    """
    Convert a sparse, unstructured representation of an array to a
    structured array, either a dense numpy array or a sparse array.

    The input value may be a dictionary, a numpy recarray, or a
    pandas DataFrame. If the value is a dictionary, it must have
    the structure {kper: {cellid: value, ...}, ...}. If the value
    is a recarray or a DataFrame, it must have exactly 3 columns:
    'kper', 'cellid', and 'value'.
    """

    df_to_array = partial(_dataframe_to_array, self_=self_, field=field)

    match value:
        case dict():
            return df_to_array(pd.DataFrame.from_dict(value, orient="index"))
        case np.recarray():
            return df_to_array(pd.DataFrame.from_records(value))
        case pd.DataFrame():
            return df_to_array(value)
        case _:
            # assume it's already an array, let xarray raise an error if not
            return value


def unstructure_array(value: DataArray) -> dict:
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


def unstructure_component(value: Component) -> dict[str, Any]:
    data = xattree.asdict(value)
    blocks = get_blocks(value.dfn)
    for block in blocks.values():
        for field_name, field in block.items():
            if is_list_field(field):
                data[field_name] = unstructure_array(data[field_name])
    return data


def unstructure_tdis(value: Any) -> dict[str, Any]:
    data = xattree.asdict(value)
    blocks = get_blocks(value.dfn)
    for block_name, block in blocks.items():
        if block_name == "perioddata":
            periods = set()  # type: ignore
            arr = data.get("perioddata", None)
            arr_d = {} if arr is None else unstructure_array(arr)
            periods.update(arr_d.keys())
            periods = sorted(periods)  # type: ignore
            perioddata = {}  # type: ignore
            for kper in periods:
                line = []
                if kper not in perioddata:
                    perioddata[kper] = []  # type: ignore
                if val := arr_d.get(kper, None):
                    field = block["perioddata"]
                    line.append(
                        unstructure(val, field["type"]) if field["dtype"] is np.object_ else val
                    )
                perioddata[kper] = tuple(line)
            data["perioddata"] = perioddata
    return data


def unstructure_chd(value: Any) -> dict[str, Any]:
    if (parent := value.parent) is None:
        raise ValueError(
            "CHD cannot be unstructured without a parent "
            "model and corresponding grid discretization."
        )
    grid = parent.grid
    data = xattree.asdict(value)
    blocks = get_blocks(value.dfn)
    for block_name, block in blocks.items():
        if block_name == "period":
            arrs_d = {}
            periods = set()  # type: ignore
            for field_name in block.keys():
                arr = data.get(field_name, None)
                arr_d = {} if arr is None else unstructure_array(arr)
                arrs_d[field_name] = arr_d
                periods.update(arr_d.keys())
            periods = sorted(periods)  # type: ignore
            perioddata = {}  # type: ignore
            for kper in periods:
                line = []
                if kper not in perioddata:
                    perioddata[kper] = []  # type: ignore
                for arr_d in arrs_d.values():
                    if val := arr_d.get(kper, None):
                        for nn, v in val.items():
                            cellid = get_cellid(nn, grid)
                            line.append((*cellid, v))
                perioddata[kper] = tuple(line)
            data["period"] = perioddata
    return data


def unstructure_oc(value: Any) -> dict[str, Any]:
    data = xattree.asdict(value)
    blocks = get_blocks(value.dfn)
    for block_name, block in blocks.items():
        if block_name == "period":
            fields = []
            for field_name, field in block.items():
                action, rtype = field_name.split("_")
                fields.append((action, rtype, field_name))
            arrs_d = {}
            periods = set()  # type: ignore
            for action, rtype, field_name in fields:
                arr = data.get(field_name, None)
                arr_d = {} if arr is None else unstructure_array(arr)
                arrs_d[(action, rtype)] = arr_d
                periods.update(arr_d.keys())
            periods = sorted(periods)  # type: ignore
            perioddata = {}  # type: ignore
            for kper in periods:
                if kper not in perioddata:
                    perioddata[kper] = []
                for (action, rtype), arr_d in arrs_d.items():
                    if arr := arr_d.get(kper, None):
                        perioddata[kper].append((action, rtype, arr))
            data["period"] = perioddata
        else:
            for field_name, field in block.items():
                if is_list_field(field):
                    data[field_name] = unstructure_array(data[field_name])
    return data
