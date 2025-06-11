from datetime import datetime
from typing import Optional

import attrs
import numpy as np
import pandas as pd
from attrs import Converter, define
from flopy.discretization.modeltime import ModelTime
from numpy.typing import NDArray
from xattree import ROOT, xattree

from flopy4.mf6.codec import structure_array
from flopy4.mf6.package import Package
from flopy4.mf6.spec import array, dim, field


@xattree
class Tdis(Package):
    @define(slots=False)
    class PeriodData:
        perlen: float = 1.0
        nstp: int = 1
        tsmult: float = 1.0

    nper: int = dim(
        block="dimensions",
        coord="per",
        default=1,
        scope=ROOT,
    )
    time_units: Optional[str] = field(block="options", default=None)
    start_date_time: Optional[datetime] = field(block="options", default=None)
    perioddata: NDArray[np.object_] = array(
        PeriodData,
        block="perioddata",
        dims=("nper",),
        reader="urword",
        converter=Converter(structure_array, takes_field=True, takes_self=True),
    )

    def to_time(self) -> ModelTime:
        """Convert the time discretization package to a `ModelTime` object."""
        perioddata = pd.DataFrame([attrs.astuple(pd) for pd in self.perioddata.to_numpy()])
        return ModelTime(
            nper=self.nper,
            time_units=self.time_units,
            start_date_time=self.start_date_time,
            perlen=perioddata.perlen,
            nstp=perioddata.nstp,
            tsmult=perioddata.tsmult,
        )

    @classmethod
    def from_time(cls, time: ModelTime) -> "Tdis":
        """Create a time discretization package from a `ModelTime` object."""
        perioddata = [Tdis.PeriodData(*t) for t in zip(time.perlen, time.nstp, time.tsmult)]
        return cls(
            nper=time.nper,
            time_units=time.time_units,
            start_date_time=time.start_datetime,
            perioddata=perioddata,
        )
