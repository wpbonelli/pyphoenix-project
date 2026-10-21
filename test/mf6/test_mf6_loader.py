"""Choosing the loader (`LoadContext.loader`): the choice reaches every
file a load reads."""

import attrs
from modflow_devtools.models import copy_to

from flopy4.mf6 import LoadContext
from flopy4.mf6.converter.ingress import typed
from flopy4.mf6.gwf import Chd
from flopy4.mf6.simulation import Simulation

MODEL = "mf6/test/test001a_Tharmonic"


def test_default_is_basic():
    assert LoadContext().loader == "basic"


def _record(monkeypatch) -> list:
    """The classes the typed loader reads, from here on."""
    read = []
    structure_typed = typed.structure_typed

    def record(parsed, cls, **kwargs):
        read.append(cls)
        return structure_typed(parsed, cls, **kwargs)

    monkeypatch.setattr(typed, "structure_typed", record)
    return read


def test_typed_reaches_children(tmp_path, monkeypatch):
    """The typed loader reads every file the simulation's files name."""
    read = _record(monkeypatch)
    workspace = copy_to(tmp_path, MODEL, verbose=False)
    sim = Simulation.load(workspace / "mfsim.nam", loader="typed")
    assert {"sim-nam", "sim-tdis", "gwf-nam", "gwf-dis", "gwf-chd", "gwf-oc", "sln-ims"} <= {
        cls.dfn_name for cls in read
    }
    assert isinstance(sim.models[0].chd[0], Chd)


def test_basic_reads_nothing_typed(tmp_path, monkeypatch):
    read = _record(monkeypatch)
    workspace = copy_to(tmp_path, MODEL, verbose=False)
    Simulation.load(workspace / "mfsim.nam")
    assert read == []


def test_loader_overrides_context(tmp_path, monkeypatch):
    read = _record(monkeypatch)
    workspace = copy_to(tmp_path, MODEL, verbose=False)
    context = attrs.evolve(LoadContext(workspace=workspace), loader="basic")
    chd = next(workspace.rglob("*.chd"))
    Chd.load(chd, dims={"nlay": 1, "nrow": 1, "ncol": 3, "nodes": 3}, context=context)
    assert read == []
    Chd.load(chd, dims={"nlay": 1, "nrow": 1, "ncol": 3, "nodes": 3}, loader="typed")
    assert read == [Chd]
