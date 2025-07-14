from os import PathLike
from warnings import warn

from modflow_devtools.misc import cd, run_cmd
from xattree import xattree

from flopy4.discretization.time import Time
from flopy4.mf6.context import Context
from flopy4.mf6.exchange import Exchange
from flopy4.mf6.model import Model
from flopy4.mf6.solution import Solution
from flopy4.mf6.spec import field
from flopy4.mf6.tdis import Tdis


def convert_time(value):
    if isinstance(value, Time):
        return Tdis.from_time(value)
    if isinstance(value, Tdis):
        return value
    raise TypeError(f"Expected Time or Tdis, got {type(value)}")


@xattree
class Simulation(Context):
    models: dict[str, Model] = field()
    exchanges: dict[str, Exchange] = field()
    solutions: dict[str, Solution] = field()
    tdis: Tdis = field(converter=convert_time)
    filename: str = field(default="mfsim.nam", init=False)

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        if self.filename != "mfsim.nam":
            warn(
                "Simulation filename must be 'mfsim.nam'.",
                UserWarning,
            )
            self.filename = "mfsim.nam"

    @property
    def time(self) -> Time:
        """Return the simulation time discretization."""
        return self.tdis.to_time()

    def run(self, exe: str | PathLike = "mf6", verbose: bool = False) -> None:
        """Run the simulation using the given executable."""
        with cd(self.workspace):
            out, err, ret = run_cmd(exe, verbose=verbose)
            if ret != 0:
                raise RuntimeError(
                    f"Simulation {self.name}: {exe} failed with "  # type: ignore
                    f"return code {ret}, output:\n\n{out + err} "
                )

    def load(self, format="ascii"):
        """Load the simulation."""
        with cd(self.workspace):
            super().load(format=format)

    def write(self, format="ascii"):
        """Write the simulation."""
        with cd(self.workspace):
            super().write(format=format)
