"""The typed loader (``flopy4.mf6.converter.ingress.typed``) reads the
components it covers as the basic loader does: the same values, the same
record of how the file wrote each array, and the same warnings. One file of
each block kind it covers, then whole corpus models."""

import warnings
from pathlib import Path

import attrs
import numpy as np
import pytest
from modflow_devtools.models import copy_to

from flopy4.mf6 import LoadContext
from flopy4.mf6.codec.reader import loads, loads_typed
from flopy4.mf6.converter.ingress.structure import structure_component
from flopy4.mf6.converter.ingress.typed import COVERED, covers, structure_typed
from flopy4.mf6.gwf import Chd, Dis, Npf, Oc, Rcha, Sto
from flopy4.mf6.simulation import Simulation
from flopy4.mf6.utl import Obs, Tas
from mf6.test_mf6_load_all_models import _load_digest

DIMS = {"nlay": 2, "nrow": 2, "ncol": 3, "ncpl": 6, "nodes": 12}


def _arrays(component) -> dict:
    context = component.write_context
    return {} if context is None else dict(context.arrays)


def _both(text: str, cls: type, workspace: Path, dims: dict | None = None):
    """``text`` read into a ``cls`` by each loader, which must agree: its
    values, its arrays' write settings, and its warnings. Returns the
    typed loader's."""
    context = LoadContext(workspace=workspace, dims=DIMS if dims is None else dims)
    with warnings.catch_warnings(record=True) as basic_warnings:
        warnings.simplefilter("always")
        basic = structure_component(loads(text), cls, context=context)
    with warnings.catch_warnings(record=True) as typed_warnings:
        warnings.simplefilter("always")
        typed = structure_typed(
            loads_typed(text, cls.dfn_name),
            cls,
            context=attrs.evolve(context, loader="typed"),
        )
    assert _load_digest(typed, workspace) == _load_digest(basic, workspace)
    assert _arrays(typed) == _arrays(basic)
    assert [str(w.message) for w in typed_warnings] == [str(w.message) for w in basic_warnings]
    return typed


def test_covers():
    assert covers(Oc) and covers(Simulation)
    assert {"sim-nam", "gwf-nam", "gwf-dis", "gwf-rcha", "utl-obs", "utl-tas"} <= COVERED


def test_griddata(tmp_path):
    """LAYERED arrays (a record per layer, CONSTANT, INTERNAL or
    OPEN/CLOSE, each with its FACTOR and IPRN), one record for the whole
    field, and an array smaller than the grid (DIS's delr)."""
    (tmp_path / "botm2.txt").write_text("-20 -20 -20\n-21 -21 -21\n")
    dis = _both(
        """
BEGIN OPTIONS
  LENGTH_UNITS meters
END OPTIONS
BEGIN DIMENSIONS
  NLAY 2
  NROW 2
  NCOL 3
END DIMENSIONS
BEGIN GRIDDATA
  DELR
    CONSTANT 100.0
  DELC
    INTERNAL FACTOR 2.0
      1.0 2.0
  TOP
    CONSTANT 10.0
  BOTM LAYERED
    INTERNAL FACTOR 1.0 IPRN 3
      -10 -10 -10 -11 -11 -11
    OPEN/CLOSE botm2.txt FACTOR 2.0 IPRN 3
  IDOMAIN LAYERED
    CONSTANT 1
    INTERNAL
      1 1 0 1 1 1
END GRIDDATA
""",
        Dis,
        tmp_path,
        dims={},
    )
    assert np.array_equal(dis.delc, [2.0, 4.0])
    assert np.array_equal(np.ravel(dis.botm)[6:], [-40, -40, -40, -42, -42, -42])


def test_griddata_options(tmp_path):
    """Options of each kind: keywords, a keyword's value from its DFN
    choices (spelled as written), and a record."""
    _both(
        """
BEGIN OPTIONS
  SAVE_FLOWS
  ALTERNATIVE_CELL_AVERAGING AMT-HMK
  THICKSTRT
  REWET WETFCT 1.0 IWETIT 1 IHDWET 0
END OPTIONS
BEGIN GRIDDATA
  ICELLTYPE
    CONSTANT 1
  K LAYERED
    CONSTANT 10.0
    CONSTANT 5.0
END GRIDDATA
""",
        Npf,
        tmp_path,
    )


def test_list_periods(tmp_path):
    """A list period's rows, one OPEN/CLOSE-redirected, and an empty
    period, which clears the list."""
    (tmp_path / "chd2.txt").write_text("1 1 1 4.0\n")
    chd = _both(
        """
BEGIN OPTIONS
  PRINT_INPUT
END OPTIONS
BEGIN DIMENSIONS
  MAXBOUND 2
END DIMENSIONS
BEGIN PERIOD 1
  1 1 1 1.0
  1 2 3 2.0
END PERIOD 1
BEGIN PERIOD 2
  OPEN/CLOSE chd2.txt
END PERIOD 2
BEGIN PERIOD 3
END PERIOD 3
""",
        Chd,
        tmp_path,
    )
    assert sorted(chd.stress_period_data) == [0, 1, 2]


def test_union_periods(tmp_path):
    """A period of union items (OC's SAVE and PRINT), whose settings are
    words or arms with values, and a record option."""
    oc = _both(
        """
BEGIN OPTIONS
  HEAD FILEOUT model.hds
  BUDGET FILEOUT model.cbc
  HEAD PRINT_FORMAT COLUMNS 10 WIDTH 15 DIGITS 6 GENERAL
END OPTIONS
BEGIN PERIOD 1
  SAVE HEAD ALL
  PRINT BUDGET LAST
END PERIOD 1
BEGIN PERIOD 3
  SAVE HEAD FREQUENCY 2
  SAVE BUDGET STEPS 1 2 3
END PERIOD 3
""",
        Oc,
        tmp_path,
    )
    assert oc.stress_period_data[2][0].ocsetting == Oc.Frequency(2)


def test_word_periods(tmp_path):
    _both(
        """
BEGIN GRIDDATA
  ICONVERT
    CONSTANT 1
  SS
    CONSTANT 1e-5
  SY
    CONSTANT 0.2
END GRIDDATA
BEGIN PERIOD 1
  STEADY-STATE
END PERIOD 1
BEGIN PERIOD 2
  transient
END PERIOD 2
""",
        Sto,
        tmp_path,
    )


def test_array_periods(tmp_path):
    """A G/A period's arrays, an auxiliary variable's by its name (in any
    case), one from a time-array series, and an empty period, which
    clears them. An auxiliary name not in AUXILIARY warns."""
    rcha = _both(
        """
BEGIN OPTIONS
  READASARRAYS
  AUXILIARY mult
END OPTIONS
BEGIN PERIOD 1
  RECHARGE
    INTERNAL FACTOR 0.001 IPRN 2
      1 2 3 4 5 6
  MULT
    CONSTANT 2.0
  OTHER
    CONSTANT 3.0
END PERIOD 1
BEGIN PERIOD 2
END PERIOD 2
BEGIN PERIOD 3
  RECHARGE TIMEARRAYSERIES rates
END PERIOD 3
""",
        Rcha,
        tmp_path,
    )
    assert set(rcha.aux[0]) == {"mult"}


def test_double_headers(tmp_path):
    """A TAS's arrays, by time, and its record attributes."""
    tas = _both(
        """
BEGIN ATTRIBUTES
  NAME rates
  METHOD LINEAR
  SFAC 2.0
END ATTRIBUTES
BEGIN TIME 0.0
  CONSTANT 0.001
END TIME
BEGIN TIME 10.5
  INTERNAL
    1 2 3 4 5 6
END TIME
""",
        Tas,
        tmp_path,
    )
    assert sorted(tas.tas_array) == [0.0, 10.5]


def test_record_headers(tmp_path):
    """OBS's output files, a block each, and one OPEN/CLOSE-redirected."""
    (tmp_path / "more.obs").write_text("h2 HEAD 1 2 3\n")
    obs = _both(
        """
BEGIN OPTIONS
  DIGITS 10
END OPTIONS
BEGIN CONTINUOUS FILEOUT heads.csv
  h1 HEAD 1 1 1
END CONTINUOUS
BEGIN CONTINUOUS FILEOUT more.bin BINARY
  OPEN/CLOSE more.obs
END CONTINUOUS
""",
        Obs,
        tmp_path,
    )
    assert len(obs.continuous) == 2


def test_fortran_exponent():
    """MF6 reads a Fortran D exponent; so does the typed grammar."""
    npf = "BEGIN OPTIONS\n  REWET WETFCT 1D-1 IWETIT 1 IHDWET 0\nEND OPTIONS\n"
    assert loads_typed(npf, "gwf-npf")["options"]["rewet"]["wetfct"] == 0.1


@pytest.mark.parametrize(
    "model_name",
    [
        "mf6/test/test001h_rch_array4",  # RCHA, aux, TAS
        "mf6/test/test005_advgw_tidal",  # OBS with OPEN/CLOSE
        "mf6/test/test001e_UZF_spring",  # STO, OBS
        "mf6/test/test006_2models_gnc",  # two models
    ],
)
def test_models(tmp_path, model_name):
    """A corpus model loads the same with either loader, and writes the
    same files."""
    loaded = {}
    for loader in ("basic", "typed"):
        workspace = copy_to(tmp_path / loader, model_name, verbose=False)
        sim = Simulation.load(workspace / "mfsim.nam", loader=loader)
        out = tmp_path / f"{loader}-out"
        out.mkdir()
        digest = _load_digest(sim, workspace)
        sim.workspace = out
        sim.write()
        written = {p.relative_to(out): p.read_bytes() for p in out.rglob("*") if p.is_file()}
        loaded[loader] = digest, written
    assert loaded["typed"] == loaded["basic"]
