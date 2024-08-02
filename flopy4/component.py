from abc import ABC, abstractmethod
from io import StringIO
from typing import Any, Optional


class MFComponent(ABC):
    """
    A component of a MODFLOW 6 simulation. A component is any
    object, from the simulation itself to a single parameter,
    which participates in defining the simulation. Each has a
    name, an optional value, and knows how to write itself to
    an MF6 input file.
    """

    def __str__(self):
        buffer = StringIO()
        self.write(buffer)
        return buffer.getvalue()

    @property
    @abstractmethod
    def name(self) -> str:
        """The parameter's name."""
        pass

    @property
    @abstractmethod
    def value(self) -> Optional[Any]:
        """The parameter's value."""
        pass

    @abstractmethod
    def write(self, f, **kwargs):
        """Write the component to file."""
        pass
