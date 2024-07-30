from threading import local
from typing import Any, Optional

from flopy4.sim import MFSim


class SimContext:
    """Thread-local simulation context usable as a context manager."""

    data = local()

    def __init__(self, sim: Optional[MFSim]):
        type(self).data.sim = sim

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_value, traceback):
        type(self).data.sim = None
        pass

    @classmethod
    def current(cls) -> Optional[MFSim]:
        return cls.data.sim

    @classmethod
    def get(cls, key) -> Optional[Any]:
        if hasattr(cls.data, "sim"):
            return cls.data.sim.get(key, None)
        return None
