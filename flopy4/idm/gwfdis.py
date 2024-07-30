from flopy4.array import MFArray
from flopy4.package import MFPackage
from flopy4.scalar import MFInteger, MFKeyword


class GwfDis(MFPackage):
    export_array_ascii = MFKeyword(
        block="options",
        longname="export array variables to layered ascii files.",
        description="keyword that specifies input griddata arrays should be"
        "written to layered ascii output files.",
        optional=True,
        default_value=False,
    )
    nlay = MFInteger(
        block="dimensions",
        longname="number of layers",
        description="is the number of layers in the model grid.",
        optional=False,
    )
    nrow = MFInteger(
        block="dimensions",
        longname="number of rows",
        description="is the number of rows in the model grid.",
        optional=False,
    )
    ncol = MFInteger(
        block="dimensions",
        longname="number of columns",
        description="is the number of columns in the model grid.",
        optional=False,
    )
    delr = MFArray(
        block="griddata",
        longname="spacing along a row",
        description="is the column spacing in the row direction.",
        optional=False,
        shape="(ncol)",
    )
    delc = MFArray(
        block="griddata",
        longname="spacing along a column",
        description="is the row spacing in the column direction.",
        optional=False,
        shape="(nrow)",
    )
    top = MFArray(
        block="griddata",
        longname="cell top elevation",
        description="is the top elevation for each cell in the top model"
        "layer.",
        optional=False,
        shape="(ncol, nrow)",
    )
    botm = MFArray(
        block="griddata",
        longname="cell bottom elevation",
        description="is the bottom elevation for each cell.",
        optional=False,
        shape="(ncol, nrow, nlay)",
    )
    idomain = MFArray(
        block="griddata",
        longname="idomain existence array",
        description="is an optional array that characterizes the existence "
        "status of a cell.  If the IDOMAIN array is not specified, then all "
        "model cells exist within the solution.  If the IDOMAIN value for a "
        "cell is 0, the cell does not exist in the simulation.  Input and "
        "output values will be read and written for the cell, but internal "
        "to the program, the cell is excluded from the solution.  If the "
        "IDOMAIN value for a cell is 1 or greater, the cell exists in the "
        "simulation.  If the IDOMAIN value for a cell is -1, the cell does "
        "not exist in the simulation.  Furthermore, the first existing cell "
        "above will be connected to the first existing cell below.  This "
        "type of cell is referred to as a ``vertical pass through'' cell.",
        optional=False,
        shape="(ncol, nrow, nlay)",
    )
