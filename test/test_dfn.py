from flopy4.mf6.simulation import Simulation


def test_sim_dfn():
    dfn = Simulation.dfn
    assert dfn is not None
