from typing import Optional

from flopy4.context import Context


class Simulation(Context):
    """
    `Simulation` is the main entry point to interact with a
    supported program.

    TODO metaclass: inspect the parameter and component spec
    and add chained methods for each? So child class can be
    initialized/configured with e.g.

    >>> sim = MySimulation(name="...", workspace=...)\
    >>>     .component1(...)\
    >>>     .subcomponent1A(...)\
    >>>     .component2(...)\
    >>>     .subcomponent2A(...)\
    >>>     .subcomponent2B(...)\

    """

    def __init__(self, name: Optional[str] = None):
        super().__init__(name, parent=None)

    def run(self):
        """Run the simulation."""
        raise NotImplementedError("Subclasses must implement run()")
