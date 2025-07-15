"""Tests for flopy4.mf6.filters module."""

import numpy as np
import xarray as xr

from flopy4.mf6.filters import data2list


def test_data2list():
    data = np.zeros((3, 4, 5))
    data[0, 1, 2] = 100.0
    data[1, 3, 0] = -50.0
    data[2, 0, 4] = 25.5
    data[data == 0] = np.nan

    arr = xr.DataArray(data, dims=["nlay", "nrow", "ncol"])
    sparse_data = list(data2list(arr))
    assert len(sparse_data) == 3
    expected = {(1, 2, 3, 100.0), (2, 4, 1, -50.0), (3, 1, 5, 25.5)}
    assert set(sparse_data) == expected

    data = np.array([[1.0, np.nan], [0.0, 2.0]])
    arr = xr.DataArray(data, dims=["nrow", "ncol"])
    sparse_data = list(data2list(arr))
    expected = {(1, 1, 1.0), (2, 1, 0.0), (2, 2, 2.0)}
    assert set(sparse_data) == expected

    data = np.array([np.nan, 5, np.nan, 10])
    arr = xr.DataArray(data, dims=["nnodes"])
    sparse_data = list(data2list(arr))
    expected = {(2, 5), (4, 10)}
    assert set(sparse_data) == expected
