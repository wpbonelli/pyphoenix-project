from datetime import datetime

import numpy as np

from flopy4.discretization.time import Time


def test_init():
    time = Time(
        perlen=[1.0, 2.0, 3.0],
        nstp=[10, 20, 30],
        tsmult=[1.1, 1.2, 1.3],
        time_units="days",
        start_datetime="2024-01-01",
    )

    assert isinstance(time.perlen, np.ndarray)
    assert isinstance(time.nstp, np.ndarray)
    assert isinstance(time.tsmult, np.ndarray)
    assert time.perlen.dtype.kind == "f"
    assert time.nstp.dtype.kind in ("i", "u")
    assert time.tsmult.dtype.kind == "f"


def test_init_scalar_conversion():
    time = Time(
        perlen=1.0,
        nstp=10,
        tsmult=1.1,
        time_units=4,
        start_datetime="2024-01-01",
    )

    assert time.perlen.shape == (1,)
    assert time.nstp.shape == (1,)
    assert time.tsmult.shape == (1,)
    assert time.time_units == "days"



def test_update():
    time = Time(
        perlen=[1.0], nstp=[10], tsmult=[1.0], time_units="days", start_datetime="2024-01-01"
    )

    time.time_units = "hours"
    time.start_datetime = "2024-06-01"

    assert isinstance(time.perlen, np.ndarray)
    assert isinstance(time.nstp, np.ndarray)
    assert isinstance(time.tsmult, np.ndarray)
    assert time.time_units == "hours"
    assert time.start_datetime == datetime(2024, 6, 1)
