from flopy4.decorators import paired_dir, paired_file
from flopy4.mf6.block import Block
from flopy4.mf6.exchange import Exchange
from flopy4.mf6.io import mf6io
from flopy4.mf6.model import Model
from flopy4.mf6.package import Package
from flopy4.mf6.solution import Solution
from flopy4.simulation import Simulation


@mf6io
@paired_file(attr_name="filename")
@paired_dir(attr_name="workspace")
class MF6Simulation(Simulation):
    """
    MODFLOW 6 simulation.
    """

    @property
    def blocks(self):
        return {
            n: c for n, c in self.components.items() if isinstance(c, Block)
        }

    @property
    def packages(self):
        return {
            n: c for n, c in self.components.items() if isinstance(c, Package)
        }

    @property
    def models(self):
        return {
            n: c for n, c in self.components.items() if isinstance(c, Model)
        }

    @property
    def exchanges(self):
        return {
            n: c for n, c in self.components.items() if isinstance(c, Exchange)
        }

    @property
    def solutions(self):
        return {
            n: c for n, c in self.components.items() if isinstance(c, Solution)
        }
