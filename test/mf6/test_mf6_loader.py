"""Choosing the loader (`LoadContext.loader`): the choice reaches every
file a load reads, and the typed loader leaves the components it doesn't
cover to the basic one."""

import attrs
from modflow_devtools.models import copy_to

from flopy4.mf6 import LoadContext
from flopy4.mf6.converter.ingress import typed
from flopy4.mf6.converter.ingress.structure import structure_component
from flopy4.mf6.gwf import Chd
from flopy4.mf6.simulation import Simulation

MODEL = "mf6/test/test001a_Tharmonic"


def test_default_is_basic():
    assert LoadContext().loader == "basic"


def test_typed_reaches_children(tmp_path, monkeypatch):
    """Every component the simulation's files name is offered to the typed
    loader; the ones it covers are read by it."""
    asked, read = [], []

    def covers(cls):
        asked.append(cls.dfn_name)
        return cls is Chd

    def structure_typed(parsed, cls, *, context, name=None):
        read.append((cls.dfn_name, list(parsed)))
        # stand in for the typed loader with the basic one
        from flopy4.mf6.codec.reader import load

        assert context.loader == "typed"
        with open(next(tmp_path.rglob("*.chd"))) as fp:
            return structure_component(load(fp), cls, context=context, name=name)

    monkeypatch.setattr(typed, "covers", covers)
    monkeypatch.setattr(typed, "structure_typed", structure_typed)
    workspace = copy_to(tmp_path, MODEL, verbose=False)
    sim = Simulation.load(workspace / "mfsim.nam", loader="typed")
    assert {"sim-nam", "sim-tdis", "gwf-nam", "gwf-dis", "gwf-chd", "gwf-oc"} <= set(asked)
    assert [name for name, _ in read] == ["gwf-chd"]
    assert any(block.startswith("period ") for block in read[0][1])  # the typed parse's
    assert isinstance(sim.models[0].chd[0], Chd)


def test_basic_offers_nothing(tmp_path, monkeypatch):
    asked = []
    monkeypatch.setattr(typed, "covers", lambda cls: asked.append(cls) or False)
    workspace = copy_to(tmp_path, MODEL, verbose=False)
    Simulation.load(workspace / "mfsim.nam")
    assert asked == []


def test_loader_overrides_context(tmp_path, monkeypatch):
    asked = []
    monkeypatch.setattr(typed, "covers", lambda cls: asked.append(cls) or False)
    workspace = copy_to(tmp_path, MODEL, verbose=False)
    context = attrs.evolve(LoadContext(workspace=workspace), loader="basic")
    chd = next(workspace.rglob("*.chd"))
    Chd.load(chd, dims={"nlay": 1, "nrow": 1, "ncol": 3, "nodes": 3}, context=context)
    assert asked == []
    Chd.load(chd, dims={"nlay": 1, "nrow": 1, "ncol": 3, "nodes": 3}, loader="typed")
    assert asked == [Chd]
