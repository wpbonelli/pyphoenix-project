from flopy4.array import MFArray
from flopy4.package import MFPackage
from flopy4.scalar import MFKeyword


class GwfIc(MFPackage):
    export_array_ascii = MFKeyword(
        block="options",
        longname="export array variables to layered ascii files.",
        description="keyword that specifies input griddata arrays should be"
        "written to layered ascii output files.",
        optional=True,
        default_value=False,
    )
    export_array_netcdf = MFKeyword(
        block="options",
        longname="export array variables to netcdf output files.",
        description="keyword that specifies input griddata arrays should be"
        "written to the model output netcdf file.",
        optional=True,
        default_value=False,
    )
    strt = MFArray(
        block="griddata",
        longname="starting head",
        description="is the initial (starting) head---that is, head at the"
        "beginning of the GWF Model simulation.  STRT must be specified for"
        "all simulations, including steady-state simulations. One value is"
        "read for every model cell. For simulations in which the first stress"
        "period is steady state, the values used for STRT generally do not"
        "affect the simulation (exceptions may occur if cells go dry and (or)"
        "rewet). The execution time, however, will be less if STRT includes"
        "hydraulic heads that are close to the steady-state solution.  A head"
        "value lower than the cell bottom can be provided if a cell should"
        "start as dry.",
        optional=False,
        shape="(nodes)",
    )
