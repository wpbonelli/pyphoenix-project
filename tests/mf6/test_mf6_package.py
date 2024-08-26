import numpy as np
from attrs import define
from numpy.typing import ArrayLike

from flopy4.context import shape
from flopy4.mf6.package import Package
from flopy4.param import param


@define
@shape("strt", ("nodes"))
# TODO support explicit relative path: @shape("strt", ("../dis/nodes"))
class GwfIc(Package):
    _export_array_ascii: bool = param(
        block="options",
        longname="export array variables to layered ascii files.",
        description="keyword that specifies input griddata arrays should be"
        "written to layered ascii output files.",
        optional=True,
        default=False,
    )
    _export_array_netcdf: bool = param(
        block="options",
        longname="export array variables to netcdf output files.",
        description="keyword that specifies input griddata arrays should be"
        "written to the model output netcdf file.",
        optional=True,
        default=False,
    )
    _strt: ArrayLike = param(
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
    )


@define
@shape("delr", ("ncol"))
@shape("delc", ("nrow"))
@shape("top", ("ncol", "nrow"))
@shape("botm", ("ncol", "nrow", "nlay"))
@shape("idomain", ("ncol", "nrow", "nlay"))
class GwfDis(Package):
    _export_array_ascii: bool = param(
        block="options",
        longname="export array variables to layered ascii files.",
        description="keyword that specifies input griddata arrays should be"
        "written to layered ascii output files.",
        optional=True,
        default_value=False,
    )
    _nlay: int = param(
        block="dimensions",
        longname="number of layers",
        description="is the number of layers in the model grid.",
        optional=False,
    )
    _nrow: int = param(
        block="dimensions",
        longname="number of rows",
        description="is the number of rows in the model grid.",
        optional=False,
    )
    _ncol: int = param(
        block="dimensions",
        longname="number of columns",
        description="is the number of columns in the model grid.",
        optional=False,
    )
    _delr: ArrayLike = param(
        block="griddata",
        longname="spacing along a row",
        description="is the column spacing in the row direction.",
        optional=False,
    )
    _delc: ArrayLike = param(
        block="griddata",
        longname="spacing along a column",
        description="is the row spacing in the column direction.",
        optional=False,
    )
    _top: ArrayLike = param(
        block="griddata",
        longname="cell top elevation",
        description="is the top elevation for each cell in the top model"
        "layer.",
        optional=False,
    )
    _botm: ArrayLike = param(
        block="griddata",
        longname="cell bottom elevation",
        description="is the bottom elevation for each cell.",
        optional=False,
    )
    _idomain: ArrayLike = param(
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
    )


def test_loadfail_gwfic(tmp_path):
    name = "gwf"
    fpth = tmp_path / f"{name}.ic"
    with open(fpth, "w") as f:
        f.write("BEGIN OPTIONS\n")
        f.write("  NOT_AN_OPTION\n")
        f.write("END OPTIONS\n")

    # test package load
    with open(fpth, "r") as f:
        try:
            GwfIc.load(f)
        except ValueError as e:
            assert "not_an_option" in str(e)


def test_load_gwfic(tmp_path):
    name = "gwf"
    fpth = tmp_path / f"{name}.ic"
    strt = [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9]
    array = " ".join(str(x) for x in strt)
    with open(fpth, "w") as f:
        f.write("BEGIN OPTIONS\n")
        f.write("  EXPORT_ARRAY_ASCII\n")
        f.write("END OPTIONS\n")
        f.write("\n")
        f.write("BEGIN GRIDDATA\n")
        f.write(f"  STRT\n    INTERNAL\n      {array}\n")
        f.write("END GRIDDATA\n")

    # test package load
    with open(fpth, "r") as f:
        gwfic = GwfIc.load(f)

    assert len(GwfIc.blocks) == len(gwfic.blocks) == 2
    assert len(GwfIc.params) == len(gwfic.params) == 3

    # instance attributes: shortcut access to param values
    assert isinstance(gwfic.export_array_ascii, bool)
    assert isinstance(gwfic.export_array_netcdf, bool)
    assert isinstance(gwfic.strt, np.ndarray)

    assert gwfic.export_array_ascii
    assert not gwfic.export_array_netcdf
    assert np.allclose(gwfic.strt, np.array(strt))


def test_load_gwfdis(tmp_path):
    name = "gwf"
    fpth = tmp_path / f"{name}.dis"
    celld = [1.0, 2.0, 3.0, 4.0, 5.0]
    spacing = " ".join(str(x) for x in celld)
    with open(fpth, "w") as f:
        f.write("BEGIN OPTIONS\n")
        f.write("  EXPORT_ARRAY_ASCII\n")
        f.write("END OPTIONS\n\n")
        f.write("BEGIN DIMENSIONS\n")
        f.write("  NLAY 3\n")
        f.write("  NROW 5\n")
        f.write("  NCOL 5\n")
        f.write("END DIMENSIONS\n\n")
        f.write("BEGIN GRIDDATA\n")
        f.write(f"  DELR\n    INTERNAL\n      {spacing}\n")
        f.write(f"  DELC\n    INTERNAL\n      {spacing}\n")
        f.write("  TOP\n     CONSTANT 4.0\n")
        f.write("  BOTM LAYERED\n")
        f.write("      CONSTANT 3.0\n")
        f.write("      CONSTANT 2.0\n")
        f.write("      CONSTANT 1.0\n")
        f.write("  IDOMAIN LAYERED\n")
        f.write("    INTERNAL  FACTOR  1\n")
        f.write("      1  1  1  1  1\n")
        f.write("      1  1  1  1  1\n")
        f.write("      1  1  0  1  1\n")
        f.write("      1  1  0  1  1\n")
        f.write("      1  1  1  1  1\n")
        f.write("    INTERNAL  FACTOR  1\n")
        f.write("      1  1  1  1  1\n")
        f.write("      1  1  1  1  1\n")
        f.write("      1  1  1  1  1\n")
        f.write("      1  1  1  1  1\n")
        f.write("      1  1  1  1  1\n")
        f.write("    INTERNAL  FACTOR  1\n")
        f.write("      1  1  1  1  1\n")
        f.write("      1  1  1  1  1\n")
        f.write("      1  1  1  1  1\n")
        f.write("      1  1  1  1  1\n")
        f.write("      1  1  1  1  1\n")
        f.write("END GRIDDATA\n")

        # test package load
    with open(fpth, "r") as f:
        gwfdis = GwfDis.load(f)

    assert len(gwfdis.blocks) == 3
    assert len(gwfdis.params) == 9

    # instance attributes: shortcut access to param values
    assert isinstance(gwfdis.export_array_ascii, bool)
    assert isinstance(gwfdis.nlay, int)
    assert isinstance(gwfdis.nrow, int)
    assert isinstance(gwfdis.ncol, int)
    assert isinstance(gwfdis.delr, np.ndarray)
    assert isinstance(gwfdis.delc, np.ndarray)
    assert isinstance(gwfdis.top, np.ndarray)
    assert isinstance(gwfdis.botm, np.ndarray)

    assert gwfdis.export_array_ascii
    assert gwfdis.nlay == 3
    assert gwfdis.nrow == 5
    assert gwfdis.ncol == 5
    assert np.allclose(gwfdis.delr, np.array(celld))
    assert np.allclose(gwfdis.delc, np.array(celld))
    assert np.allclose(gwfdis.top, np.ones((5, 5)) * 4.0)
    # botm
    b = np.ones((3, 5, 5))
    b[0, :, :] = 3.0
    b[1, :, :] = 2.0
    b[2, :, :] = 1.0
    assert np.allclose(gwfdis.botm, b)
    # idomain
    i = np.ones((3, 5, 5))
    i[0, :, :] = [
        [1, 1, 1, 1, 1],
        [1, 1, 1, 1, 1],
        [1, 1, 0, 1, 1],
        [1, 1, 0, 1, 1],
        [1, 1, 1, 1, 1],
    ]
    assert np.allclose(gwfdis.idomain, i)
